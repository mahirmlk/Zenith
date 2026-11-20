"""Bounded, idempotent monitoring of official Hugging Face benchmarks."""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import math
import re
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import quote, urlsplit

import httpx

logger = logging.getLogger(__name__)

HF_ORIGIN = "https://huggingface.co"
MAX_ENABLED_WATCHES = 50
MAX_CONCURRENCY = 3
REQUEST_TIMEOUT_SECONDS = 8.0
MAX_RESPONSE_BYTES = 2 * 1024 * 1024
MAX_LEADERBOARD_ROWS = 500
MAX_SNAPSHOT_ENTRIES = 100
_DATASET_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,95}/[A-Za-z0-9][A-Za-z0-9_.-]{0,95}$")


class BenchmarkProviderError(ValueError):
    """HF returned an unavailable, unsafe, or malformed benchmark response."""


def validate_dataset_id(dataset_id: str) -> str:
    """Require an exact HF namespace/dataset identifier."""
    if not isinstance(dataset_id, str) or not _DATASET_ID.fullmatch(dataset_id):
        raise BenchmarkProviderError("Dataset must be an exact namespace/dataset identifier")
    return dataset_id


def dataset_page_url(dataset_id: str) -> str:
    validate_dataset_id(dataset_id)
    return f"{HF_ORIGIN}/datasets/{dataset_id}"


def _new_http_client() -> httpx.AsyncClient:
    return httpx.AsyncClient(
        timeout=httpx.Timeout(REQUEST_TIMEOUT_SECONDS),
        follow_redirects=False,
        limits=httpx.Limits(max_connections=MAX_CONCURRENCY),
    )


def _safe_source_url(value: Any) -> str | None:
    if not isinstance(value, str) or len(value) > 2048:
        return None
    try:
        parsed = urlsplit(value)
        _ = parsed.port
    except ValueError:
        return None
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or any(char.isspace() for char in value)
    ):
        return None
    return value


def parse_leaderboard(payload: Any) -> list[dict[str, Any]]:
    """Validate and normalize up to 100 highest-ranked verified entries."""
    rows: list[Any] | None = None
    if isinstance(payload, list):
        rows = payload
    elif isinstance(payload, dict):
        for key in ("leaderboard", "rows", "entries"):
            candidate = payload.get(key)
            if isinstance(candidate, list):
                rows = candidate
                break
    if not isinstance(rows, list) or len(rows) > MAX_LEADERBOARD_ROWS:
        raise BenchmarkProviderError("Leaderboard response has an invalid row collection")

    normalized: list[dict[str, Any]] = []
    seen: set[str] = set()
    for row in rows:
        if not isinstance(row, dict) or row.get("verified") is not True:
            continue
        entry_id = row.get("id") or row.get("model_id") or row.get("modelId") or row.get("name")
        if not isinstance(entry_id, str) or not entry_id.strip() or len(entry_id) > 300:
            raise BenchmarkProviderError("Verified leaderboard row has no valid model ID")
        entry_id = entry_id.strip()
        rank = row.get("rank")
        if isinstance(rank, str) and rank.isascii() and rank.isdigit():
            rank = int(rank)
        score = row.get("score", row.get("value"))
        source = row.get("source")
        nested_source_url = source.get("url") if isinstance(source, dict) else None
        source_url = _safe_source_url(
            row.get("source_url") or row.get("sourceUrl") or nested_source_url or row.get("url")
        )
        if (
            isinstance(rank, bool)
            or not isinstance(rank, int)
            or rank < 1
            or isinstance(score, bool)
            or not isinstance(score, (int, float))
            or not math.isfinite(float(score))
            or source_url is None
            or entry_id in seen
        ):
            raise BenchmarkProviderError("Verified leaderboard row is missing a valid rank, score, or source URL")
        seen.add(entry_id)
        normalized.append(
            {
                "id": entry_id,
                "rank": rank,
                "score": float(score),
                "source_url": source_url,
                "verified": True,
            }
        )
    normalized.sort(key=lambda item: (item["rank"], item["id"]))
    return normalized[:MAX_SNAPSHOT_ENTRIES]


def _canonical_hash(value: Any) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    return hashlib.sha256(encoded).hexdigest()


