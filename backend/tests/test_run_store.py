import pytest
import asyncio
import services.run_store as run_store_module
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import uuid4

from services.run_store import (
    AccountDeletionInProgressError,
    PostgresRunStore,
    RedisRunStore,
    RunStore,
)


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


class _FakePostgres:
    def __init__(self):
        self.runs = {}
        self.events = {}
        self.rpc_calls = []
        self.reject_run_admission = False

    def rpc(self, name, params):
        self.rpc_calls.append((name, params))
        return _FakePostgresRPC(self, name, params)

    def table(self, name):
        return _FakePostgresQuery(self, name)


class _FakePostgresRPC:
    def __init__(self, database, name, params):
        self.database = database
        self.name = name
        self.params = params

    async def execute(self):
        p = self.params
        if self.name == "create_research_run_atomic":
            if self.database.reject_run_admission:
                raise RuntimeError("account_deletion_in_progress")
            existing = next(
                (
                    run for run in self.database.runs.values()
                    if p["p_idempotency_key"]
                    and run["user_id"] == p["p_user_id"]
                    and run["idempotency_key"] == p["p_idempotency_key"]
                ),
                None,
            )
            if existing:
                return SimpleNamespace(data=[existing])
            row = {
                "id": p["p_run_id"],
                "user_id": p["p_user_id"],
                "query": p["p_query"],
                "model": p["p_model"],
                "results": [],
                "idempotency_key": p["p_idempotency_key"],
                "status": "pending",
                "started": False,
                "created_at": datetime.now(timezone.utc).isoformat(),
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
            self.database.runs[row["id"]] = row
            return SimpleNamespace(data=[row])
        if self.name == "update_research_run_atomic":
            row = self.database.runs.get(p["p_run_id"])
            if not row:
                return SimpleNamespace(data=False)
            if row["status"] in {"complete", "failed", "cancelled"} and p["p_status"] != row["status"]:
                return SimpleNamespace(data=False)
            if p["p_status"] is not None:
                row["status"] = p["p_status"]
            if p["p_results"] is not None:
                row["results"] = p["p_results"]
            row["started"] = row["started"] or p["p_started"] or row["status"] == "running"
            return SimpleNamespace(data=True)
        if self.name == "append_run_event_atomic":
            if p["p_run_id"] not in self.database.runs:
                return SimpleNamespace(data=[])
            events = self.database.events.setdefault(p["p_run_id"], [])
            row = {
                "sequence": len(events) + 1,
                "kind": p["p_kind"],
                "safe_payload": p["p_payload"],
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
            events.append(row)
            return SimpleNamespace(data=[row])
        raise AssertionError(self.name)


class _FakePostgresQuery:
    def __init__(self, database, table):
        self.database = database
        self.table_name = table
        self.filters = {}
        self.is_delete = False

    def select(self, *_fields):
        return self

    def limit(self, _count):
        return self

    def maybe_single(self):
        return self

    def eq(self, key, value):
        self.filters[key] = value
        return self

    def in_(self, key, values):
        self.filters[f"in:{key}"] = values
        return self

    def order(self, _key):
        return self

    def delete(self):
        self.is_delete = True
        return self

    def lt(self, key, value):
        self.filters[f"lt:{key}"] = value
        return self

    async def execute(self):
        if self.table_name == "research_runs":
            rows = list(self.database.runs.values())
            if self.is_delete:
                cutoff = datetime.fromisoformat(self.filters["lt:created_at"])
                statuses = self.filters.get("in:status", [])
                stale_ids = [
                    row["id"] for row in rows
                    if datetime.fromisoformat(row["created_at"]) < cutoff
                    and row.get("status") in statuses
                ]
                for run_id in stale_ids:
                    del self.database.runs[run_id]
                return SimpleNamespace(data=[])
            for key, value in self.filters.items():
                rows = [row for row in rows if row.get(key) == value]
            return SimpleNamespace(data=rows[:1] if self.filters else [])
        if self.table_name == "run_events":
            rows = self.database.events.get(self.filters.get("run_id"), [])
            return SimpleNamespace(data=sorted(rows, key=lambda row: row["sequence"]))
        raise AssertionError(self.table_name)


class _FakeRedisLease:
    def __init__(self):
        self.values = {}

    async def set(self, key, value, nx=False, ex=None):
        if nx and key in self.values:
            return None
        self.values[key] = value
        return True

    async def eval(self, script, _key_count, key, token, *_args):
        if self.values.get(key) != token:
            return 0
        if "del" in script:
            del self.values[key]
            return 1
        return 1


@pytest.mark.asyncio
async def test_postgres_run_store_is_canonical_for_metadata_events_and_idempotency():
    database = _FakePostgres()
    store = PostgresRunStore(database, redis_url="redis://fake")
    run_id = str(uuid4())
    await store.verify_schema()

    created = await store.create(
        run_id,
        "grounded query",
        model="model-a",
        user_id=str(uuid4()),
        idempotency_key="secret-client-key",
    )
    replay = await store.find_idempotent(created.user_id, "secret-client-key")
    loaded = await store.get(run_id)

    assert replay is not None and replay.run_id == run_id
    assert loaded is not None and loaded.query == "grounded query"
    assert database.runs[run_id]["idempotency_key"] != "secret-client-key"
    create_call = next(call for call in database.rpc_calls if call[0] == "create_research_run_atomic")
    assert create_call[1]["p_ttl_seconds"] == store._ttl
    assert isinstance(create_call[1]["p_ttl_seconds"], int)
    with pytest.raises(ValueError, match="different request"):
        await store.create(
            str(uuid4()),
            "different query",
            model="model-a",
            user_id=created.user_id,
            idempotency_key="secret-client-key",
        )


@pytest.mark.asyncio
async def test_postgres_run_store_maps_deletion_admission_rejection():
    database = _FakePostgres()
    database.reject_run_admission = True
    store = PostgresRunStore(database, redis_url="redis://fake")

    with pytest.raises(AccountDeletionInProgressError, match="deletion is in progress"):
        await store.create(str(uuid4()), "query", user_id=str(uuid4()))


@pytest.mark.asyncio
async def test_postgres_run_store_preserves_terminal_state_and_ordered_events():
    database = _FakePostgres()
    store = PostgresRunStore(database, redis_url="redis://fake")
    run_id = str(uuid4())
    await store.create(run_id, "query", user_id=str(uuid4()))

    await store.add_event(run_id, "agent_step", {"agent": "research"})
    await store.add_event(run_id, "result", {"count": 1})
    await store.update(run_id, status="cancelled")
    await store.update(run_id, status="complete", results=[{"id": "paper-1"}])

    state = await store.get(run_id)
    events = await store.get_events(run_id)
    assert state is not None and state.status == "cancelled" and state.results == []
    assert [event["sequence"] for event in events] == [1, 2]
    assert [event["event"] for event in events] == ["agent_step", "result"]


@pytest.mark.asyncio
async def test_postgres_run_cleanup_retains_active_runs_and_expires_only_terminal_runs():
    database = _FakePostgres()
    store = PostgresRunStore(database, redis_url="redis://fake", ttl_seconds=60)
    now = datetime.now(timezone.utc)
    database.runs = {
        "active": {
            "id": "active",
            "status": "running",
            "created_at": (now - timedelta(hours=2)).isoformat(),
        },
        "finished": {
            "id": "finished",
            "status": "complete",
            "created_at": (now - timedelta(hours=2)).isoformat(),
        },
        "fresh": {
            "id": "fresh",
            "status": "failed",
            "created_at": now.isoformat(),
        },
    }

    await store.cleanup()

    assert set(database.runs) == {"active", "fresh"}


@pytest.mark.asyncio
async def test_postgres_run_store_uses_redis_lease_for_worker_recovery():
    database = _FakePostgres()
    store = PostgresRunStore(database, redis_url="redis://fake")
    store._redis = _FakeRedisLease()
    run_id = str(uuid4())
    await store.create(run_id, "query", user_id=str(uuid4()))

    assert await store.try_start(run_id) is True
    assert await store.try_start(run_id) is False
    assert await store.heartbeat(run_id) is True
    await store.release(run_id)
    assert await store.try_start(run_id) is True


@pytest.mark.asyncio
async def test_run_store_proxy_delegates_worker_heartbeat_and_release(monkeypatch):
    class FakeStore:
        called = []

        async def heartbeat(self, run_id):
            self.called.append(("heartbeat", run_id))
            return True

        async def release(self, run_id):
            self.called.append(("release", run_id))

    fake_store = FakeStore()
    monkeypatch.setattr(run_store_module, "_instance", fake_store)

    assert await run_store_module.run_store.heartbeat("run-1") is True
    await run_store_module.run_store.release("run-1")

    assert fake_store.called == [("heartbeat", "run-1"), ("release", "run-1")]


@pytest.mark.asyncio
async def test_production_run_store_fails_closed_without_redis(monkeypatch):
    monkeypatch.setattr(
        "config.get_settings",
        lambda: SimpleNamespace(app_env="production", redis_url=""),
    )

    with pytest.raises(RuntimeError, match="REDIS_URL is required"):
        await run_store_module._create_run_store()


@pytest.mark.asyncio
async def test_production_run_store_does_not_fall_back_when_supabase_is_missing(monkeypatch):
    monkeypatch.setattr(
        "config.get_settings",
        lambda: SimpleNamespace(app_env="production", redis_url="redis://redis"),
    )

    async def unavailable_database():
        raise RuntimeError("Supabase not configured")

    monkeypatch.setattr("services.supabase_client.get_supabase", unavailable_database)
    with pytest.raises(RuntimeError, match="Supabase not configured"):
        await run_store_module._create_run_store()
