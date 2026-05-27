from fastapi import APIRouter
from services.papers_with_code import fetch_paper_repos

router = APIRouter(prefix="/api/papers", tags=["papers_with_code"])


@router.get("/{paper_id}/code")
async def get_paper_code(paper_id: str):
    data = await fetch_paper_repos(paper_id)
    return data
