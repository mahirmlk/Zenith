import logging
from fastapi import APIRouter, HTTPException, Depends, Query
from typing import Optional
from models.schemas import Paper, SavePaperRequest
from services.supabase_client import get_supabase
from services.mem0_client import add_memory
from dependencies import get_user_id

router = APIRouter(prefix="/api/papers", tags=["papers"])
logger = logging.getLogger(__name__)


@router.get("", response_model=list[Paper])
async def list_papers(  # type: ignore[no-untyped-def]
    q: Optional[str] = None,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    supabase=Depends(get_supabase),
    user_id: str = Depends(get_user_id),
) -> list[Paper]:
    try:
        query = supabase.table("papers").select("*")
        if q:
            query = query.ilike("title", f"%{q}%")
        query = query.order("published_at", desc=True).range(offset, offset + limit - 1)
        response = await query.execute()
        data = response.data or []
        return [Paper.model_validate(item) for item in data]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


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
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


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
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{paper_id}/save")
async def save_paper(  # type: ignore[no-untyped-def]
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
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

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
    paper_id: str,
    supabase=Depends(get_supabase),
    user_id: str = Depends(get_user_id),
) -> dict[str, str]:
    try:
        await supabase.table("user_papers").delete().eq("user_id", user_id).eq("paper_id", paper_id).execute()
        return {"status": "ok"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
