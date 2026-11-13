"""Background run queue.

Development uses a process-local asyncio queue. Redis deployments use a
consumer group: delivered messages remain pending until acknowledged, and
idle pending messages can be claimed after a worker dies. Production run
records and events are canonical in Postgres; Redis stores queue messages and
worker leases.
"""
import asyncio
import logging
import os
import uuid
from dataclasses import dataclass
from typing import Any, cast

logger = logging.getLogger(__name__)

_queue: asyncio.Queue[str] | None = None
_worker_task: asyncio.Task | None = None  # type: ignore[type-arg]
_active_tasks: set[asyncio.Task] = set()  # type: ignore[type-arg]
_redis = None
_consumer = f"{os.getenv('HOSTNAME', 'worker')}-{uuid.uuid4().hex[:8]}"
QUEUE_KEY = "zenith:runs:stream"
CONSUMER_GROUP = "zenith:runs:workers"
RECOVER_AFTER_MS = 90_000


@dataclass(frozen=True)
class QueueMessage:
    run_id: str
    message_id: str | None = None


def _use_redis() -> bool:
    from config import get_settings

    return bool(get_settings().redis_url)


async def _redis_client() -> Any:
    global _redis
    if _redis is None:
        import redis.asyncio as redis_mod

        from config import get_settings

        factory = cast(Any, redis_mod.from_url)
        _redis = factory(
            get_settings().redis_url,
            decode_responses=True,
        )
    return _redis


async def _ensure_group(client: Any) -> None:
    try:
        await client.xgroup_create(QUEUE_KEY, CONSUMER_GROUP, id="0", mkstream=True)
    except Exception as exc:
        # BUSYGROUP means another worker already created the shared group.
        if "BUSYGROUP" not in str(exc):
            raise


def _get_queue() -> asyncio.Queue[str]:
    global _queue
    if _queue is None:
        _queue = asyncio.Queue()
    return _queue


async def enqueue(run_id: str) -> None:
    if _use_redis():
        client = await _redis_client()
        await _ensure_group(client)
        await client.xadd(QUEUE_KEY, {"run_id": run_id})
        return
    await _get_queue().put(run_id)


async def remove_runs(run_ids: set[str]) -> None:
    """Remove queued IDs for runs being erased; no user payload is stored here."""
    if not run_ids:
        return
    if not _use_redis():
        queue = _get_queue()
        retained: list[str] = []
        while True:
            try:
                run_id = queue.get_nowait()
            except asyncio.QueueEmpty:
                break
            queue.task_done()
            if run_id not in run_ids:
                retained.append(run_id)
        for run_id in retained:
            queue.put_nowait(run_id)
        return

    client = await _redis_client()
    await _ensure_group(client)
    cursor = "-"
    while True:
        batch = await client.xrange(QUEUE_KEY, min=cursor, count=500)
        if not batch:
            break
        ids_to_delete = [
            message_id
            for message_id, fields in batch
            if fields.get("run_id") in run_ids
        ]
        if ids_to_delete:
            await client.xack(QUEUE_KEY, CONSUMER_GROUP, *ids_to_delete)
            await client.xdel(QUEUE_KEY, *ids_to_delete)
        last_id = batch[-1][0]
        cursor = f"({last_id}"
        if len(batch) < 500:
            break


def queue_depth() -> int:
    return _get_queue().qsize() if _queue else 0


async def _dequeue() -> QueueMessage:
    if not _use_redis():
        run_id = await asyncio.wait_for(_get_queue().get(), timeout=5)
        return QueueMessage(run_id=run_id)

    client = await _redis_client()
    await _ensure_group(client)
    # Recover work left pending by a crashed worker before reading new work.
    claimed = await client.xautoclaim(
        QUEUE_KEY,
        CONSUMER_GROUP,
        _consumer,
        min_idle_time=RECOVER_AFTER_MS,
        start_id="0-0",
        count=1,
    )
    messages = claimed[1] if claimed and len(claimed) > 1 else []
    if messages:
        message_id, fields = messages[0]
        run_id = fields.get("run_id")
        if run_id:
            return QueueMessage(run_id=run_id, message_id=message_id)

    batches = await client.xreadgroup(
        CONSUMER_GROUP,
        _consumer,
        {QUEUE_KEY: ">"},
        count=1,
        block=5_000,
    )
    if not batches:
        raise asyncio.TimeoutError
    message_id, fields = batches[0][1][0]
    return QueueMessage(run_id=fields["run_id"], message_id=message_id)


