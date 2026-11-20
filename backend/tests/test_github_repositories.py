"""GitHub repository discovery tests; no live requests are made."""
from __future__ import annotations

import httpx
import pytest

from services import github_repositories


@pytest.mark.asyncio
async def test_searches_public_repositories_by_identifier_and_sanitizes_title(monkeypatch):
    queries: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        queries.append(request.url.params["q"])
        return httpx.Response(
            200,
            json={
                "total_count": 2,
                "incomplete_results": False,
                "items": [
                    {
                        "html_url": "https://github.com/lab/model.git",
                        "stargazers_count": 12,
                        "private": False,
                    },
                    {"html_url": "https://github.com/lab/model", "stargazers_count": 99},
                    {"html_url": "https://evil.example/lab/model", "stargazers_count": 500},
                    {"html_url": "https://github.com/other/private", "private": True, "stargazers_count": 80},
                ],
            },
        )

    monkeypatch.setattr(github_repositories, "get_settings", lambda: type("Settings", (), {"github_token": ""})())
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await github_repositories.search_paper_repositories(
            {
                "id": "2301.01234v2",
                "title": "A Study: Ignore user:someone OR is:private!",
            },
            client=client,
        )

    assert len(queries) == 1
    assert '"2301.01234v2" is:public' == queries[0]
    assert result["source"] == "github"
    assert result["repos"] == [{"url": "https://github.com/lab/model", "stars": 12}]


@pytest.mark.asyncio
async def test_doi_is_used_before_arxiv_or_title(monkeypatch):
    monkeypatch.setattr(github_repositories, "get_settings", lambda: type("Settings", (), {"github_token": ""})())
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.url.params["q"])
        return httpx.Response(200, json={"total_count": 0, "items": []})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        await github_repositories.search_paper_repositories(
            {"id": "2301.01234", "doi": "https://doi.org/10.1234/ABC", "title": "Paper title"},
            client=client,
        )

    assert seen == ['"10.1234/ABC" is:public']


@pytest.mark.asyncio
async def test_search_fails_closed_and_rejects_missing_identifiers(monkeypatch):
    monkeypatch.setattr(github_repositories, "get_settings", lambda: type("Settings", (), {"github_token": ""})())
    missing = await github_repositories.search_paper_repositories({"title": "!!!"})
    assert missing["source_error"] == "paper_identifier_missing"

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(403, json={"message": "rate limit"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await github_repositories.search_paper_repositories({"id": "2301.01234"}, client=client)
    assert result == {"repos": [], "source": "github", "source_error": "http_403"}


@pytest.mark.asyncio
async def test_title_is_used_when_no_strong_identifier_exists(monkeypatch):
    monkeypatch.setattr(github_repositories, "get_settings", lambda: type("Settings", (), {"github_token": ""})())
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.url.params["q"])
        return httpx.Response(200, json={"items": []})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        await github_repositories.search_paper_repositories(
            {"id": "paper-uuid", "title": "A Study: Ignore user:someone OR is:private!"}, client=client
        )

    assert len(seen) == 1
    assert "user:someone" not in seen[0]
    assert "is:private" not in seen[0]
    assert seen[0].endswith("is:public")


@pytest.mark.asyncio
async def test_oversized_source_identifier_falls_back_to_bounded_title(monkeypatch):
    monkeypatch.setattr(github_repositories, "get_settings", lambda: type("Settings", (), {"github_token": ""})())
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.url.params["q"])
        return httpx.Response(200, json={"items": []})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        await github_repositories.search_paper_repositories(
            {"id": "x/" + "1" * 90, "title": "Bounded title"}, client=client
        )

    assert seen == ['"Bounded title" is:public']


@pytest.mark.asyncio
async def test_optional_token_is_sent_only_to_github_public_search(monkeypatch):
    monkeypatch.setattr(
        github_repositories,
        "get_settings",
        lambda: type("Settings", (), {"github_token": "ghp-test-only"})(),
    )
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={"items": []})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        await github_repositories.search_paper_repositories({"id": "2301.77777"}, client=client)

    assert len(seen) == 1
    assert seen[0].url.host == "api.github.com"
    assert seen[0].headers["Authorization"] == "Bearer ghp-test-only"
    assert seen[0].url.params["q"].endswith("is:public")
