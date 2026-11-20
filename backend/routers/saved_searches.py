"""Saved query configurations; executions are fresh metered research runs."""
from __future__ import annotations

import uuid
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status

from dependencies import get_current_user
from models.schemas import (
    SavedSearchCreate,
    SavedSearchResponse,
    SavedSearchRunResponse,
    SavedSearchUpdate,
    SearchRequest,
)
from services.supabase_client import get_supabase

router = APIRouter(prefix="/api/saved-searches", tags=["saved searches"])


def _rows(response: Any) -> list[dict[str, Any]]:
    data = getattr(response, "data", None)
    if isinstance(data, dict):
        return [data]
    return [item for item in (data or []) if isinstance(item, dict)]


async def _project_reader(supabase: Any, project_id: str, user_id: str) -> dict[str, Any]:
    from routers.projects import _owned_project

    return await _owned_project(supabase, project_id, user_id)


async def _project_writer(supabase: Any, project_id: str, user_id: str) -> dict[str, Any]:
    from routers.projects import _writable_project

    return await _writable_project(supabase, project_id, user_id)


def _validate_model(model: str | None) -> None:
    if model is None:
        return
    from services.llm_router import validate_model

    try:
        validate_model(model)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


async def _load_accessible(
    supabase: Any, saved_search_id: UUID, user_id: str, *, write: bool = False
) -> dict[str, Any]:
    response = await (
        supabase.table("saved_searches")
        .select("*")
        .eq("id", str(saved_search_id))
        .maybe_single()
        .execute()
    )
    rows = _rows(response)
    if not rows:
        raise HTTPException(status_code=404, detail="Saved search not found")
    row = rows[0]
    project_id = row.get("project_id")
    if project_id is None:
        if row.get("created_by") != user_id:
            raise HTTPException(status_code=404, detail="Saved search not found")
    else:
        try:
            await _project_reader(supabase, str(project_id), user_id)
        except HTTPException as exc:
            raise HTTPException(status_code=404, detail="Saved search not found") from exc
        if write:
            try:
                await _project_writer(supabase, str(project_id), user_id)
            except HTTPException as exc:
                if exc.status_code != 403 or row.get("created_by") != user_id:
                    raise
                # A creator may maintain their project search while they still
                # belong to the project, even if their role was downgraded.
    return row


async def _list_rows(supabase: Any, user_id: str) -> list[dict[str, Any]]:
    own = await (
        supabase.table("saved_searches")
        .select("*")
        .eq("created_by", user_id)
        .is_("project_id", "null")
        .range(0, 99)
        .execute()
    )
    rows = _rows(own)
    owned_projects = await (
        supabase.table("projects")
        .select("id")
        .eq("owner_id", user_id)
        .is_("deleted_at", "null")
        .range(0, 99)
        .execute()
    )
    memberships = await (
        supabase.table("project_members")
        .select("project_id")
        .eq("user_id", user_id)
        .range(0, 99)
        .execute()
    )
    project_ids = {
        str(row["id"]) for row in _rows(owned_projects) if row.get("id")
    } | {
        str(row["project_id"]) for row in _rows(memberships) if row.get("project_id")
    }
    for project_id in sorted(project_ids):
        try:
            await _project_reader(supabase, project_id, user_id)
        except HTTPException:
            continue
        result = await (
            supabase.table("saved_searches")
            .select("*")
            .eq("project_id", project_id)
            .range(0, 99)
            .execute()
        )
        rows.extend(_rows(result))
        if len(rows) >= 100:
            break
    return sorted(rows, key=lambda row: str(row.get("updated_at") or row.get("created_at") or ""), reverse=True)[:100]


@router.get("", response_model=list[SavedSearchResponse])
async def list_saved_searches(
    user: dict[str, Any] = Depends(get_current_user),
    supabase: Any = Depends(get_supabase),
) -> list[SavedSearchResponse]:
    rows = await _list_rows(supabase, str(user["user_id"]))
    return [SavedSearchResponse(**row) for row in rows]


