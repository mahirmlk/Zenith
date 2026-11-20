import logging

from fastapi import APIRouter, HTTPException, Depends, Query, Request, Response
from pydantic import BaseModel
from typing import Optional
from models.schemas import Paper, PublicPaperEvidenceResponse, SavePaperRequest
from services.supabase_client import get_supabase
from services.mem0_client import add_memory
from dependencies import get_user_id

router = APIRouter(prefix="/api/papers", tags=["papers"])
logger = logging.getLogger(__name__)


class PaperStatusWatchState(BaseModel):
    watching: bool


@router.get("", response_model=list[Paper])
async def list_papers(  # type: ignore[no-untyped-def]
    q: Optional[str] = Query(default=None, max_length=200),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    supabase=Depends(get_supabase),
    user_id: str = Depends(get_user_id),
) -> list[Paper]:
    try:
        query = supabase.table("papers").select("*")
        if q:
            # M1: escape LIKE wildcards so %/_ are literal.
            safe_q = q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
            query = query.ilike("title", f"%{safe_q}%")
        query = query.order("published_at", desc=True).range(offset, offset + limit - 1)
        response = await query.execute()
        data = response.data or []
        return [Paper.model_validate(item) for item in data]
    except Exception:
        logger.exception("papers request failed")
        raise HTTPException(status_code=500, detail="Internal error")


@router.get("/saved", response_model=list[Paper])
async def list_saved_papers(  # type: ignore[no-untyped-def]
    supabase=Depends(get_supabase),
    user_id: str = Depends(get_user_id),
) -> list[Paper]:
    try:
        saved_resp = (
            await supabase.table("user_papers")
            .select("paper_id")
            .eq("user_id", user_id)
            .eq("dismissed", False)
            .execute()
        )
        paper_ids = [r["paper_id"] for r in (saved_resp.data or [])]
        if not paper_ids:
            return []

        papers_resp = (
            await supabase.table("papers")
            .select("*")
            .in_("id", paper_ids)
            .order("published_at", desc=True)
            .execute()
        )
        data = papers_resp.data or []
        return [Paper.model_validate(item) for item in data]
    except Exception:
        logger.exception("papers request failed")
        raise HTTPException(status_code=500, detail="Internal error")


@router.get("/{paper_id}", response_model=Paper)
async def get_paper(  # type: ignore[no-untyped-def]
    paper_id: str,
    supabase=Depends(get_supabase),
    user_id: str = Depends(get_user_id),
) -> Paper:
    try:
        response = await supabase.table("papers").select("*").eq("id", paper_id).single().execute()
        if not response.data:
            raise HTTPException(status_code=404, detail="Paper not found")
        return Paper.model_validate(response.data)
    except HTTPException:
        raise
    except Exception:
        logger.exception("papers request failed")
        raise HTTPException(status_code=500, detail="Internal error")


@router.get("/{paper_id}/public-evidence", response_model=PublicPaperEvidenceResponse)
async def get_public_paper_evidence(  # type: ignore[no-untyped-def]
    request: Request,
    paper_id: str,
    response: Response,
    query: str = Query(min_length=1, max_length=256),
    supabase=Depends(get_supabase),
    user_id: str = Depends(get_user_id),
) -> PublicPaperEvidenceResponse:
    """Return ephemeral page evidence only for exact-version CC BY/CC0 arXiv papers."""
    del request, user_id
    response.headers["Cache-Control"] = "no-store, private"
    from config import get_settings
    from services.public_paper_evidence import PublicEvidenceError, fetch_public_paper_evidence

    if not get_settings().public_paper_evidence_enabled:
        raise HTTPException(status_code=404, detail="Public paper evidence is unavailable")
    try:
        result = await (
            supabase.table("papers")
            .select("id,preprint_id,source_version,title")
            .eq("id", paper_id)
            .maybe_single()
            .execute()
        )
        paper = result.data
        if not isinstance(paper, dict):
            raise HTTPException(status_code=404, detail="Paper not found")
        evidence = await fetch_public_paper_evidence(paper, query)
        return PublicPaperEvidenceResponse.model_validate(evidence)
    except PublicEvidenceError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("public paper evidence request failed")
        raise HTTPException(status_code=500, detail="Public paper evidence could not be loaded") from exc


