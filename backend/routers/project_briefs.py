"""Project briefs with immutable, source-snapshotted versions."""
from __future__ import annotations

import hashlib
import logging
from typing import Any, NoReturn
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from dependencies import get_current_user
from models.schemas import (
    ProjectBriefCreate,
    ProjectBriefCreateResponse,
    ProjectBriefResponse,
    ProjectBriefSourceLocator,
    ProjectBriefVersionCreate,
    ProjectBriefVersionResponse,
)
from services.supabase_client import get_supabase

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/projects/{project_id}/briefs", tags=["project briefs"])


def _rpc_object(data: Any) -> dict[str, Any]:
    if isinstance(data, list):
        data = data[0] if data else None
    if isinstance(data, dict):
        return data
    raise HTTPException(status_code=500, detail="Brief operation returned no data")


async def _project(project_id: str, user_id: str, supabase: Any, *, write: bool = False) -> dict[str, Any]:
    from routers.projects import _owned_project, _writable_project

    return await (
        _writable_project(supabase, project_id, user_id)
        if write
        else _owned_project(supabase, project_id, user_id)
    )


async def _load_brief(
    project_id: str, brief_id: UUID, user_id: str, supabase: Any, *, write: bool = False
) -> dict[str, Any]:
    await _project(project_id, user_id, supabase, write=write)
    response = await (
        supabase.table("project_briefs")
        .select("*")
        .eq("id", str(brief_id))
        .eq("project_id", project_id)
        .maybe_single()
        .execute()
    )
    if not isinstance(response.data, dict):
        raise HTTPException(status_code=404, detail="Brief not found")
    return response.data


async def _normalize_source_snapshot(
    supabase: Any, project_id: str, locators: list[ProjectBriefSourceLocator]
) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for locator in locators:
        if locator.source_type == "paper_abstract":
            source_id = str(locator.paper_source_id)
            source = await (
                supabase.table("project_sources")
                .select("id,paper_id")
                .eq("id", source_id)
                .eq("project_id", project_id)
                .maybe_single()
                .execute()
            )
            if not isinstance(source.data, dict) or not source.data.get("paper_id"):
                raise HTTPException(status_code=422, detail="Brief citation paper is not attached to this project")
            paper = await (
                supabase.table("papers")
                .select("id,title,abstract")
                .eq("id", str(source.data["paper_id"]))
                .maybe_single()
                .execute()
            )
            if not isinstance(paper.data, dict) or not isinstance(paper.data.get("abstract"), str):
                raise HTTPException(status_code=422, detail="Brief citation abstract is unavailable")
            text = paper.data["abstract"]
            source_fields = {
                "source_id": source_id,
                "paper_source_id": source_id,
                "paper_id": str(source.data["paper_id"]),
                "source_label": paper.data.get("title") or str(source.data["paper_id"]),
            }
        else:
            document_id = str(locator.document_id)
            document = await (
                supabase.table("project_documents")
                .select("id,filename")
                .eq("id", document_id)
                .eq("project_id", project_id)
                .maybe_single()
                .execute()
            )
            if not isinstance(document.data, dict):
                raise HTTPException(status_code=422, detail="Brief citation PDF is not in this project")
            page = await (
                supabase.table("project_document_pages")
                .select("text")
                .eq("document_id", document_id)
                .eq("page_number", locator.page_number)
                .maybe_single()
                .execute()
            )
            if not isinstance(page.data, dict) or not isinstance(page.data.get("text"), str):
                raise HTTPException(status_code=422, detail="Brief citation PDF page is unavailable")
            text = page.data["text"]
            source_fields = {
                "source_id": document_id,
                "document_id": document_id,
                "page_number": locator.page_number,
                "source_label": document.data.get("filename") or document_id,
            }

        if (
            locator.end_offset > len(text)
            or text[locator.start_offset : locator.end_offset] != locator.quote
        ):
            raise HTTPException(status_code=422, detail="Brief citation quote does not match the current source")
        normalized.append({
            "source_type": locator.source_type,
            **source_fields,
            "start_offset": locator.start_offset,
            "end_offset": locator.end_offset,
            "quote": locator.quote,
            "quote_sha256": hashlib.sha256(locator.quote.encode("utf-8")).hexdigest(),
            "source_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
        })
    return normalized


