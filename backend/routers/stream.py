import asyncio
import uuid
from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, Depends, HTTPException, Query
from sse_starlette.sse import EventSourceResponse
from agents.orchestrator import run_orchestrator
from dependencies import get_current_user
from models.schemas import AgentStep, PaperSearchResult
from services.run_store import run_store

router = APIRouter(prefix="/api/stream", tags=["stream"])

_sse_sessions: dict[str, dict] = {}  # type: ignore[type-arg]


@router.post("/session")
async def create_sse_session(user: dict = Depends(get_current_user)) -> dict[str, str]:  # type: ignore[type-arg]
    """Exchange JWT for a short-lived SSE session token."""
    session_id = str(uuid.uuid4())
    _sse_sessions[session_id] = {
        "user_id": user["user_id"],
        "created_at": datetime.now(timezone.utc),
        "expires_at": datetime.now(timezone.utc) + timedelta(minutes=5),
    }
    return {"session_token": session_id}


def _validate_sse_session(session_token: str) -> str | None:
    """Validate SSE session token. Returns user_id or None."""
    session = _sse_sessions.get(session_token)
    if not session:
        return None
    if datetime.now(timezone.utc) > session["expires_at"]:
        del _sse_sessions[session_token]
        return None
    return session["user_id"]  # type: ignore[no-any-return]


async def event_generator(  # type: ignore[no-untyped-def]
    run_id: str, query: str, user_id: str, model: str | None
):
    queue: asyncio.Queue[dict] = asyncio.Queue()  # type: ignore[type-arg]

    async def callback(step: AgentStep) -> None:
        await queue.put({"event": "agent_step", "data": step.model_dump()})

    task = asyncio.create_task(run_orchestrator(run_id, query, callback, user_id=user_id, model=model))

    try:
        while True:
            if task.done():
                if task.exception() is None:
                    result = task.result()
                    if isinstance(result, PaperSearchResult):
                        yield {"event": "result", "data": result.model_dump()}
                    else:
                        yield {"event": "result", "data": {"papers": [], "run_id": run_id}}
                else:
                    exc = task.exception()
                    yield {"event": "error", "data": {"message": str(exc)}}
                break

            try:
                item = await asyncio.wait_for(queue.get(), timeout=30.0)
                yield item
                if item.get("event") in ("result", "error"):
                    break
            except asyncio.TimeoutError:
                yield {"event": "error", "data": {"message": "Stream timeout"}}
                break
    finally:
        if not task.done():
            task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass


@router.get("/{run_id}")
async def stream(
    run_id: str,
    token: str | None = Query(default=None, description="SSE session token"),
) -> EventSourceResponse:
    user_id = _validate_sse_session(token) if token else None
    if not user_id:
        raise HTTPException(status_code=401, detail="Valid authentication required")

    state = await run_store.get(run_id)
    if not state:
        raise HTTPException(status_code=404, detail="Run not found or expired")
    return EventSourceResponse(event_generator(run_id, state.query, user_id, state.model))  # type: ignore[arg-type,unused-ignore]
