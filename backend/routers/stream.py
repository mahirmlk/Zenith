import asyncio
from fastapi import APIRouter, HTTPException, Depends
from sse_starlette.sse import EventSourceResponse
from agents.orchestrator import run_orchestrator
from models.schemas import AgentStep, PaperSearchResult
from services.run_store import run_store
from dependencies import get_user_id

router = APIRouter(prefix="/api/stream", tags=["stream"])


async def event_generator(run_id: str, query: str, user_id: str, model: str | None):
    queue: asyncio.Queue[dict] = asyncio.Queue()

    async def callback(step: AgentStep):
        await queue.put({"event": "agent_step", "data": step.model_dump()})

    task = asyncio.create_task(run_orchestrator(run_id, query, callback, user_id=user_id, model=model))

    try:
        while True:
            try:
                item = await asyncio.wait_for(queue.get(), timeout=30.0)
                yield item
                if item.get("event") in ("result", "error"):
                    break
            except asyncio.TimeoutError:
                yield {"event": "error", "data": {"message": "Stream timeout"}}
                break

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
    user_id: str = Depends(get_user_id),
):
    state = await run_store.get(run_id)
    if not state:
        raise HTTPException(status_code=404, detail="Run not found or expired")
    return EventSourceResponse(event_generator(run_id, state.query, user_id, state.model))
