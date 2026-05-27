from fastapi import APIRouter
from config import get_settings
from services.supabase_client import get_supabase

router = APIRouter(prefix="/api/health", tags=["health"])


@router.get("")
async def health_check():
    checks = {
        "supabase": False,
        "openrouter": False,
    }

    try:
        supabase = get_supabase()
        checks["supabase"] = True
    except Exception:
        pass

    try:
        settings = get_settings()
        if settings.openrouter_api_key:
            checks["openrouter"] = True
    except Exception:
        pass

    all_ok = all(checks.values())
    return {
        "status": "ok" if all_ok else "degraded",
        "service": "ai-paper-agent-backend",
        "checks": checks,
    }