async def _get_json(client: httpx.AsyncClient, url: str) -> Any:
    """Read a fixed-origin JSON response with redirect and byte ceilings."""
    parsed = urlsplit(url)
    if parsed.scheme != "https" or parsed.hostname != "huggingface.co":
        raise BenchmarkProviderError("Benchmark requests must use the fixed HF origin")
    async with client.stream("GET", url, follow_redirects=False) as response:
        if 300 <= response.status_code < 400:
            raise BenchmarkProviderError("HF benchmark endpoint redirected")
        response.raise_for_status()
        content_length = response.headers.get("content-length")
        if content_length:
            try:
                if int(content_length) > MAX_RESPONSE_BYTES:
                    raise BenchmarkProviderError("HF response exceeds the size limit")
            except ValueError as exc:
                raise BenchmarkProviderError("HF response has an invalid content length") from exc
        data = bytearray()
        async for chunk in response.aiter_bytes():
            data.extend(chunk)
            if len(data) > MAX_RESPONSE_BYTES:
                raise BenchmarkProviderError("HF response exceeds the size limit")
    try:
        return json.loads(data)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise BenchmarkProviderError("HF returned invalid JSON") from exc


async def _validated_dataset(client: httpx.AsyncClient, dataset_id: str) -> None:
    encoded_id = "/".join(quote(part, safe="") for part in validate_dataset_id(dataset_id).split("/"))
    info = await _get_json(client, f"{HF_ORIGIN}/api/datasets/{encoded_id}")
    if not isinstance(info, dict):
        raise BenchmarkProviderError("HF returned invalid dataset metadata")
    tags = info.get("tags")
    if (
        info.get("id") != dataset_id
        or info.get("private") is not False
        or info.get("gated") is not False
        or not isinstance(tags, list)
        or "benchmark:official" not in tags
    ):
        raise BenchmarkProviderError("Dataset must be public, ungated, and tagged benchmark:official")


async def validate_hf_benchmark_dataset(dataset_id: str) -> str:
    """Validate public eligibility at HF before creating a watch."""
    dataset_id = validate_dataset_id(dataset_id)
    async with _new_http_client() as client:
        await _validated_dataset(client, dataset_id)
    return dataset_id


async def _fetch_snapshot(client: httpx.AsyncClient, dataset_id: str) -> list[dict[str, Any]]:
    await _validated_dataset(client, dataset_id)
    encoded_id = "/".join(quote(part, safe="") for part in dataset_id.split("/"))
    payload = await _get_json(
        client,
        f"{HF_ORIGIN}/api/datasets/{encoded_id}/leaderboard",
    )
    return parse_leaderboard(payload)


def _transition_notifications(
    watch: dict[str, Any],
    previous: list[dict[str, Any]],
    current: list[dict[str, Any]],
    previous_hash: str,
    current_hash: str,
    observed_at: datetime,
) -> list[dict[str, Any]]:
    old_by_id = {entry["id"]: entry for entry in previous}
    dataset_id = str(watch["target_id"])
    source_url = dataset_page_url(dataset_id)
    rows: list[dict[str, Any]] = []
    for entry in current:
        old = old_by_id.get(entry["id"])
        if old is not None and (old.get("score") == entry["score"] and old.get("rank") == entry["rank"]):
            continue
        transition = {
            "previous_snapshot": previous_hash,
            "current_snapshot": current_hash,
            "entry_id": entry["id"],
        }
        key = f"hf-benchmark:{watch['id']}:{_canonical_hash(transition)}"
        if old is None:
            change = (
                f"New verified entry: {entry['id']}; score unavailable → {entry['score']}; "
                f"rank unavailable → {entry['rank']}."
            )
        else:
            change = (
                f"Verified entry {entry['id']}: score {old['score']} → {entry['score']}; "
                f"rank {old['rank']} → {entry['rank']}."
            )
        rows.append(
            {
                "user_id": watch["user_id"],
                "watchlist_id": watch["id"],
                "project_id": watch.get("project_id"),
                "kind": "benchmark",
                "title": f"Verified benchmark update: {dataset_id}"[:200],
                "body": (
                    f"{change} Entry source: {entry['source_url']}. "
                    f"Observed {observed_at.astimezone(timezone.utc).isoformat()}."
                )[:2000],
                "reason_code": "benchmark_result_observed",
                "reason_text": f"Observed verified leaderboard change for {dataset_id}."[:500],
                "notification_key": key,
                "source_url": source_url,
                "paper_id": None,
            }
        )
    return rows


