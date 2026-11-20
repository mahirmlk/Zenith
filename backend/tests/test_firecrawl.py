"""Hosted paper crawling stays disabled until fetch-time controls are available."""

import pytest

from services import firecrawl


@pytest.mark.parametrize("url", ["https://example.org/paper", "http://127.0.0.1/admin"])
def test_direct_crawl_fails_closed(url: str) -> None:
    with pytest.raises(RuntimeError, match="redirect and egress controls"):
        firecrawl.crawl_paper(url)


def test_cached_crawl_fails_closed_without_reading_legacy_cache(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from services import supabase_client

    async def forbidden_cache_read() -> None:
        pytest.fail("disabled crawling must not read or write the legacy cache")

    monkeypatch.setattr(supabase_client, "get_supabase", forbidden_cache_read)
    with pytest.raises(RuntimeError, match="redirect and egress controls"):
        firecrawl.crawl_paper_cached("paper-1", "https://example.org/paper").send(None)


def test_service_reports_unavailable() -> None:
    assert firecrawl.is_available() is False
