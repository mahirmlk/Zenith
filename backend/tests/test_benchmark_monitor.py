from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

import httpx
import pytest

from services.benchmark_monitor import (
    BenchmarkProviderError,
    _fetch_snapshot,
    parse_leaderboard,
    poll_benchmark_watches,
    validate_hf_benchmark_dataset,
)


DATASET_ID = "zenith/benchmark"
NOW = datetime(2026, 11, 20, 2, tzinfo=timezone.utc)


def _info(dataset_id: str = DATASET_ID) -> dict[str, object]:
    return {"id": dataset_id, "private": False, "gated": False, "tags": ["benchmark:official"]}


def _entry(model_id: str = "org/model", *, rank: int = 1, value: float = 0.75) -> dict[str, object]:
    return {
        "modelId": model_id,
        "rank": rank,
        "value": value,
        "verified": True,
        "source": {"url": f"https://huggingface.co/{model_id}"},
    }


def _client(leaderboard: object) -> httpx.AsyncClient:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host != "huggingface.co":
            return httpx.Response(400)
        if request.url.path == f"/api/datasets/{DATASET_ID}":
            return httpx.Response(200, json=_info())
        if request.url.path == f"/api/datasets/{DATASET_ID}/leaderboard":
            return httpx.Response(200, json=leaderboard)
        return httpx.Response(404)

    return httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        timeout=8,
        follow_redirects=False,
    )


class FakeQuery:
    def __init__(self, db: "FakeSupabase", table: str):
        self.db = db
        self.table_name = table
        self.filters: dict[str, object] = {}
        self.action = "select"
        self.payload: object = None

    def select(self, *_args: object) -> "FakeQuery":
        return self

    def eq(self, field: str, value: object) -> "FakeQuery":
        self.filters[field] = value
        return self

    def limit(self, value: int) -> "FakeQuery":
        self.db.watch_limit = value
        return self

    def order(self, *_args: object, **_kwargs: object) -> "FakeQuery":
        return self

    def maybe_single(self) -> "FakeQuery":
        return self

    def update(self, payload: object) -> "FakeQuery":
        self.action = "update"
        self.payload = payload
        return self

    def upsert(self, payload: object, **_kwargs: object) -> "FakeQuery":
        self.action = "upsert"
        self.payload = payload
        return self

    async def execute(self) -> SimpleNamespace:
        if self.table_name == "watchlists" and self.action == "select":
            return SimpleNamespace(data=self.db.watches[: self.db.watch_limit or 50])
        if self.table_name == "benchmark_watch_snapshots" and self.action == "select":
            return SimpleNamespace(data=self.db.snapshot)
        if self.table_name == "notifications" and self.action == "upsert":
            self.db.calls.append("notifications")
            if self.db.fail_notifications:
                raise RuntimeError("notification upsert failed")
            rows = self.payload
            assert isinstance(rows, list)
            for row in rows:
                assert isinstance(row, dict)
                if not any(item["notification_key"] == row["notification_key"] for item in self.db.notifications):
                    self.db.notifications.append(row)
            return SimpleNamespace(data=[])
        if self.table_name == "benchmark_watch_snapshots" and self.action == "upsert":
            self.db.calls.append("snapshot")
            if self.db.fail_snapshot:
                raise RuntimeError("snapshot upsert failed")
            assert isinstance(self.payload, dict)
            self.db.snapshot = self.payload
            return SimpleNamespace(data=[])
        if self.table_name == "watchlists" and self.action == "update":
            self.db.calls.append("cursor")
            if self.db.fail_cursor:
                raise RuntimeError("cursor update failed")
            self.db.watches[0].update(self.payload)
            return SimpleNamespace(data=[])
        raise AssertionError((self.table_name, self.action))


class FakeSupabase:
    def __init__(self, *, snapshot: dict[str, object] | None = None):
        self.watches = [
            {
                "id": "watch-1",
                "user_id": "user-1",
                "query": DATASET_ID,
                "target_id": DATASET_ID,
                "target_type": "benchmark",
                "enabled": True,
            }
        ]
        self.snapshot = snapshot
        self.notifications: list[dict[str, object]] = []
        self.calls: list[str] = []
        self.watch_limit: int | None = None
        self.fail_notifications = False
        self.fail_snapshot = False
        self.fail_cursor = False

    def table(self, name: str) -> FakeQuery:
        return FakeQuery(self, name)


