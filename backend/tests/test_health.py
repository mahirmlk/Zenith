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
    assert result == {
        "status": "not_ready",
        "checks": {"supabase": False, "redis": False, "run_store": False},
    }


@pytest.mark.asyncio
async def test_production_readiness_fails_when_run_store_schema_is_missing(monkeypatch):
    import redis.asyncio as redis_mod
    from types import SimpleNamespace

    class Settings:
        app_env = "production"
        supabase_url = "https://example.supabase.co"
        supabase_service_role_key = "test-service-role-key"
        redis_url = "redis://example:6379"

    class SupabaseQuery:
        def select(self, *_args):
            return self

        def limit(self, *_args):
            return self

        async def execute(self):
            return SimpleNamespace(data=[])

    class Supabase:
        def table(self, _name):
            return SupabaseQuery()

    class Redis:
        async def ping(self):
            return True

        async def aclose(self):
            return None

    async def get_supabase():
        return Supabase()

    async def missing_run_store():
        raise RuntimeError("run-store migration is missing")

    monkeypatch.setattr(health, "get_settings", lambda: Settings())
    monkeypatch.setattr("services.supabase_client.get_supabase", get_supabase)
    monkeypatch.setattr(redis_mod, "from_url", lambda *_args, **_kwargs: Redis())
    monkeypatch.setattr("services.run_store.get_run_store", missing_run_store)
    response = Response()

    result = await health.readiness(response)

    assert response.status_code == 503
    assert result == {
        "status": "not_ready",
        "checks": {"supabase": True, "redis": True, "run_store": False},
    }
