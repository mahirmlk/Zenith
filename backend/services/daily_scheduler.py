"""Singleton UTC scheduler for daily paper ingestion and watchlist delivery.

Every API replica may run the polling task, but a Redis lease admits only one
ingest attempt for a UTC day. Failed attempts are retried with bounded
exponential backoff; completed days are recorded to suppress duplicate runs.
"""
from __future__ import annotations

import asyncio
import logging
import secrets
from datetime import date, datetime, time, timezone
from typing import Awaitable, Callable

logger = logging.getLogger(__name__)

POLL_SECONDS = 30
RUN_AT_UTC = time(hour=2)
LOCK_TTL_SECONDS = 120
LOCK_RENEW_SECONDS = 30
MAX_ATTEMPTS = 3
MAX_RUN_SECONDS = 4 * 60 * 60
STATE_TTL_SECONDS = 3 * 24 * 60 * 60
RETRY_BASE_SECONDS = 60

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


def _day_keys(day: date) -> tuple[str, str, str, str]:
    suffix = day.isoformat()
    prefix = f"zenith:scheduler:daily-ingest:{suffix}"
    return f"{prefix}:lock", f"{prefix}:attempts", f"{prefix}:retry-at", f"{prefix}:complete"


def _due_at(now: datetime) -> datetime:
    return datetime.combine(now.date(), RUN_AT_UTC, tzinfo=timezone.utc)


async def _redis_client():
    global _redis
    if _redis is None:
        from config import get_settings
        import redis.asyncio as redis_mod

        url = get_settings().redis_url
        if not url:
            raise RuntimeError("REDIS_URL is required for scheduled ingestion")
        _redis = redis_mod.from_url(url, decode_responses=True, socket_connect_timeout=3)
    return _redis


async def run_due_once(
    *,
    now: datetime | None = None,
    redis=None,
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

    heartbeat: asyncio.Task[None] | None = None
    try:
        # Recheck after acquiring: another worker may have completed just
        # before this lease was obtained.
        if await client.get(complete_key):
            return False

        attempt = int(await client.eval(_INCREMENT_ATTEMPT, 1, attempts_key, STATE_TTL_SECONDS))
        heartbeat = asyncio.create_task(_renew_lock(client, lock_key, owner))
        if runner is None:
            from services.ingestion import run_daily_fetch

            runner = run_daily_fetch
        await asyncio.wait_for(runner(), timeout=MAX_RUN_SECONDS)
        await client.set(complete_key, "1", ex=STATE_TTL_SECONDS)
        await client.delete(retry_key)
        logger.info("Scheduled daily ingestion completed for %s", current.date())
        return True
    except asyncio.CancelledError:
        raise
    except Exception:
        logger.exception("Scheduled daily ingestion attempt %s failed for %s", attempt, current.date())
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
        if heartbeat is not None:
            heartbeat.cancel()
            await asyncio.gather(heartbeat, return_exceptions=True)
        try:
            await client.eval(_RELEASE_LOCK, 1, lock_key, owner)
        except Exception:
            logger.exception("Could not release daily ingestion lease for %s", current.date())


async def _renew_lock(client, lock_key: str, owner: str) -> None:
    while True:
        await asyncio.sleep(LOCK_RENEW_SECONDS)
        renewed = await client.eval(_RENEW_LOCK, 1, lock_key, owner, LOCK_TTL_SECONDS)
        if not renewed:
            return


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
        await _redis.aclose()
        _redis = None
