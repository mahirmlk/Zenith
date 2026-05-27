import logging
from fastapi import APIRouter, HTTPException, Depends
from typing import Optional
from models.schemas import Paper, SavePaperRequest
from services.supabase_client import get_supabase
from services.mem0_client import add_memory
from dependencies import get_user_id

router = APIRouter(prefix="/api/papers", tags=["papers"])
logger = logging.getLogger(__name__)


@router.get("", response_model=list[Paper])
async def list_papers(
    q: Optional[str] = None,
    supabase=Depends(get_supabase),
    user_id: str = Depends(get_user_id),
):
    try:
        if q:
            response = await supabase.table("papers").select("*").ilike("title", f"%{q}%").limit(50).execute()
        else:
            response = await supabase.table("papers").select("*").order("published_at", desc=True).limit(50).execute()
        data = response.data or []
        return [Paper.model_validate(item) for item in data]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{paper_id}", response_model=Paper)
async def get_paper(
    paper_id: str,
    supabase=Depends(get_supabase),
    user_id: str = Depends(get_user_id),
):
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
async def save_paper(
    paper_id: str,
    req: SavePaperRequest,
    supabase=Depends(get_supabase),
    user_id: str = Depends(get_user_id),
):
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
        add_memory(user_id, [{"role": "user", "content": content}])
    except Exception:
        logger.exception("Failed to add memory for paper %s", paper_id)

    return {"status": "ok"}


@router.delete("/{paper_id}/save")
async def unsave_paper(
    paper_id: str,
    supabase=Depends(get_supabase),
    user_id: str = Depends(get_user_id),
):
    try:
        await supabase.table("user_papers").delete().eq("user_id", user_id).eq("paper_id", paper_id).execute()
        return {"status": "ok"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
