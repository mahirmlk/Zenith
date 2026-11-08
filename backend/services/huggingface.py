import httpx
from typing import Any
from services.retry import async_retry

HF_DAILY_URL = "https://huggingface.co/api/daily_papers"

# Shared async client with connection pooling
_http_client: httpx.AsyncClient | None = None
PaperRecord = dict[str, Any]


def _get_client() -> httpx.AsyncClient:
    global _http_client
    if _http_client is None or _http_client.is_closed:
        _http_client = httpx.AsyncClient(timeout=30.0, limits=httpx.Limits(max_connections=10))
    return _http_client


async def fetch_hf_daily(date: str | None = None) -> list[PaperRecord]:
    params: dict[str, str] = {}
    if date:
        params["date"] = date

    async def _fetch() -> Any:
        client = _get_client()
        r = await client.get(HF_DAILY_URL, params=params)
        r.raise_for_status()
        return r.json()

    data = await async_retry(_fetch, max_retries=3, base_delay=1.0)
    papers: list[PaperRecord] = []
    for item in data:
        paper = item.get("paper", {})
        papers.append({
            "id": paper.get("id", ""),
            "title": paper.get("title", ""),
            "abstract": paper.get("summary", ""),
            "url": paper.get("url", ""),
            "authors": [a.get("name", "") for a in paper.get("authors", [])],
            "published_at": item.get("publishedAt", ""),
        })
    return papers
