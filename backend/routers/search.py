import uuid

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel

from dependencies import get_optional_user
from models.schemas import SearchRequest
from services.llm_router import validate_model
from services.run_store import run_store

router = APIRouter(prefix="/api", tags=["search"])


class SearchResponse(BaseModel):
    run_id: str


@router.post("/search", response_model=SearchResponse)
async def search(
    req: SearchRequest,
    user: dict | None = Depends(get_optional_user),  # type: ignore[type-arg]
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> SearchResponse:
    # Model registry gate (update.md §14): reject unknown/expensive models.
    if req.model is not None:
        try:
            validate_model(req.model)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
    user_id = user["user_id"] if user else None
    run_id = str(uuid.uuid4())
    state = await run_store.create(
        run_id, req.query, req.model, user_id=user_id, idempotency_key=idempotency_key
    )
    return SearchResponse(run_id=state.run_id)
