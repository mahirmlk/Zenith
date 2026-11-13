"""Failure-injection coverage for durable account deletion jobs."""
from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from services import account_deletion


class FakeStore:
    def __init__(self, active: set[str] | None = None) -> None:
        self.active = active or set()
        self.updated: list[tuple[str, str]] = []
        self.deleted: list[str] = []

    async def update(self, run_id: str, *, status: str) -> None:
        self.updated.append((run_id, status))

    async def has_active_run(self, run_id: str) -> bool:
        return run_id in self.active

    async def delete_run(self, run_id: str) -> None:
        self.deleted.append(run_id)


class FakeQuery:
    def __init__(self, db: "FakeSupabase", table: str) -> None:
        self.db = db
        self.table = table
        self.action = "select"
        self.filters: dict[str, Any] = {}
        self.in_filters: dict[str, list[Any]] = {}
        self.payload: dict[str, Any] = {}

    def update(self, payload: dict[str, Any]) -> "FakeQuery":
        self.action = "update"
        self.payload = payload
        return self

    def delete(self) -> "FakeQuery":
        self.action = "delete"
        return self

    def eq(self, key: str, value: Any) -> "FakeQuery":
        self.filters[key] = value
        return self

    def in_(self, key: str, values: list[Any]) -> "FakeQuery":
        self.in_filters[key] = list(values)
        return self

    async def execute(self) -> SimpleNamespace:
        self.db.operations.append((self.table, self.action, dict(self.filters), dict(self.in_filters)))
        return SimpleNamespace(data=[])


class FakeRpc:
    def __init__(self, db: "FakeSupabase", name: str, params: dict[str, Any]) -> None:
        self.db = db
        self.name = name
        self.params = params

    async def execute(self) -> SimpleNamespace:
        job = self.db.job
        if self.name == "claim_account_deletion_job":
            if job["status"] == "complete" or job["status"] == "processing":
                return SimpleNamespace(data=[])
            job["status"] = "processing"
            job["attempts"] += 1
            job["lease_owner"] = self.params["p_lease_owner"]
            return SimpleNamespace(data=[dict(job)])
        if self.name == "complete_account_deletion_step":
            if job["lease_owner"] != self.params["p_lease_owner"]:
                return SimpleNamespace(data=False)
            step = self.params["p_step"]
            if step in self.db.fail_mark_steps:
                self.db.fail_mark_steps.remove(step)
                return SimpleNamespace(data=False)
            if step not in job["completed_steps"]:
                job["completed_steps"].append(step)
            return SimpleNamespace(data=True)
        if self.name == "release_account_deletion_job":
            job["status"] = "pending"
            job["last_error_code"] = self.params["p_error_code"]
            job["lease_owner"] = None
            return SimpleNamespace(data=True)
        if self.name == "finish_account_deletion_job":
            if len(job["completed_steps"]) != 8:
                return SimpleNamespace(data=False)
            job["status"] = "complete"
            job["lease_owner"] = None
            return SimpleNamespace(data=True)
        raise AssertionError(self.name)


class FakeSupabase:
    def __init__(self, run_ids: list[str] | None = None) -> None:
        self.job = {
            "id": "job-1",
            "user_id": "u1",
            "run_ids": run_ids or [],
            "completed_steps": [],
            "status": "pending",
            "attempts": 0,
            "last_error_code": None,
        }
        self.operations: list[tuple[str, str, dict[str, Any], dict[str, list[Any]]]] = []
        self.deleted_auth_users: set[str] = set()
        self.auth = SimpleNamespace(admin=SimpleNamespace(delete_user=self.delete_user))
        self.fail_mark_steps: set[str] = set()

    def table(self, name: str) -> FakeQuery:
        return FakeQuery(self, name)

    def rpc(self, name: str, params: dict[str, Any]) -> FakeRpc:
        return FakeRpc(self, name, params)

    async def delete_user(self, user_id: str) -> None:
        if user_id in self.deleted_auth_users:
            error = RuntimeError("user not found")
            error.status = 404
            raise error
        self.deleted_auth_users.add(user_id)


async def _setup(monkeypatch, db: FakeSupabase, store: FakeStore):
    async def get_supabase():
        return db

    async def get_store():
        return store

    async def remove_runs(_run_ids: set[str]) -> None:
        return None

    async def delete_checkpoints(_run_ids: list[str]) -> None:
        return None

    monkeypatch.setattr(account_deletion, "get_supabase", get_supabase)
    monkeypatch.setattr(account_deletion, "get_run_store", get_store)
    monkeypatch.setattr(account_deletion, "remove_runs", remove_runs)
    monkeypatch.setattr("agents.orchestrator.delete_checkpoints_for_runs", delete_checkpoints)
    monkeypatch.setattr(account_deletion.mem0_client, "is_configured", lambda: False)


@pytest.mark.asyncio
async def test_deletion_resumes_after_a_transient_external_cleanup_failure(monkeypatch):
    db = FakeSupabase()
    store = FakeStore()
    await _setup(monkeypatch, db, store)
    monkeypatch.setattr(account_deletion.mem0_client, "is_configured", lambda: True)
    calls = 0

    async def fail_once(_user_id: str) -> None:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise RuntimeError("temporary provider outage")

    monkeypatch.setattr(account_deletion.mem0_client, "delete_user_memories", fail_once)

    assert await account_deletion.process_one_account_deletion()
    assert db.job["status"] == "pending"
    assert db.job["completed_steps"] == ["cancel_runs"]
    assert db.job["last_error_code"] == "memories"
    assert db.deleted_auth_users == set()

    assert await account_deletion.process_one_account_deletion()
    assert db.job["status"] == "complete"
    assert len(db.job["completed_steps"]) == 8
    assert db.deleted_auth_users == {"u1"}
    assert calls == 2


@pytest.mark.asyncio
async def test_active_worker_lease_defers_destructive_steps_until_retry(monkeypatch):
    db = FakeSupabase(["run-1"])
    store = FakeStore(active={"run-1"})
    await _setup(monkeypatch, db, store)

    await account_deletion.process_one_account_deletion()
    assert store.updated == [("run-1", "cancelled")]
    assert db.job["last_error_code"] == "active_run_lease"
    assert db.job["completed_steps"] == ["cancel_runs"]
    assert not any(action == "delete" for _, action, _, _ in db.operations)

    store.active.clear()
    await account_deletion.process_one_account_deletion()
    assert db.job["status"] == "complete"
    assert store.deleted == ["run-1"]


@pytest.mark.asyncio
async def test_worker_treats_auth_deletion_404_as_success_after_restart(monkeypatch):
    db = FakeSupabase()
    store = FakeStore()
    await _setup(monkeypatch, db, store)
    original_mark = account_deletion._mark_step
    failed_once = False

    async def fail_after_auth_delete(supabase, job_id, step):
        nonlocal failed_once
        if step == "auth_user" and not failed_once:
            failed_once = True
            raise RuntimeError("worker stopped after external Auth deletion")
        await original_mark(supabase, job_id, step)

    monkeypatch.setattr(account_deletion, "_mark_step", fail_after_auth_delete)
    await account_deletion.process_one_account_deletion()
    assert db.deleted_auth_users == {"u1"}
    assert db.job["status"] == "pending"

    monkeypatch.setattr(account_deletion, "_mark_step", original_mark)
    await account_deletion.process_one_account_deletion()
    assert db.job["status"] == "complete"
    assert db.deleted_auth_users == {"u1"}