async def _execute_run(run_id: str) -> bool:
    from routers.stream import _run_once
    from services.run_store import run_store

    try:
        state = await run_store.get(run_id)
        if state is None:
            logger.warning("Queue: unknown run %s, acknowledging", run_id)
            return True
        if state.status in ("complete", "failed", "cancelled"):
            return True
        if not await run_store.try_start(run_id):
            # A live worker owns the lease. Keep this stream message pending;
            # it will be redelivered after the lease and visibility timeout.
            return False

        heartbeat = asyncio.create_task(_heartbeat_run(run_id))
        try:
            from config import get_settings

            settings = get_settings()
            plan_marker = "__research_plan_execution__"
            if state.model == plan_marker or settings.research_plan_execution_enabled:
                from services.research_plan_execution import get_plan_execution, is_missing_plan_execution_table

                try:
                    plan_metadata = await get_plan_execution(run_id)
                except Exception as exc:
                    if (
                        state.model == plan_marker
                        or settings.research_plan_execution_enabled
                        or not is_missing_plan_execution_table(exc)
                    ):
                        raise
                    # With the feature off, legacy standard runs work on an
                    # installation that has not applied migration 0019 yet.
                    plan_metadata = None
                if state.model == plan_marker and plan_metadata is None:
                    from services.research_plan_execution import PlanExecutionError

                    raise PlanExecutionError("Marked plan run is missing its execution metadata")
            else:
                plan_metadata = None

            if state.model == plan_marker or plan_metadata is not None:
                # Persisted marker and metadata determine dispatch, so a
                # rolling flag change cannot reinterpret accepted plan work.
                from services.research_plan_execution import run_plan_execution

                await run_plan_execution(run_id, state.user_id or "anonymous", state.query)
            else:
                await _run_once(run_id, state.query, state.user_id or "anonymous", state.model)
        finally:
            heartbeat.cancel()
            await asyncio.gather(heartbeat, return_exceptions=True)
            await run_store.release(run_id)
        return True
    except asyncio.CancelledError:
        # Leave the stream entry pending so another worker can recover it.
        raise
    except Exception:
        logger.exception("Queue worker failed on run %s", run_id)
        try:
            await run_store.update(run_id, status="failed")
        except Exception:
            logger.exception("Could not persist failed status for run %s", run_id)
            return False
        return True


async def _heartbeat_run(run_id: str) -> None:
    from services.run_store import run_store

    while True:
        await asyncio.sleep(30)
        if not await run_store.heartbeat(run_id):
            return


async def _ack(message: QueueMessage) -> None:
    if not message.message_id:
        _get_queue().task_done()
        return
    client = await _redis_client()
    await client.xack(QUEUE_KEY, CONSUMER_GROUP, message.message_id)


_semaphore: asyncio.Semaphore | None = None


async def worker_loop() -> None:
    """Consume jobs with bounded concurrency and graceful cancellation."""
    global _semaphore
    if _semaphore is None:
        _semaphore = asyncio.Semaphore(4)

    async def _bounded(message: QueueMessage) -> None:
        async with _semaphore:
            handled = await _execute_run(message.run_id)
            if handled:
                await _ack(message)

    try:
        while True:
            try:
                message = await _dequeue()
            except asyncio.TimeoutError:
                continue
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("Run queue poll failed; retrying")
                await asyncio.sleep(1)
                continue
            task = asyncio.create_task(_bounded(message))
            _active_tasks.add(task)
            task.add_done_callback(_active_tasks.discard)
    except asyncio.CancelledError:
        for task in tuple(_active_tasks):
            task.cancel()
        await asyncio.gather(*tuple(_active_tasks), return_exceptions=True)
        _active_tasks.clear()
        raise


def start_worker() -> None:
    global _worker_task
    if _worker_task is None or _worker_task.done():
        _worker_task = asyncio.create_task(worker_loop())
        logger.info("Job queue worker started (redis=%s)", _use_redis())


async def stop_worker() -> None:
    global _worker_task
    task = _worker_task
    _worker_task = None
    if task is not None:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
