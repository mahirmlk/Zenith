import asyncio
from firecrawl import FirecrawlApp
from config import get_settings

_app: FirecrawlApp | None = None


def get_firecrawl_app() -> FirecrawlApp:
    global _app
    if _app is None:
        settings = get_settings()
        if not settings.firecrawl_api_key:
            raise RuntimeError("FIRECRAWL_API_KEY not configured")
        _app = FirecrawlApp(api_key=settings.firecrawl_api_key)
    return _app


def crawl_paper(url: str) -> str:
    """Crawl a paper URL and return clean markdown content."""
    from services.ssrf import validate_public_url

    validate_public_url(url)
    app = get_firecrawl_app()
    result = app.scrape_url(url, params={"formats": ["markdown"]})
    markdown = result.get("markdown", "")
    return markdown if isinstance(markdown, str) else ""


async def crawl_paper_cached(paper_id: str, url: str) -> str:
    """Crawl a paper URL, caching the result in Supabase keyed by paper ID.

    Full-text crawls are the most expensive external call per paper and
    popular papers get re-crawled across users, so the fetched markdown is
    stored once in the ``crawled_content`` table and served from cache on
    subsequent requests.
    """
    try:
        from services.supabase_client import get_supabase

        supabase = await get_supabase()

        response = (
            await supabase.table("crawled_content")
            .select("content")
            .eq("paper_id", paper_id)
            .maybe_single()
            .execute()
        )
        cached = response.data.get("content") if isinstance(response.data, dict) else None
        if isinstance(cached, str) and cached:
            return cached

        content = await asyncio.to_thread(crawl_paper, url)

        await supabase.table("crawled_content").upsert({
            "paper_id": paper_id,
            "url": url,
            "content": content,
        }).execute()
        return content
    except Exception:
        # If Supabase caching is unavailable, fall back to a direct crawl.
        return await asyncio.to_thread(crawl_paper, url)


def is_available() -> bool:
    """Check if Firecrawl is configured and available."""
    try:
        settings = get_settings()
        return bool(settings.firecrawl_api_key)
    except Exception:
        return False
