"""Offline tests for bounded opt-in Crossref status watch processing."""

from datetime import date, datetime, timezone
from types import SimpleNamespace
from typing import Any

import pytest

from services import crossref_monitor
from services.crossref_updates import CrossrefLookup, CrossrefUpdate


class FakeSupabase:
    def __init__(self) -> None:
        self.watches = [
            {"user_id": "u1", "paper_id": "p1", "last_attempt_at": None},
            {"user_id": "u2", "paper_id": "p1", "last_attempt_at": None},
        ]
        self.papers = [{"id": "p1", "title": "Original paper", "doi": "10.1234/original"}]
        self.notifications: list[dict[str, Any]] = []

    def table(self, name: str) -> "FakeQuery":
        return FakeQuery(self, name)


class FakeQuery:
    def __init__(self, db: FakeSupabase, table: str) -> None:
        self.db = db
        self.name = table
        self.action = "select"
        self.filters: dict[str, Any] = {}
        self.in_filter: tuple[str, set[Any]] | None = None
        self.payload: Any = None
        self.options: dict[str, Any] = {}

    def select(self, *_args: Any) -> "FakeQuery":
        self.action = "select"
        return self

    def or_(self, _filter: str) -> "FakeQuery":
        return self

    def order(self, *_args: Any, **_kwargs: Any) -> "FakeQuery":
        return self

    def limit(self, _limit: int) -> "FakeQuery":
        return self

    def in_(self, column: str, values: list[Any]) -> "FakeQuery":
        self.in_filter = (column, set(values))
        return self

    def eq(self, key: str, value: Any) -> "FakeQuery":
        self.filters[key] = value
        return self

    def update(self, payload: dict[str, Any]) -> "FakeQuery":
        self.action = "update"
        self.payload = payload
        return self

    def upsert(self, payload: Any, **options: Any) -> "FakeQuery":
        self.action = "upsert"
        self.payload = payload
        self.options = options
        return self

    async def execute(self) -> SimpleNamespace:
        if self.name == "paper_status_watches" and self.action == "select":
            return SimpleNamespace(data=self.db.watches)
        if self.name == "papers" and self.action == "select":
            assert self.in_filter is not None
            column, values = self.in_filter
            return SimpleNamespace(data=[row for row in self.db.papers if row.get(column) in values])
        if self.action == "update" and self.name == "papers":
            for row in self.db.papers:
                if all(row.get(key) == value for key, value in self.filters.items()):
                    row.update(self.payload)
            return SimpleNamespace(data=[])
        if self.action == "update" and self.name == "paper_status_watches":
            for row in self.db.watches:
                if all(row.get(key) == value for key, value in self.filters.items()):
                    row.update(self.payload)
            return SimpleNamespace(data=[])
        if self.name == "notifications" and self.action == "upsert":
            assert self.options == {
                "on_conflict": "user_id,notification_key",
                "ignore_duplicates": True,
            }
            for row in self.payload:
                key = (row["user_id"], row["notification_key"])
                if not any((old["user_id"], old["notification_key"]) == key for old in self.db.notifications):
                    self.db.notifications.append(row)
            return SimpleNamespace(data=[])
        raise AssertionError((self.name, self.action))


