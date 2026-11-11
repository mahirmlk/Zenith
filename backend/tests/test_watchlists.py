"""Watchlist project authorization and soft-delete tests."""
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi import HTTPException

from routers.watchlists import WatchCreate, create_watch


class FakeQuery:
    def __init__(self, project: dict[str, Any] | None) -> None:
        self.project = project
        self.null_filters: set[str] = set()
        self.inserted: dict[str, Any] | None = None

    def select(self, *_args: Any) -> "FakeQuery":
        return self

    def eq(self, _key: str, _value: Any) -> "FakeQuery":
        return self

    def is_(self, key: str, value: str) -> "FakeQuery":
        assert value == "null"
        self.null_filters.add(key)
        return self

    def maybe_single(self) -> "FakeQuery":
        return self

    def insert(self, payload: dict[str, Any]) -> "FakeQuery":
        self.inserted = payload
        return self

    async def execute(self) -> SimpleNamespace:
        if self.inserted is not None:
            return SimpleNamespace(data=[self.inserted])
        if self.project and any(self.project.get(key) is not None for key in self.null_filters):
            return SimpleNamespace(data=None)
        return SimpleNamespace(data=self.project)


class FakeSupabase:
    def __init__(self, project: dict[str, Any] | None) -> None:
        self.project = project
        self.tables: list[str] = []

    def table(self, name: str) -> FakeQuery:
        self.tables.append(name)
        return FakeQuery(self.project)


@pytest.mark.asyncio
async def test_cannot_create_watchlist_for_soft_deleted_project():
    db = FakeSupabase({"id": "project-1", "owner_id": "owner", "deleted_at": "2026-11-01T00:00:00Z"})

    with pytest.raises(HTTPException) as error:
        await create_watch(
            WatchCreate(query="transformers", project_id="project-1"),
            {"user_id": "owner"},
            db,
        )

    assert error.value.status_code == 404
    assert "watchlists" not in db.tables