async def _process_watch(
    supabase: Any,
    watch: dict[str, Any],
    client: httpx.AsyncClient,
    observed_at: datetime,
) -> int:
    dataset_id = validate_dataset_id(str(watch.get("target_id") or ""))
    if watch.get("query") not in (None, "", dataset_id):
        raise BenchmarkProviderError("Benchmark query must exactly match its target ID")
    current = await _fetch_snapshot(client, dataset_id)
    snapshot_hash = _canonical_hash(current)
    existing_result = await (
        supabase.table("benchmark_watch_snapshots")
        .select("snapshot,snapshot_hash")
        .eq("watchlist_id", watch["id"])
        .maybe_single()
        .execute()
    )
    existing = existing_result.data if isinstance(existing_result.data, dict) else None
    if existing is None:
        notifications: list[dict[str, Any]] = []
    else:
        previous = existing.get("snapshot")
        if not isinstance(previous, list):
            raise BenchmarkProviderError("Stored benchmark snapshot is malformed")
        previous_hash = existing.get("snapshot_hash")
        if not isinstance(previous_hash, str) or not re.fullmatch(r"[0-9a-f]{64}", previous_hash):
            previous_hash = _canonical_hash(previous)
        notifications = _transition_notifications(
            watch, previous, current, previous_hash, snapshot_hash, observed_at
        )

    if notifications:
        await supabase.table("notifications").upsert(
            notifications,
            on_conflict="user_id,notification_key",
            ignore_duplicates=True,
        ).execute()

    # Advance durable state only after notifications have been accepted. If a
    # later write fails, notification_key makes the next daily retry safe.
    await supabase.table("benchmark_watch_snapshots").upsert(
        {
            "watchlist_id": watch["id"],
            "snapshot": current,
            "snapshot_hash": snapshot_hash,
            "observed_at": observed_at.isoformat(),
        },
        on_conflict="watchlist_id",
    ).execute()
    await (
        supabase.table("watchlists")
        .update({"last_checked_at": observed_at.isoformat()})
        .eq("id", watch["id"])
        .eq("user_id", watch["user_id"])
        .execute()
    )
    return len(notifications)


async def poll_benchmark_watches(
    supabase: Any,
    *,
    now: datetime | None = None,
    client: httpx.AsyncClient | None = None,
) -> int:
    """Poll at most 50 enabled benchmark watches with at most three requests in flight."""
    observed_at = now or datetime.now(timezone.utc)
    observed_at = observed_at.replace(tzinfo=timezone.utc) if observed_at.tzinfo is None else observed_at.astimezone(timezone.utc)
    try:
        result = await (
            supabase.table("watchlists")
            .select("id,user_id,query,target_id,project_id,enabled,cadence,last_checked_at")
            .eq("enabled", True)
            .eq("target_type", "benchmark")
            .order("last_checked_at", desc=False, nullsfirst=True)
            .limit(MAX_ENABLED_WATCHES)
            .execute()
        )
    except Exception:
        logger.exception("Could not load benchmark watches")
        return 0
    watches = []
    for watch in result.data or []:
        last_checked = watch.get("last_checked_at")
        if not last_checked:
            watches.append(watch)
            continue
        try:
            previous_check = datetime.fromisoformat(str(last_checked).replace("Z", "+00:00"))
            previous_check = previous_check.replace(tzinfo=timezone.utc) if previous_check.tzinfo is None else previous_check.astimezone(timezone.utc)
        except ValueError:
            # A malformed cursor is treated as due; the provider response and
            # successful persistence will replace it with a valid timestamp.
            watches.append(watch)
            continue
        cadence = timedelta(days=7) if watch.get("cadence") == "weekly" else timedelta(days=1)
        if observed_at - previous_check >= cadence:
            watches.append(watch)
    owns_client = client is None
    if client is None:
        client = _new_http_client()
    semaphore = asyncio.Semaphore(MAX_CONCURRENCY)

    async def poll_one(watch: dict[str, Any]) -> int:
        async with semaphore:
            try:
                return await _process_watch(supabase, watch, client, observed_at)
            except Exception:
                logger.exception("Benchmark watch poll failed for watch %s", watch.get("id"))
                return 0

    try:
        return sum(await asyncio.gather(*(poll_one(watch) for watch in watches)))
    finally:
        if owns_client:
            await client.aclose()
