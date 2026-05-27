import asyncio
from typing import Optional
import arxiv
from services.retry import async_retry

client = arxiv.Client()


async def search_arxiv(query: str, max_results: int = 20) -> list[dict]:
    search = arxiv.Search(
        query=query,
        max_results=max_results,
        sort_by=arxiv.SortCriterion.SubmittedDate,
    )

    results = []
    loop = asyncio.get_event_loop()

    def _fetch():
        for result in client.results(search):
            results.append({
                "id": result.entry_id.split("/")[-1],
                "title": result.title,
                "abstract": result.summary,
                "url": result.pdf_url,
                "authors": [a.name for a in result.authors],
                "published_at": result.published.isoformat(),
            })
        return results

    async def _fetch_async():
        return await loop.run_in_executor(None, _fetch)

    return await async_retry(_fetch_async, max_retries=3, base_delay=1.0)


async def fetch_latest_papers(categories: Optional[list[str]] = None, max_results: int = 50) -> list[dict]:
    cats = categories or ["cs.AI", "cs.LG", "cs.CL", "stat.ML"]
    query = " OR ".join(f"cat:{c}" for c in cats)
    return await search_arxiv(query, max_results)
