"""Offline tests for source-attributed arXiv record metadata."""
from datetime import datetime, timezone

import arxiv
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
        links=[arxiv.Result.Link("https://arxiv.org/pdf/2401.12345v2", rel="related", content_type="application/pdf")],
    )


def test_paper_record_keeps_canonical_id_version_and_update_time():
    record = arxiv_service._paper_record(make_result(2))

    assert record["id"] == "2401.12345v2"
    assert record["preprint_id"] == "2401.12345"
    assert record["source_version"] == 2
    assert record["source_updated_at"] == "2026-11-12T00:00:00+00:00"
    assert record["published_at"] == "2024-01-01T00:00:00+00:00"


def test_paper_record_keeps_legacy_id_stable_and_normalizes_versionless_id():
    result = make_result(2)
    result.entry_id = "https://arxiv.org/abs/hep-ex/0307015v2"

    record = arxiv_service._paper_record(result)

    assert record["id"] == "0307015v2"
    assert record["preprint_id"] == "0307015"
    assert record["source_version"] == 2


@pytest.mark.asyncio
async def test_updated_paper_poll_uses_last_updated_sort_and_marks_saturation(monkeypatch):
    captured = []

    class FakeClient:
        def results(self, search):
            captured.append(search)
            return iter([make_result(2)])

    monkeypatch.setattr(arxiv_service, "client", FakeClient())
    records, complete = await arxiv_service.fetch_recently_updated_papers(
        categories=["cs.AI"], max_results=2
    )

    assert captured[0].sort_by == arxiv.SortCriterion.LastUpdatedDate
    assert captured[0].query == "cat:cs.AI"
    assert records[0]["source_version"] == 2
    assert complete is True


@pytest.mark.asyncio
async def test_updated_paper_poll_at_result_bound_is_incomplete(monkeypatch):
    class FakeClient:
        def results(self, _search):
            return iter([make_result(2)])

    monkeypatch.setattr(arxiv_service, "client", FakeClient())
    records, complete = await arxiv_service.fetch_recently_updated_papers(
        categories=["cs.AI"], max_results=1
    )

    assert len(records) == 1
    assert complete is False
