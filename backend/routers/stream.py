import asyncio
import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, AsyncIterator

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
import jwt
from jwt.exceptions import InvalidTokenError
from sse_starlette.sse import EventSourceResponse

from config import get_settings
from agents.orchestrator import run_orchestrator
from dependencies import get_current_user
from models.schemas import AgentStep
from security.authorization import can_access_run
from services.run_store import run_store

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/stream", tags=["stream"])
sse_bearer = HTTPBearer(auto_error=False)

# Background tasks started once per run (update.md §7.1): a disconnect or
# reconnect must never cancel or duplicate the work.
_running_tasks: dict[str, asyncio.Task] = {}  # type: ignore[type-arg]


@router.post("/session")
async def create_sse_session(request: Request, user: dict = Depends(get_current_user)) -> dict[str, str]:  # type: ignore[type-arg]
    """Exchange a bearer JWT for a short-lived stateless SSE token.

    Using a server-only key lets every API replica verify the token without
    process-local session state.
    """
    key = get_settings().supabase_service_role_key
    if not key:
        raise HTTPException(status_code=503, detail="Streaming authentication unavailable")
    now = datetime.now(timezone.utc)
    session_token = jwt.encode(
        {
            "sub": user["user_id"],
            "iat": now,
            "exp": now + timedelta(minutes=5),
            "iss": "zenith-sse",
            "jti": str(uuid.uuid4()),
        },
        key,
        algorithm="HS256",
    )
    return {"session_token": session_token}


def _validate_sse_session(session_token: str) -> str | None:
    key = get_settings().supabase_service_role_key
    if not key:
        return None
    try:
        payload = jwt.decode(
            session_token,
            key,
            algorithms=["HS256"],
            issuer="zenith-sse",
            options={"require": ["sub", "iat", "exp", "iss", "jti"]},
        )
        subject = payload.get("sub")
        return subject if isinstance(subject, str) and subject else None
    except InvalidTokenError:
        return None


def _parse_last_event_id(value: str | None) -> int:
    """Parse the SSE replay cursor as a nonnegative ASCII integer."""
    if value is None:
        return 0
    if not value or not value.isascii() or not value.isdecimal():
        raise HTTPException(status_code=400, detail="Invalid Last-Event-ID")
    try:
        return int(value)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid Last-Event-ID") from exc


async def _run_once(run_id: str, query: str, user_id: str, model: str | None) -> None:
    """Run the orchestrator exactly once per run_id (start-once guard)."""
    async def callback(step: AgentStep) -> None:
        state = await run_store.get(run_id)
        if state and state.status == "cancelled":
            return
        await run_store.add_event(run_id, "agent_step", step.model_dump())

    try:
        result = await run_orchestrator(run_id, query, callback, user_id=user_id, model=model)
        state = await run_store.get(run_id)
        if state and state.status == "cancelled":
            await run_store.add_event(run_id, "cancelled", {"run_id": run_id})
            return
        await run_store.add_event(run_id, "result", result.model_dump())
    except Exception:  # noqa: BLE001 - record safe error class only
        logger.exception("Run %s failed", run_id)
        await run_store.update(run_id, status="failed")
        await run_store.add_event(run_id, "error", {"error_code": "run_failed", "message": "Run failed"})
    finally:
        _running_tasks.pop(run_id, None)


async def event_generator(
    run_id: str,
    query: str,
    user_id: str,
    model: str | None,
    last_event_id: int = 0,
) -> AsyncIterator[dict[str, Any]]:
    # Replay persisted events first (reconnect safety, update.md §7.1).
    # Track by max sequence (not len) to avoid missing events appended
    # between the replay read and the poll loop (bug-hunt P1).
    replayed = await run_store.get_events(run_id)
    terminal_events = {"result", "error", "cancelled"}
    for evt in replayed:
        if evt["sequence"] <= last_event_id:
            continue
        yield {"event": evt["event"], "data": evt["data"], "id": str(evt["sequence"])}
        if evt["event"] in terminal_events:
            return  # Terminal event already replayed — no duplicate result.
    if any(
        evt["sequence"] <= last_event_id and evt["event"] in terminal_events
        for evt in replayed
    ):
        return  # The client cursor already covers the terminal event.

    state = await run_store.get(run_id)
    if state and state.status == "complete" and state.results:
        yield {"event": "result", "data": {"papers": state.results, "run_id": run_id}}
        return

    # Workers own job execution. The SSE request is a read-only subscription
    # and cannot race the queue for a run claim.
    seen_seq = max(last_event_id, max((e["sequence"] for e in replayed), default=0))
    deadline = datetime.now(timezone.utc) + timedelta(minutes=10)
    while datetime.now(timezone.utc) < deadline:
        await asyncio.sleep(0.5)
        events = await run_store.get_events(run_id)
        for evt in events:
            if evt["sequence"] > seen_seq:
                yield {"event": evt["event"], "data": evt["data"], "id": str(evt["sequence"])}
                seen_seq = evt["sequence"]
                if evt["event"] in ("result", "error", "cancelled"):
                    return
        state = await run_store.get(run_id)
        if state and state.status in ("complete", "failed", "cancelled"):
            if state.status == "complete" and state.results:
                yield {"event": "result", "data": {"papers": state.results, "run_id": run_id}}
            elif state.status == "cancelled":
                yield {"event": "cancelled", "data": {"run_id": run_id}}
            return


@router.get("/{run_id}")
async def stream(
    run_id: str,
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(sse_bearer),
    last_event_id: str | None = Header(default=None, alias="Last-Event-ID"),
) -> EventSourceResponse:
    if credentials is None or credentials.scheme.casefold() != "bearer":
        raise HTTPException(status_code=401, detail="Valid authentication required")
    user_id = _validate_sse_session(credentials.credentials)
    if not user_id:
        raise HTTPException(status_code=401, detail="Valid authentication required")
    cursor = _parse_last_event_id(last_event_id)

    state = await run_store.get(run_id)
    if not state:
        raise HTTPException(status_code=404, detail="Run not found or expired")
    # Ownership (update.md §5.2): a run bound to a user is only streamable
    # by that user. 404 (not 403) avoids leaking existence.
    if not can_access_run(getattr(state, "user_id", None), user_id):
        raise HTTPException(status_code=404, detail="Run not found or expired")
    return EventSourceResponse(
        event_generator(run_id, state.query, user_id, state.model, cursor)
    )  # type: ignore[arg-type,unused-ignore]
