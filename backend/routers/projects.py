"""Research projects vertical slice (update.md §8.1, §15).

Supabase-backed; every operation enforces owner/member authorization
server-side (RLS in migration 0001 is defence-in-depth, not the only check).
"""
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from dependencies import get_current_user
from services.supabase_client import get_supabase

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/projects", tags=["projects"])


class ProjectCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)
    description: Optional[str] = Field(default=None, max_length=2000)


class ProjectUpdate(BaseModel):
    title: Optional[str] = Field(default=None, min_length=1, max_length=200)
    description: Optional[str] = Field(default=None, max_length=2000)


class NoteCreate(BaseModel):
    content: str = Field(..., min_length=1, max_length=20000)
    source_id: Optional[str] = None


async def _owned_project(supabase, project_id: str, user_id: str) -> dict:
    resp = await supabase.table("projects").select("*").eq("id", project_id).single().execute()
    if not resp.data:
        raise HTTPException(status_code=404, detail="Project not found")
    if resp.data.get("owner_id") != user_id:
        # Membership lookup would go here (project_members); owners only
        # until sharing is enabled (Phase P4).
        raise HTTPException(status_code=404, detail="Project not found")
    return resp.data


@router.post("")
async def create_project(body: ProjectCreate, user: dict = Depends(get_current_user), supabase=Depends(get_supabase)):
    try:
        resp = await supabase.table("projects").insert({
            "owner_id": user["user_id"], "title": body.title, "description": body.description,
        }).execute()
        return resp.data
    except Exception:
        logger.exception("create_project failed")
        raise HTTPException(status_code=500, detail="Internal error")


@router.get("")
async def list_projects(user: dict = Depends(get_current_user), supabase=Depends(get_supabase)):
    try:
        resp = await supabase.table("projects").select("*").eq("owner_id", user["user_id"]).is_("deleted_at", "null").execute()
        return resp.data or []
    except Exception:
        logger.exception("list_projects failed")
        raise HTTPException(status_code=500, detail="Internal error")


@router.get("/{project_id}")
async def get_project(project_id: str, user: dict = Depends(get_current_user), supabase=Depends(get_supabase)):
    return await _owned_project(supabase, project_id, user["user_id"])


@router.patch("/{project_id}")
async def update_project(project_id: str, body: ProjectUpdate, user: dict = Depends(get_current_user), supabase=Depends(get_supabase)):
    await _owned_project(supabase, project_id, user["user_id"])
    patch = {k: v for k, v in body.model_dump().items() if v is not None}
    try:
        resp = await supabase.table("projects").update(patch).eq("id", project_id).execute()
        return resp.data
    except Exception:
        logger.exception("update_project failed")
        raise HTTPException(status_code=500, detail="Internal error")


@router.delete("/{project_id}")
async def delete_project(project_id: str, user: dict = Depends(get_current_user), supabase=Depends(get_supabase)):
    """Soft delete (deleted_at) — reversible, never hard-deletes user data."""
    await _owned_project(supabase, project_id, user["user_id"])
    try:
        from datetime import datetime, timezone
        await supabase.table("projects").update(
            {"deleted_at": datetime.now(timezone.utc).isoformat()}
        ).eq("id", project_id).execute()
        return {"status": "ok"}
    except Exception:
        logger.exception("delete_project failed")
        raise HTTPException(status_code=500, detail="Internal error")


@router.post("/{project_id}/members")
async def add_member(project_id: str, body: dict, user: dict = Depends(get_current_user), supabase=Depends(get_supabase)):
    """Invite a member (owner-only). Role changes are audited.

    Body: {"user_id": "...", "role": "viewer|editor"} — the invited
    user's id is data, the *authorizer* is always the JWT owner.
    """
    await _owned_project(supabase, project_id, user["user_id"])
    role = body.get("role")
    if role not in ("viewer", "editor"):
        raise HTTPException(status_code=422, detail="Role must be viewer or editor")
    try:
        from security.audit import audit
        audit(user["user_id"], "project:invite", "allowed", project_id)
        resp = await supabase.table("project_members").upsert({
            "project_id": project_id, "user_id": body.get("user_id"), "role": role,
        }).execute()
        return resp.data
    except HTTPException:
        raise
    except Exception:
        logger.exception("add_member failed")
        raise HTTPException(status_code=500, detail="Internal error")


@router.post("/{project_id}/notes")
async def create_note(project_id: str, body: NoteCreate, user: dict = Depends(get_current_user), supabase=Depends(get_supabase)):
    await _owned_project(supabase, project_id, user["user_id"])
    try:
        resp = await supabase.table("notes").insert({
            "project_id": project_id, "created_by": user["user_id"],
            "source_id": body.source_id, "content": body.content,
        }).execute()
        return resp.data
    except Exception:
        logger.exception("create_note failed")
        raise HTTPException(status_code=500, detail="Internal error")


@router.get("/{project_id}/notes")
async def list_notes(project_id: str, user: dict = Depends(get_current_user), supabase=Depends(get_supabase)):
    await _owned_project(supabase, project_id, user["user_id"])
    try:
        resp = await supabase.table("notes").select("*").eq("project_id", project_id).execute()
        return resp.data or []
    except Exception:
        logger.exception("list_notes failed")
        raise HTTPException(status_code=500, detail="Internal error")
