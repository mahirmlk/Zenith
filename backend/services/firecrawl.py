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
    return result.get("markdown", "")


async def crawl_paper_cached(paper_id: str, url: str) -> str:
    """Crawl a paper URL, caching the result in Supabase keyed by paper ID.

    Full-text crawls are the most expensive external call per paper and
    popular papers get re-crawled across users, so the fetched markdown is
    stored once in the ``crawled_content`` table and served from cache on
    subsequent requests.
    """
    try:
        from services.supabase_client import get_supabase

        supabase = get_supabase()

        def _get_cached():
            response = (
                supabase.table("crawled_content")
                .select("content")
                .eq("paper_id", paper_id)
                .maybe_single()
                .execute()
            )
            return response.data.get("content") if response.data else None

        cached = await asyncio.to_thread(_get_cached)
        if cached:
            return cached

        content = await asyncio.to_thread(crawl_paper, url)

        def _store():
            return supabase.table("crawled_content").upsert({
                "paper_id": paper_id,
                "url": url,
                "content": content,
            }).execute()

        await asyncio.to_thread(_store)
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