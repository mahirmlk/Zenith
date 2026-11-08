import pytest
import asyncio
from services.run_store import RunStore


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
