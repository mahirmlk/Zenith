"""Model registry endpoint (update.md §14).

Frontend ModelSelector fetches this instead of hardcoding IDs.
"""
from fastapi import APIRouter
from typing import Any

from services.llm_router import MODEL_REGISTRY

router = APIRouter(prefix="/api/models", tags=["models"])


@router.get("")
async def list_models() -> dict[str, Any]:
    return {
        "models": [
            {"id": model_id, "agents": entry["agents"]}
            for model_id, entry in MODEL_REGISTRY.items()
        ]
    }
