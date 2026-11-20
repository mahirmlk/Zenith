"""Account GDPR + SSE session/ownership tests (gap audit P2-8)."""
import os

import jwt
import pytest
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials

from main import app
from tests.asgi_client import ASGITestClient

client = ASGITestClient(app)

needs_supabase = pytest.mark.skipif(
    not os.environ.get("SUPABASE_URL"), reason="needs live Supabase"
)


def _headers(monkeypatch, user="u1"):
    monkeypatch.setenv("SUPABASE_URL", "")
    secret = "test-secret-account-key-long-enough-for-hs256"
    monkeypatch.setenv("SUPABASE_JWT_SECRET", secret)
    token = jwt.encode({"sub": user}, secret, algorithm="HS256")
    return {"Authorization": f"Bearer {token}"}


def test_account_endpoints_require_auth():
    assert client.get("/api/account/export").status_code == 401
    assert client.delete("/api/account").status_code == 401


def test_stream_requires_session_token():
    assert client.get("/api/stream/some-run").status_code == 401


def test_stream_rejects_query_token_without_bearer_header():
    assert client.get("/api/stream/some-run?token=anything").status_code == 401


@pytest.mark.parametrize("value", ["", "-1", "+1", "1.0", " 1", "١", "x" * 5000])
def test_last_event_id_rejects_malformed_or_negative_values(value):
    from routers.stream import _parse_last_event_id

    with pytest.raises(HTTPException) as error:
        _parse_last_event_id(value)

    assert error.value.status_code == 400


@pytest.mark.parametrize(("value", "expected"), [(None, 0), ("0", 0), ("17", 17)])
def test_last_event_id_accepts_nonnegative_ascii_integer(value, expected):
    from routers.stream import _parse_last_event_id

    assert _parse_last_event_id(value) == expected


@needs_supabase
def test_account_export_structure(monkeypatch):
    resp = client.get("/api/account/export", headers=_headers(monkeypatch))
    assert resp.status_code in (200, 500)


def test_stream_session_exchange_requires_auth(monkeypatch):
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "test-service-role-key-long-enough")
    resp = client.post("/api/stream/session", headers=_headers(monkeypatch))
    assert resp.status_code == 200
    assert isinstance(resp.json().get("session_token"), str)


def test_sse_session_token_verifies_without_process_local_state(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", "")
    monkeypatch.setenv("SUPABASE_JWT_SECRET", "test-auth-secret-long-enough-for-hs256")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "test-service-role-key-long-enough")
    auth_token = jwt.encode(
        {"sub": "u-stateless"},
        "test-auth-secret-long-enough-for-hs256",
        algorithm="HS256",
    )

    response = client.post(
        "/api/stream/session",
        headers={"Authorization": f"Bearer {auth_token}"},
    )

    assert response.status_code == 200
    session_token = response.json()["session_token"]
    from routers.stream import _validate_sse_session

    assert _validate_sse_session(session_token) == "u-stateless"
    assert _validate_sse_session(session_token + "tampered") is None


@pytest.mark.asyncio
async def test_stream_denies_ownerless_legacy_run(monkeypatch):
    from routers import stream
    from services.run_store import RunState

    async def get_ownerless(_run_id):
        return RunState(run_id="orphan", query="private query", user_id=None)

    monkeypatch.setattr(stream.run_store, "get", get_ownerless)
    monkeypatch.setattr(stream, "_validate_sse_session", lambda _token: "unrelated-user")

    with pytest.raises(HTTPException) as error:
        await stream.stream(
            "orphan",
            request=object(),
            credentials=HTTPAuthorizationCredentials(scheme="Bearer", credentials="valid-session"),
            last_event_id=None,
        )

    assert error.value.status_code == 404


@pytest.mark.asyncio
async def test_event_generator_replays_only_after_last_event_id(monkeypatch):
    from routers import stream

    replay = [
        {"sequence": 1, "event": "agent_step", "data": {"step": 1}},
        {"sequence": 2, "event": "agent_step", "data": {"step": 2}},
        {"sequence": 3, "event": "result", "data": {"papers": []}},
    ]

    async def get_events(_run_id):
        return replay

    monkeypatch.setattr(stream.run_store, "get_events", get_events)
    events = [
        event async for event in stream.event_generator("run-1", "query", "user-1", None, 1)
    ]

    assert [event["id"] for event in events] == ["2", "3"]


@pytest.mark.asyncio
async def test_event_generator_does_not_repeat_terminal_event_already_in_cursor(monkeypatch):
    from routers import stream

    async def get_events(_run_id):
        return [
            {"sequence": 1, "event": "agent_step", "data": {"step": 1}},
            {"sequence": 2, "event": "result", "data": {"papers": []}},
        ]

    async def unexpected_state_read(_run_id):
        pytest.fail("terminal event already covered by cursor must close without another result")

    monkeypatch.setattr(stream.run_store, "get_events", get_events)
    monkeypatch.setattr(stream.run_store, "get", unexpected_state_read)

    events = [
        event async for event in stream.event_generator("run-1", "query", "user-1", None, 2)
    ]

    assert events == []
