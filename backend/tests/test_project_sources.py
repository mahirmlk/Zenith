"""Project source lifecycle and role enforcement tests."""
from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest
from fastapi import HTTPException

from routers.projects import (
    ProjectSourceCreate,
    attach_project_source,
    list_project_sources,
    remove_project_source,
)


class FakeQuery:
    def __init__(self, db: "FakeSupabase", table: str) -> None:
        self.db = db
        self.table = table
        self.action = "select"
        self.filters: dict[str, Any] = {}
        self.in_filters: dict[str, list[Any]] = {}
        self.null_filters: set[str] = set()
        self.payload: dict[str, Any] | None = None
        self.single = False
        self.start = 0
        self.end: int | None = None

    def select(self, *_args: Any) -> "FakeQuery":
        return self

    def insert(self, payload: dict[str, Any]) -> "FakeQuery":
        self.action = "insert"
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

    def is_(self, key: str, value: str) -> "FakeQuery":
        assert value == "null"
        self.null_filters.add(key)
        return self

    def maybe_single(self) -> "FakeQuery":
        self.single = True
        return self

    def order(self, *_args: Any, **_kwargs: Any) -> "FakeQuery":
        return self

    def range(self, start: int, end: int) -> "FakeQuery":
        self.start = start
        self.end = end
        return self

    async def execute(self) -> SimpleNamespace:
        if self.action == "insert":
            assert self.payload is not None
            source = {"id": f"source-{len(self.db.sources) + 1}", **self.payload}
            self.db.sources.append(source)
            return SimpleNamespace(data=[source])
        if self.action == "delete":
            self.db.sources[:] = [
                row for row in self.db.sources
                if not all(row.get(key) == value for key, value in self.filters.items())
            ]
            return SimpleNamespace(data=[])

        if self.table == "projects":
            rows = [self.db.project]
        elif self.table == "project_members":
            rows = self.db.members
        elif self.table == "papers":
            rows = self.db.papers
        elif self.table == "project_sources":
            rows = self.db.sources
        else:
            raise AssertionError(self.table)
        rows = [
            row for row in rows
            if all(row.get(key) == value for key, value in self.filters.items())
            and all(row.get(key) in values for key, values in self.in_filters.items())
            and all(row.get(key) is None for key in self.null_filters)
        ]
        if self.end is not None:
            rows = rows[self.start:self.end + 1]
        return SimpleNamespace(data=(rows[0] if rows else None) if self.single else rows)


class FakeSupabase:
    def __init__(self, members: list[dict[str, str]] | None = None) -> None:
        self.project = {"id": "project-1", "owner_id": "owner-1", "deleted_at": None}
        self.members = members or []
        self.papers = [{"id": "paper-1", "title": "Paper 1", "authors": ["A. Author"], "url": "https://example.org/paper-1", "published_at": "2026-01-01T00:00:00Z"}]
        self.sources: list[dict[str, Any]] = []

    def table(self, table: str) -> FakeQuery:
        return FakeQuery(self, table)


@pytest.mark.asyncio
async def test_owner_can_attach_list_and_remove_paper_source():
    db = FakeSupabase()
    user = {"user_id": "owner-1"}

    created = await attach_project_source("project-1", ProjectSourceCreate(paper_id="paper-1"), user, db)
    listed = await list_project_sources("project-1", 50, 0, user, db)
    removed = await remove_project_source("project-1", created[0]["id"], user, db)

    assert created[0]["paper_id"] == "paper-1"
    assert listed[0]["id"] == created[0]["id"]
    assert listed[0]["paper"]["title"] == "Paper 1"
    assert removed == {"status": "ok"}
    assert db.sources == []


@pytest.mark.asyncio
async def test_attaching_same_paper_is_idempotent():
    db = FakeSupabase()
    user = {"user_id": "owner-1"}
    body = ProjectSourceCreate(paper_id="paper-1")

    first = await attach_project_source("project-1", body, user, db)
    second = await attach_project_source("project-1", body, user, db)

    assert first == second
    assert len(db.sources) == 1


@pytest.mark.asyncio
async def test_editor_can_attach_but_viewer_cannot_remove_source():
    editor_db = FakeSupabase([{"project_id": "project-1", "user_id": "editor-1", "role": "editor"}])
    created = await attach_project_source(
        "project-1", ProjectSourceCreate(paper_id="paper-1"), {"user_id": "editor-1"}, editor_db
    )

    viewer_db = FakeSupabase([{"project_id": "project-1", "user_id": "viewer-1", "role": "viewer"}])
    viewer_db.sources = created.copy()
    with pytest.raises(HTTPException) as error:
        await remove_project_source(
            "project-1", created[0]["id"], {"user_id": "viewer-1"}, viewer_db
        )

    assert error.value.status_code == 403
    assert len(viewer_db.sources) == 1


@pytest.mark.asyncio
async def test_unknown_paper_is_not_attached():
    db = FakeSupabase()
    with pytest.raises(HTTPException) as error:
        await attach_project_source(
            "project-1", ProjectSourceCreate(paper_id="missing"), {"user_id": "owner-1"}, db
        )

    assert error.value.status_code == 404
    assert db.sources == []


@pytest.mark.asyncio
async def test_soft_deleted_project_cannot_read_or_mutate_sources():
    db = FakeSupabase()
    db.project["deleted_at"] = "2026-11-01T00:00:00Z"

    with pytest.raises(HTTPException) as error:
        await attach_project_source(
            "project-1", ProjectSourceCreate(paper_id="paper-1"), {"user_id": "owner-1"}, db
        )

    assert error.value.status_code == 404
    assert db.sources == []
