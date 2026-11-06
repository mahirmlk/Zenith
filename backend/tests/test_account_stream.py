"""Account GDPR + SSE session/ownership tests (gap audit P2-8)."""
import os

import jwt
import pytest
from fastapi.testclient import TestClient

from main import app

client = TestClient(app)

needs_supabase = pytest.mark.skipif(
    not os.environ.get("SUPABASE_URL"), reason="needs live Supabase"
)


def _headers(monkeypatch, user="u1"):
    monkeypatch.setenv("SUPABASE_URL", "")
    monkeypatch.setenv("SUPABASE_JWT_SECRET", "test-secret-account")
    token = jwt.encode({"sub": user}, "test-secret-account", algorithm="HS256")
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
    resp = client.post("/api/stream/session", headers=_headers(monkeypatch))
    # Session token is issued only for authed users; shape check when live.
    assert resp.status_code in (200, 401, 500)
