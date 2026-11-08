import uuid

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import BaseModel

from dependencies import get_current_user
from models.schemas import SearchRequest
from services.llm_router import validate_model
from services.run_store import run_store

router = APIRouter(prefix="/api", tags=["search"])


class SearchResponse(BaseModel):
    run_id: str


@router.post("/search", response_model=SearchResponse)
async def search(
    request: Request,
    req: SearchRequest,
    user: dict = Depends(get_current_user),  # type: ignore[type-arg]
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> SearchResponse:
    """Authenticated only (update.md §5.2): anonymous callers must not
    trigger the LLM pipeline. Frontend already sends the Supabase JWT
    via `Authorization: Bearer` (lib/api.ts getHeaders)."""
    # Model registry gate (update.md §14): reject unknown/expensive models.
    if req.model is not None:
        try:
            validate_model(req.model)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
    user_id = user["user_id"]
    run_id = str(uuid.uuid4())
    from config import get_settings

    from services import budget

    if idempotency_key:
        existing = await run_store.find_idempotent(user_id, idempotency_key)
        if existing:
            if existing.query != req.query or existing.model != req.model:
                raise HTTPException(status_code=409, detail="Idempotency key reused for a different request")
            if existing.status == "pending" and not existing.started:
                from services.job_queue import enqueue

                await enqueue(existing.run_id)
            return SearchResponse(run_id=existing.run_id)

    try:
        within_budget = await budget.consume(
            user_id, get_settings().max_searches_per_day_per_user
        )
    except budget.BudgetUnavailableError as exc:
        raise HTTPException(status_code=503, detail="Search service temporarily unavailable") from exc
    if not within_budget:
        raise HTTPException(status_code=429, detail="Daily search budget exceeded")

    try:
        state = await run_store.create(
            run_id, req.query, req.model, user_id=user_id, idempotency_key=idempotency_key
        )
    except ValueError as exc:
        await budget.refund(user_id)
        raise HTTPException(status_code=409, detail="Idempotency key reused for a different request") from exc
    if state.run_id != run_id:
        await budget.refund(user_id)
    # Durable enqueue (update.md §7.1): work starts in the worker, never
    # in the SSE handler. Idempotent replays return the existing run_id
    # and enqueue nothing new.
    if state.run_id == run_id and not state.started:
        from services.job_queue import enqueue

        await enqueue(state.run_id)
    return SearchResponse(run_id=state.run_id)
