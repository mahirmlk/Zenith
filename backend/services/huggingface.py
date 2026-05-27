import httpx
from services.retry import async_retry

HF_DAILY_URL = "https://huggingface.co/api/daily_papers"


async def fetch_hf_daily(date: str | None = None) -> list[dict]:
    params = {}
    if date:
        params["date"] = date

    async def _fetch():
        async with httpx.AsyncClient() as client:
            r = await client.get(HF_DAILY_URL, params=params)
            r.raise_for_status()
            return r.json()

    data = await async_retry(_fetch, max_retries=3, base_delay=1.0)
    papers = []
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
