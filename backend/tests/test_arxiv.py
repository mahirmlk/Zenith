"""Offline tests for source-attributed arXiv record metadata."""
from datetime import datetime, timezone

import arxiv
import httpx
import pytest

from services import arxiv as arxiv_service


def make_result(version: int) -> arxiv.Result:
    published = datetime(2024, 1, 1, tzinfo=timezone.utc)
    updated = datetime(2026, 11, 12, tzinfo=timezone.utc)
    return arxiv.Result(
        entry_id=f"https://arxiv.org/abs/2401.12345v{version}",
        updated=updated,
        published=published,
        title="Graph retrieval",
        authors=[arxiv.Result.Author("A. Researcher")],
        summary="A paper about graph retrieval.",
        doi="10.1234/graph-retrieval",
        links=[arxiv.Result.Link("https://arxiv.org/pdf/2401.12345v2", rel="related", content_type="application/pdf")],
    )


def test_paper_record_keeps_canonical_id_version_and_update_time():
    record = arxiv_service._paper_record(make_result(2))

    assert record["id"] == "2401.12345v2"
    assert record["preprint_id"] == "2401.12345"
    assert record["source_version"] == 2
    assert record["source_updated_at"] == "2026-11-12T00:00:00+00:00"
    assert record["published_at"] == "2024-01-01T00:00:00+00:00"
    assert record["doi"] == "10.1234/graph-retrieval"


def test_paper_record_keeps_legacy_id_stable_and_normalizes_versionless_id():
    result = make_result(2)
    result.entry_id = "https://arxiv.org/abs/hep-ex/0307015v2"

    record = arxiv_service._paper_record(result)

    assert record["id"] == "0307015v2"
    assert record["preprint_id"] == "hep-ex/0307015"
    assert record["source_version"] == 2


@pytest.mark.asyncio
async def test_updated_paper_poll_uses_last_updated_sort_and_marks_saturation(monkeypatch):
    captured = []
    async def fake_search(query, max_results, sort_by):
        captured.append((query, max_results, sort_by))
        return [arxiv_service._paper_record(make_result(2))]

    monkeypatch.setattr(arxiv_service, "_search_papers", fake_search)
    records, complete = await arxiv_service.fetch_recently_updated_papers(
        categories=["cs.AI"], max_results=2
    )

    assert captured[0] == ("cat:cs.AI", 2, arxiv.SortCriterion.LastUpdatedDate)
    assert records[0]["source_version"] == 2
    assert complete is True


@pytest.mark.asyncio
async def test_updated_paper_poll_at_result_bound_is_incomplete(monkeypatch):
    async def fake_search(_query, _max_results, _sort_by):
        return [arxiv_service._paper_record(make_result(2))]

    monkeypatch.setattr(arxiv_service, "_search_papers", fake_search)
    records, complete = await arxiv_service.fetch_recently_updated_papers(
        categories=["cs.AI"], max_results=1
    )

    assert len(records) == 1
    assert complete is False


def atom_feed(version: int, total: int = 1) -> bytes:
    return f'''<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom"
      xmlns:opensearch="http://a9.com/-/spec/opensearch/1.1/"
      xmlns:arxiv="http://arxiv.org/schemas/atom">
  <opensearch:totalResults>{total}</opensearch:totalResults>
  <entry>
    <id>https://arxiv.org/abs/2401.12345v{version}</id>
    <updated>2026-11-12T00:00:00Z</updated>
    <published>2024-01-01T00:00:00Z</published>
    <title>Graph retrieval</title><summary>A paper about graph retrieval.</summary>
    <author><name>A. Researcher</name></author>
    <link title="pdf" href="https://arxiv.org/pdf/2401.12345v{version}.pdf"/>
    <arxiv:doi>10.1234/graph-retrieval</arxiv:doi>
  </entry>
</feed>'''.encode()


@pytest.mark.asyncio
async def test_arxiv_query_keeps_result_parser_sort_maximum_and_shared_gate(monkeypatch):
    calls = []

    class FakeGate:
        async def before_request(self):
            calls.append("gate")

    from contextlib import asynccontextmanager

    @asynccontextmanager
    async def fake_session():
        yield FakeGate()

    monkeypatch.setattr(arxiv_service, "arxiv_api_session", fake_session)

    def respond(request):
        calls.append(request)
        return httpx.Response(200, content=atom_feed(3), request=request)

    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as http:
        records = await arxiv_service._search_papers(
            "cat:cs.AI", 1, arxiv.SortCriterion.LastUpdatedDate, http_client=http
        )

    request = next(item for item in calls if isinstance(item, httpx.Request))
    assert request.url.host == "export.arxiv.org"
    assert request.url.params["search_query"] == "cat:cs.AI"
    assert request.url.params["sortBy"] == "lastUpdatedDate"
    assert request.url.params["max_results"] == "1"
    assert records[0]["id"] == "2401.12345v3"
    assert records[0]["source_version"] == 3
    assert records[0]["authors"] == ["A. Researcher"]
    assert records[0]["doi"] == "10.1234/graph-retrieval"
    assert calls[0] == "gate"
