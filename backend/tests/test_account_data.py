"""Offline tests for account export/deletion scope and external cleanup."""
from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from routers import account


class FakeSupabase:
    def __init__(self, tables: dict[str, list[dict[str, Any]]]) -> None:
        self.tables = tables
        self.operations: list[tuple[str, str, dict[str, Any], dict[str, list[Any]]]] = []

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

    def is_(self, key: str, value: Any) -> "FakeQuery":
        self.filters[key] = None if value == "null" else value
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


def _export_tables() -> dict[str, list[dict[str, Any]]]:
    return {
        "user_papers": [{"user_id": "u1", "paper_id": "p1"}, {"user_id": "u2", "paper_id": "private"}],
        "user_prefs": [{"user_id": "u1", "interests": ["ml"]}],
        "papers": [
            {"id": "p1", "title": "Saved paper", "abstract": "Public metadata"},
            {"id": "p2", "title": "Shared source", "abstract": "Public metadata"},
            {"id": "p3", "title": "Unrelated paper", "abstract": "Do not export"},
        ],
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
        "project_annotations": [
            {"id": "a-owned", "project_id": "owned", "created_by": "u2", "content": "Owned annotation"},
            {"id": "a-shared", "project_id": "shared", "created_by": "u1", "content": "My annotation"},
            {"id": "a-shared-other", "project_id": "shared", "created_by": "u2", "content": "Their annotation"},
        ],
        "saved_searches": [
            {"id": "ss-personal", "created_by": "u1", "project_id": None, "query": "personal"},
            {"id": "ss-owned", "created_by": "u2", "project_id": "owned", "query": "owned"},
            {"id": "ss-shared", "created_by": "u1", "project_id": "shared", "query": "mine"},
            {"id": "ss-shared-other", "created_by": "u2", "project_id": "shared", "query": "theirs"},
        ],
        "project_briefs": [
            {"id": "brief-owned", "project_id": "owned", "created_by": "u2", "current_version": 2},
            {"id": "brief-shared", "project_id": "shared", "created_by": "u2", "current_version": 2},
            {"id": "brief-other", "project_id": "other", "created_by": "u3", "current_version": 1},
        ],
        "project_brief_versions": [
            {"id": "bv-owned", "brief_id": "brief-owned", "created_by": "u2", "version": 1},
            {"id": "bv-shared-mine", "brief_id": "brief-shared", "created_by": "u1", "version": 1},
            {"id": "bv-shared-other", "brief_id": "brief-shared", "created_by": "u2", "version": 2},
            {"id": "bv-other", "brief_id": "brief-other", "created_by": "u3", "version": 1},
        ],
        "project_documents": [
            {"id": "owned-doc", "project_id": "owned", "created_by": "u2", "filename": "owned.pdf"},
            {"id": "shared-doc", "project_id": "shared", "created_by": "u1", "filename": "mine.pdf"},
            {"id": "shared-other-doc", "project_id": "shared", "created_by": "u2", "filename": "theirs.pdf"},
            {"id": "other-doc", "project_id": "other", "created_by": "u1", "filename": "private.pdf"},
        ],
        "project_document_pages": [
            {"document_id": "owned-doc", "page_number": 1, "text": "Owned project text."},
            {"document_id": "shared-doc", "page_number": 2, "text": "My shared project text."},
            {"document_id": "shared-other-doc", "page_number": 3, "text": "Another member's text."},
            {"document_id": "other-doc", "page_number": 4, "text": "Unrelated project text."},
        ],
        "watchlists": [{"user_id": "u1", "query": "ml"}],
        "notifications": [{
            "user_id": "u1",
            "title": "new paper",
            "source_url": "https://huggingface.co/datasets/zenith/benchmark",
        }],
        "notification_email_preferences": [
            {
                "user_id": "u1",
                "email_opt_in": True,
                "email_frequency": "weekly",
                "timezone": "Asia/Kolkata",
                "suppressed": False,
                "recipient_hash": "secret-hash-u1",
                "consented_at": "2026-01-02T03:04:05Z",
                "updated_at": "2026-01-02T03:04:05Z",
            },
            {"user_id": "u2", "email_opt_in": False, "recipient_hash": "secret-hash-u2"},
        ],
        "notification_email_consent_events": [
            {
                "id": 1,
                "user_id": "u1",
                "action": "opt_in",
                "source": "settings",
                "recipient_hash": "secret-hash-u1",
                "created_at": "2026-01-02T03:04:05Z",
            },
            {"id": 2, "user_id": "u2", "action": "opt_in", "recipient_hash": "secret-hash-u2"},
        ],
        "notification_email_outbox": [
            {"user_id": "u1", "provider_message_id": "internal-message-id"},
        ],
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
    assert result["notifications"][0]["source_url"] == "https://huggingface.co/datasets/zenith/benchmark"
    assert result["saved_papers"] == [{"user_id": "u1", "paper_id": "p1"}]
    assert {row["id"] for row in result["paper_metadata"]} == {"p1", "p2"}
    assert {row["id"] for row in result["projects"]} == {"owned", "shared"}
    assert {row["content"] for row in result["project_notes"]} == {"owned note", "shared note"}
    assert {row["paper_id"] for row in result["project_sources"]} == {"p1", "p2"}
    assert {row["id"] for row in result["project_annotations"]} == {"a-owned", "a-shared"}
    assert {row["id"] for row in result["saved_searches"]} == {"ss-personal", "ss-owned", "ss-shared"}
    assert {row["id"] for row in result["project_briefs"]} == {"brief-owned", "brief-shared"}
    assert {row["id"] for row in result["project_brief_versions"]} == {"bv-owned", "bv-shared-mine"}
    assert {row["id"] for row in result["project_documents"]} == {"owned-doc", "shared-doc"}
    assert {row["document_id"] for row in result["project_document_pages"]} == {"owned-doc", "shared-doc"}
    assert {row["text"] for row in result["project_document_pages"]} == {
        "Owned project text.", "My shared project text."
    }
    assert result["research_runs"] == [{"id": "r1", "user_id": "u1", "query": "private query"}]
    assert result["run_events"] == [{"run_id": "r1", "safe_payload": {"x": 1}}]
    assert result["notification_email_preferences"] == [{
        "email_opt_in": True,
        "email_frequency": "weekly",
        "timezone": "Asia/Kolkata",
        "suppressed": False,
        "consented_at": "2026-01-02T03:04:05Z",
        "updated_at": "2026-01-02T03:04:05Z",
    }]
    assert result["notification_email_consent_events"] == [{
        "action": "opt_in",
        "source": "settings",
        "created_at": "2026-01-02T03:04:05Z",
    }]
    assert "notification_email_outbox" not in result
    assert "secret-hash-u1" not in str(result)
    assert "secret-hash-u2" not in str(result)
    assert "internal-message-id" not in str(result)
    assert result["memories"] == [{"memory": "prefers ML"}]
    assert result["memory_export_status"] == "exported"


@pytest.mark.asyncio
async def test_export_skips_mem0_when_external_spend_limit_is_unconfirmed(monkeypatch):
    db = FakeSupabase(_export_tables())
    monkeypatch.setattr(account.mem0_client, "is_configured", lambda: False)
    monkeypatch.setattr(account.mem0_client, "has_credentials", lambda: True)

    async def memories(_user_id: str) -> list[dict[str, Any]]:
        raise AssertionError("Mem0 usage was attempted without spend-limit confirmation")

    monkeypatch.setattr(account.mem0_client, "get_user_profile", memories)
    result = await account.export_account(object(), {"user_id": "u1", "email": "u1@example.com"}, db)

    assert result["memory_export_status"] == "withheld: provider spend limit unconfirmed"
    assert result["memories"] == []


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
async def test_delete_persists_an_idempotent_intent_and_returns_accepted_receipt(monkeypatch):
    requested: list[str] = []

    async def request_deletion(user_id: str) -> str:
        requested.append(user_id)
        return "job-u1"

    monkeypatch.setattr(account, "request_account_deletion", request_deletion)

    result = await account.delete_account(object(), {"user_id": "u1"}, object())

    assert result == {"status": "accepted", "request_id": "job-u1"}
    assert requested == ["u1"]
