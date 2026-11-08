"""Shared per-user daily search budget (update.md §5.4).

Production requires Redis so counters are consistent across API replicas.
Development can use the in-process counter when Redis is not configured.
"""
import asyncio
import hashlib
import logging
from collections import defaultdict
from datetime import datetime, timedelta, timezone

from config import get_settings

logger = logging.getLogger(__name__)
_counts: dict[tuple[str, str], int] = defaultdict(int)
_lock = asyncio.Lock()
_redis = None
_redis_url: str | None = None


class BudgetUnavailableError(RuntimeError):
    """The shared budget store is required but unavailable."""


def _utc_day_and_ttl(now: datetime | None = None) -> tuple[str, int]:
    current = now or datetime.now(timezone.utc)
    current = current.astimezone(timezone.utc)
    next_midnight = datetime.combine(
        current.date() + timedelta(days=1), datetime.min.time(), tzinfo=timezone.utc
    )
    ttl = max(1, int((next_midnight - current).total_seconds()))
    return current.date().isoformat(), ttl


async def _get_redis_client(redis_url: str):
    global _redis, _redis_url
    if _redis is None or _redis_url != redis_url:
        import redis.asyncio as redis_mod

        _redis = redis_mod.from_url(redis_url, decode_responses=True)
        _redis_url = redis_url
    return _redis


async def _consume_redis(user_id: str, daily_limit: int, redis_url: str) -> bool:
    client = await _get_redis_client(redis_url)
    day, ttl = _utc_day_and_ttl()
    user_digest = hashlib.sha256(user_id.encode("utf-8")).hexdigest()
    key = f"zenith:budget:search:{user_digest}:{day}"
    # The entire check/increment/expiry operation runs atomically in Redis.
    script = """
    local current = tonumber(redis.call('GET', KEYS[1]) or '0')
    local limit = tonumber(ARGV[1])
    if current >= limit then return 0 end
    local next_count = redis.call('INCR', KEYS[1])
    if next_count == 1 then redis.call('EXPIRE', KEYS[1], ARGV[2]) end
    return 1
    """
    return bool(await client.eval(script, 1, key, daily_limit, ttl))


async def _consume_memory(user_id: str, daily_limit: int) -> bool:
    day, _ = _utc_day_and_ttl()
    async with _lock:
        # Keep the development-only map bounded across UTC day changes.
        expired = [key for key in _counts if key[1] != day]
        for key in expired:
            del _counts[key]
        key = (user_id, day)
        if _counts[key] >= daily_limit:
            return False
        _counts[key] += 1
        return True


async def consume(user_id: str, daily_limit: int) -> bool:
    """Consume one slot if available; raises in production if Redis is unavailable."""
    settings = get_settings()
    if not user_id:
        raise ValueError("user_id is required for search budgeting")
    if daily_limit <= 0:
        return False

    if settings.redis_url:
        try:
            return await _consume_redis(user_id, daily_limit, settings.redis_url)
        except Exception as exc:
            if settings.app_env.lower() == "production":
                raise BudgetUnavailableError("Shared search budget store unavailable") from exc
            logger.warning("Redis search budget unavailable; using process-local development counter")
    elif settings.app_env.lower() == "production":
        raise BudgetUnavailableError("Redis is required for production search budgets")

    return await _consume_memory(user_id, daily_limit)


async def refund(user_id: str) -> None:
    """Refund a reservation when a concurrent idempotent create replays."""
    settings = get_settings()
    day, _ = _utc_day_and_ttl()
    user_digest = hashlib.sha256(user_id.encode("utf-8")).hexdigest()
    key = f"zenith:budget:search:{user_digest}:{day}"
    if settings.redis_url:
        client = await _get_redis_client(settings.redis_url)
        await client.eval(
            "local current = tonumber(redis.call('GET', KEYS[1]) or '0') "
            "if current <= 0 then return 0 end "
            "return redis.call('DECR', KEYS[1])",
            1,
            key,
        )
        return
    if settings.app_env.lower() == "production":
        raise BudgetUnavailableError("Redis is required for production search budgets")
    async with _lock:
        if _counts.get((user_id, day), 0) > 0:
            _counts[(user_id, day)] -= 1


def reset_for_tests() -> None:
    """Clear process-local state and the cached client reference for tests."""
    global _redis, _redis_url
    _counts.clear()
    _redis = None
    _redis_url = None