def _raise_rpc_error(exc: Exception) -> NoReturn:
    message = str(exc)
    if "brief_version_conflict" in message or getattr(exc, "code", None) == "40001":
        raise HTTPException(status_code=409, detail="A newer brief version already exists") from exc
    if "source_quote_mismatch" in message or "invalid_source" in message:
        raise HTTPException(status_code=422, detail="Brief citation does not match a current project source") from exc
    if "project_write_denied" in message or getattr(exc, "code", None) == "42501":
        raise HTTPException(status_code=403, detail="Project is read-only") from exc
    logger.exception("Project brief RPC failed")
    raise HTTPException(status_code=500, detail="Brief could not be saved") from exc


@router.get("", response_model=list[ProjectBriefResponse])
async def list_project_briefs(
    project_id: str,
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0, le=10000),
    user: dict[str, Any] = Depends(get_current_user),
    supabase: Any = Depends(get_supabase),
) -> list[ProjectBriefResponse]:
    await _project(project_id, str(user["user_id"]), supabase)
    response = await (
        supabase.table("project_briefs")
        .select("*")
        .eq("project_id", project_id)
        .order("updated_at", desc=True)
        .range(offset, offset + limit - 1)
        .execute()
    )
    return [ProjectBriefResponse(**row) for row in (response.data or []) if isinstance(row, dict)]


@router.post("", response_model=ProjectBriefCreateResponse, status_code=201)
async def create_project_brief(
    project_id: str,
    body: ProjectBriefCreate,
    request: Request,
    user: dict[str, Any] = Depends(get_current_user),
    supabase: Any = Depends(get_supabase),
) -> ProjectBriefCreateResponse:
    del request
    actor_id = str(user["user_id"])
    await _project(project_id, actor_id, supabase, write=True)
    snapshot = await _normalize_source_snapshot(supabase, project_id, body.source_snapshot)
    params = {
        "p_actor": actor_id,
        "p_project_id": project_id,
        "p_title": body.title,
        "p_content": body.content,
        "p_source_snapshot": snapshot,
        "p_content_sha256": hashlib.sha256(body.content.encode("utf-8")).hexdigest(),
    }
    try:
        result = _rpc_object((await supabase.rpc("create_project_brief", params).execute()).data)
        return ProjectBriefCreateResponse(brief=result["brief"], version=result["version"])
    except HTTPException:
        raise
    except Exception as exc:
        _raise_rpc_error(exc)


@router.get("/{brief_id}", response_model=ProjectBriefResponse)
async def get_project_brief(
    project_id: str,
    brief_id: UUID,
    user: dict[str, Any] = Depends(get_current_user),
    supabase: Any = Depends(get_supabase),
) -> ProjectBriefResponse:
    row = await _load_brief(project_id, brief_id, str(user["user_id"]), supabase)
    return ProjectBriefResponse(**row)


@router.get("/{brief_id}/versions", response_model=list[ProjectBriefVersionResponse])
async def list_project_brief_versions(
    project_id: str,
    brief_id: UUID,
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0, le=10000),
    user: dict[str, Any] = Depends(get_current_user),
    supabase: Any = Depends(get_supabase),
) -> list[ProjectBriefVersionResponse]:
    await _load_brief(project_id, brief_id, str(user["user_id"]), supabase)
    response = await (
        supabase.table("project_brief_versions")
        .select("*")
        .eq("brief_id", str(brief_id))
        .order("version")
        .range(offset, offset + limit - 1)
        .execute()
    )
    return [ProjectBriefVersionResponse(**row) for row in (response.data or []) if isinstance(row, dict)]


@router.post("/{brief_id}/versions", response_model=ProjectBriefVersionResponse, status_code=201)
async def append_project_brief_version(
    project_id: str,
    brief_id: UUID,
    body: ProjectBriefVersionCreate,
    request: Request,
    user: dict[str, Any] = Depends(get_current_user),
    supabase: Any = Depends(get_supabase),
) -> ProjectBriefVersionResponse:
    del request
    actor_id = str(user["user_id"])
    await _load_brief(project_id, brief_id, actor_id, supabase, write=True)
    snapshot = await _normalize_source_snapshot(supabase, project_id, body.source_snapshot)
    params = {
        "p_actor": actor_id,
        "p_brief_id": str(brief_id),
        "p_expected_current_version": body.expected_current_version,
        "p_content": body.content,
        "p_source_snapshot": snapshot,
        "p_content_sha256": hashlib.sha256(body.content.encode("utf-8")).hexdigest(),
    }
    try:
        data = (await supabase.rpc("append_project_brief_version", params).execute()).data
        return ProjectBriefVersionResponse(**_rpc_object(data))
    except HTTPException:
        raise
    except Exception as exc:
        _raise_rpc_error(exc)
