"""Public GitHub candidate discovery for paper-to-code planning."""
import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request

from dependencies import get_user_id
from services.github_repositories import search_paper_repositories
from services.supabase_client import get_supabase

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/papers", tags=["paper_code"])


@router.get("/{paper_id}/code")
async def get_paper_code(
    request: Request,
    paper_id: str,
    user_id: str = Depends(get_user_id),
    supabase: Any = Depends(get_supabase),
) -> dict[str, Any]:
    try:
        response = await supabase.table("papers").select("*").eq("id", paper_id).maybe_single().execute()
        if not response.data:
            raise HTTPException(status_code=404, detail="Paper not found")
        return await search_paper_repositories(response.data)
    except HTTPException:
        raise
    except Exception:
        logger.exception("Paper repository lookup failed")
        raise HTTPException(status_code=500, detail="Internal error")
