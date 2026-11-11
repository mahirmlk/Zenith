"""Offline tests for account export/deletion scope and external cleanup."""
from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest
from fastapi import HTTPException

from routers import account


class FakeSupabase:
    def __init__(self, tables: dict[str, list[dict[str, Any]]]) -> None:
        self.tables = tables
        self.operations: list[tuple[str, str, dict[str, Any], dict[str, list[Any]]]] = []
        self.deleted_auth_users: list[str] = []
        self.auth = SimpleNamespace(admin=SimpleNamespace(delete_user=self.delete_user))

    async def delete_user(self, user_id: str) -> None:
        self.deleted_auth_users.append(user_id)
        self.operations.append(("auth.users", "delete", {}, {}))

    def table(self, name: str) -> "FakeQuery":
        return FakeQuery(self, name)


class FakeQuery:
    def __init__(self, db: FakeSupabase, table: str) -> None:
        self.db = db
        self.name = table
        self.action = "select"
        self.filters: dict[str, Any] = {}
        self.sets: dict[str, Any] = {}
        self.in_filters: dict[str, list[Any]] = {}
        self.start = 0
        self.end: int | None = None

    def select(self, *_args: Any) -> "FakeQuery":
        self.action = "select"
        return self

    def eq(self, key: str, value: Any) -> "FakeQuery":
        self.filters[key] = value
        return self

    def in_(self, key: str, values: list[Any]) -> "FakeQuery":
        self.in_filters[key] = list(values)
        return self

    def range(self, start: int, end: int) -> "FakeQuery":
        self.start = start
        self.end = end
        return self

    def delete(self) -> "FakeQuery":
        self.action = "delete"
        return self

    def update(self, values: dict[str, Any]) -> "FakeQuery":
        self.action = "update"
        self.sets = values
        return self

    async def execute(self) -> SimpleNamespace:
        self.db.operations.append((self.name, self.action, dict(self.filters), dict(self.in_filters)))
        rows = self.db.tables.get(self.name, [])
        if self.action == "select":
            selected = [
                row for row in rows
                if all(row.get(key) == value for key, value in self.filters.items())
                and all(row.get(key) in values for key, values in self.in_filters.items())
            ]
            if self.end is not None:
                selected = selected[self.start:self.end + 1]
            return SimpleNamespace(data=selected)
        if self.action == "delete":
            self.db.tables[self.name] = [
                row for row in rows
                if not (
                    all(row.get(key) == value for key, value in self.filters.items())
                    and all(row.get(key) in values for key, values in self.in_filters.items())
                )
            ]
        return SimpleNamespace(data=[])


class FakeRunStore:
    def __init__(self, active: set[str] | None = None) -> None:
        self.active = active or set()
        self.deleted: list[str] = []
        self.updated: list[tuple[str, str]] = []

    async def has_active_run(self, run_id: str) -> bool:
        return run_id in self.active

    async def update(self, run_id: str, *, status: str) -> None:
        self.updated.append((run_id, status))

    async def delete_run(self, run_id: str) -> None:
        self.deleted.append(run_id)


def _export_tables() -> dict[str, list[dict[str, Any]]]:
    return {
        "user_papers": [{"user_id": "u1", "paper_id": "p1"}, {"user_id": "u2", "paper_id": "private"}],
        "user_prefs": [{"user_id": "u1", "interests": ["ml"]}],
        "projects": [
            {"id": "owned", "owner_id": "u1"},
            {"id": "shared", "owner_id": "u2"},
            {"id": "other", "owner_id": "u3"},
        ],
        "project_members": [
            {"project_id": "shared", "user_id": "u1", "role": "viewer"},
            {"project_id": "other", "user_id": "u3", "role": "viewer"},
        ],
        "notes": [
            {"project_id": "owned", "content": "owned note"},
            {"project_id": "shared", "content": "shared note", "created_by": "u1"},
            {"project_id": "other", "content": "private note"},
        ],
        "project_sources": [
            {"project_id": "owned", "paper_id": "p1"},
            {"project_id": "shared", "paper_id": "p2", "created_by": "u1"},
            {"project_id": "other", "paper_id": "p3"},
        ],
        "watchlists": [{"user_id": "u1", "query": "ml"}],
        "notifications": [{"user_id": "u1", "title": "new paper"}],
        "research_runs": [{"id": "r1", "user_id": "u1", "query": "private query"}, {"id": "r2", "user_id": "u2"}],
        "run_events": [{"run_id": "r1", "safe_payload": {"x": 1}}, {"run_id": "r2", "safe_payload": {"secret": 1}}],
    }


@pytest.mark.asyncio
async def test_export_includes_caller_data_and_accessible_project_content(monkeypatch):
    db = FakeSupabase(_export_tables())
    monkeypatch.setattr(account.mem0_client, "is_configured", lambda: True)

    async def memories(user_id: str) -> list[dict[str, Any]]:
        assert user_id == "u1"
        return [{"memory": "prefers ML"}]

    monkeypatch.setattr(account.mem0_client, "get_user_profile", memories)

    result = await account.export_account(object(), {"user_id": "u1", "email": "u1@example.com"}, db)

    assert result["email"] == "u1@example.com"
    assert result["saved_papers"] == [{"user_id": "u1", "paper_id": "p1"}]
    assert {row["id"] for row in result["projects"]} == {"owned", "shared"}
    assert {row["content"] for row in result["project_notes"]} == {"owned note", "shared note"}
    assert {row["paper_id"] for row in result["project_sources"]} == {"p1", "p2"}
    assert result["research_runs"] == [{"id": "r1", "user_id": "u1", "query": "private query"}]
    assert result["run_events"] == [{"run_id": "r1", "safe_payload": {"x": 1}}]
    assert result["memories"] == [{"memory": "prefers ML"}]
    assert result["memory_export_status"] == "exported"


