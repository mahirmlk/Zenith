"""Hybrid search endpoint (update.md §8.3, §15).

Project-scoped when project_id is given (only sources in that project);
otherwise the public corpus. Caller-supplied project access is always
verified server-side against the DB, never trusted from the body.
"""
import logging
import re
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from dependencies import get_current_user
from security.authorization import can_access_project
from security.prompt_injection import scan_untrusted
from services.retrieval import hybrid_rank, query_terms
from services.supabase_client import get_supabase

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/retrieval", tags=["retrieval"])
PAPER_FIELDS = "id,title,abstract"


def _pdf_page_candidates(
    query: str,
    documents: list[dict[str, Any]],
    pages: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Return one exact matching sentence per page with stable page citations."""
    terms = query_terms(query)
    if not terms:
        return []
    document_by_id = {
        str(document["id"]): document
        for document in documents
        if document.get("id")
    }
    candidates: list[dict[str, Any]] = []
    for page in pages:
        document = document_by_id.get(str(page.get("document_id") or ""))
        text = page.get("text")
        if document is None or not isinstance(text, str):
            continue
        best: tuple[int, int, str, int, int] | None = None
        for match in re.finditer(r"[^.!?\n]+(?:[.!?]+|$)", text):
            raw_sentence = match.group(0)
            sentence = raw_sentence.strip()
            if not sentence or scan_untrusted(sentence):
                continue
            overlap = len(terms.intersection(query_terms(sentence)))
            if overlap == 0:
                continue
            start = match.start() + len(raw_sentence) - len(raw_sentence.lstrip())
            end = start + len(sentence)
            key = (overlap, -start, sentence, start, end)
            if best is None or key[:2] > best[:2]:
                best = key
        if best is None:
            continue
        sentence, start, end = best[2], best[3], best[4]
        document_id = str(document["id"])
        page_number = page.get("page_number")
        citation_id = f"{document_id}:page:{page_number}"
        filename = str(document.get("filename") or "Uploaded PDF")
        candidates.append(
            {
                "id": citation_id,
                "source_type": "pdf_page",
                "citation_id": citation_id,
                "document_id": document_id,
                "filename": filename,
                "page_number": page_number,
                "title": filename,
                "snippet": sentence,
                "start_offset": start,
                "end_offset": end,
                # hybrid_rank searches title + abstract; map the exact page
                # sentence to abstract for ranking without presenting it as one.
                "abstract": sentence,
            }
        )
    return candidates


class HybridSearchRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=500)
    project_id: Optional[str] = None
    limit: int = Field(default=20, ge=1, le=100)


@router.post("/search")
async def hybrid_search(
    body: HybridSearchRequest,
    request: Request,
    user: dict[str, Any] = Depends(get_current_user),
    supabase: Any = Depends(get_supabase),
) -> dict[str, Any]:
    try:
        if body.project_id:
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
            members = await (
                supabase.table("project_members")
                .select("user_id,role")
                .eq("project_id", body.project_id)
                .execute()
            )
            member_roles = {
                row["user_id"]: row["role"]
                for row in (members.data or [])
                if row.get("user_id") and row.get("role")
            }
            if not can_access_project(
                proj.data.get("owner_id", ""), member_roles, user["user_id"]
            ):
                raise HTTPException(status_code=404, detail="Project not found")
            src = await (
                supabase.table("project_sources")
                .select("paper_id")
                .eq("project_id", body.project_id)
                .range(0, 199)
                .execute()
            )
            ids = [r["paper_id"] for r in (src.data or []) if r.get("paper_id")]
            paper_rows: list[dict[str, Any]] = []
            if ids:
                papers = await (
                    supabase.table("papers")
                    .select(PAPER_FIELDS)
                    .in_("id", ids)
                    .execute()
                )
                paper_rows = [
                    {**row, "source_type": "paper"}
                    for row in (papers.data or [])
                    if isinstance(row, dict) and row.get("id")
                ]

            documents_result = await (
                supabase.table("project_documents")
                .select("id,filename")
                .eq("project_id", body.project_id)
                .order("created_at", desc=True)
                .range(0, 9)
                .execute()
            )
            documents = [
                row for row in (documents_result.data or [])
                if isinstance(row, dict) and row.get("id")
            ]
            document_ids = [str(row["id"]) for row in documents]
            pdf_rows: list[dict[str, Any]] = []
            if document_ids:
                pages_result = await (
                    supabase.table("project_document_pages")
                    .select("document_id,page_number,text")
                    .in_("document_id", document_ids)
                    .order("document_id")
                    .order("page_number")
                    .range(0, 499)
                    .execute()
                )
                pdf_rows = _pdf_page_candidates(
                    body.query,
                    documents,
                    [row for row in (pages_result.data or []) if isinstance(row, dict)],
                )
            docs = sorted(
                [*paper_rows, *pdf_rows],
                key=lambda row: (str(row.get("source_type") or ""), str(row.get("id") or "")),
            )
        else:
            papers = await (
                supabase.table("papers")
                .select(PAPER_FIELDS)
                .order("published_at", desc=True)
                .range(0, 199)
                .execute()
            )
            docs = [
                {**row, "source_type": "paper"}
                for row in (papers.data or [])
                if isinstance(row, dict) and row.get("id")
            ]
        ranked = hybrid_rank(body.query, docs)[: body.limit]
        for result in ranked:
            if result.get("source_type") == "pdf_page":
                # `abstract` is an internal ranking field holding the matched
                # sentence; expose it only once, as the exact `snippet` span.
                result.pop("abstract", None)
        return {"results": ranked}
    except HTTPException:
        raise
    except Exception:
        logger.exception("hybrid_search failed")
        raise HTTPException(status_code=500, detail="Internal error")
