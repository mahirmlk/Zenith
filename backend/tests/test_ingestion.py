"""Offline tests for watchlist notification delivery."""
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from services.ingestion import _notify_watchlists


class FakeQuery:
    def __init__(self, db, table):
        self.db = db
        self.table = table
        self.filters = {}
        self.action = "select"
        self.payload = None
        self.upsert_options = {}

    def select(self, *_args):
        self.action = "select"
        return self

    def eq(self, key, value):
        self.filters[key] = value
        return self

    def update(self, payload):
        self.action = "update"
        self.payload = payload
        return self

    def upsert(self, payload, **options):
        self.action = "upsert"
        self.payload = payload
        self.upsert_options = options
        return self

    async def execute(self):
        if self.table == "watchlists" and self.action == "select":
            rows = self.db.watchlists
            if self.filters.get("enabled") is not None:
                rows = [row for row in rows if row.get("enabled") == self.filters["enabled"]]
            return SimpleNamespace(data=rows)
        if self.table == "watchlists" and self.action == "update":
            if self.db.fail_cursor_update:
                self.db.fail_cursor_update = False
                raise RuntimeError("simulated cursor update failure")
            for row in self.db.watchlists:
                if all(row.get(key) == value for key, value in self.filters.items()):
                    row.update(self.payload)
            return SimpleNamespace(data=[])
        if self.table == "notifications" and self.action == "upsert":
            assert self.upsert_options == {
                "on_conflict": "user_id,watchlist_id,paper_id",
                "ignore_duplicates": True,
            }
            for row in self.payload:
                key = (row["user_id"], row["watchlist_id"], row["paper_id"])
                if not any(
                    (old["user_id"], old["watchlist_id"], old["paper_id"]) == key
                    for old in self.db.notifications
                ):
                    self.db.notifications.append(row)
            return SimpleNamespace(data=[])
        if self.table == "papers" and self.action == "upsert":
            assert self.upsert_options == {"on_conflict": "id", "ignore_duplicates": True}
            self.db.provider_papers.extend(self.payload)
            return SimpleNamespace(data=[])
        raise AssertionError((self.table, self.action))


class FakeSupabase:
    def __init__(self, watchlists, *, fail_cursor_update=False):
        self.watchlists = watchlists
        self.notifications = []
        self.provider_papers = []
        self.fail_cursor_update = fail_cursor_update

    def table(self, name):
        return FakeQuery(self, name)


def make_paper(paper_id, title, published_at):
    return {
        "id": paper_id,
        "title": title,
        "abstract": "This paper studies transformer language models.",
        "published_at": published_at.isoformat(),
    }


@pytest.mark.asyncio
async def test_watchlist_notifications_filter_disabled_and_respect_cadence():
    now = datetime(2026, 11, 8, 12, tzinfo=timezone.utc)
    db = FakeSupabase([
        {"id": "disabled", "user_id": "u1", "query": "transformer", "cadence": "daily", "enabled": False},
        {"id": "daily-recent", "user_id": "u1", "query": "transformer", "cadence": "daily", "enabled": True, "last_checked_at": (now - timedelta(hours=12)).isoformat()},
        {"id": "weekly-due", "user_id": "u2", "query": "transformer language", "cadence": "weekly", "enabled": True, "last_checked_at": (now - timedelta(days=8)).isoformat()},
    ])
    papers = [make_paper("paper-1", "Transformer Language Models", now - timedelta(days=1))]

    count = await _notify_watchlists(db, papers, now=now)

    assert count == 1
    assert [row["watchlist_id"] for row in db.notifications] == ["weekly-due"]
    assert db.watchlists[2]["last_checked_at"] == now.isoformat()
    assert db.watchlists[1]["last_checked_at"] == (now - timedelta(hours=12)).isoformat()


@pytest.mark.asyncio
async def test_notifications_match_migration_schema_and_are_idempotent_on_retry():
    now = datetime(2026, 11, 8, 12, tzinfo=timezone.utc)
    db = FakeSupabase([
        {"id": "watch-1", "user_id": "u1", "query": "transformer language", "cadence": "daily", "enabled": True},
    ], fail_cursor_update=True)
    papers = [make_paper("paper-1", "Transformer Language Models", now - timedelta(hours=2))]

    await _notify_watchlists(db, papers, now=now)
    await _notify_watchlists(db, papers, now=now)

    assert len(db.notifications) == 1
    notification = db.notifications[0]
    assert notification["kind"] == "watchlist"
    assert notification["watchlist_id"] == "watch-1"
    assert notification["project_id"] is None
    assert notification["paper_id"] == "paper-1"
    assert "title" in notification and "body" in notification
    assert "type" not in notification and "data" not in notification


@pytest.mark.asyncio
async def test_project_watchlist_notification_preserves_project_context():
    now = datetime(2026, 11, 8, 12, tzinfo=timezone.utc)
    db = FakeSupabase([{
        "id": "watch-project",
        "user_id": "u1",
        "query": "transformer",
        "cadence": "daily",
        "enabled": True,
        "project_id": "project-1",
    }])
    papers = [make_paper("paper-1", "Transformer Models", now - timedelta(hours=1))]

    await _notify_watchlists(db, papers, now=now)

    assert db.notifications[0]["project_id"] == "project-1"


@pytest.mark.asyncio
async def test_partial_source_failure_does_not_advance_watchlist_cursor():
    now = datetime(2026, 11, 8, 12, tzinfo=timezone.utc)
    db = FakeSupabase([
        {"id": "watch-1", "user_id": "u1", "query": "transformer", "cadence": "daily", "enabled": True},
    ])
    papers = [make_paper("paper-1", "Transformer Models", now - timedelta(hours=2))]

    await _notify_watchlists(db, papers, now=now, sources_complete=False)

    assert len(db.notifications) == 1
    assert "last_checked_at" not in db.watchlists[0]


@pytest.mark.asyncio
async def test_citation_watch_fetches_inbound_results_and_persists_linked_paper(monkeypatch):
    now = datetime(2026, 11, 8, 12, tzinfo=timezone.utc)
    db = FakeSupabase([{
        "id": "watch-citations",
        "user_id": "u1",
        "query": "Seed paper",
        "target_type": "citation",
        "target_id": "seed-id",
        "cadence": "daily",
        "enabled": True,
    }])
    provider_paper = make_paper("new-citer", "A paper citing the seed", now - timedelta(hours=1))

    async def fetch_watch_papers(target_type, target_id, since):
        assert (target_type, target_id) == ("citation", "seed-id")
        return [provider_paper]

    monkeypatch.setattr("services.semantic_scholar.fetch_watch_papers", fetch_watch_papers)
    count = await _notify_watchlists(db, [], now=now)

    assert count == 1
    assert db.notifications[0]["paper_id"] == "new-citer"
    assert db.provider_papers[0]["id"] == "new-citer"
    assert db.watchlists[0]["last_checked_at"] == now.isoformat()
