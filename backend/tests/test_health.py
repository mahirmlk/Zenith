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
        "checks": {
            "supabase": False,
            "redis": False,
            "run_store": False,
            "graph_checkpointer": False,
            "account_deletion_jobs": False,
            "model_gateway": True,
            "model_gateway_status": "gated",
        },
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
        "checks": {
            "supabase": True,
            "redis": True,
            "run_store": False,
            "graph_checkpointer": False,
            "account_deletion_jobs": False,
            "model_gateway": True,
            "model_gateway_status": "gated",
        },
    }


@pytest.mark.asyncio
async def test_production_readiness_fails_when_graph_checkpointer_is_unavailable(monkeypatch):
    import redis.asyncio as redis_mod
    from types import SimpleNamespace
    from services.run_store import PostgresRunStore

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

        def rpc(self, *_args):
            return SupabaseQuery()

    class Redis:
        async def ping(self):
            return True

        async def aclose(self):
            return None

    async def get_supabase():
        return Supabase()

    async def get_run_store():
        return object.__new__(PostgresRunStore)

    async def checkpointer_unavailable():
        return False

    monkeypatch.setattr(health, "get_settings", lambda: Settings())
    monkeypatch.setattr("services.supabase_client.get_supabase", get_supabase)
    monkeypatch.setattr(redis_mod, "from_url", lambda *_args, **_kwargs: Redis())
    monkeypatch.setattr("services.run_store.get_run_store", get_run_store)
    monkeypatch.setattr("agents.orchestrator.checkpointer_ready", checkpointer_unavailable)
    response = Response()

    result = await health.readiness(response)

    assert response.status_code == 503
    assert result == {
        "status": "not_ready",
        "checks": {
            "supabase": True,
            "redis": True,
            "run_store": True,
            "graph_checkpointer": False,
            "account_deletion_jobs": True,
            "model_gateway": True,
            "model_gateway_status": "gated",
        },
    }


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("provider_key", "daily_cap", "monthly_cap", "ledger_ready", "expected"),
    [
        ("", 100, 100, True, False),
        ("provider-key", 0, 100, True, False),
        ("provider-key", 100, 0, True, False),
        ("provider-key", 100, 100, False, False),
        ("provider-key", 100, 100, True, True),
    ],
)
async def test_model_gateway_readiness_requires_key_positive_caps_and_ledger(
    monkeypatch, provider_key, daily_cap, monthly_cap, ledger_ready, expected
):
    from services import spend_meter

    class Settings:
        llm_enabled = True
        openrouter_api_key = provider_key
        llm_daily_spend_cap_usd_micros = daily_cap
        llm_monthly_spend_cap_usd_micros = monthly_cap

    async def ready():
        return ledger_ready

    monkeypatch.setattr(spend_meter, "meter_ready", ready)

    assert await health._model_gateway_ready(Settings()) is expected


@pytest.mark.asyncio
async def test_model_gateway_readiness_reports_intentional_gate_as_optional():
    class Settings:
        llm_enabled = False
        openrouter_api_key = ""
        llm_daily_spend_cap_usd_micros = 0
        llm_monthly_spend_cap_usd_micros = 0

    assert await health._model_gateway_status(Settings()) == "gated"
    assert await health._model_gateway_ready(Settings()) is True


@pytest.mark.asyncio
async def test_production_readiness_does_not_fail_only_for_gated_model_gateway(monkeypatch):
    import redis.asyncio as redis_mod
    from types import SimpleNamespace
    from services.run_store import PostgresRunStore

    class Settings:
        app_env = "production"
        llm_enabled = False
        supabase_url = "https://example.supabase.co"
        supabase_service_role_key = "service-key"
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

        def rpc(self, _name, _params):
            return SupabaseQuery()

    class Redis:
        async def ping(self):
            return True

        async def aclose(self):
            return None

    async def get_supabase():
        return Supabase()

    async def get_run_store():
        return object.__new__(PostgresRunStore)

    async def checkpointer_ready():
        return True

    monkeypatch.setattr(health, "get_settings", lambda: Settings())
    monkeypatch.setattr("services.supabase_client.get_supabase", get_supabase)
    monkeypatch.setattr(redis_mod, "from_url", lambda *_args, **_kwargs: Redis())
    monkeypatch.setattr("services.run_store.get_run_store", get_run_store)
    monkeypatch.setattr("agents.orchestrator.checkpointer_ready", checkpointer_ready)
    response = Response()

    result = await health.readiness(response)

    assert response.status_code == 200
    assert result["status"] == "ready"
    assert result["checks"]["model_gateway"] is True
    assert result["checks"]["model_gateway_status"] == "gated"
