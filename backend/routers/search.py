import uuid
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from models.schemas import SearchRequest
from services.run_store import run_store
from dependencies import get_current_user

router = APIRouter(prefix="/api", tags=["search"])


class SearchResponse(BaseModel):
    run_id: str


async def _optional_user_id(
    user: dict | None = Depends(get_current_user),
) -> str | None:
    return user.get("user_id") if user else None


@router.post("/search", response_model=SearchResponse)
async def search(
    req: SearchRequest,
    user_id: str | None = Depends(_optional_user_id),
):
    run_id = str(uuid.uuid4())
    await run_store.create(run_id, req.query, req.model)
    return SearchResponse(run_id=run_id)
