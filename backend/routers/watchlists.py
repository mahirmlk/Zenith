"""Watchlists / topic monitoring (update.md §12, §15).

In-app alerts only (no email until consent/unsubscribe infra exists).
Cadence daily|weekly; dedupe by (watch_id, paper_id) via seen set.
"""
import logging
from typing import Any, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from dependencies import get_current_user
from services.supabase_client import get_supabase
from services.semantic_scholar import validate_watch_target
import httpx

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/watchlists", tags=["watchlists"])


class WatchCreate(BaseModel):
    query: str = Field(default="", max_length=500)
    target_type: Literal["topic", "author", "citation"] = "topic"
    target_id: Optional[str] = Field(default=None, min_length=1, max_length=200)
    project_id: Optional[str] = None
    cadence: str = Field(default="daily", pattern="^(daily|weekly)$")


class WatchUpdate(BaseModel):
    enabled: Optional[bool] = None
    cadence: Optional[str] = Field(default=None, pattern="^(daily|weekly)$")


@router.post("")
async def create_watch(
    body: WatchCreate,
    user: dict[str, Any] = Depends(get_current_user),
    supabase: Any = Depends(get_supabase),
) -> Any:
    target_label = body.query.strip()
    if body.target_type == "topic":
        if not target_label:
            raise HTTPException(status_code=422, detail="Enter a topic to watch")
        if body.target_id:
            raise HTTPException(status_code=422, detail="Topic watchlists do not accept a target ID")
    else:
        if not body.target_id:
            raise HTTPException(status_code=422, detail="Enter a Semantic Scholar ID")
    if body.project_id:
        # H5: project must be owned by (or shared with) the caller.
        proj = await (
            supabase.table("projects")
            .select("owner_id")
            .eq("id", body.project_id)
            .is_("deleted_at", "null")
            .maybe_single()
            .execute()
        )
        if not proj.data:
            raise HTTPException(status_code=404, detail="Project not found")
        if proj.data.get("owner_id") != user["user_id"]:
            members = await supabase.table("project_members").select("user_id").eq("project_id", body.project_id).eq("user_id", user["user_id"]).execute()
            if not (members.data or []):
                raise HTTPException(status_code=404, detail="Project not found")
    if body.target_type != "topic":
        try:
            target_label = await validate_watch_target(body.target_type, body.target_id or "")
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 404:
                raise HTTPException(status_code=422, detail="Semantic Scholar target was not found") from exc
            raise HTTPException(status_code=503, detail="Semantic Scholar could not validate this target") from exc
        except Exception as exc:
            logger.warning("Semantic Scholar target validation failed: %s", exc)
            raise HTTPException(status_code=503, detail="Semantic Scholar could not validate this target") from exc
    try:
        resp = await supabase.table("watchlists").insert({
            "user_id": user["user_id"], "query": target_label,
            "target_type": body.target_type, "target_id": body.target_id,
            "project_id": body.project_id, "cadence": body.cadence,
        }).execute()
        return resp.data
    except Exception:
        logger.exception("create_watch failed")
        raise HTTPException(status_code=500, detail="Internal error")


@router.get("")
async def list_watches(
    user: dict[str, Any] = Depends(get_current_user),
    supabase: Any = Depends(get_supabase),
) -> Any:
    try:
        resp = await supabase.table("watchlists").select("*").eq("user_id", user["user_id"]).execute()
        return resp.data or []
    except Exception:
        logger.exception("list_watches failed")
        raise HTTPException(status_code=500, detail="Internal error")


@router.patch("/{watch_id}")
async def update_watch(
    watch_id: str,
    body: WatchUpdate,
    user: dict[str, Any] = Depends(get_current_user),
    supabase: Any = Depends(get_supabase),
) -> Any:
    patch = {k: v for k, v in body.model_dump().items() if v is not None}
    try:
        resp = await supabase.table("watchlists").update(patch).eq("id", watch_id).eq("user_id", user["user_id"]).execute()
        if not resp.data:
            raise HTTPException(status_code=404, detail="Watchlist not found")
        return resp.data
    except HTTPException:
        raise
    except Exception:
        logger.exception("update_watch failed")
        raise HTTPException(status_code=500, detail="Internal error")


@router.delete("/{watch_id}")
async def delete_watch(
    watch_id: str,
    user: dict[str, Any] = Depends(get_current_user),
    supabase: Any = Depends(get_supabase),
) -> dict[str, str]:
    try:
        await supabase.table("watchlists").delete().eq("id", watch_id).eq("user_id", user["user_id"]).execute()
        return {"status": "ok"}
    except Exception:
        logger.exception("delete_watch failed")
        raise HTTPException(status_code=500, detail="Internal error")