@router.get("/{paper_id}/status-watch", response_model=PaperStatusWatchState)
async def get_paper_status_watch(  # type: ignore[no-untyped-def]
    paper_id: str,
    supabase=Depends(get_supabase),
    user_id: str = Depends(get_user_id),
) -> PaperStatusWatchState:
    try:
        paper = await supabase.table("papers").select("id").eq("id", paper_id).maybe_single().execute()
        if not paper.data:
            raise HTTPException(status_code=404, detail="Paper not found")
        response = await (
            supabase.table("paper_status_watches")
            .select("paper_id")
            .eq("user_id", user_id)
            .eq("paper_id", paper_id)
            .maybe_single()
            .execute()
        )
        return PaperStatusWatchState(watching=bool(response.data))
    except HTTPException:
        raise
    except Exception:
        logger.exception("paper status watch lookup failed")
        raise HTTPException(status_code=500, detail="Internal error")


@router.post("/{paper_id}/status-watch", response_model=PaperStatusWatchState)
async def create_paper_status_watch(  # type: ignore[no-untyped-def]
    request: Request,
    paper_id: str,
    supabase=Depends(get_supabase),
    user_id: str = Depends(get_user_id),
) -> PaperStatusWatchState:
    try:
        paper = await (
            supabase.table("papers")
            .select("id,doi")
            .eq("id", paper_id)
            .maybe_single()
            .execute()
        )
        if not paper.data:
            raise HTTPException(status_code=404, detail="Paper not found")
        from services.crossref_updates import normalize_doi

        if not normalize_doi(paper.data.get("doi")):
            raise HTTPException(status_code=422, detail="Crossref monitoring requires a valid DOI")
        await supabase.table("paper_status_watches").upsert(
            {"user_id": user_id, "paper_id": paper_id},
            on_conflict="user_id,paper_id",
            ignore_duplicates=True,
        ).execute()
        return PaperStatusWatchState(watching=True)
    except HTTPException:
        raise
    except Exception:
        logger.exception("paper status watch creation failed")
        raise HTTPException(status_code=500, detail="Internal error")


@router.delete("/{paper_id}/status-watch", response_model=PaperStatusWatchState)
async def delete_paper_status_watch(  # type: ignore[no-untyped-def]
    request: Request,
    paper_id: str,
    supabase=Depends(get_supabase),
    user_id: str = Depends(get_user_id),
) -> PaperStatusWatchState:
    try:
        await (
            supabase.table("paper_status_watches")
            .delete()
            .eq("user_id", user_id)
            .eq("paper_id", paper_id)
            .execute()
        )
        return PaperStatusWatchState(watching=False)
    except Exception:
        logger.exception("paper status watch deletion failed")
        raise HTTPException(status_code=500, detail="Internal error")


@router.post("/{paper_id}/save")
async def save_paper(  # type: ignore[no-untyped-def]
    request: Request,
    paper_id: str,
    req: SavePaperRequest,
    supabase=Depends(get_supabase),
    user_id: str = Depends(get_user_id),
) -> dict[str, str]:
    try:
        await supabase.table("user_papers").upsert({
            "user_id": user_id,
            "paper_id": paper_id,
            "dismissed": req.dismissed,
        }).execute()
    except Exception:
        logger.exception("papers request failed")
        raise HTTPException(status_code=500, detail="Internal error")

    try:
        paper_resp = await supabase.table("papers").select("title, abstract").eq("id", paper_id).single().execute()
        paper_data = paper_resp.data or {}
        title = paper_data.get("title", paper_id)
        abstract_preview = (paper_data.get("abstract", "") or "")[:120]
        action = "Dismissed" if req.dismissed else "Saved"
        content = f"{action} paper: {title}"
        if abstract_preview:
            content += f" about {abstract_preview}..."
        await add_memory(user_id, [{"role": "user", "content": content}])
    except Exception:
        logger.exception("Failed to add memory for paper %s", paper_id)

    return {"status": "ok"}


@router.delete("/{paper_id}/save")
async def unsave_paper(  # type: ignore[no-untyped-def]
    request: Request,
    paper_id: str,
    supabase=Depends(get_supabase),
    user_id: str = Depends(get_user_id),
) -> dict[str, str]:
    try:
        await supabase.table("user_papers").delete().eq("user_id", user_id).eq("paper_id", paper_id).execute()
        return {"status": "ok"}
    except Exception:
        logger.exception("papers request failed")
        raise HTTPException(status_code=500, detail="Internal error")
