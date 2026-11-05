"""Durable-run job queue (update.md §7.1).

Stdlib asyncio queue + background worker for single-process deploys.
For multi-instance production, swap `enqueue`/`worker_loop` for arq/
Dramatiq backed by Redis — the run_id/event contract stays identical.
Postgres remains canonical for run metadata (migration 0001).
"""
import asyncio
import logging

logger = logging.getLogger(__name__)

_queue: asyncio.Queue | None = None
_worker_task: asyncio.Task | None = None  # type: ignore[type-arg]


def _get_queue() -> asyncio.Queue:  # type: ignore[type-arg]
    global _queue
    if _queue is None:
        _queue = asyncio.Queue()
    return _queue


async def enqueue(run_id: str) -> None:
    await _get_queue().put(run_id)


def queue_depth() -> int:
    return _get_queue().qsize() if _queue else 0


async def worker_loop() -> None:
    """Consume run_ids and execute each exactly once."""
    from routers.stream import _run_once  # local import: avoid cycle

    while True:
        run_id = await _get_queue().get()
        try:
            from services.run_store import run_store

            state = await run_store.get(run_id)
            if state is None:
                logger.warning("Queue: unknown run %s, skipping", run_id)
                continue
            if not await run_store.try_start(run_id):
                logger.info("Queue: run %s already started, skipping duplicate", run_id)
                continue
            await _run_once(run_id, state.query, state.user_id or "anonymous", state.model)
        except Exception:
            logger.exception("Queue worker failed on run %s", run_id)
        finally:
            _get_queue().task_done()


def start_worker() -> None:
    global _worker_task
    if _worker_task is None:
        _worker_task = asyncio.create_task(worker_loop())
        logger.info("Job queue worker started")


def stop_worker() -> None:
    global _worker_task
    if _worker_task is not None:
        _worker_task.cancel()
        _worker_task = None
