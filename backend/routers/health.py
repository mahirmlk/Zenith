import asyncio
from collections.abc import Callable
from typing import Any, cast
from typing import Protocol

from fastapi import APIRouter, Response

from config import get_settings
from services.llm_router import llm_is_enabled

router = APIRouter(prefix="/api/health", tags=["health"])
ready_router = APIRouter(prefix="/api", tags=["health"])


class RedisHealthClient(Protocol):
    async def ping(self) -> bool: ...

    async def aclose(self) -> None: ...


async def _model_gateway_status(settings: Any) -> str:
    """Report optional model service as gated, ready, or misconfigured."""
    if not llm_is_enabled(settings):
        return "gated"
    if not (
        getattr(settings, "openrouter_api_key", "")
        and getattr(settings, "llm_daily_spend_cap_usd_micros", 0) > 0
        and getattr(settings, "llm_monthly_spend_cap_usd_micros", 0) > 0
    ):
        return "not_ready"
    try:
        from services.spend_meter import meter_ready

        return "ready" if await asyncio.wait_for(meter_ready(), timeout=3.0) else "not_ready"
    except Exception:
        return "not_ready"


async def _model_gateway_ready(settings: Any) -> bool:
    """Legacy boolean helper: gated is optional and therefore ready for app health."""
    return await _model_gateway_status(settings) != "not_ready"


@router.get("")
async def health_check() -> dict[str, object]:
    """Liveness: cheap, never masks dependency failures with a bare 200
    claim — `checks` reports configured dependencies (update.md §16)."""
    settings = get_settings()
    return {
        "status": "ok",
        "service": "ai-paper-agent-backend",
        "checks": {
            "supabase_configured": bool(settings.supabase_url),
            "redis_configured": bool(settings.redis_url),
            "openrouter_configured": bool(settings.openrouter_api_key),
            "llm_enabled": llm_is_enabled(settings),
        },
    }


@ready_router.get("/ready")
async def readiness(response: Response) -> dict[str, object]:
    """Check required runtime dependencies; never expose connection details."""
    settings = get_settings()
    checks: dict[str, bool | str] = {"supabase": False, "redis": False}

    if settings.supabase_url and settings.supabase_service_role_key:
        try:
            from services.supabase_client import get_supabase

            async def _check_supabase() -> None:
                client = await get_supabase()
                await client.table("papers").select("id").limit(1).execute()

            await asyncio.wait_for(_check_supabase(), timeout=3.0)
            checks["supabase"] = True
        except Exception:
            checks["supabase"] = False

    if settings.redis_url:
        client: RedisHealthClient | None = None
        try:
            import redis.asyncio as redis_mod

            redis_from_url = cast(
                Callable[..., RedisHealthClient], redis_mod.from_url
            )
            client = redis_from_url(
                settings.redis_url,
                socket_connect_timeout=2,
                socket_timeout=2,
            )
            checks["redis"] = bool(await asyncio.wait_for(client.ping(), timeout=3.0))
        except Exception:
            checks["redis"] = False
        finally:
            if client is not None:
                try:
                    await client.aclose()
                except Exception:
                    pass

    if settings.app_env == "production":
        checks["run_store"] = False
        checks["graph_checkpointer"] = False
        checks["account_deletion_jobs"] = False
        model_gateway_status = await _model_gateway_status(settings)
        checks["model_gateway"] = model_gateway_status != "not_ready"
        checks["model_gateway_status"] = model_gateway_status
        try:
            from services.supabase_client import get_supabase

            supabase_client = await get_supabase()
            await supabase_client.table("account_deletion_jobs").select("id").limit(0).execute()
            # Safe no-op probe: the sentinel ID cannot match a real job.
            await supabase_client.rpc(
                "release_account_deletion_job",
                {
                    "p_job_id": "00000000-0000-0000-0000-000000000000",
                    "p_lease_owner": "readiness-probe",
                    "p_error_code": "readiness_probe",
                    "p_delay_seconds": 5,
                },
            ).execute()
            checks["account_deletion_jobs"] = True
        except Exception:
            checks["account_deletion_jobs"] = False
        if checks["supabase"] and checks["redis"]:
            try:
                from services.run_store import PostgresRunStore, get_run_store

                store = await asyncio.wait_for(get_run_store(), timeout=5.0)
                checks["run_store"] = isinstance(store, PostgresRunStore)
            except Exception:
                checks["run_store"] = False
        try:
            from agents.orchestrator import checkpointer_ready

            checks["graph_checkpointer"] = await asyncio.wait_for(
                checkpointer_ready(), timeout=3.0
            )
        except Exception:
            checks["graph_checkpointer"] = False

    required = (
        all(value is True for key, value in checks.items() if key != "model_gateway_status")
        if settings.app_env == "production"
        else checks["supabase"] is True
    )
    if not required:
        response.status_code = 503
        return {"status": "not_ready", "checks": checks}
    return {"status": "ready", "checks": checks}
