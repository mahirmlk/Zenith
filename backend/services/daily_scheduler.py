"""Singleton UTC scheduler and shared lease for daily paper ingestion.

Every ingestion trigger (API scheduler, Fly cron, admin route) uses one Redis
lease. The UTC scheduler adds per-day completion and bounded retry state;
heartbeat loss cancels its active fetch before another trigger can proceed.
"""
from __future__ import annotations

import asyncio
import logging
import secrets
from datetime import date, datetime, time, timezone
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, cast

logger = logging.getLogger(__name__)

POLL_SECONDS = 30
RUN_AT_UTC = time(hour=2)
LOCK_TTL_SECONDS = 120
LOCK_RENEW_SECONDS = 30
MAX_ATTEMPTS = 3
MAX_RUN_SECONDS = 4 * 60 * 60
STATE_TTL_SECONDS = 3 * 24 * 60 * 60
RETRY_BASE_SECONDS = 60
GLOBAL_INGESTION_LOCK_KEY = "zenith:{ingestion}:global:lock"

_scheduler_task: asyncio.Task[None] | None = None
_redis = None

_RENEW_LOCK = """
if redis.call('GET', KEYS[1]) == ARGV[1] then
  return redis.call('EXPIRE', KEYS[1], ARGV[2])
end
return 0
"""
_RELEASE_LOCK = """
if redis.call('GET', KEYS[1]) == ARGV[1] then
  return redis.call('DEL', KEYS[1])
end
return 0
"""
_INCREMENT_ATTEMPT = """
local attempts = redis.call('INCR', KEYS[1])
if attempts == 1 then redis.call('EXPIRE', KEYS[1], ARGV[1]) end
return attempts
"""
_MARK_COMPLETE = """
if redis.call('GET', KEYS[1]) ~= ARGV[1] then return 0 end
redis.call('SET', KEYS[2], '1', 'EX', ARGV[2])
return 1
"""


class IngestionLeaseLost(RuntimeError):
    """Raised when Redis no longer confirms ownership of the global lease."""


@dataclass(frozen=True)
class LeaseResult:
    acquired: bool
    result: object | None = None


def _day_keys(day: date) -> tuple[str, str, str, str]:
    suffix = day.isoformat()
    prefix = f"zenith:{{ingestion}}:daily-ingest:{suffix}"
    return f"{prefix}:lock", f"{prefix}:attempts", f"{prefix}:retry-at", f"{prefix}:complete"


def _due_at(now: datetime) -> datetime:
    return datetime.combine(now.date(), RUN_AT_UTC, tzinfo=timezone.utc)


async def _redis_client() -> Any:
    global _redis
    if _redis is None:
        from config import get_settings
        import redis.asyncio as redis_mod

        url = get_settings().redis_url
        if not url:
            raise RuntimeError("REDIS_URL is required for scheduled ingestion")
        factory = cast(Any, redis_mod.from_url)
        _redis = factory(
            url,
            decode_responses=True,
            socket_connect_timeout=3,
            socket_timeout=5,
        )
    return _redis


async def run_with_ingestion_lease(
    runner: Callable[[], Awaitable[object]],
    *,
    source: str,
    redis: Any | None = None,
    on_acquired: Callable[[], Awaitable[None]] | None = None,
    completion_day: date | None = None,
) -> LeaseResult:
    """Run ingestion under the cross-trigger Redis lease.

    The scheduled poller, Fly cron command, and admin endpoint all call this
    helper. Loss of the Redis lease cancels the active runner before another
    worker can reclaim the expired lock and begin a duplicate fetch.
    """
    client = redis or await _redis_client()
    owner = secrets.token_urlsafe(24)
    acquired = await client.set(
        GLOBAL_INGESTION_LOCK_KEY,
        owner,
        ex=LOCK_TTL_SECONDS,
        nx=True,
    )
    if not acquired:
        logger.info("Skipping %s ingestion trigger: another fetch owns the lease", source)
        return LeaseResult(acquired=False)

    heartbeat: asyncio.Task[None] | None = None
    run_task: asyncio.Task[object] | None = None
    day = completion_day or datetime.now(timezone.utc).date()
    try:
        if on_acquired is not None:
            await on_acquired()
        heartbeat = asyncio.create_task(
            _renew_lock(client, GLOBAL_INGESTION_LOCK_KEY, owner)
        )
        run_task = asyncio.create_task(
            asyncio.wait_for(runner(), timeout=MAX_RUN_SECONDS)
        )
        done, _ = await asyncio.wait(
            {heartbeat, run_task},
            return_when=asyncio.FIRST_COMPLETED,
        )
        if heartbeat in done:
            try:
                await heartbeat
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                if not run_task.done():
                    run_task.cancel()
                await asyncio.gather(run_task, return_exceptions=True)
                raise IngestionLeaseLost(
                    f"Redis lease lost during {source} ingestion"
                ) from exc
            if not run_task.done():
                run_task.cancel()
                await asyncio.gather(run_task, return_exceptions=True)
                raise IngestionLeaseLost(
                    f"Redis lease expired during {source} ingestion"
                )

        result = await run_task
        if source in ("scheduled", "fly-cron"):
            _, _, _, complete_key = _day_keys(day)
            marked = await client.eval(
                _MARK_COMPLETE,
                2,
                GLOBAL_INGESTION_LOCK_KEY,
                complete_key,
                owner,
                STATE_TTL_SECONDS,
            )
            if not marked:
                raise IngestionLeaseLost(
                    f"Redis lease was lost before marking {source} ingestion complete"
                )
        return LeaseResult(acquired=True, result=result)
    except asyncio.CancelledError:
        if run_task is not None and not run_task.done():
            run_task.cancel()
            await asyncio.gather(run_task, return_exceptions=True)
        raise
    finally:
        if heartbeat is not None:
            heartbeat.cancel()
            await asyncio.gather(heartbeat, return_exceptions=True)
        try:
            await client.eval(_RELEASE_LOCK, 1, GLOBAL_INGESTION_LOCK_KEY, owner)
        except Exception:
            logger.exception("Could not release shared ingestion lease after %s", source)


