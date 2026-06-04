from fastapi import APIRouter, Depends
from services.papers_with_code import fetch_paper_repos
from dependencies import get_user_id

router = APIRouter(prefix="/api/papers", tags=["papers_with_code"])


@router.get("/{paper_id}/code")
async def get_paper_code(paper_id: str, user_id: str = Depends(get_user_id)):
    data = await fetch_paper_repos(paper_id)
    return data
