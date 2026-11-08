"""Daily paper ingestion pipeline.

Extracted from ``scripts/daily_fetch.py`` so it can be triggered both by the
CLI script and by an authenticated internal HTTP endpoint (for scheduled
runs on Fly machines or GitHub Actions).
"""
import asyncio
import logging
import re
from datetime import datetime, timedelta, timezone
from typing import Any, Awaitable, Callable

from models.schemas import AgentStep

logger = logging.getLogger(__name__)

MAX_EMBED_BATCH = 100
SUMMARY_BATCH_SIZE = 5
_TOKEN_RE = re.compile(r"[a-z0-9]+")


def _as_utc(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)
    if isinstance(value, str) and value:
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            return parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed.astimezone(timezone.utc)
        except ValueError:
            return None
    return None


def _watchlist_matches(query: str, paper: dict) -> bool:
    normalized_query = " ".join(_TOKEN_RE.findall(query.lower()))
    if not normalized_query:
        return False
    title = str(paper.get("title") or "")
    abstract = str(paper.get("abstract") or "")
    normalized_text = " ".join(_TOKEN_RE.findall(f"{title} {abstract}".lower()))
    if normalized_query in normalized_text:
        return True
    terms = set(normalized_query.split())
    if not terms:
        return False
    overlap = terms.intersection(normalized_text.split())
    # Require at least two thirds of query terms to match. A lone query term
    # must match exactly in a title or abstract token.
    return len(overlap) == len(terms) if len(terms) == 1 else len(overlap) / len(terms) >= 2 / 3


async def _notify_watchlists(
    supabase,
    papers: list[dict],
    *,
    now: datetime | None = None,
    sources_complete: bool = True,
) -> int:
    """Deliver idempotent, cadence-aware in-app alerts for recent papers.

    A notification is one row per (user, watchlist, paper). The database
    unique index added in migration 0007 makes retries safe.
    """
    now = now or datetime.now(timezone.utc)
    now = now.replace(tzinfo=timezone.utc) if now.tzinfo is None else now.astimezone(timezone.utc)
    notified = 0
    try:
        response = await (
            supabase.table("watchlists")
            .select("id,user_id,query,cadence,enabled,last_checked_at")
            .eq("enabled", True)
            .execute()
        )
    except Exception:
        logger.exception("Could not load enabled watchlists")
        return 0

    for watch in response.data or []:
        query = str(watch.get("query") or "").strip()
        cadence = watch.get("cadence", "daily")
        interval = timedelta(days=7) if cadence == "weekly" else timedelta(days=1)
        last_checked = _as_utc(watch.get("last_checked_at"))
        if last_checked and now - last_checked < interval:
            continue
        since = last_checked or now - interval
        matches = [
            paper for paper in papers
            if paper.get("id")
            and (published := _as_utc(paper.get("published_at"))) is not None
            and published >= since
            and _watchlist_matches(query, paper)
        ][:5]

        try:
            if matches:
                rows = [
                    {
                        "user_id": watch["user_id"],
                        "watchlist_id": watch["id"],
                        "kind": "watchlist",
                        "title": f"New paper for {query}"[:200],
                        "body": str(paper.get("title") or "")[:200],
                        "paper_id": paper["id"],
                    }
                    for paper in matches
                ]
                await (
                    supabase.table("notifications")
                    .upsert(
                        rows,
                        on_conflict="user_id,watchlist_id,paper_id",
                        ignore_duplicates=True,
                    )
                    .execute()
                )
                notified += len(matches)

            # Do not move the cursor after a partial provider outage. The
            # idempotency index prevents duplicates on the next full run.
            if sources_complete:
                await (
                    supabase.table("watchlists")
                    .update({"last_checked_at": now.isoformat()})
                    .eq("id", watch["id"])
                    .eq("user_id", watch["user_id"])
                    .execute()
                )
        except Exception:
            logger.exception("Could not process watchlist %s", watch.get("id"))
    return notified


