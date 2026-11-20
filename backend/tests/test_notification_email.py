"""Focused safety tests for optional notification email delivery."""
from __future__ import annotations

import base64
import hashlib
import hmac
import time
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

from config import Settings
from services import notification_email as mail


def _run_immediate(coro):
    """Run async fakes that complete without scheduling external I/O."""
    try:
        return coro.send(None)
    except StopIteration as completed:
        return completed.value


def test_delivery_is_disabled_without_every_secret(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("services.notification_email.get_settings", lambda: Settings(
        notifications_email_enabled=True,
        resend_api_key="key",
        notifications_from_email="research@example.com",
        resend_webhook_secret="whsec_abc",
    ))
    assert mail.delivery_available() is False


def test_rotation_preserves_issued_unsubscribe_hashes_and_checks_old_recipient_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("services.notification_email.get_settings", lambda: Settings(
        notifications_unsubscribe_secret="new-key",
        notifications_unsubscribe_secret_previous="old-key,older-key",
    ))
    token_hash_after_rotation = mail._token_hash("issued-token")
    expected = hashlib.sha256(b"unsubscribe:issued-token").hexdigest()
    assert token_hash_after_rotation == expected
    assert len(mail._recipient_hashes(" User@Example.com ")) == 3


def test_daily_digest_window_uses_local_boundaries_across_dst() -> None:
    # US spring-forward: local midnight boundaries span 23 UTC hours.
    now = datetime(2026, 3, 8, 11, tzinfo=timezone.utc)
    start, scheduled = mail.next_digest_window(now, "daily", "America/New_York")
    assert start.isoformat() == "2026-03-07T13:00:00+00:00"
    assert scheduled.isoformat() == "2026-03-08T12:00:00+00:00"


def test_weekly_digest_uses_monday_local_08_boundary() -> None:
    now = datetime(2026, 11, 10, 16, tzinfo=timezone.utc)  # Tuesday in New York
    start, scheduled = mail.next_digest_window(now, "weekly", "America/New_York")
    assert scheduled.isoformat() == "2026-11-16T13:00:00+00:00"
    assert start.isoformat() == "2026-11-09T13:00:00+00:00"


def test_svix_verification_checks_raw_body_and_freshness() -> None:
    raw = b'{"type":"email.bounced"}'
    secret = base64.b64encode(b"test-secret-key").decode()
    timestamp = str(int(time.time()))
    message_id = "msg-1"
    signature = base64.b64encode(hmac.new(
        b"test-secret-key", f"{message_id}.{timestamp}.".encode() + raw, hashlib.sha256
    ).digest()).decode()
    headers = {"svix-id": message_id, "svix-timestamp": timestamp, "svix-signature": f"v1,{signature}"}
    assert mail.verify_svix(raw, headers, f"whsec_{secret}")
    assert not mail.verify_svix(raw + b" ", headers, f"whsec_{secret}")
    assert not mail.verify_svix(raw, {**headers, "svix-timestamp": "1"}, f"whsec_{secret}")


def test_signed_webhook_rejects_non_object_json_payload(monkeypatch: pytest.MonkeyPatch) -> None:
    raw = b"[]"
    secret_bytes = b"test-secret-key"
    secret = base64.b64encode(secret_bytes).decode()
    timestamp = str(int(time.time()))
    msg_id = "msg-invalid-shape"
    signature = base64.b64encode(hmac.new(
        secret_bytes, f"{msg_id}.{timestamp}.".encode() + raw, hashlib.sha256
    ).digest()).decode()
    headers = {"svix-id": msg_id, "svix-timestamp": timestamp, "svix-signature": f"v1,{signature}"}
    monkeypatch.setattr("services.notification_email.get_settings", lambda: Settings(resend_webhook_secret=f"whsec_{secret}"))

    class DB:
        def rpc(self, *_args: object, **_kwargs: object) -> None:
            raise AssertionError("malformed payload must not reach suppression RPC")

    assert _run_immediate(mail.process_webhook(DB(), raw, headers)) is False


def test_migration_recovers_expired_final_attempt_claims() -> None:
    migration = Path(__file__).resolve().parents[2] / "supabase" / "migrations" / "0020_notification_email_delivery.sql"
    sql = migration.read_text(encoding="utf-8").casefold()
    assert "set status='failed'" in sql
    assert "status='processing' and attempts >= 5 and lease_expires_at < now()" in sql
    assert "next_attempt_at <= now() and attempts < 5" in sql


def test_worker_does_not_claim_or_send_when_delivery_is_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(mail, "delivery_available", lambda: False)

    class DB:
        def rpc(self, *_args, **_kwargs):
            raise AssertionError("disabled delivery must not claim or send")

    assert _run_immediate(mail.process_due_batch(DB())) == 0


def test_preferences_response_schema_is_exact() -> None:
    from routers.notifications import EmailPreferencesUpdate

    model = EmailPreferencesUpdate(email_opt_in=True, email_frequency="weekly", timezone="Europe/Paris")
    assert model.model_dump() == {
        "email_opt_in": True,
        "email_frequency": "weekly",
        "timezone": "Europe/Paris",
    }


@pytest.mark.parametrize(
    ("content_type", "body", "query"),
    [
        ("application/json", b'{"token":"abcdefghijklmnopqrstuvwxyz0123456789"}', b""),
        ("application/x-www-form-urlencoded", b"List-Unsubscribe=One-Click", b"?token=abcdefghijklmnopqrstuvwxyz0123456789"),
    ],
)
def test_unsubscribe_endpoint_accepts_json_and_rfc8058_form(
    monkeypatch: pytest.MonkeyPatch, content_type: str, body: bytes, query: bytes
) -> None:
    from starlette.requests import Request
    from routers.notifications import unsubscribe_email

    monkeypatch.setattr("services.notification_email.get_settings", lambda: Settings(
        notifications_unsubscribe_secret="secret-key",
    ))
    calls: list[tuple[str, dict[str, str]]] = []

    class Query:
        async def execute(self) -> SimpleNamespace:
            return SimpleNamespace(data=True)

    class DB:
        def rpc(self, name: str, args: dict[str, str]) -> Query:
            calls.append((name, args))
            return Query()

    sent = False

    async def receive() -> dict[str, object]:
        nonlocal sent
        if sent:
            return {"type": "http.request", "body": b"", "more_body": False}
        sent = True
        return {"type": "http.request", "body": body, "more_body": False}

    req = Request({
        "type": "http", "method": "POST", "path": "/api/notifications/unsubscribe",
        "query_string": query.lstrip(b"?"), "headers": [(b"content-type", content_type.encode())],
        "server": ("test", 80), "client": ("test", 1), "scheme": "http",
    }, receive)
    assert _run_immediate(unsubscribe_email(req, None, DB())) == {"status": "ok"}
    assert calls and calls[0][0] == "notification_email_unsubscribe"


def test_webhook_replay_uses_stable_per_recipient_event_id(monkeypatch: pytest.MonkeyPatch) -> None:
    import json

    secret_bytes = b"webhook-secret"
    secret = "whsec_" + base64.b64encode(secret_bytes).decode()
    monkeypatch.setattr("services.notification_email.get_settings", lambda: Settings(resend_webhook_secret=secret, notifications_unsubscribe_secret="pepper"))
    body = json.dumps({"type": "email.bounced", "data": {"to": ["Research@Example.com"]}}).encode()
    timestamp = str(int(time.time()))
    event_id = "evt-123"
    sig = base64.b64encode(hmac.new(secret_bytes, f"{event_id}.{timestamp}.".encode() + body, hashlib.sha256).digest()).decode()
    headers = {"svix-id": event_id, "svix-timestamp": timestamp, "svix-signature": f"v1,{sig}"}
    recorded: list[dict[str, str]] = []

    class Query:
        async def execute(self) -> SimpleNamespace:
            return SimpleNamespace(data=True)

    class DB:
        def rpc(self, _name: str, args: dict[str, str]) -> Query:
            recorded.append(args)
            return Query()

    assert _run_immediate(mail.process_webhook(DB(), body, headers)) is True
    assert _run_immediate(mail.process_webhook(DB(), body, headers)) is True
    assert len(recorded) == 2
    assert recorded[0] == recorded[1]
    assert recorded[0]["p_reason"] == "bounce"
    assert recorded[0]["p_event_id"].startswith("evt-123:")


def test_retry_cap_marks_outbox_failed_after_fifth_total_attempt() -> None:
    calls: list[tuple[str, dict[str, object]]] = []

    class Query:
        async def execute(self) -> SimpleNamespace:
            return SimpleNamespace(data=True)

    class Table:
        def update(self, payload: dict[str, object]) -> "Table":
            calls.append(("update", payload))
            return self

        def eq(self, *_args: object) -> "Table":
            return self

        async def execute(self) -> SimpleNamespace:
            return SimpleNamespace(data=[])

    class DB:
        def rpc(self, name: str, args: dict[str, object]) -> Query:
            calls.append((name, args))
            return Query()

        def table(self, _name: str) -> Table:
            return Table()

    _run_immediate(mail._retry(DB(), {"id": "outbox-1", "attempts": 5}, "TimeoutError"))
    assert calls[0][0] == "notification_email_finish"
    assert calls[0][1]["p_status"] == "failed"
    assert calls[1][0] == "update"
    assert calls[1][1]["last_error_code"] == "TimeoutError"
    assert mail.provider_idempotency_key("outbox-1") == "zenith-watch-digest-outbox-1"


def test_opted_out_user_is_suppressed_before_provider_send(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(mail, "delivery_available", lambda: True)
    monkeypatch.setattr("services.notification_email.get_settings", lambda: Settings(
        notifications_email_enabled=True, resend_api_key="key", notifications_from_email="from@example.com",
        resend_webhook_secret="hook", notifications_unsubscribe_secret="pepper",
    ))
    monkeypatch.setattr(mail, "confirmed_email", lambda *_args: _immediate_value("user@example.com"))
    calls: list[tuple[str, dict[str, object]]] = []

    class Query:
        def __init__(self, table: str) -> None:
            self.table = table
        def select(self, *_args: object, **_kwargs: object) -> "Query": return self
        def eq(self, *_args: object) -> "Query": return self
        def maybe_single(self) -> "Query": return self
        async def execute(self) -> SimpleNamespace:
            return SimpleNamespace(data={"email_opt_in": False} if self.table.endswith("preferences") else [])

    class RPC:
        async def execute(self) -> SimpleNamespace: return SimpleNamespace(data=True)

    class DB:
        def table(self, name: str) -> Query: return Query(name)
        def rpc(self, name: str, args: dict[str, object]) -> RPC:
            calls.append((name, args))
            return RPC()

    assert _run_immediate(mail.send_one(DB(), {"id": "outbox-1", "user_id": "u-1"})) is False
    assert calls == [("notification_email_finish", {
        "p_id": "outbox-1", "p_lease_owner": mail._worker_id, "p_status": "suppressed", "p_message_id": None,
    })]


def _immediate_value(value):
    async def done():
        return value
    return done()


def test_delivery_uses_provider_idempotency_and_generic_digest_payload(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = Settings(
        notifications_email_enabled=True, resend_api_key="key", notifications_from_email="from@example.com",
        resend_webhook_secret="hook", notifications_unsubscribe_secret="pepper", app_url="https://zenith.test",
        next_public_api_url="https://api.zenith.test",
    )
    monkeypatch.setattr("services.notification_email.get_settings", lambda: settings)
    monkeypatch.setattr(mail, "delivery_available", lambda: True)
    monkeypatch.setattr(mail, "confirmed_email", lambda *_args: _immediate_value("user@example.com"))
    captured: list[dict[str, object]] = []

    class Query:
        def __init__(self, table: str) -> None:
            self.table, self.payload = table, None
        def select(self, *_args: object, **_kwargs: object) -> "Query": return self
        def eq(self, *_args: object) -> "Query": return self
        def in_(self, *_args: object) -> "Query": return self
        def gte(self, *_args: object) -> "Query": return self
        def lt(self, *_args: object) -> "Query": return self
        def maybe_single(self) -> "Query": return self
        def limit(self, *_args: object) -> "Query": return self
        def update(self, payload: dict[str, object]) -> "Query":
            self.payload = payload
            return self
        def upsert(self, payload: dict[str, object], **_kwargs: object) -> "Query":
            self.payload = payload
            return self
        async def execute(self) -> SimpleNamespace:
            if self.table.endswith("preferences"):
                return SimpleNamespace(data={"email_opt_in": True, "suppressed": False, "recipient_hash": mail._hash("user@example.com")})
            if self.table.endswith("suppressions"):
                return SimpleNamespace(data=[])
            if self.table == "notifications":
                return SimpleNamespace(data=[{"id": "1"}, {"id": "2"}], count=2)
            return SimpleNamespace(data=[])

    class RPC:
        async def execute(self) -> SimpleNamespace:
            return SimpleNamespace(data=True)

    class DB:
        def table(self, name: str) -> Query: return Query(name)
        def rpc(self, name: str, args: dict[str, object]) -> RPC:
            captured.append({"rpc": name, **args})
            return RPC()

    class Response:
        def raise_for_status(self) -> None: pass
        def json(self) -> dict[str, str]: return {"id": "resend-1"}

    class Client:
        def __init__(self, **_kwargs: object) -> None: pass
        async def __aenter__(self) -> "Client": return self
        async def __aexit__(self, *_args: object) -> None: return None
        async def post(self, _url: str, *, json: dict[str, object], headers: dict[str, str]) -> Response:
            captured.append({"payload": json, "headers": headers})
            return Response()

    monkeypatch.setattr(mail.httpx, "AsyncClient", Client)
    result = _run_immediate(mail.send_one(DB(), {
        "id": "outbox-123", "user_id": "u-1", "window_start": "2026-11-12T00:00:00+00:00",
        "scheduled_at": "2026-11-13T00:00:00+00:00",
    }))
    assert result is True
    request = next(item for item in captured if "payload" in item)
    assert request["headers"]["Idempotency-Key"] == "zenith-watch-digest-outbox-123"
    text = request["payload"]["text"]
    assert request["payload"]["to"] == ["user@example.com"]
    assert request["payload"]["subject"] == "Your Zenith research updates"
    assert "2 new watchlist research update(s)" in text
    assert "notifications" in text
    for private_detail in ("paper title", "project title", "watch query", "watchlist name"):
        assert private_detail not in text.casefold()
    assert "api.zenith.test/api/notifications/unsubscribe?token=" in request["payload"]["headers"]["List-Unsubscribe"]
    assert next(item for item in captured if item.get("rpc") == "notification_email_finish")["p_status"] == "sent"
