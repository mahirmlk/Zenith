"""Watchlist project authorization and soft-delete tests."""
from types import SimpleNamespace
from typing import Any

import pytest
import httpx
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


@pytest.mark.asyncio
async def test_author_watch_is_validated_and_stores_provider_identity(monkeypatch):
    async def validate(target_type: str, target_id: str) -> str:
        assert (target_type, target_id) == ("author", "12345")
        return "Ada Lovelace"

    monkeypatch.setattr("routers.watchlists.validate_watch_target", validate)
    db = FakeSupabase(None)
    result = await create_watch(
        WatchCreate(target_type="author", target_id="12345"),
        {"user_id": "owner"},
        db,
    )

    assert result[0]["query"] == "Ada Lovelace"
    assert result[0]["target_type"] == "author"
    assert result[0]["target_id"] == "12345"


@pytest.mark.asyncio
async def test_provider_watch_rejects_unknown_target(monkeypatch):
    async def validate(_target_type: str, _target_id: str) -> str:
        raise httpx.HTTPStatusError("missing", request=httpx.Request("GET", "https://example.test"), response=httpx.Response(404))

    monkeypatch.setattr("routers.watchlists.validate_watch_target", validate)
    db = FakeSupabase(None)
    with pytest.raises(HTTPException) as error:
        await create_watch(
            WatchCreate(target_type="citation", target_id="missing"),
            {"user_id": "owner"},
            db,
        )
    assert error.value.status_code == 422
    assert "watchlists" not in db.tables


@pytest.mark.asyncio
async def test_project_watch_authorization_precedes_provider_lookup(monkeypatch):
    async def validate(_target_type: str, _target_id: str) -> str:
        raise AssertionError("provider must not be called before project authorization")

    monkeypatch.setattr("routers.watchlists.validate_watch_target", validate)
    db = FakeSupabase({"id": "project-1", "owner_id": "owner", "deleted_at": "2026-11-01T00:00:00Z"})
    with pytest.raises(HTTPException) as error:
        await create_watch(
            WatchCreate(target_type="citation", target_id="seed-id", project_id="project-1"),
            {"user_id": "owner"},
            db,
        )
    assert error.value.status_code == 404
    assert "watchlists" not in db.tables