async def run_daily_fetch_with_lease(source: str = "manual") -> LeaseResult:
    """Execute the standard ingestion pipeline through the global lease."""
    from services.ingestion import run_daily_fetch

    return await run_with_ingestion_lease(run_daily_fetch, source=source)


async def run_due_once(
    *,
    now: datetime | None = None,
    redis: Any | None = None,
    runner: Callable[[], Awaitable[object]] | None = None,
) -> bool:
    """Run this UTC day's ingestion once when due; return whether claimed.

    Dependency arguments are injectable for deterministic tests. Redis stores
    the lease and day state, so API replicas share the same schedule boundary.
    """
    from config import get_settings

    settings = get_settings()
    if not settings.redis_url and redis is None:
        return False

    current = now or datetime.now(timezone.utc)
    current = current.replace(tzinfo=timezone.utc) if current.tzinfo is None else current.astimezone(timezone.utc)
    if current < _due_at(current):
        return False

    client = redis or await _redis_client()
    lock_key, attempts_key, retry_key, complete_key = _day_keys(current.date())
    if await client.get(complete_key):
        return False

    retry_after = await client.get(retry_key)
    if retry_after and current.timestamp() < float(retry_after):
        return False
    attempts = int(await client.get(attempts_key) or 0)
    if attempts >= MAX_ATTEMPTS:
        return False

    owner = secrets.token_urlsafe(24)
    acquired = await client.set(lock_key, owner, ex=LOCK_TTL_SECONDS, nx=True)
    if not acquired:
        return False

    attempt = 0
    try:
        # Recheck after acquiring: another worker may have completed just
        # before this lease was obtained.
        if await client.get(complete_key):
            return False

        async def count_attempt() -> None:
            nonlocal attempt
            attempt = int(
                await client.eval(
                    _INCREMENT_ATTEMPT,
                    1,
                    attempts_key,
                    STATE_TTL_SECONDS,
                )
            )

        if runner is None:
            from services.ingestion import run_daily_fetch

            runner = run_daily_fetch
        lease_result = await run_with_ingestion_lease(
            runner,
            source="scheduled",
            redis=client,
            on_acquired=count_attempt,
            completion_day=current.date(),
        )
        if not lease_result.acquired:
            return False
        await client.delete(retry_key)
        logger.info("Scheduled daily ingestion completed for %s", current.date())
        return True
    except asyncio.CancelledError:
        raise
    except Exception:
        logger.exception("Scheduled daily ingestion attempt %s failed for %s", attempt, current.date())
        if attempt == 0:
            raise
        if attempt < MAX_ATTEMPTS:
            retry_delay = RETRY_BASE_SECONDS * (2 ** (attempt - 1))
            failed_at = max(current.timestamp(), datetime.now(timezone.utc).timestamp())
            await client.set(
                retry_key,
                str(failed_at + retry_delay),
                ex=STATE_TTL_SECONDS,
            )
        return True
    finally:
        try:
            await client.eval(_RELEASE_LOCK, 1, lock_key, owner)
        except Exception:
            logger.exception("Could not release daily ingestion lease for %s", current.date())


async def _renew_lock(client: Any, lock_key: str, owner: str) -> None:
    while True:
        await asyncio.sleep(LOCK_RENEW_SECONDS)
        try:
            renewed = await client.eval(_RENEW_LOCK, 1, lock_key, owner, LOCK_TTL_SECONDS)
        except Exception as exc:
            raise IngestionLeaseLost("Redis lease heartbeat failed") from exc
        if not renewed:
            raise IngestionLeaseLost("Redis no longer owns the ingestion lease")


async def scheduler_loop() -> None:
    """Poll Redis for the UTC schedule and keep running through transient errors."""
    while True:
        try:
            await run_due_once()
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Daily ingestion scheduler tick failed")
        await asyncio.sleep(POLL_SECONDS)


def start_daily_scheduler() -> asyncio.Task[None] | None:
    """Start polling only when shared Redis is configured."""
    global _scheduler_task
    from config import get_settings

    settings = get_settings()
    missing = [
        name
        for name, value in (
            ("REDIS_URL", settings.redis_url),
            ("SUPABASE_URL", settings.supabase_url),
            ("SUPABASE_SERVICE_ROLE_KEY", settings.supabase_service_role_key),
        )
        if not value
    ]
    if missing:
        logger.info("Daily ingestion scheduler disabled; missing required settings: %s", ", ".join(missing))
        return None
    if _scheduler_task is None or _scheduler_task.done():
        _scheduler_task = asyncio.create_task(scheduler_loop())
        logger.info("Daily ingestion scheduler started")
    return _scheduler_task


async def stop_daily_scheduler() -> None:
    """Cancel the poller and close its Redis connection cleanly."""
    global _scheduler_task, _redis
    task = _scheduler_task
    _scheduler_task = None
    if task is not None:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
    if _redis is not None:
        close = getattr(_redis, "aclose", None)
        if close is None:
            close = getattr(_redis, "close")
        await close()
        _redis = None