@router.post("", response_model=SavedSearchResponse, status_code=status.HTTP_201_CREATED)
async def create_saved_search(
    body: SavedSearchCreate,
    request: Request,
    user: dict[str, Any] = Depends(get_current_user),
    supabase: Any = Depends(get_supabase),
) -> SavedSearchResponse:
    del request
    user_id = str(user["user_id"])
    _validate_model(body.model)
    if body.project_id is not None:
        await _project_writer(supabase, str(body.project_id), user_id)
    response = await supabase.table("saved_searches").insert({
        "created_by": user_id,
        "project_id": str(body.project_id) if body.project_id else None,
        "name": body.name,
        "query": body.query,
        "model": body.model,
    }).execute()
    rows = _rows(response)
    if not rows:
        raise HTTPException(status_code=500, detail="Saved search could not be created")
    return SavedSearchResponse(**rows[0])


@router.get("/{saved_search_id}", response_model=SavedSearchResponse)
async def get_saved_search(
    saved_search_id: UUID,
    user: dict[str, Any] = Depends(get_current_user),
    supabase: Any = Depends(get_supabase),
) -> SavedSearchResponse:
    row = await _load_accessible(supabase, saved_search_id, str(user["user_id"]))
    return SavedSearchResponse(**row)


@router.patch("/{saved_search_id}", response_model=SavedSearchResponse)
async def update_saved_search(
    saved_search_id: UUID,
    body: SavedSearchUpdate,
    request: Request,
    user: dict[str, Any] = Depends(get_current_user),
    supabase: Any = Depends(get_supabase),
) -> SavedSearchResponse:
    del request
    user_id = str(user["user_id"])
    row = await _load_accessible(supabase, saved_search_id, user_id, write=True)
    if row.get("project_id") is None and row.get("created_by") != user_id:
        raise HTTPException(status_code=404, detail="Saved search not found")
    changes = body.model_dump(exclude_unset=True)
    if "model" in changes:
        _validate_model(changes["model"])
    response = await (
        supabase.table("saved_searches")
        .update(changes)
        .eq("id", str(saved_search_id))
        .execute()
    )
    rows = _rows(response)
    return SavedSearchResponse(**(rows[0] if rows else {**row, **changes}))


@router.delete("/{saved_search_id}")
async def delete_saved_search(
    saved_search_id: UUID,
    request: Request,
    user: dict[str, Any] = Depends(get_current_user),
    supabase: Any = Depends(get_supabase),
) -> dict[str, str]:
    del request
    row = await _load_accessible(supabase, saved_search_id, str(user["user_id"]), write=True)
    response = await (
        supabase.table("saved_searches")
        .delete()
        .eq("id", str(saved_search_id))
        .execute()
    )
    if getattr(response, "data", None) == [] and row.get("created_by") != str(user["user_id"]):
        # Service-role queries can silently return no rows on policy mismatch.
        raise HTTPException(status_code=404, detail="Saved search not found")
    return {"status": "ok"}


@router.post("/{saved_search_id}/run", response_model=SavedSearchRunResponse)
async def run_saved_search(
    saved_search_id: UUID,
    request: Request,
    user: dict[str, Any] = Depends(get_current_user),
    supabase: Any = Depends(get_supabase),
) -> SavedSearchRunResponse:
    row = await _load_accessible(supabase, saved_search_id, str(user["user_id"]))
    # A saved search captures configuration only. Each explicit run receives a
    # fresh idempotency key so it cannot replay yesterday's stored result.
    from routers.search import search

    result = await search(
        request,
        SearchRequest(query=row["query"], model=row.get("model")),
        user=user,
        idempotency_key=f"saved-search:{saved_search_id}:{uuid.uuid4()}",
    )
    return SavedSearchRunResponse(run_id=result.run_id)
