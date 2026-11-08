import httpx
from config import get_settings
from services.retry import async_retry
from typing import Any

S2_API_URL = "https://api.semanticscholar.org/graph/v1"

# Shared async client with connection pooling
_http_client: httpx.AsyncClient | None = None


def _get_client() -> httpx.AsyncClient:
    global _http_client
    if _http_client is None or _http_client.is_closed:
        _http_client = httpx.AsyncClient(timeout=30.0, limits=httpx.Limits(max_connections=5))
    return _http_client


async def get_paper_citations(paper_id: str, limit: int = 20) -> dict[str, Any]:
    settings = get_settings()
    headers: dict[str, str] = {}
    if settings.semantic_scholar_api_key:
        headers["x-api-key"] = settings.semantic_scholar_api_key

    async def _fetch() -> Any:
        client = _get_client()
        r = await client.get(
            f"{S2_API_URL}/paper/{paper_id}",
            params={"fields": "title,authors,year,citationCount,references,paperId", "limit": limit},
            headers=headers,
        )
        r.raise_for_status()
        return r.json()

    return await async_retry(_fetch, max_retries=3, base_delay=1.0)
