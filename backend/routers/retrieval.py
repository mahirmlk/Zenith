"""Hybrid search endpoint (update.md §8.3, §15).

Project-scoped when project_id is given (only sources in that project);
otherwise the public corpus. Caller-supplied project access is always
verified server-side against the DB, never trusted from the body.
"""
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from dependencies import get_current_user
from services.retrieval import hybrid_rank
from services.supabase_client import get_supabase

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/retrieval", tags=["retrieval"])


class HybridSearchRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=500)
    project_id: Optional[str] = None
    limit: int = Field(default=20, ge=1, le=100)


@router.post("/search")
async def hybrid_search(body: HybridSearchRequest, user: dict = Depends(get_current_user), supabase=Depends(get_supabase)):
    try:
        if body.project_id:
            proj = await supabase.table("projects").select("owner_id").eq("id", body.project_id).single().execute()
            if not proj.data or proj.data.get("owner_id") != user["user_id"]:
                raise HTTPException(status_code=404, detail="Project not found")
            src = await supabase.table("project_sources").select("paper_id").eq("project_id", body.project_id).execute()
            ids = [r["paper_id"] for r in (src.data or []) if r.get("paper_id")]
            if not ids:
                return {"results": []}
            papers = await supabase.table("papers").select("*").in_("id", ids).execute()
        else:
            papers = await supabase.table("papers").select("*").order("published_at", desc=True).range(0, 199).execute()
        docs = papers.data or []
        ranked = hybrid_rank(body.query, docs)[: body.limit]
        return {"results": ranked}
    except HTTPException:
        raise
    except Exception:
        logger.exception("hybrid_search failed")
        raise HTTPException(status_code=500, detail="Internal error")
