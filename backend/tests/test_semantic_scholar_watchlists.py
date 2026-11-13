"""Offline contract tests for provider-backed author and citation watchlists."""
from datetime import datetime, timezone

import httpx
import pytest

from services import semantic_scholar


def test_provider_paper_uses_arxiv_identity_when_available():
    paper = semantic_scholar._paper_record({
        "paperId": "s2-hash",
        "title": "A study",
        "abstract": "Evidence",
        "externalIds": {"ArXiv": "2601.12345"},
        "authors": [{"name": "Ada"}],
        "publicationDate": "2026-01-04",
    })

    assert paper == {
        "id": "2601.12345",
        "title": "A study",
        "abstract": "Evidence",
        "authors": ["Ada"],
        "url": "https://www.semanticscholar.org/paper/s2-hash",
        "published_at": "2026-01-04T00:00:00+00:00",
    }


@pytest.mark.asyncio
async def test_citation_watch_reads_citing_papers_and_author_watch_reads_author_papers(monkeypatch):
    requests = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.path.endswith("/citations"):
            data = [{"citingPaper": {"paperId": "citing-id", "title": "New work", "year": 2026}}]
        else:
            data = [{"paperId": "author-paper", "title": "Author work", "year": 2026}]
        return httpx.Response(200, json={"data": data})

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    monkeypatch.setattr(semantic_scholar, "_get_client", lambda: client)
    since = datetime(2026, 1, 1, tzinfo=timezone.utc)
    try:
        citing = await semantic_scholar.fetch_watch_papers("citation", "seed-id", since)
        authored = await semantic_scholar.fetch_watch_papers("author", "author-id", since)
    finally:
        await client.aclose()

    assert citing[0]["id"] == "citing-id"
    assert citing[0]["title"] == "New work"
    assert authored[0]["id"] == "author-paper"
    assert requests[0].url.path.endswith("/paper/seed-id/citations")
    assert "citingPaper.title" in requests[0].url.params["fields"]
    assert requests[1].url.path.endswith("/author/author-id/papers")


@pytest.mark.asyncio
async def test_watch_poll_fails_closed_when_provider_pagination_is_truncated(monkeypatch):
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"data": [{"paperId": str(index)} for index in range(100)]})

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    monkeypatch.setattr(semantic_scholar, "_get_client", lambda: client)
    try:
        with pytest.raises(RuntimeError, match="pagination bound"):
            await semantic_scholar.fetch_watch_papers(
                "author", "author-id", datetime(2026, 1, 1, tzinfo=timezone.utc), max_pages=1
            )
    finally:
        await client.aclose()
