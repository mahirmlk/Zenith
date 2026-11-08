from typing import Any, Awaitable, Callable, cast
import asyncio
from models.schemas import AgentStep


PaperData = dict[str, Any]
ArxivSearch = Callable[[str, int], Awaitable[list[PaperData]]]
HuggingFaceFetch = Callable[[], Awaitable[list[PaperData]]]

try:
    from services.arxiv import search_arxiv as _search_arxiv
except ImportError:
    search_arxiv: ArxivSearch | None = None
else:
    search_arxiv = cast(ArxivSearch, _search_arxiv)

try:
    from services.huggingface import fetch_hf_daily as _fetch_hf_daily
except ImportError:
    fetch_hf_daily: HuggingFaceFetch | None = None
else:
    fetch_hf_daily = cast(HuggingFaceFetch, _fetch_hf_daily)


async def research_agent(
    query: str,
    callback: Callable[[AgentStep], Awaitable[None]],
) -> list[PaperData]:
    await callback(AgentStep(agent="research", status="fetching_arxiv"))

    async def _fetch_arxiv() -> list[PaperData]:
        if search_arxiv is not None:
            return await search_arxiv(query, 20)
        return []

    async def _fetch_hf() -> list[PaperData]:
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
    seen: set[str] = set()
    papers: list[PaperData] = []
    for p in arxiv_papers + hf_papers:
        pid = p.get("id", "")
        if pid and pid not in seen:
            seen.add(pid)
            papers.append(p)

    await callback(AgentStep(agent="research", status="deduplication_complete", count=len(papers)))
    return papers