async def _noop_callback(step: AgentStep) -> None:
    pass


async def run_daily_fetch(
    max_results: int = 200,
    callback: Callable[[AgentStep], Awaitable[None]] | None = None,
) -> dict[str, Any]:
    """Fetch, embed, store, and summarise newly published papers."""
    from services.arxiv import fetch_latest_papers
    from services.huggingface import fetch_hf_daily
    from services.embeddings import embed_texts
    from services.retry import async_retry
    from services.supabase_client import get_supabase
    from agents.summary_agent import summary_agent

    cb = callback or _noop_callback
    supabase = await get_supabase()

    logger.info("Fetching ArXiv papers...")
    arxiv_papers = await fetch_latest_papers(max_results=max_results)
    logger.info("Found %s ArXiv papers", len(arxiv_papers))

    logger.info("Fetching HuggingFace daily papers...")
    sources_complete = True
    try:
        hf_papers = await fetch_hf_daily()
    except Exception as exc:
        logger.warning("HF fetch failed: %s", exc)
        hf_papers = []
        sources_complete = False
    logger.info("Found %s HF papers", len(hf_papers))

    deduped = {p["id"]: p for p in arxiv_papers + hf_papers}
    papers = list(deduped.values())

    response = await supabase.table("papers").select("id").execute()
    existing_ids = {row["id"] for row in (response.data or [])}
    new_papers = [p for p in papers if p["id"] not in existing_ids]
    logger.info("%s new papers to insert", len(new_papers))

    if not new_papers:
        notified = await _notify_watchlists(
            supabase, papers, sources_complete=sources_complete
        )
        return {
            "fetched": len(papers),
            "inserted": 0,
            "summarised": 0,
            "watchlists_notified": notified,
        }

    texts = [f"{p['title']}\n{p['abstract']}" for p in new_papers]
    try:
        embeddings = await embed_texts(texts)
    except Exception as exc:
        logger.warning("Embedding failed: %s", exc)
        embeddings = [None] * len(new_papers)

    rows = []
    for p, emb in zip(new_papers, embeddings):
        rows.append({
            "id": p["id"],
            "title": p["title"],
            "abstract": p["abstract"],
            "authors": p.get("authors", []),
            "url": p.get("url", ""),
            "published_at": p.get("published_at"),
            "embedding": emb,
        })

    for i in range(0, len(rows), MAX_EMBED_BATCH):
        batch = rows[i:i + MAX_EMBED_BATCH]

        async def _upsert(b=batch):
            return await supabase.table("papers").upsert(b).execute()

        await async_retry(_upsert, max_retries=3, base_delay=1.0)
        logger.info("Inserted batch %s", i // MAX_EMBED_BATCH + 1)

    summarised = 0
    try:
        for i in range(0, len(new_papers), SUMMARY_BATCH_SIZE):
            batch = new_papers[i:i + SUMMARY_BATCH_SIZE]
            paper_dicts = [
                {"id": p["id"], "title": p["title"], "abstract": p["abstract"]}
                for p in batch
            ]
            enriched = await summary_agent(paper_dicts, cb)
            for paper in enriched:
                if paper.get("summary_tldr"):
                    summarised += 1
                async def _update(p=paper):
                    return await supabase.table("papers").update({
                        "summary_tldr": p.get("summary_tldr"),
                        "difficulty": p.get("difficulty", "intermediate"),
                    }).eq("id", p["id"]).execute()

                await async_retry(_update, max_retries=3, base_delay=1.0)
            logger.info("Summarised batch %s", i // SUMMARY_BATCH_SIZE + 1)
            if i + SUMMARY_BATCH_SIZE < len(new_papers):
                await asyncio.sleep(2)
    except Exception as exc:
        logger.warning("Summary generation failed: %s", exc)

    notified = await _notify_watchlists(
        supabase, papers, sources_complete=sources_complete
    )

    return {
        "fetched": len(papers),
        "inserted": len(new_papers),
        "summarised": summarised,
        "watchlists_notified": notified,
    }
