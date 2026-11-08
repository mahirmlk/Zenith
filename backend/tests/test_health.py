from fastapi.testclient import TestClient
from main import app
from fastapi import Response

client = TestClient(app)


def test_health():
    response = client.get("/api/health")
    assert response.status_code == 200
    data = response.json()
    assert data["service"] == "ai-paper-agent-backend"
    assert "status" in data
    assert "checks" in data


def test_readiness_returns_503_when_required_dependency_is_unreachable(monkeypatch):
    from routers import health

    class Settings:
        app_env = "production"
        supabase_url = "https://example.supabase.co"
        supabase_service_role_key = "test-key"
        redis_url = ""

    async def unavailable_supabase():
        raise RuntimeError("not reachable")

    monkeypatch.setattr(health, "get_settings", lambda: Settings())
    monkeypatch.setattr("services.supabase_client.get_supabase", unavailable_supabase)
    response = Response()

    import asyncio

    result = asyncio.run(health.readiness(response))
    assert response.status_code == 503
    assert result == {"status": "not_ready", "checks": {"supabase": False, "redis": False}}