@pytest.mark.asyncio
async def test_poll_persists_crossref_provenance_and_deduplicates_per_user_notice(monkeypatch):
    db = FakeSupabase()

    async def lookup(_doi: str, *, client: Any) -> CrossrefLookup:
        assert client is not None
        return CrossrefLookup(
            record_found=True,
            updates=(CrossrefUpdate(
                update_type="retraction",
                notice_doi="10.9999/retraction-notice",
                label="Retraction",
                updated_at=date(2026, 3, 4),
                deposit_source="retraction-watch",
            ),),
        )

    monkeypatch.setattr(crossref_monitor, "lookup_crossref_updates", lookup)
    now = datetime(2026, 11, 13, tzinfo=timezone.utc)

    first = await crossref_monitor.poll_crossref_status_watches(db, now=now)
    second = await crossref_monitor.poll_crossref_status_watches(db, now=now)

    assert first == 2
    assert second == 2
    assert db.papers[0]["publication_update_type"] == "retraction"
    assert db.papers[0]["publication_update_doi"] == "10.9999/retraction-notice"
    assert db.papers[0]["publication_update_source"] == "crossref"
    assert db.papers[0]["publication_update_deposit_source"] == "retraction-watch"
    assert db.papers[0]["publication_update_checked_at"] == now.isoformat()
    assert len(db.notifications) == 2
    assert {row["user_id"] for row in db.notifications} == {"u1", "u2"}
    assert all(row["reason_code"] == "publication_status_update" for row in db.notifications)
    assert all("Depositor/source: Retraction Watch" in row["body"] for row in db.notifications)
    assert all("not evidence that no update exists" in row["body"] for row in db.notifications)


@pytest.mark.asyncio
async def test_empty_provider_metadata_is_recorded_as_check_not_negative_status(monkeypatch):
    db = FakeSupabase()
    async def lookup(_doi: str, *, client: Any) -> CrossrefLookup:
        return CrossrefLookup(record_found=True, updates=())

    monkeypatch.setattr(crossref_monitor, "lookup_crossref_updates", lookup)
    now = datetime(2026, 11, 13, tzinfo=timezone.utc)

    count = await crossref_monitor.poll_crossref_status_watches(db, now=now)

    assert count == 0
    assert db.papers[0]["publication_update_checked_at"] == now.isoformat()
    assert "publication_update_type" not in db.papers[0]
    assert db.notifications == []


@pytest.mark.asyncio
async def test_one_doi_lookup_updates_each_versioned_paper_row(monkeypatch):
    db = FakeSupabase()
    db.papers.append({"id": "p1v2", "title": "Version two", "doi": "10.1234/original"})
    db.watches.append({"user_id": "u1", "paper_id": "p1v2", "last_attempt_at": None})

    async def lookup(_doi: str, *, client: Any) -> CrossrefLookup:
        return CrossrefLookup(
            record_found=True,
            updates=(CrossrefUpdate(
                update_type="withdrawal",
                notice_doi="10.9999/withdrawal-notice",
                deposit_source="publisher",
            ),),
        )

    monkeypatch.setattr(crossref_monitor, "lookup_crossref_updates", lookup)

    count = await crossref_monitor.poll_crossref_status_watches(
        db, now=datetime(2026, 11, 13, tzinfo=timezone.utc)
    )

    assert count == 3
    assert all(paper["publication_update_type"] == "withdrawal" for paper in db.papers)
    assert all(paper["publication_update_deposit_source"] == "publisher" for paper in db.papers)
    assert len(db.notifications) == 3


@pytest.mark.asyncio
async def test_provider_failure_only_advances_retry_backoff(monkeypatch):
    db = FakeSupabase()
    db.papers[0].update(
        {
            "publication_update_type": "expression_of_concern",
            "publication_update_doi": "10.9999/concern",
            "publication_update_source": "crossref",
            "publication_update_checked_at": "2026-10-01T00:00:00+00:00",
        }
    )

    async def lookup(_doi: str, *, client: Any) -> CrossrefLookup:
        raise TimeoutError("provider unavailable")

    monkeypatch.setattr(crossref_monitor, "lookup_crossref_updates", lookup)
    now = datetime(2026, 11, 13, tzinfo=timezone.utc)

    count = await crossref_monitor.poll_crossref_status_watches(db, now=now)

    assert count == 0
    assert db.papers[0]["publication_update_type"] == "expression_of_concern"
    assert db.papers[0]["publication_update_checked_at"] == "2026-10-01T00:00:00+00:00"
    assert all(row["last_attempt_at"] == now.isoformat() for row in db.watches)
    assert db.notifications == []
