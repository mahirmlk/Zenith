"""Supabase-backed cache for Semantic Scholar citation edges.

The Semantic Scholar public API is aggressively rate-limited (~100 requests
per 5 minutes unshared). Caching citation edges in the ``citations`` table
means the citation graph only hits S2 once per paper, then serves cached
edges until they go stale (7 days).
"""
import logging
from datetime import datetime, timedelta, timezone
from typing import Any

logger = logging.getLogger(__name__)

CACHE_TTL = timedelta(days=7)
CitationRow = dict[str, Any]


def _parse_timestamp(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        ts = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        return ts
    except (ValueError, TypeError):
        return None


async def get_cached_citations(paper_id: str) -> list[CitationRow] | None:
    """Return cached citation rows for ``paper_id``, or None if missing/stale."""
    try:
        from services.supabase_client import get_supabase

        supabase = await get_supabase()

        response = await supabase.table("citations").select("*").eq("paper_id", paper_id).execute()
        rows = response.data or []
        if not rows:
            return None

        timestamps = [
            timestamp
            for row in rows
            if (timestamp := _parse_timestamp(row.get("fetched_at"))) is not None
        ]
        newest = max(timestamps, default=None)
        if newest is None or datetime.now(timezone.utc) - newest > CACHE_TTL:
            return None
        return rows
    except Exception as exc:
        logger.warning("Citation cache read failed for %s: %s", paper_id, exc)
        return None


async def store_citations(
    paper_id: str, root_title: str, references: list[CitationRow]
) -> None:
    """Upsert a paper's citation edges into the cache table."""
    try:
        from services.supabase_client import get_supabase

        supabase = await get_supabase()
        rows = [
            {
                "paper_id": paper_id,
                "root_title": root_title,
                "cited_id": ref.get("paperId", f"ref-{i}"),
                "cited_title": ref.get("title", "Related"),
            }
            for i, ref in enumerate(references)
        ]
        if not rows:
            return

        await supabase.table("citations").upsert(rows).execute()
    except Exception as exc:
        logger.warning("Citation cache write failed for %s: %s", paper_id, exc)
