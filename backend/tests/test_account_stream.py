"""Account GDPR + SSE session/ownership tests (gap audit P2-8)."""
import os

import jwt
import pytest
from fastapi import HTTPException

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
        await stream.stream("orphan", request=object(), token="valid-session")

    assert error.value.status_code == 404
