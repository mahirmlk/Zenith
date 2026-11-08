"""Deterministic tests for singleton daily ingestion scheduling."""
import asyncio
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from services import daily_scheduler


class FakeRedis:
    def __init__(self):
        self.values = {}
        self.expirations = {}
        self.closed = False
        self.lose_renewal = False
        self.fail_renewal = False

    async def get(self, key):
        return self.values.get(key)

    async def set(self, key, value, *, ex=None, nx=False):
        if nx and key in self.values:
            return False
        self.values[key] = str(value)
        if ex is not None:
            self.expirations[key] = ex
        return True

    async def delete(self, key):
        self.values.pop(key, None)
        return 1

    async def aclose(self):
        self.closed = True

    async def eval(self, script, numkeys, *args):
        if script == daily_scheduler._MARK_COMPLETE:
            assert numkeys == 2
            lock_key, complete_key, owner, ttl = args
            if self.values.get(lock_key) != owner:
                return 0
            self.values[complete_key] = "1"
            self.expirations[complete_key] = int(ttl)
            return 1

        assert numkeys == 1
        key = args[0]
        if script == daily_scheduler._INCREMENT_ATTEMPT:
            self.values[key] = str(int(self.values.get(key, "0")) + 1)
            self.expirations[key] = int(args[1])
            return int(self.values[key])
        owner = args[1]
        if script == daily_scheduler._RENEW_LOCK:
            if self.fail_renewal:
                raise ConnectionError("Redis heartbeat unavailable")
            if self.lose_renewal:
                return 0
            if self.values.get(key) == owner:
                self.expirations[key] = int(args[2])
                return 1
            return 0
        if script == daily_scheduler._RELEASE_LOCK:
            if self.values.get(key) == owner:
                self.values.pop(key)
                return 1
            return 0
        raise AssertionError("unexpected Redis script")


@pytest.fixture
def due_time():
    return datetime(2026, 11, 8, 3, 0, tzinfo=timezone.utc)


@pytest.mark.asyncio
async def test_daily_ingest_runs_once_per_utc_day(due_time):
    redis = FakeRedis()
    calls = []

    async def runner():
        calls.append("run")

    assert await daily_scheduler.run_due_once(now=due_time, redis=redis, runner=runner)
    assert not await daily_scheduler.run_due_once(now=due_time, redis=redis, runner=runner)
    assert calls == ["run"]
    lock_key, attempts_key, _, complete_key = daily_scheduler._day_keys(due_time.date())
    assert redis.values[attempts_key] == "1"
    assert redis.values[complete_key] == "1"
    assert lock_key not in redis.values


@pytest.mark.asyncio
async def test_admin_manual_run_does_not_mark_scheduled_day_complete():
    redis = FakeRedis()

    async def runner():
        return {"fetched": 0}

    result = await daily_scheduler.run_with_ingestion_lease(
        runner,
        source="admin",
        redis=redis,
    )

    today = datetime.now(timezone.utc).date()
    _, _, _, complete_key = daily_scheduler._day_keys(today)
    assert result.acquired
    assert complete_key not in redis.values


@pytest.mark.asyncio
async def test_daily_ingest_waits_until_scheduled_utc_hour():
    redis = FakeRedis()
    called = False

    async def runner():
        nonlocal called
        called = True

    before_due = datetime(2026, 11, 8, 1, 59, tzinfo=timezone.utc)
    assert not await daily_scheduler.run_due_once(now=before_due, redis=redis, runner=runner)
    assert not called
    assert redis.values == {}


@pytest.mark.asyncio
async def test_daily_ingest_uses_shared_lease_to_prevent_parallel_runs(due_time):
    redis = FakeRedis()
    started = asyncio.Event()
    release = asyncio.Event()

    async def runner():
        started.set()
        await release.wait()

    first = asyncio.create_task(
        daily_scheduler.run_due_once(now=due_time, redis=redis, runner=runner)
    )
    await started.wait()
    second = await daily_scheduler.run_due_once(
        now=due_time, redis=redis, runner=runner
    )
    release.set()

    assert await first
    assert second is False


@pytest.mark.parametrize("source", ["admin", "fly-cron"])
@pytest.mark.asyncio
async def test_manual_and_cron_triggers_cannot_overlap_scheduled_run(due_time, source):
    redis = FakeRedis()
    started = asyncio.Event()
    release = asyncio.Event()
    active = 0
    maximum_active = 0

    async def scheduled_runner():
        nonlocal active, maximum_active
        active += 1
        maximum_active = max(maximum_active, active)
        started.set()
        try:
            await release.wait()
        finally:
            active -= 1

    async def competing_runner():
        nonlocal active, maximum_active
        active += 1
        maximum_active = max(maximum_active, active)
        active -= 1

    scheduled = asyncio.create_task(
        daily_scheduler.run_due_once(
            now=due_time,
            redis=redis,
            runner=scheduled_runner,
        )
    )
    await started.wait()
    competing = await daily_scheduler.run_with_ingestion_lease(
        competing_runner,
        source=source,
        redis=redis,
    )
    release.set()

    assert not competing.acquired
    assert await scheduled
    assert maximum_active == 1


