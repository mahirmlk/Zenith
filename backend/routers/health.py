import asyncio

from fastapi import APIRouter, Response

from config import get_settings

router = APIRouter(prefix="/api/health", tags=["health"])
ready_router = APIRouter(prefix="/api", tags=["health"])


@router.get("")
async def health_check() -> dict:
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
        },
    }


@ready_router.get("/ready")
async def readiness(response: Response) -> dict:
    """Check required runtime dependencies; never expose connection details."""
    settings = get_settings()
    checks = {"supabase": False, "redis": False}

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
        client = None
        try:
            import redis.asyncio as redis_mod

            client = redis_mod.from_url(settings.redis_url, socket_connect_timeout=2, socket_timeout=2)
            checks["redis"] = bool(await asyncio.wait_for(client.ping(), timeout=3.0))
        except Exception:
            checks["redis"] = False
        finally:
            if client is not None:
                try:
                    await client.aclose()
                except Exception:
                    pass

    required = all(checks.values()) if settings.app_env == "production" else checks["supabase"]
    if not required:
        response.status_code = 503
        return {"status": "not_ready", "checks": checks}
    return {"status": "ready", "checks": checks}
