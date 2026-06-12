import uuid
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from models.schemas import SearchRequest
from services.run_store import run_store
from dependencies import get_optional_user

router = APIRouter(prefix="/api", tags=["search"])


class SearchResponse(BaseModel):
    run_id: str


@router.post("/search", response_model=SearchResponse)
async def search(
    req: SearchRequest,
    user: dict | None = Depends(get_optional_user),  # type: ignore[type-arg]
) -> SearchResponse:
    run_id = str(uuid.uuid4())
    await run_store.create(run_id, req.query, req.model)
    return SearchResponse(run_id=run_id)
