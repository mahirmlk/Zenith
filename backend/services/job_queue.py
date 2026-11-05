"""Durable-run job queue (update.md §7.1).

Two backends, same run_id/event contract:
- In-process asyncio queue (dev/single-process, default).
- Redis list (multi-instance production) when `REDIS_URL` is set:
  producers LPUSH, workers BRPOP — any instance can run any run, and
  `try_start` in the run store prevents duplicate execution.
Postgres remains canonical for run metadata (migration 0001).
"""
import asyncio
import logging

logger = logging.getLogger(__name__)

_queue: asyncio.Queue | None = None
_worker_task: asyncio.Task | None = None  # type: ignore[type-arg]
_redis = None
QUEUE_KEY = "zenith:runs:queue"


def _use_redis() -> bool:
    from config import get_settings

    return bool(get_settings().redis_url)


async def _redis_client():
    global _redis
    if _redis is None:
        import redis.asyncio as redis_mod

        from config import get_settings

        _redis = redis_mod.from_url(get_settings().redis_url, decode_responses=True)
    return _redis


def _get_queue() -> asyncio.Queue:  # type: ignore[type-arg]
    global _queue
    if _queue is None:
        _queue = asyncio.Queue()
    return _queue


async def enqueue(run_id: str) -> None:
    if _use_redis():
        client = await _redis_client()
        await client.lpush(QUEUE_KEY, run_id)
        return
    await _get_queue().put(run_id)


def queue_depth() -> int:
    return _get_queue().qsize() if _queue else 0


async def _dequeue() -> str:
    if _use_redis():
        client = await _redis_client()
        item = await client.brpop(QUEUE_KEY, timeout=5)
        if item is None:
            raise asyncio.TimeoutError
        return item[1]
    return await asyncio.wait_for(_get_queue().get(), timeout=5)


_semaphore: asyncio.Semaphore | None = None


async def _execute_run(run_id: str) -> None:
    from routers.stream import _run_once  # local import: avoid cycle

    try:
        from services.run_store import run_store

        state = await run_store.get(run_id)
        if state is None:
            logger.warning("Queue: unknown run %s, skipping", run_id)
            return
        if not await run_store.try_start(run_id):
            logger.info("Queue: run %s already started, skipping duplicate", run_id)
            return
        await _run_once(run_id, state.query, state.user_id or "anonymous", state.model)
    except Exception:
        logger.exception("Queue worker failed on run %s", run_id)
        try:
            from services.run_store import run_store

            await run_store.update(run_id, status="failed")
        except Exception:
            pass


async def worker_loop() -> None:
    """Consume run_ids, executing with bounded concurrency (4) so one
    long LLM run cannot starve the queue head (bug-hunt P1)."""
    global _semaphore
    if _semaphore is None:
        _semaphore = asyncio.Semaphore(4)

    async def _bounded(run_id: str):
        async with _semaphore:
            await _execute_run(run_id)
            if not _use_redis():
                _get_queue().task_done()

    while True:
        try:
            run_id = await _dequeue()
        except asyncio.TimeoutError:
            continue
        asyncio.create_task(_bounded(run_id))


def start_worker() -> None:
    global _worker_task
    if _worker_task is None:
        _worker_task = asyncio.create_task(worker_loop())
        logger.info("Job queue worker started (redis=%s)", _use_redis())


def stop_worker() -> None:
    global _worker_task
    if _worker_task is not None:
        _worker_task.cancel()
        _worker_task = None
