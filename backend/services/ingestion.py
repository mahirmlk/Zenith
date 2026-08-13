"""Daily paper ingestion pipeline.

Extracted from ``scripts/daily_fetch.py`` so it can be triggered both by the
CLI script and by an authenticated internal HTTP endpoint (for scheduled
runs on Fly machines or GitHub Actions).
"""
import asyncio
import logging
from typing import Any, Awaitable, Callable

from models.schemas import AgentStep

logger = logging.getLogger(__name__)

MAX_EMBED_BATCH = 100
SUMMARY_BATCH_SIZE = 5


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
    supabase = get_supabase()

    logger.info("Fetching ArXiv papers...")
    arxiv_papers = await fetch_latest_papers(max_results=max_results)
    logger.info("Found %s ArXiv papers", len(arxiv_papers))

    logger.info("Fetching HuggingFace daily papers...")
    try:
        hf_papers = await fetch_hf_daily()
    except Exception as exc:
        logger.warning("HF fetch failed: %s", exc)
        hf_papers = []
    logger.info("Found %s HF papers", len(hf_papers))

    deduped = {p["id"]: p for p in arxiv_papers + hf_papers}
    papers = list(deduped.values())

    def _existing_ids():
        response = supabase.table("papers").select("id").execute()
        return {row["id"] for row in (response.data or [])}

    existing_ids = await asyncio.to_thread(_existing_ids)
    new_papers = [p for p in papers if p["id"] not in existing_ids]
    logger.info("%s new papers to insert", len(new_papers))

    if not new_papers:
        return {"fetched": len(papers), "inserted": 0, "summarised": 0}

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
        await async_retry(
            lambda b=batch: asyncio.to_thread(lambda: supabase.table("papers").upsert(b).execute()),
            max_retries=3,
            base_delay=1.0,
        )
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
                await async_retry(
                    lambda p=paper: asyncio.to_thread(
                        lambda: supabase.table("papers")
                        .update({
                            "summary_tldr": p.get("summary_tldr"),
                            "difficulty": p.get("difficulty", "intermediate"),
                        })
                        .eq("id", p["id"])
                        .execute()
                    ),
                    max_retries=3,
                    base_delay=1.0,
                )
            logger.info("Summarised batch %s", i // SUMMARY_BATCH_SIZE + 1)
            if i + SUMMARY_BATCH_SIZE < len(new_papers):
                await asyncio.sleep(2)
    except Exception as exc:
        logger.warning("Summary generation failed: %s", exc)

    return {"fetched": len(papers), "inserted": len(new_papers), "summarised": summarised}