@pytest.mark.parametrize("heartbeat_failure", ["lost", "error"])
@pytest.mark.asyncio
async def test_lease_loss_cancels_active_fetch(monkeypatch, heartbeat_failure):
    redis = FakeRedis()
    redis.lose_renewal = heartbeat_failure == "lost"
    redis.fail_renewal = heartbeat_failure == "error"
    monkeypatch.setattr(daily_scheduler, "LOCK_RENEW_SECONDS", 0.01)
    started = asyncio.Event()
    cancelled = asyncio.Event()

    async def blocked_fetch():
        started.set()
        try:
            await asyncio.Event().wait()
        finally:
            cancelled.set()

    with pytest.raises(daily_scheduler.IngestionLeaseLost):
        await daily_scheduler.run_with_ingestion_lease(
            blocked_fetch,
            source="test",
            redis=redis,
        )

    assert started.is_set()
    assert cancelled.is_set()
    assert daily_scheduler.GLOBAL_INGESTION_LOCK_KEY not in redis.values


@pytest.mark.asyncio
async def test_fetch_timeout_cancels_runner_and_releases_lease(monkeypatch):
    redis = FakeRedis()
    monkeypatch.setattr(daily_scheduler, "MAX_RUN_SECONDS", 0.01)
    cancelled = asyncio.Event()

    async def blocked_fetch():
        try:
            await asyncio.Event().wait()
        finally:
            cancelled.set()

    with pytest.raises(TimeoutError):
        await daily_scheduler.run_with_ingestion_lease(
            blocked_fetch,
            source="timeout-test",
            redis=redis,
        )

    assert cancelled.is_set()
    assert daily_scheduler.GLOBAL_INGESTION_LOCK_KEY not in redis.values


@pytest.mark.asyncio
async def test_failed_ingestion_retries_with_backoff_and_stops_at_limit(due_time):
    redis = FakeRedis()
    calls = 0

    async def runner():
        nonlocal calls
        calls += 1
        raise RuntimeError("provider unavailable")

    assert await daily_scheduler.run_due_once(now=due_time, redis=redis, runner=runner)
    assert calls == 1
    assert not await daily_scheduler.run_due_once(now=due_time, redis=redis, runner=runner)

    _, _, retry_key, _ = daily_scheduler._day_keys(due_time.date())
    retry_at = datetime.fromtimestamp(float(redis.values[retry_key]), tz=timezone.utc)
    assert await daily_scheduler.run_due_once(now=retry_at, redis=redis, runner=runner)
    third_attempt = datetime.fromtimestamp(float(redis.values[retry_key]), tz=timezone.utc)
    assert await daily_scheduler.run_due_once(now=third_attempt, redis=redis, runner=runner)
    assert calls == daily_scheduler.MAX_ATTEMPTS
    assert not await daily_scheduler.run_due_once(
        now=third_attempt + timedelta(seconds=3600),
        redis=redis,
        runner=runner,
    )


def test_scheduler_does_not_start_without_shared_redis(monkeypatch):
    monkeypatch.setattr(
        "config.get_settings",
        lambda: SimpleNamespace(
            redis_url="",
            supabase_url="https://example.supabase.co",
            supabase_service_role_key="service-role-key",
        ),
    )
    assert daily_scheduler.start_daily_scheduler() is None


def test_scheduler_does_not_start_without_supabase(monkeypatch):
    monkeypatch.setattr(
        "config.get_settings",
        lambda: SimpleNamespace(
            redis_url="redis://localhost:6379",
            supabase_url="",
            supabase_service_role_key="",
        ),
    )
    assert daily_scheduler.start_daily_scheduler() is None


@pytest.mark.asyncio
async def test_scheduler_shutdown_cancels_polling_task_and_closes_redis():
    redis = FakeRedis()
    started = asyncio.Event()

    async def poller():
        started.set()
        await asyncio.Event().wait()

    task = asyncio.create_task(poller())
    daily_scheduler._scheduler_task = task
    daily_scheduler._redis = redis
    await started.wait()

    await daily_scheduler.stop_daily_scheduler()

    assert task.cancelled()
    assert redis.closed
    assert daily_scheduler._scheduler_task is None
    assert daily_scheduler._redis is None


@pytest.mark.asyncio
async def test_fly_cron_entrypoint_uses_shared_ingestion_lease(monkeypatch):
    from scripts import daily_fetch

    calls = []

    async def fake_leased_run(source):
        calls.append(source)
        return daily_scheduler.LeaseResult(
            acquired=True,
            result={"fetched": 1, "inserted": 1, "summarised": 1},
        )

    monkeypatch.setattr(daily_fetch, "run_daily_fetch_with_lease", fake_leased_run)

    await daily_fetch.main()

    assert calls == ["fly-cron"]
