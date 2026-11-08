"""Run status / events / cancel (update.md §7.1, §15).

Compatibility adapter for the older `/api/search` + `/api/stream/{id}`
flow: these endpoints never start work; they read persisted state.
"""
from fastapi import APIRouter, Depends, HTTPException

from dependencies import get_current_user
from security.authorization import can_access_run
from services.run_store import run_store

router = APIRouter(prefix="/api/runs", tags=["runs"])


async def _get_owned(run_id: str, user: dict) -> object:
    state = await run_store.get(run_id)
    if not state or not can_access_run(getattr(state, "user_id", None), user["user_id"]):
        raise HTTPException(status_code=404, detail="Run not found or expired")
    return state


@router.get("/{run_id}")
async def run_status(run_id: str, user: dict = Depends(get_current_user)):
    state = await _get_owned(run_id, user)
    return {
        "run_id": state.run_id,
        "status": state.status,
        "query": state.query,
        "result_count": len(state.results),
        "created_at": state.created_at.isoformat(),
    }


@router.get("/{run_id}/events")
async def run_events(run_id: str, user: dict = Depends(get_current_user)):
    await _get_owned(run_id, user)
    return {"run_id": run_id, "events": await run_store.get_events(run_id)}


@router.post("/{run_id}/cancel")
async def run_cancel(run_id: str, user: dict = Depends(get_current_user)):
    state = await _get_owned(run_id, user)
    if state.status in ("complete", "failed", "cancelled"):
        return {"run_id": run_id, "status": state.status}
    await run_store.update(run_id, status="cancelled")
    state = await run_store.get(run_id)
    if state and state.status == "cancelled":
        await run_store.add_event(run_id, "cancelled", {"run_id": run_id})
    # Cancellation is terminal for result publication. An in-flight provider
    # call may finish, but the late response is discarded by _run_once.
    return {"run_id": run_id, "status": state.status if state else "cancelled"}
