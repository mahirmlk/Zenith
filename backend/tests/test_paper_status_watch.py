"""Tests for user-owned publication update watch controls."""

from types import SimpleNamespace
from typing import Any

import pytest
from fastapi import HTTPException

from routers import papers


class FakeSupabase:
    def __init__(self, doi: str | None = "10.1234/original") -> None:
        self.paper = {"id": "p1", "doi": doi}
        self.watches: set[tuple[str, str]] = set()

    def table(self, name: str) -> "FakeQuery":
        return FakeQuery(self, name)


class FakeQuery:
    def __init__(self, db: FakeSupabase, name: str) -> None:
        self.db = db
        self.name = name
        self.action = "select"
        self.filters: dict[str, Any] = {}
        self.payload: dict[str, Any] | None = None

    def select(self, *_args: Any) -> "FakeQuery":
        self.action = "select"
        return self

    def eq(self, key: str, value: Any) -> "FakeQuery":
        self.filters[key] = value
        return self

    def maybe_single(self) -> "FakeQuery":
        return self

    def upsert(self, payload: dict[str, Any], **_kwargs: Any) -> "FakeQuery":
        self.action = "upsert"
        self.payload = payload
        return self

    def delete(self) -> "FakeQuery":
        self.action = "delete"
        return self

    async def execute(self) -> SimpleNamespace:
        if self.name == "papers":
            paper = self.db.paper if self.db.paper["id"] == self.filters.get("id") else None
            return SimpleNamespace(data=paper)
        key = (str(self.filters.get("user_id")), str(self.filters.get("paper_id")))
        if self.action == "select":
            return SimpleNamespace(data={"paper_id": key[1]} if key in self.db.watches else None)
        if self.action == "upsert":
            assert self.payload is not None
            self.db.watches.add((self.payload["user_id"], self.payload["paper_id"]))
        elif self.action == "delete":
            self.db.watches.discard(key)
        return SimpleNamespace(data=[])


@pytest.mark.asyncio
async def test_watch_requires_known_paper_with_doi():
    with pytest.raises(HTTPException) as missing:
        await papers.create_paper_status_watch(None, "missing", FakeSupabase(), "u1")
    assert missing.value.status_code == 404

    with pytest.raises(HTTPException) as no_doi:
        await papers.create_paper_status_watch(None, "p1", FakeSupabase(doi=None), "u1")
    assert no_doi.value.status_code == 422


@pytest.mark.asyncio
async def test_status_watch_is_idempotent_and_scoped_to_the_calling_user():
    db = FakeSupabase()

    assert (await papers.create_paper_status_watch(None, "p1", db, "u1")).watching is True
    assert (await papers.create_paper_status_watch(None, "p1", db, "u1")).watching is True
    assert (await papers.get_paper_status_watch("p1", db, "u2")).watching is False
    assert (await papers.delete_paper_status_watch(None, "p1", db, "u1")).watching is False
    assert (await papers.get_paper_status_watch("p1", db, "u1")).watching is False
    assert db.watches == set()
