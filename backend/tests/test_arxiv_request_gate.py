"""Concurrency and lease-safety tests for the distributed arXiv gate."""
import asyncio
import time

import pytest

from config import Settings
from services import arxiv_request_gate as gate


class FakeRedis:
    def __init__(self, *, fail_renew_after: int | None = None) -> None:
        self.lock_token: str | None = None
        self.lock_expires = 0.0
        self.last_start = 0.0
        self.renew_count = 0
        self.releases: list[str] = []
        self.fail_renew_after = fail_renew_after

    async def set(self, _key, token, *, nx, px):
        now = time.monotonic()
        if self.lock_token and self.lock_expires <= now:
            self.lock_token = None
        if nx and self.lock_token:
            return False
        self.lock_token = token
        self.lock_expires = now + px / 1000
        return True

    async def eval(self, script, _key_count, key, *args):
        if script == gate._RENEW_LOCK:
            token, ttl_ms = args
            self.renew_count += 1
            if self.fail_renew_after is not None and self.renew_count > self.fail_renew_after:
                return 0
            if self.lock_token != token:
                return 0
            self.lock_expires = time.monotonic() + int(ttl_ms) / 1000
            return 1
        if script == gate._RELEASE_LOCK:
            (token,) = args
            self.releases.append(token)
            if self.lock_token == token:
                self.lock_token = None
                return 1
            return 0
        if script == gate._MARK_START:
            (interval_ms,) = args
            now = time.monotonic()
            delay_ms = max(0, int(interval_ms) - int((now - self.last_start) * 1000))
            if delay_ms == 0:
                self.last_start = now
            return delay_ms
        raise AssertionError(f"Unexpected Redis script: {script}")


def configure_production_gate(monkeypatch, redis: FakeRedis) -> None:
    monkeypatch.setattr(
        gate,
        "get_settings",
        lambda: Settings(app_env="production", redis_url="redis://test"),
    )
    async def client(_url):
        return redis
    monkeypatch.setattr(gate, "_get_redis_client", client)
    monkeypatch.setattr(gate, "MIN_INTERVAL_MS", 1)
    monkeypatch.setattr(gate, "LOCK_TTL_MS", 30)
    monkeypatch.setattr(gate, "LOCK_HEARTBEAT_SECONDS", 0.01)
    monkeypatch.setattr(gate, "LOCK_HEARTBEAT_TIMEOUT_SECONDS", 0.02)


@pytest.mark.asyncio
async def test_redis_gate_serializes_long_sessions_and_renews_short_lease(monkeypatch):
    redis = FakeRedis()
    configure_production_gate(monkeypatch, redis)
    active = 0
    maximum_active = 0

    async def run_session(duration):
        nonlocal active, maximum_active
        async with gate.arxiv_api_session() as session:
            await session.before_request()
            active += 1
            maximum_active = max(maximum_active, active)
            await asyncio.sleep(duration)
            active -= 1

    await asyncio.gather(run_session(0.08), run_session(0.03))
    assert maximum_active == 1
    assert redis.renew_count >= 4  # Request-start renewals plus heartbeat renewals.
    assert redis.lock_token is None
    assert len(redis.releases) == 2


@pytest.mark.asyncio
async def test_gate_body_error_propagates_and_releases_only_its_owner_token(monkeypatch):
    redis = FakeRedis()
    configure_production_gate(monkeypatch, redis)
    with pytest.raises(RuntimeError, match="body error"):
        async with gate.arxiv_api_session() as session:
            await session.before_request()
            raise RuntimeError("body error")
    assert redis.lock_token is None
    assert len(redis.releases) == 1

    async with gate.arxiv_api_session():
        redis.lock_token = "other-owner"
    assert redis.lock_token == "other-owner"


@pytest.mark.asyncio
async def test_heartbeat_loss_cancels_query_before_lease_expiry(monkeypatch):
    redis = FakeRedis(fail_renew_after=1)
    configure_production_gate(monkeypatch, redis)
    with pytest.raises(asyncio.CancelledError):
        async with gate.arxiv_api_session() as session:
            await session.before_request()
            await asyncio.sleep(0.2)
    assert redis.lock_token is None
    assert len(redis.releases) == 1


@pytest.mark.asyncio
async def test_local_gate_fallback_does_not_swallow_body_exception(monkeypatch):
    monkeypatch.setattr(
        gate,
        "get_settings",
        lambda: Settings(app_env="development", redis_url=""),
    )
    gate.reset_local_gate_for_tests()
    with pytest.raises(LookupError, match="preserve body error"):
        async with gate.arxiv_api_session():
            raise LookupError("preserve body error")
