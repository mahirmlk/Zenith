import asyncio
import logging
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sse_starlette.sse import EventSourceResponse

from agents.orchestrator import run_orchestrator
from dependencies import get_current_user
from models.schemas import AgentStep
from services.run_store import run_store

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/stream", tags=["stream"])

_sse_sessions: dict[str, dict] = {}  # type: ignore[type-arg]
# Background tasks started once per run (update.md §7.1): a disconnect or
# reconnect must never cancel or duplicate the work.
_running_tasks: dict[str, asyncio.Task] = {}  # type: ignore[type-arg]


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
    session = _sse_sessions.get(session_token)
    if not session:
        return None
    if datetime.now(timezone.utc) > session["expires_at"]:
        del _sse_sessions[session_token]
        return None
    return session["user_id"]  # type: ignore[no-any-return]


async def _run_once(run_id: str, query: str, user_id: str, model: str | None) -> None:
    """Run the orchestrator exactly once per run_id (start-once guard)."""
    async def callback(step: AgentStep) -> None:
        await run_store.add_event(run_id, "agent_step", step.model_dump())

    try:
        result = await run_orchestrator(run_id, query, callback, user_id=user_id, model=model)
        await run_store.add_event(run_id, "result", result.model_dump())
    except Exception:  # noqa: BLE001 - record safe error class only
        logger.exception("Run %s failed", run_id)
        await run_store.update(run_id, status="failed")
        await run_store.add_event(run_id, "error", {"error_code": "run_failed", "message": "Run failed"})
    finally:
        _running_tasks.pop(run_id, None)


async def event_generator(run_id: str, query: str, user_id: str, model: str | None):
    # Replay persisted events first (reconnect safety, update.md §7.1).
    for evt in await run_store.get_events(run_id):
        yield {"event": evt["event"], "data": evt["data"], "id": str(evt["sequence"])}

    state = await run_store.get(run_id)
    if state and state.status == "complete" and state.results:
        yield {"event": "result", "data": {"papers": state.results, "run_id": run_id}}
        return

    # Start work only once; other subscribers just wait for events.
    if await run_store.try_start(run_id):
        task = asyncio.create_task(_run_once(run_id, query, user_id, model))
        _running_tasks[run_id] = task

    # Poll persisted events until terminal state; disconnect does NOT cancel.
    seen = len(await run_store.get_events(run_id))
    deadline = datetime.now(timezone.utc) + timedelta(minutes=10)
    while datetime.now(timezone.utc) < deadline:
        await asyncio.sleep(0.5)
        events = await run_store.get_events(run_id)
        for evt in events[seen:]:
            yield {"event": evt["event"], "data": evt["data"], "id": str(evt["sequence"])}
        seen = len(events)
        if events and events[-1]["event"] in ("result", "error"):
            break
        state = await run_store.get(run_id)
        if state and state.status in ("complete", "failed"):
            if state.status == "complete" and state.results:
                yield {"event": "result", "data": {"papers": state.results, "run_id": run_id}}
            break


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
    # Ownership (update.md §5.2): a run bound to a user is only streamable
    # by that user. 404 (not 403) avoids leaking existence.
    if getattr(state, "user_id", None) and state.user_id != user_id:
        raise HTTPException(status_code=404, detail="Run not found or expired")
    return EventSourceResponse(event_generator(run_id, state.query, user_id, state.model))  # type: ignore[arg-type,unused-ignore]