@pytest.mark.asyncio
async def test_export_collection_paginates_past_postgrest_default_page():
    expected = [{"id": f"r{index}", "user_id": "u1"} for index in range(501)]
    db = FakeSupabase({"research_runs": expected})

    result = await account._fetch_all(
        lambda: db.table("research_runs").select("*").eq("user_id", "u1"),
        page_size=500,
    )

    assert len(result) == 501
    assert result[0] == expected[0]
    assert result[-1] == expected[-1]


@pytest.mark.asyncio
async def test_delete_removes_only_authenticated_user_and_auth_identity(monkeypatch):
    db = FakeSupabase(_export_tables())
    run_store = FakeRunStore()
    removed_from_queue: list[set[str]] = []
    checkpoint_deletions: list[list[str]] = []
    monkeypatch.setattr(account, "get_run_store", lambda: _async_value(run_store))
    monkeypatch.setattr(account, "remove_runs", lambda ids: _async_value(removed_from_queue.append(ids)))
    monkeypatch.setattr(account.mem0_client, "is_configured", lambda: False)

    async def delete_checkpoints(run_ids: list[str]) -> None:
        checkpoint_deletions.append(run_ids)

    monkeypatch.setattr("agents.orchestrator.delete_checkpoints_for_runs", delete_checkpoints)

    result = await account.delete_account(object(), {"user_id": "u1"}, db)

    assert result == {"status": "ok"}
    assert db.deleted_auth_users == ["u1"]
    assert removed_from_queue == [{"r1"}]
    assert checkpoint_deletions == [["r1"]]
    assert run_store.deleted == ["r1"]
    assert all(row.get("user_id") != "u1" for row in db.tables["user_papers"])
    assert any(name == "projects" and action == "delete" and filters == {"owner_id": "u1"} for name, action, filters, _ in db.operations)
    assert not any(name == "projects" and action == "delete" and filters == {"owner_id": "u2"} for name, action, filters, _ in db.operations)


@pytest.mark.asyncio
async def test_delete_chunks_run_event_cleanup_for_large_histories(monkeypatch):
    run_rows = [{"id": f"r{index}", "user_id": "u1"} for index in range(401)]
    event_rows = [{"run_id": row["id"]} for row in run_rows]
    db = FakeSupabase({"research_runs": run_rows, "run_events": event_rows})
    run_store = FakeRunStore()
    monkeypatch.setattr(account, "get_run_store", lambda: _async_value(run_store))
    monkeypatch.setattr(account, "remove_runs", lambda ids: _async_value(None))
    monkeypatch.setattr(account.mem0_client, "is_configured", lambda: False)

    async def delete_checkpoints(_run_ids: list[str]) -> None:
        return None

    monkeypatch.setattr("agents.orchestrator.delete_checkpoints_for_runs", delete_checkpoints)

    result = await account.delete_account(object(), {"user_id": "u1"}, db)

    event_deletes = [
        in_filters["run_id"]
        for name, action, _filters, in_filters in db.operations
        if name == "run_events" and action == "delete"
    ]
    assert result == {"status": "ok"}
    assert [len(chunk) for chunk in event_deletes] == [200, 200, 1]
    assert db.tables["run_events"] == []


@pytest.mark.asyncio
async def test_delete_cancels_but_does_not_erase_while_worker_lease_is_active(monkeypatch):
    db = FakeSupabase({"research_runs": [{"id": "active", "user_id": "u1", "status": "running"}]})
    run_store = FakeRunStore(active={"active"})
    monkeypatch.setattr(account, "get_run_store", lambda: _async_value(run_store))

    with pytest.raises(HTTPException) as exc:
        await account.delete_account(object(), {"user_id": "u1"}, db)

    assert exc.value.status_code == 409
    assert run_store.updated == [("active", "cancelled")]
    assert db.deleted_auth_users == []
    assert not any(action == "delete" for _, action, _, _ in db.operations)


@pytest.mark.asyncio
async def test_delete_does_not_report_success_when_mem0_cleanup_fails(monkeypatch):
    db = FakeSupabase({"research_runs": []})
    run_store = FakeRunStore()
    monkeypatch.setattr(account, "get_run_store", lambda: _async_value(run_store))
    monkeypatch.setattr(account.mem0_client, "is_configured", lambda: True)

    async def fail_mem0(_user_id: str) -> None:
        raise RuntimeError("upstream unavailable")

    monkeypatch.setattr(account.mem0_client, "delete_user_memories", fail_mem0)

    with pytest.raises(HTTPException) as exc:
        await account.delete_account(object(), {"user_id": "u1"}, db)

    assert exc.value.status_code == 502
    assert db.deleted_auth_users == []
    assert not any(action == "delete" for _, action, _, _ in db.operations)


async def _async_value(value: Any) -> Any:
    return value
