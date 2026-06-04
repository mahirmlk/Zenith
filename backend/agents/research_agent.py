from typing import Callable, Awaitable
import asyncio
from models.schemas import AgentStep


try:
    from services.arxiv import search_arxiv
except Exception:
    search_arxiv = None  # type: ignore[misc]

try:
    from services.huggingface import fetch_hf_daily
except Exception:
    fetch_hf_daily = None  # type: ignore[misc]


async def research_agent(
    query: str,
    callback: Callable[[AgentStep], Awaitable[None]],
) -> list[dict]:
    await callback(AgentStep(agent="research", status="fetching_arxiv"))

    async def _fetch_arxiv():
        if search_arxiv is not None:
            return await search_arxiv(query, max_results=20)
        return []

    async def _fetch_hf():
        if fetch_hf_daily is not None:
            try:
                return await fetch_hf_daily()
            except Exception:
                return []
        return []

    arxiv_papers, hf_papers = await asyncio.gather(_fetch_arxiv(), _fetch_hf())

    await callback(AgentStep(agent="research", status="arxiv_fetched", count=len(arxiv_papers)))
    await callback(AgentStep(agent="research", status="huggingface_fetched", count=len(hf_papers)))

    # Deduplicate by ID
    seen = set()
    papers = []
    for p in arxiv_papers + hf_papers:
        pid = p.get("id", "")
        if pid and pid not in seen:
            seen.add(pid)
            papers.append(p)

    await callback(AgentStep(agent="research", status="deduplication_complete", count=len(papers)))
    return papers
