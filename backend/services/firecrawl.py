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
    app = get_firecrawl_app()
    result = app.scrape_url(url, params={"formats": ["markdown"]})
    return result.get("markdown", "")
