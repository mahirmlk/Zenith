"""Research projects vertical slice (update.md §8.1, §15).

Supabase-backed; every operation enforces owner/member authorization
server-side (RLS in migration 0001 is defence-in-depth, not the only check).
"""
import logging
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from dependencies import get_current_user
from security.authorization import can_write_project
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


async def _owned_project(
    supabase: Any,
    project_id: str,
    user_id: str,
) -> dict[str, Any]:
    """Owner OR member access (H2 fix: members were locked out)."""
    from security.authorization import can_access_project

    resp = await supabase.table("projects").select("*").eq("id", project_id).maybe_single().execute()
    project = resp.data
    if not isinstance(project, dict):
        raise HTTPException(status_code=404, detail="Project not found")
    if project.get("owner_id") == user_id:
        return project
    members = await supabase.table("project_members").select("user_id,role").eq("project_id", project_id).execute()
    member_roles = {m["user_id"]: m["role"] for m in (members.data or [])}
    if not can_access_project(project["owner_id"], member_roles, user_id):
        raise HTTPException(status_code=404, detail="Project not found")
    return project


@router.post("")
async def create_project(
    body: ProjectCreate,
    user: dict[str, Any] = Depends(get_current_user),
    supabase: Any = Depends(get_supabase),
) -> Any:
    try:
        resp = await supabase.table("projects").insert({
            "owner_id": user["user_id"], "title": body.title, "description": body.description,
        }).execute()
        return resp.data
    except Exception:
        logger.exception("create_project failed")
        raise HTTPException(status_code=500, detail="Internal error")


@router.get("")
async def list_projects(
    user: dict[str, Any] = Depends(get_current_user),
    supabase: Any = Depends(get_supabase),
) -> Any:
    try:
        user_id = user["user_id"]
        memberships = await (
            supabase.table("project_members")
            .select("project_id")
            .eq("user_id", user_id)
            .execute()
        )
        project_ids = list(dict.fromkeys(
            row["project_id"] for row in (memberships.data or []) if row.get("project_id")
        ))
        owned = await (
            supabase.table("projects")
            .select("*")
            .eq("owner_id", user_id)
            .is_("deleted_at", "null")
            .execute()
        )
        shared: list[dict[str, Any]] = []
        if project_ids:
            shared_response = await (
                supabase.table("projects")
                .select("*")
                .in_("id", project_ids)
                .is_("deleted_at", "null")
                .execute()
            )
            shared = shared_response.data or []
        projects = {project["id"]: project for project in [*(owned.data or []), *shared]}
        return list(projects.values())
    except Exception:
        logger.exception("list_projects failed")
        raise HTTPException(status_code=500, detail="Internal error")


@router.get("/{project_id}")
async def get_project(
    project_id: str,
    user: dict[str, Any] = Depends(get_current_user),
    supabase: Any = Depends(get_supabase),
) -> dict[str, Any]:
    return await _owned_project(supabase, project_id, user["user_id"])


@router.patch("/{project_id}")
async def update_project(
    project_id: str,
    body: ProjectUpdate,
    user: dict[str, Any] = Depends(get_current_user),
    supabase: Any = Depends(get_supabase),
) -> Any:
    project = await _owned_project(supabase, project_id, user["user_id"])
    # Project metadata is owner-controlled. Editors may add notes/sources, but
    # migration 0009 intentionally limits title/description updates to owners.
    if project["owner_id"] != user["user_id"]:
        raise HTTPException(status_code=403, detail="Only the project owner can update project metadata")
    patch = {k: v for k, v in body.model_dump().items() if v is not None}
    try:
        # C3: bind the mutation to the owner as defence-in-depth.
        resp = await supabase.table("projects").update(patch).eq("id", project_id).eq("owner_id", project["owner_id"]).execute()
        return resp.data
    except Exception:
        logger.exception("update_project failed")
        raise HTTPException(status_code=500, detail="Internal error")


@router.delete("/{project_id}")
async def delete_project(
    project_id: str,
    user: dict[str, Any] = Depends(get_current_user),
    supabase: Any = Depends(get_supabase),
) -> dict[str, str]:
    """Soft delete (deleted_at) — reversible, never hard-deletes user data."""
    project = await _owned_project(supabase, project_id, user["user_id"])
    if project["owner_id"] != user["user_id"]:
        raise HTTPException(status_code=403, detail="Only the project owner can delete it")
    try:
        from datetime import datetime, timezone
        await supabase.table("projects").update(
            {"deleted_at": datetime.now(timezone.utc).isoformat()}
        ).eq("id", project_id).execute()
        return {"status": "ok"}
    except Exception:
        logger.exception("delete_project failed")
        raise HTTPException(status_code=500, detail="Internal error")


class MemberInvite(BaseModel):
    user_id: str = Field(..., min_length=1, max_length=100)
    role: str = Field(..., pattern="^(viewer|editor)$")


@router.post("/{project_id}/members")
async def add_member(
    project_id: str,
    body: MemberInvite,
    user: dict[str, Any] = Depends(get_current_user),
    supabase: Any = Depends(get_supabase),
) -> Any:
    """Invite a member (owner-only). Role changes are audited."""
    project = await _owned_project(supabase, project_id, user["user_id"])
    if project["owner_id"] != user["user_id"]:
        raise HTTPException(status_code=403, detail="Only the project owner can invite members")
    try:
        from security.audit import audit
        audit(user["user_id"], "project:invite", "allowed", project_id)
        resp = await supabase.table("project_members").upsert({
            "project_id": project_id, "user_id": body.user_id, "role": body.role,
        }).execute()
        return resp.data
    except HTTPException:
        raise
    except Exception:
        logger.exception("add_member failed")
        raise HTTPException(status_code=500, detail="Internal error")


@router.post("/{project_id}/notes")
async def create_note(
    project_id: str,
    body: NoteCreate,
    user: dict[str, Any] = Depends(get_current_user),
    supabase: Any = Depends(get_supabase),
) -> Any:
    project = await _owned_project(supabase, project_id, user["user_id"])
    members = await (
        supabase.table("project_members")
        .select("user_id,role")
        .eq("project_id", project_id)
        .execute()
    )
    member_roles = {m["user_id"]: m["role"] for m in (members.data or [])}
    if not can_write_project(project["owner_id"], member_roles, user["user_id"]):
        raise HTTPException(status_code=403, detail="Project is read-only")
    if body.source_id:
        # H5: source must belong to this project.
        src = await supabase.table("project_sources").select("id").eq("id", body.source_id).eq("project_id", project_id).maybe_single().execute()
        if not src.data:
            raise HTTPException(status_code=422, detail="Source does not belong to this project")
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
async def list_notes(
    project_id: str,
    user: dict[str, Any] = Depends(get_current_user),
    supabase: Any = Depends(get_supabase),
) -> Any:
    await _owned_project(supabase, project_id, user["user_id"])
    try:
        resp = await supabase.table("notes").select("*").eq("project_id", project_id).execute()
        return resp.data or []
    except Exception:
        logger.exception("list_notes failed")
        raise HTTPException(status_code=500, detail="Internal error")
