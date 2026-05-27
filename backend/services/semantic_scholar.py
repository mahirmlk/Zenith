import httpx
from config import get_settings
from services.retry import async_retry

S2_API_URL = "https://api.semanticscholar.org/graph/v1"


async def get_paper_citations(paper_id: str, limit: int = 20) -> dict:
    settings = get_settings()
    headers = {}
    if settings.semantic_scholar_api_key:
        headers["x-api-key"] = settings.semantic_scholar_api_key

    async def _fetch():
        async with httpx.AsyncClient() as client:
            r = await client.get(
                f"{S2_API_URL}/paper/{paper_id}",
                params={"fields": "title,authors,year,citationCount,references,paperId", "limit": limit},
                headers=headers,
            )
            r.raise_for_status()
            return r.json()

    return await async_retry(_fetch, max_retries=3, base_delay=1.0)
