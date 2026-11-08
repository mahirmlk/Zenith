from main import app
from tests.asgi_client import ASGITestClient

client = ASGITestClient(app)


def test_ingest_requires_admin_key_when_unconfigured(monkeypatch):
    monkeypatch.delenv("ADMIN_API_KEY", raising=False)
    response = client.post("/api/internal/ingest")
    assert response.status_code == 503


def test_ingest_rejects_missing_header(monkeypatch):
    monkeypatch.setenv("ADMIN_API_KEY", "top-secret")
    response = client.post("/api/internal/ingest")
    assert response.status_code == 401


def test_ingest_rejects_bad_key(monkeypatch):
    monkeypatch.setenv("ADMIN_API_KEY", "top-secret")
    response = client.post("/api/internal/ingest", headers={"X-Admin-Key": "wrong"})
    assert response.status_code == 401


def test_ingest_accepts_valid_key(monkeypatch):
    monkeypatch.setenv("ADMIN_API_KEY", "top-secret")

    async def fake_run():
        return {"fetched": 0, "inserted": 0, "summarised": 0}

    import routers.internal

    monkeypatch.setattr(routers.internal, "run_daily_fetch", fake_run)
    response = client.post("/api/internal/ingest", headers={"X-Admin-Key": "top-secret"})
    assert response.status_code == 200
    assert response.json() == {"status": "started"}
