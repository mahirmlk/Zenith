"""Shared connection lock and request spacing for arXiv API traffic."""
from __future__ import annotations

import asyncio
import time
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any, cast

from config import get_settings

MIN_INTERVAL_MS = 3_000
LOCK_TTL_MS = 90_000  # Each HTTP request is bounded to 15 seconds.
LOCK_WAIT_SECONDS = 30.0
LOCK_HEARTBEAT_SECONDS = 20.0
LOCK_HEARTBEAT_TIMEOUT_SECONDS = 3.0
_LOCK_KEY = "zenith:arxiv:api-lock:v1"
_LAST_START_KEY = "zenith:arxiv:last-start-ms:v1"
_MARK_START = """
local time_parts = redis.call('TIME')
local now_ms = (tonumber(time_parts[1]) * 1000) + math.floor(tonumber(time_parts[2]) / 1000)
local last_ms = tonumber(redis.call('GET', KEYS[1]) or '0')
local delay_ms = math.max(0, tonumber(ARGV[1]) - (now_ms - last_ms))
if delay_ms == 0 then redis.call('SET', KEYS[1], now_ms, 'PX', 60000) end
return delay_ms
"""
_RELEASE_LOCK = "if redis.call('GET', KEYS[1]) == ARGV[1] then return redis.call('DEL', KEYS[1]) else return 0 end"
_RENEW_LOCK = "if redis.call('GET', KEYS[1]) == ARGV[1] then return redis.call('PEXPIRE', KEYS[1], ARGV[2]) else return 0 end"

_local_lock = asyncio.Lock()
_local_last_start = 0.0
_redis_client: Any = None
_redis_url: str | None = None


class ArxivGateUnavailable(RuntimeError):
    """The shared production throttle could not safely serialize an API call."""


class ArxivApiSession:
    """Owner of the global lock for one query, including all its pages/retries."""

    def __init__(self, client: Any = None, token: str | None = None) -> None:
        self.client = client
        self.token = token

    async def before_request(self) -> None:
        """Space this query's next HTTP request from all previous arXiv calls."""
        global _local_last_start
        if self.client is None:
            remaining = MIN_INTERVAL_MS / 1000 - (time.monotonic() - _local_last_start)
            if _local_last_start and remaining > 0:
                await asyncio.sleep(remaining)
            _local_last_start = time.monotonic()
            return

        while True:
            try:
                renewed = await self.client.eval(
                    _RENEW_LOCK, 1, _LOCK_KEY, self.token, LOCK_TTL_MS
                )
                if not renewed:
                    raise ArxivGateUnavailable("Shared arXiv request lock expired")
                delay_ms = max(
                    0,
                    int(await self.client.eval(_MARK_START, 1, _LAST_START_KEY, MIN_INTERVAL_MS)),
                )
            except ArxivGateUnavailable:
                raise
            except Exception as exc:
                raise ArxivGateUnavailable("Shared arXiv request gate is unavailable") from exc
            if delay_ms == 0:
                return
            await asyncio.sleep(delay_ms / 1000)


async def _get_redis_client(redis_url: str) -> Any:
    global _redis_client, _redis_url
    if _redis_client is None or _redis_url != redis_url:
        import redis.asyncio as redis_mod

        _redis_from_url = cast(Any, redis_mod.from_url)
        _redis_client = _redis_from_url(redis_url, decode_responses=True)
        _redis_url = redis_url
    return _redis_client


@asynccontextmanager
async def arxiv_api_session() -> AsyncIterator[ArxivApiSession]:
    """Hold a shared owner-token lock across the complete API query."""
    settings = get_settings()
    if not settings.redis_url:
        if settings.app_env == "production":
            raise ArxivGateUnavailable("REDIS_URL is required for the shared arXiv request gate")
        async with _local_lock:
            yield ArxivApiSession()
        return

    try:
        client = await _get_redis_client(settings.redis_url)
        token = uuid.uuid4().hex
        deadline = time.monotonic() + LOCK_WAIT_SECONDS
        acquired = False
        while time.monotonic() < deadline:
            acquired = bool(await client.set(_LOCK_KEY, token, nx=True, px=LOCK_TTL_MS))
            if acquired:
                break
            await asyncio.sleep(0.1)
        if not acquired:
            raise ArxivGateUnavailable("Timed out waiting for the shared arXiv request gate")
    except Exception as exc:
        if settings.app_env == "production":
            if isinstance(exc, ArxivGateUnavailable):
                raise
            raise ArxivGateUnavailable("Shared arXiv request gate is unavailable") from exc
        # Development fallback is process-local and must not mask body errors.
        async with _local_lock:
            yield ArxivApiSession()
        return

    try:
        owner_task = asyncio.current_task()

        async def heartbeat() -> None:
            while True:
                await asyncio.sleep(LOCK_HEARTBEAT_SECONDS)
                try:
                    renewed = await asyncio.wait_for(
                        client.eval(_RENEW_LOCK, 1, _LOCK_KEY, token, LOCK_TTL_MS),
                        timeout=LOCK_HEARTBEAT_TIMEOUT_SECONDS,
                    )
                    if not renewed:
                        raise ArxivGateUnavailable("Shared arXiv request lock expired")
                except asyncio.CancelledError:
                    raise
                except Exception:
                    # Cancel the query body before the lease can expire and let
                    # another replica start an overlapping connection.
                    if owner_task is not None:
                        owner_task.cancel()
                    return

        heartbeat_task = asyncio.create_task(heartbeat())
        try:
            yield ArxivApiSession(client, token)
        finally:
            heartbeat_task.cancel()
            await asyncio.gather(heartbeat_task, return_exceptions=True)
    finally:
        try:
            await asyncio.shield(client.eval(_RELEASE_LOCK, 1, _LOCK_KEY, token))
        except Exception as exc:
            if settings.app_env == "production":
                raise ArxivGateUnavailable("Could not release shared arXiv request lock") from exc


@asynccontextmanager
async def arxiv_api_request() -> AsyncIterator[None]:
    """Gate a single arXiv API request when a full query context is unnecessary."""
    async with arxiv_api_session() as session:
        await session.before_request()
        yield


def reset_local_gate_for_tests() -> None:
    """Reset process-local state for deterministic unit tests."""
    global _local_last_start
    _local_last_start = 0.0
