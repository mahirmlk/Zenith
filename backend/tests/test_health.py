from fastapi import Response
import pytest

from routers import health



@pytest.mark.asyncio
async def test_health():
    data = await health.health_check()
    assert data["service"] == "ai-paper-agent-backend"
    assert "status" in data
    assert "checks" in data


@pytest.mark.asyncio
async def test_readiness_returns_503_when_required_dependency_is_unreachable(monkeypatch):
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

    result = await health.readiness(response)
    assert response.status_code == 503
    assert result == {"status": "not_ready", "checks": {"supabase": False, "redis": False}}
