from typing import Callable, Awaitable
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
    if search_arxiv is not None:
        arxiv_papers = await search_arxiv(query, max_results=20)
    else:
        arxiv_papers = []
    await callback(AgentStep(agent="research", status="arxiv_fetched", count=len(arxiv_papers)))

    await callback(AgentStep(agent="research", status="fetching_huggingface"))
    if fetch_hf_daily is not None:
        try:
            hf_papers = await fetch_hf_daily()
        except Exception:
            hf_papers = []
    else:
        hf_papers = []
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
