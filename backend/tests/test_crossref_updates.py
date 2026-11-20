"""Offline tests for Crossref's DOI update relation contract."""

import httpx
import pytest

from services.crossref_updates import (
    CrossrefUnavailable,
    lookup_crossref_updates,
    normalize_doi,
    parse_update_relations,
)


DOI = "10.1234/original.work"


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("10.1234/ABC", "10.1234/abc"),
        ("https://doi.org/10.1234/ABC", "10.1234/abc"),
        ("HTTP://DX.DOI.ORG/10.1234/ABC", "10.1234/abc"),
        ("not-a-doi", None),
        ("10.12/a", None),
        ("10.1234/a\nInjected", None),
    ],
)
def test_normalize_doi(raw, expected):
    assert normalize_doi(raw) == expected


def test_parse_supported_update_types_and_ignore_other_relations():
    types = ["retraction", "partial_retraction", "withdrawal", "removal", "expression_of_concern"]
    relations = [
        {
            "type": update_type,
            "DOI": f"10.9999/notice-{index}",
            "label": update_type.replace("_", " ").title(),
            "updated": {"date-parts": [[2025, 2, index + 1]]},
        }
        for index, update_type in enumerate(types)
    ]
    relations.extend(
        [
            {"type": "correction", "DOI": "10.9999/correction"},
            {"type": "retraction", "DOI": "invalid"},
            "malformed relation",
        ]
    )

    updates = parse_update_relations({"message": {"update-to": relations}})

    assert [update.update_type for update in updates] == types
    assert updates[0].notice_doi == "10.9999/notice-0"
    assert updates[0].updated_at.isoformat() == "2025-02-01"


def test_parse_preserves_only_known_notice_deposit_sources():
    updates = parse_update_relations(
        {
            "message": {
                "update-to": [
                    {"type": "retraction", "DOI": "10.9999/publisher", "source": "publisher"},
                    {"type": "withdrawal", "DOI": "10.9999/rw", "source": "retraction-watch"},
                    {"type": "removal", "DOI": "10.9999/unknown", "source": "unknown-source"},
                    {"type": "expression_of_concern", "DOI": "10.9999/missing"},
                    {"type": "partial_retraction", "DOI": "10.9999/malformed", "source": []},
                ]
            }
        }
    )

    assert [update.deposit_source for update in updates] == [
        "publisher",
        "retraction-watch",
        None,
        None,
        None,
    ]


def test_empty_crossref_relations_are_empty_metadata_not_negative_status():
    assert parse_update_relations({"message": {"DOI": DOI, "update-to": []}}) == ()


@pytest.mark.asyncio
async def test_lookup_quotes_doi_and_returns_sourced_relations():
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(
            200,
            json={
                "message": {
                    "DOI": DOI,
                    "update-to": [{"type": "retraction", "DOI": "10.9999/notice"}],
                }
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await lookup_crossref_updates(DOI, client=client)

    assert result.record_found is True
    assert result.updates[0].update_type == "retraction"
    assert str(seen[0].url).endswith("10.1234%2Foriginal.work")


@pytest.mark.asyncio
async def test_lookup_treats_missing_doi_record_as_unknown_metadata():
    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda _request: httpx.Response(404))) as client:
        result = await lookup_crossref_updates(DOI, client=client)

    assert result.record_found is False
    assert result.updates == ()


@pytest.mark.asyncio
async def test_lookup_retries_provider_failures_and_rejects_mismatched_records():
    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda _request: httpx.Response(503))) as client:
        with pytest.raises(CrossrefUnavailable):
            await lookup_crossref_updates(DOI, client=client)

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda _request: httpx.Response(200, json={"message": {"DOI": "10.1234/different", "update-to": []}})
        )
    ) as client:
        with pytest.raises(CrossrefUnavailable):
            await lookup_crossref_updates(DOI, client=client)


@pytest.mark.asyncio
async def test_lookup_rejects_invalid_doi_without_network_access():
    with pytest.raises(ValueError):
        await lookup_crossref_updates("invalid")
