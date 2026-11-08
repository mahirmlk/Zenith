import pytest
import asyncio
from services.run_store import RedisRunStore, RunStore


@pytest.mark.asyncio
async def test_run_store_create():
    store = RunStore(ttl_seconds=60)
    state = await store.create("run-1", "test query", model="gpt-4o")
    assert state.run_id == "run-1"
    assert state.query == "test query"
    assert state.model == "gpt-4o"
    assert state.status == "pending"


@pytest.mark.asyncio
async def test_run_store_get():
    store = RunStore(ttl_seconds=60)
    await store.create("run-1", "test query")
    state = await store.get("run-1")
    assert state is not None
    assert state.run_id == "run-1"


@pytest.mark.asyncio
async def test_run_store_get_expired():
    store = RunStore(ttl_seconds=0)
    await store.create("run-1", "test query")
    await asyncio.sleep(0.1)
    state = await store.get("run-1")
    assert state is None


@pytest.mark.asyncio
async def test_run_store_update():
    store = RunStore(ttl_seconds=60)
    await store.create("run-1", "test query")
    await store.update("run-1", status="complete", results=[{"id": "p1"}])
    state = await store.get("run-1")
    assert state.status == "complete"
    assert len(state.results) == 1


@pytest.mark.asyncio
async def test_run_store_cleanup():
    store = RunStore(ttl_seconds=0)
    await store.create("run-1", "query 1")
    await store.create("run-2", "query 2")
    await asyncio.sleep(0.1)
    await store.cleanup()
    assert await store.get("run-1") is None
    assert await store.get("run-2") is None


@pytest.mark.asyncio
async def test_run_store_get_nonexistent():
    store = RunStore(ttl_seconds=60)
    state = await store.get("nonexistent")
    assert state is None


@pytest.mark.asyncio
async def test_run_store_cancelled_run_cannot_be_completed():
    store = RunStore(ttl_seconds=60)
    await store.create("run-cancel", "query")
    assert await store.try_start("run-cancel") is True

    await store.update("run-cancel", status="cancelled")
    await store.update("run-cancel", status="complete", results=[{"id": "paper"}])

    state = await store.get("run-cancel")
    assert state.status == "cancelled"
    assert state.results == []


@pytest.mark.asyncio
async def test_run_store_running_lease_is_released_for_recovery():
    store = RunStore(ttl_seconds=60)
    await store.create("run-recover", "query")
    assert await store.try_start("run-recover") is True
    assert await store.try_start("run-recover") is False

    await store.release("run-recover")
    assert await store.try_start("run-recover") is True


@pytest.mark.asyncio
async def test_run_store_idempotency_replays_same_request():
    store = RunStore(ttl_seconds=60)
    first = await store.create(
        "run-first", "same query", model="model-a", user_id="user-1", idempotency_key="key-1"
    )
    replay = await store.create(
        "run-second", "same query", model="model-a", user_id="user-1", idempotency_key="key-1"
    )

    assert replay.run_id == first.run_id


@pytest.mark.asyncio
async def test_run_store_idempotency_rejects_key_reuse_for_different_request():
    store = RunStore(ttl_seconds=60)
    await store.create(
        "run-first", "original query", model="model-a", user_id="user-1", idempotency_key="key-1"
    )

    with pytest.raises(ValueError, match="different request"):
        await store.create(
            "run-second", "different query", model="model-a", user_id="user-1", idempotency_key="key-1"
        )


class _FakeRedis:
    def __init__(self):
        self.values = {}

    async def eval(self, _script, _key_count, index_key, run_id, serialized, ttl):
        current = self.values.get(index_key)
        if current and current in self.values:
            return current
        self.values[run_id] = serialized
        self.values[index_key] = run_id
        return run_id

    async def get(self, key):
        return self.values.get(key)


@pytest.mark.asyncio
async def test_redis_run_store_idempotency_uses_atomic_index_and_replays():
    store = RedisRunStore()
    store._redis = _FakeRedis()

    async def connected():
        return None

    store._ensure_connected = connected
    first = await store.create(
        "redis-first", "same query", model="model-a", user_id="user-1", idempotency_key="key-1"
    )
    replay = await store.create(
        "redis-second", "same query", model="model-a", user_id="user-1", idempotency_key="key-1"
    )

    assert replay.run_id == first.run_id == "redis-first"
    with pytest.raises(ValueError, match="different request"):
        await store.create(
            "redis-third", "different query", model="model-a", user_id="user-1", idempotency_key="key-1"
        )
