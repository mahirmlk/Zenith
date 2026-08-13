"""Supabase-backed cache for Semantic Scholar citation edges.

The Semantic Scholar public API is aggressively rate-limited (~100 requests
per 5 minutes unshared). Caching citation edges in the ``citations`` table
means the citation graph only hits S2 once per paper, then serves cached
edges until they go stale (7 days).
"""
import asyncio
import logging
from datetime import datetime, timedelta, timezone

logger = logging.getLogger(__name__)

CACHE_TTL = timedelta(days=7)


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


async def get_cached_citations(paper_id: str) -> list[dict] | None:
    """Return cached citation rows for ``paper_id``, or None if missing/stale."""
    try:
        from services.supabase_client import get_supabase

        supabase = get_supabase()

        def _fetch():
            response = (
                supabase.table("citations")
                .select("*")
                .eq("paper_id", paper_id)
                .execute()
            )
            return response.data or []

        rows = await asyncio.to_thread(_fetch)
        if not rows:
            return None

        newest = max((_parse_timestamp(r.get("fetched_at")) for r in rows if r.get("fetched_at")), default=None)
        if newest is None or datetime.now(timezone.utc) - newest > CACHE_TTL:
            return None
        return rows
    except Exception as exc:
        logger.warning("Citation cache read failed for %s: %s", paper_id, exc)
        return None


async def store_citations(paper_id: str, root_title: str, references: list[dict]) -> None:
    """Upsert a paper's citation edges into the cache table."""
    try:
        from services.supabase_client import get_supabase

        supabase = get_supabase()
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

        def _upsert():
            return supabase.table("citations").upsert(rows).execute()

        await asyncio.to_thread(_upsert)
    except Exception as exc:
        logger.warning("Citation cache write failed for %s: %s", paper_id, exc)