@pytest.mark.asyncio
async def test_validate_requires_public_ungated_official_dataset(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "services.benchmark_monitor._new_http_client",
        lambda **kwargs: _client([]),
    )
    assert await validate_hf_benchmark_dataset(DATASET_ID) == DATASET_ID

    async def fake_get_json(_client: httpx.AsyncClient, _url: str) -> dict[str, object]:
        return {**_info(), "gated": "auto"}

    monkeypatch.setattr("services.benchmark_monitor._get_json", fake_get_json)
    with pytest.raises(BenchmarkProviderError):
        await _fetch_snapshot(_client([]), DATASET_ID)


def test_parse_leaderboard_supports_official_rest_fields_and_rejects_malformed_verified_rows() -> None:
    parsed = parse_leaderboard([_entry(), {**_entry("unverified/model"), "verified": False}])
    assert parsed == [
        {
            "id": "org/model",
            "rank": 1,
            "score": 0.75,
            "source_url": "https://huggingface.co/org/model",
            "verified": True,
        }
    ]
    with pytest.raises(BenchmarkProviderError):
        parse_leaderboard([{**_entry(), "value": float("inf")}])
    with pytest.raises(BenchmarkProviderError):
        parse_leaderboard([{**_entry(), "sourceUrl": "javascript:alert(1)"}])
    with pytest.raises(BenchmarkProviderError):
        parse_leaderboard([_entry(str(index)) for index in range(501)])


@pytest.mark.asyncio
async def test_first_successful_snapshot_is_silent_and_second_observes_changes() -> None:
    db = FakeSupabase()
    client = _client([_entry()])
    try:
        assert await poll_benchmark_watches(db, now=NOW, client=client) == 0
        assert db.calls == ["snapshot", "cursor"]
        baseline = db.snapshot
        assert baseline and baseline["snapshot_hash"]
        await client.aclose()
        client = _client([_entry(rank=2, value=0.8), _entry("new/model", rank=3, value=0.7)])
        assert await poll_benchmark_watches(db, now=NOW.replace(day=21), client=client) == 2
        assert db.calls[-3:] == ["notifications", "snapshot", "cursor"]
        assert len(db.notifications) == 2
        changed = next(row for row in db.notifications if "org/model" in str(row["body"]))
        assert "0.75 → 0.8" in str(changed["body"])
        assert "1 → 2" in str(changed["body"])
        assert changed["source_url"] == f"https://huggingface.co/datasets/{DATASET_ID}"
        assert changed["reason_code"] == "benchmark_result_observed"
        assert db.snapshot != baseline
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_notification_failure_does_not_advance_snapshot_or_cursor() -> None:
    previous = [{"id": "org/model", "rank": 1, "score": 0.75, "source_url": "https://huggingface.co/org/model", "verified": True}]
    db = FakeSupabase(snapshot={"watchlist_id": "watch-1", "snapshot": previous, "snapshot_hash": "a" * 64, "observed_at": NOW.isoformat()})
    db.fail_notifications = True
    client = _client([_entry(rank=2, value=0.8)])
    try:
        assert await poll_benchmark_watches(db, now=NOW, client=client) == 0
        assert db.calls == ["notifications"]
        assert db.snapshot["snapshot"] == previous
        assert "last_checked_at" not in db.watches[0]
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_snapshot_failure_retries_notification_idempotently_before_cursor() -> None:
    previous = [{"id": "org/model", "rank": 1, "score": 0.75, "source_url": "https://huggingface.co/org/model", "verified": True}]
    db = FakeSupabase(snapshot={"watchlist_id": "watch-1", "snapshot": previous, "snapshot_hash": "a" * 64, "observed_at": NOW.isoformat()})
    db.fail_snapshot = True
    client = _client([_entry(rank=2, value=0.8)])
    try:
        assert await poll_benchmark_watches(db, now=NOW, client=client) == 0
        assert db.calls == ["notifications", "snapshot"]
        assert len(db.notifications) == 1
        db.fail_snapshot = False
        assert await poll_benchmark_watches(db, now=NOW, client=client) == 1
        assert len(db.notifications) == 1
        assert db.calls[-3:] == ["notifications", "snapshot", "cursor"]
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_fetch_failure_does_not_advance_snapshot_or_cursor() -> None:
    db = FakeSupabase()

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/leaderboard"):
            return httpx.Response(503)
        return httpx.Response(200, json=_info())

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler), follow_redirects=False)
    try:
        assert await poll_benchmark_watches(db, now=NOW, client=client) == 0
        assert db.calls == []
        assert db.snapshot is None
        assert "last_checked_at" not in db.watches[0]
    finally:
        await client.aclose()
