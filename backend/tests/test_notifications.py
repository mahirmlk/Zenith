"""Notification read operations remain scoped to the authenticated user."""
from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from routers.notifications import mark_notification_read


class FakeQuery:
    def __init__(self) -> None:
        self.filters: dict[str, Any] = {}
        self.null_filters: dict[str, str] = {}
        self.payload: dict[str, Any] | None = None

    def update(self, payload: dict[str, Any]) -> "FakeQuery":
        self.payload = payload
        return self

    def eq(self, key: str, value: Any) -> "FakeQuery":
        self.filters[key] = value
        return self

    def is_(self, key: str, value: str) -> "FakeQuery":
        self.null_filters[key] = value
        return self

    async def execute(self) -> SimpleNamespace:
        return SimpleNamespace(data=[])


class FakeSupabase:
    def __init__(self) -> None:
        self.query = FakeQuery()

    def table(self, name: str) -> FakeQuery:
        assert name == "notifications"
        return self.query


@pytest.mark.asyncio
async def test_mark_notification_read_updates_only_matching_user_and_unread_row():
    db = FakeSupabase()

    result = await mark_notification_read("notice-1", {"user_id": "user-1"}, db)

    assert result == {"status": "ok"}
    assert db.query.filters == {"id": "notice-1", "user_id": "user-1"}
    assert db.query.null_filters == {"read_at": "null"}
    assert db.query.payload is not None and "read_at" in db.query.payload
