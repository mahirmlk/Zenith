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
    """Readiness: 503 when a critical dependency is missing in production."""
    settings = get_settings()
    checks = {
        "supabase_configured": bool(settings.supabase_url),
        "redis_configured": bool(settings.redis_url),
    }
    if settings.app_env == "production" and not all(checks.values()):
        response.status_code = 503
        return {"status": "not_ready", "checks": checks}
    return {"status": "ready", "checks": checks}
