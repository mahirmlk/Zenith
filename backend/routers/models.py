"""Model registry endpoint (update.md §14).

Frontend ModelSelector fetches this instead of hardcoding IDs.
"""
from fastapi import APIRouter
from typing import Any, cast

from services.llm_router import AGENT_MODEL_MAP, effective_models

router = APIRouter(prefix="/api/models", tags=["models"])


@router.get("")
async def list_models() -> dict[str, Any]:
    models = effective_models()
    from services.spend_meter import meter_ready

    if models and not await meter_ready():
        models = []
    default = AGENT_MODEL_MAP["summary_default"]
    summary_models = [
        item for item in models if "summary_default" in cast(list[str], item["agents"])
    ]
    available_default = default if any(item["id"] == default for item in summary_models) else None
    return {
        "available": bool(summary_models and available_default),
        "default_model": available_default,
        "models": models,
    }
