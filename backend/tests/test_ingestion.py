"""Offline tests for watchlist notification delivery."""
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from services.ingestion import (
    _load_existing_paper_rows,
    _mark_preprint_version_changes,
    _notify_watchlists,
    _watchlist_reason,
)


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

    def in_(self, key, values):
        self.filters[f"in:{key}"] = set(values)
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
        if self.table == "papers" and self.action == "select":
            rows = self.db.paper_rows
            for key, values in self.filters.items():
                if key.startswith("in:"):
                    column = key.split(":", 1)[1]
                    rows = [row for row in rows if row.get(column) in values]
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
        self.paper_rows = []
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


@pytest.mark.parametrize(
    ("target_type", "query", "paper", "expected_code", "expected_phrase"),
    [
        ("topic", "transformer language", {"title": "Transformer Models", "abstract": "Language systems."}, "topic_term_overlap", "2/2 topic-watch terms"),
        ("author", "Author label", {}, "author_relation", "Semantic Scholar returned this paper"),
        ("citation", "Seed title", {}, "citation_relation", "reports that this paper cites"),
        (
            "topic", "graph retrieval",
            {"_version_change_from": 1, "source_version": 2, "source_updated_at": "2026-11-12T00:00:00Z"},
            "preprint_version_updated", "arXiv reports this preprint changed from v1 to v2",
        ),
    ],
)
def test_watchlist_reason_explains_auditable_match_basis(
    target_type, query, paper, expected_code, expected_phrase
):
    reason_code, reason_text = _watchlist_reason(target_type, query, paper)

    assert reason_code == expected_code
    assert expected_phrase in reason_text
    assert len(reason_text) <= 500


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
    assert notification["reason_code"] == "topic_term_overlap"
    assert "topic-watch terms" in notification["reason_text"]
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
@pytest.mark.parametrize(
    ("oldest_update", "expected_cursor"),
    [
        ("2026-11-12T11:00:00Z", True),
        ("2026-11-12T13:00:00Z", False),
    ],
)
async def test_capped_arxiv_poll_advances_only_when_its_records_cover_watch_window(
    oldest_update, expected_cursor
):
    now = datetime(2026, 11, 13, 12, tzinfo=timezone.utc)
    last_checked = datetime(2026, 11, 12, 12, tzinfo=timezone.utc)
    db = FakeSupabase([{
        "id": "topic-watch",
        "user_id": "u1",
        "query": "graph retrieval",
        "cadence": "daily",
        "enabled": True,
        "last_checked_at": last_checked.isoformat(),
    }])
    oldest_update_at = datetime.fromisoformat(oldest_update.replace("Z", "+00:00"))

    await _notify_watchlists(
        db,
        [],
        now=now,
        arxiv_updates_complete=False,
        arxiv_updates_oldest_at=oldest_update_at,
    )

    assert (db.watchlists[0].get("last_checked_at") == now.isoformat()) is expected_cursor


@pytest.mark.asyncio
@pytest.mark.parametrize("target_type,target_id", [("author", "author-id"), ("citation", "seed-id")])
async def test_provider_watch_persists_results_without_topic_text_overlap(
    monkeypatch, target_type, target_id
):
    now = datetime(2026, 11, 8, 12, tzinfo=timezone.utc)
    db = FakeSupabase([{
        "id": "watch-citations",
        "user_id": "u1",
        "query": "Provider display label",
        "target_type": target_type,
        "target_id": target_id,
        "cadence": "daily",
        "enabled": True,
    }])
    provider_paper = make_paper("provider-result", "Independent work", now - timedelta(hours=1))

    async def fetch_watch_papers(target_type, target_id, since):
        assert (target_type, target_id) == (watch_type, target_id)
        return [provider_paper]

    watch_type = target_type
    monkeypatch.setattr("services.semantic_scholar.fetch_watch_papers", fetch_watch_papers)
    count = await _notify_watchlists(
        db,
        [],
        now=now,
        arxiv_updates_complete=False,
        arxiv_updates_oldest_at=now,
    )

    assert count == 1
    assert db.notifications[0]["paper_id"] == "provider-result"
    assert db.provider_papers[0]["id"] == "provider-result"
    assert db.watchlists[0]["last_checked_at"] == now.isoformat()
    assert db.notifications[0]["reason_code"] == f"{target_type}_relation"


@pytest.mark.asyncio
async def test_duplicate_provider_candidates_create_one_notification(monkeypatch):
    now = datetime(2026, 11, 8, 12, tzinfo=timezone.utc)
    db = FakeSupabase([{
        "id": "watch-author",
        "user_id": "u1",
        "query": "Author label",
        "target_type": "author",
        "target_id": "author-id",
        "cadence": "daily",
        "enabled": True,
    }])
    candidate = make_paper("provider-result", "Independent work", now - timedelta(hours=1))

    async def fetch_watch_papers(_target_type, _target_id, _since):
        return [candidate, dict(candidate)]

    monkeypatch.setattr("services.semantic_scholar.fetch_watch_papers", fetch_watch_papers)
    count = await _notify_watchlists(db, [], now=now)

    assert count == 1
    assert len(db.notifications) == 1


@pytest.mark.asyncio
async def test_preprint_update_uses_source_update_time_and_explains_version_change():
    now = datetime(2026, 11, 13, 12, tzinfo=timezone.utc)
    db = FakeSupabase([{
        "id": "topic-watch",
        "user_id": "u1",
        "query": "graph retrieval",
        "target_type": "topic",
        "cadence": "daily",
        "enabled": True,
    }])
    paper = {
        "id": "2401.12345v2",
        "title": "Graph retrieval for research",
        "abstract": "A revised method for graph retrieval.",
        "published_at": "2024-01-01T00:00:00Z",
        "source_updated_at": "2026-11-12T13:00:00Z",
        "source_version": 2,
        "_version_change_from": 1,
    }

    count = await _notify_watchlists(db, [paper], now=now)

    assert count == 1
    notification = db.notifications[0]
    assert notification["title"] == "New arXiv version for graph retrieval"
    assert notification["reason_code"] == "preprint_version_updated"
    assert "v1 to v2" in notification["reason_text"]


@pytest.mark.asyncio
async def test_existing_paper_lookup_is_candidate_bounded_and_includes_prior_versions():
    db = FakeSupabase([])
    db.paper_rows = [
        {"id": "2401.12345v1", "preprint_id": "2401.12345", "source_version": 1},
        {"id": "other", "preprint_id": None, "source_version": None},
    ]

    existing = await _load_existing_paper_rows(db, [{"id": "2401.12345v2", "preprint_id": "2401.12345"}])

    assert existing == [db.paper_rows[0]]


def test_preprint_version_change_requires_a_known_older_version():
    papers = [
        {"id": "2401.12345v2", "preprint_id": "2401.12345", "source_version": 2},
        {"id": "2401.12345v1", "preprint_id": "2401.12345", "source_version": 1},
        {"id": "2402.99999v2", "preprint_id": "2402.99999", "source_version": 2},
    ]

    _mark_preprint_version_changes(papers, [
        {"id": "2401.12345v1", "preprint_id": "2401.12345", "source_version": 1},
    ])

    assert papers[0]["_version_change_from"] == 1
    assert "_version_change_from" not in papers[1]
    assert "_version_change_from" not in papers[2]
