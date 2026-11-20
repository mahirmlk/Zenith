"""Crossref Crossmark update metadata with explicit coverage provenance.

Crossref reflects metadata deposited by members and trusted sources. An empty
update list means only that no supported update is recorded there; it is not
proof that a work has never been corrected, withdrawn, or retracted.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from typing import Any, Literal
from urllib.parse import quote

import httpx
from pydantic import BaseModel, ConfigDict, Field

CROSSREF_WORKS_URL = "https://api.crossref.org/works"
CROSSREF_TIMEOUT_SECONDS = 8.0
MAX_UPDATE_RELATIONS = 50
_DOI_RE = re.compile(r"^10\.\d{4,9}/\S+$", re.IGNORECASE)

UpdateType = Literal[
    "retraction",
    "partial_retraction",
    "withdrawal",
    "removal",
    "expression_of_concern",
]
DepositSource = Literal["publisher", "retraction-watch"]

SUPPORTED_UPDATE_TYPES = frozenset(
    {
        "retraction",
        "partial_retraction",
        "withdrawal",
        "removal",
        "expression_of_concern",
    }
)


class CrossrefUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    update_type: UpdateType
    notice_doi: str = Field(min_length=7, max_length=255)
    deposit_source: DepositSource | None = None
    label: str | None = Field(default=None, max_length=200)
    updated_at: date | None = None


@dataclass(frozen=True)
class CrossrefLookup:
    record_found: bool
    updates: tuple[CrossrefUpdate, ...]


class CrossrefUnavailable(RuntimeError):
    """Crossref could not return trustworthy metadata for this request."""


def normalize_doi(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    doi = value.strip()
    lowered = doi.casefold()
    for prefix in ("https://doi.org/", "http://doi.org/", "https://dx.doi.org/", "http://dx.doi.org/"):
        if lowered.startswith(prefix):
            doi = doi[len(prefix):]
            break
    if len(doi) > 255 or not _DOI_RE.fullmatch(doi):
        return None
    return doi.lower()


def _date_from_parts(value: object) -> date | None:
    if not isinstance(value, dict):
        return None
    parts = value.get("date-parts")
    if not isinstance(parts, list) or not parts or not isinstance(parts[0], list):
        return None
    first = parts[0]
    if not first or not all(isinstance(item, int) and not isinstance(item, bool) for item in first[:3]):
        return None
    try:
        year = first[0]
        month = first[1] if len(first) > 1 else 1
        day = first[2] if len(first) > 2 else 1
        return date(year, month, day)
    except (TypeError, ValueError, OverflowError):
        return None


def parse_update_relations(payload: object) -> tuple[CrossrefUpdate, ...]:
    if not isinstance(payload, dict):
        raise CrossrefUnavailable("Crossref returned an invalid response")
    message = payload.get("message")
    if not isinstance(message, dict):
        raise CrossrefUnavailable("Crossref returned an invalid response")
    relations = message.get("update-to", [])
    if relations is None:
        relations = []
    if not isinstance(relations, list) or len(relations) > MAX_UPDATE_RELATIONS:
        raise CrossrefUnavailable("Crossref returned invalid update metadata")

    updates: list[CrossrefUpdate] = []
    for relation in relations:
        if not isinstance(relation, dict):
            continue
        update_type = relation.get("type")
        notice_doi = normalize_doi(relation.get("DOI"))
        if update_type not in SUPPORTED_UPDATE_TYPES or not notice_doi:
            continue
        label = relation.get("label")
        raw_source = relation.get("source")
        deposit_source: DepositSource | None = None
        if raw_source == "publisher":
            deposit_source = "publisher"
        elif raw_source == "retraction-watch":
            deposit_source = "retraction-watch"
        updates.append(
            CrossrefUpdate(
                update_type=update_type,
                notice_doi=notice_doi,
                deposit_source=deposit_source,
                label=label[:200] if isinstance(label, str) else None,
                updated_at=_date_from_parts(relation.get("updated")),
            )
        )
    return tuple(updates)


async def lookup_crossref_updates(
    doi: str,
    *,
    client: httpx.AsyncClient | None = None,
) -> CrossrefLookup:
    """Look up Crossmark update relations for one DOI.

    Invalid DOI input is rejected locally. A missing Crossref record is a
    successful lookup with `record_found=False`; transient/provider failures
    raise `CrossrefUnavailable` so callers can retry without advancing status.
    """
    normalized = normalize_doi(doi)
    if normalized is None:
        raise ValueError("A valid DOI is required")

    async def request(active_client: httpx.AsyncClient) -> CrossrefLookup:
        try:
            response = await active_client.get(
                f"{CROSSREF_WORKS_URL}/{quote(normalized, safe='')}",
                timeout=CROSSREF_TIMEOUT_SECONDS,
                headers={"User-Agent": "Zenith/0.1 (Crossref metadata lookup)"},
            )
        except httpx.HTTPError as exc:
            raise CrossrefUnavailable("Crossref request failed") from exc
        if response.status_code == 404:
            return CrossrefLookup(record_found=False, updates=())
        if response.status_code == 429 or response.status_code >= 500:
            raise CrossrefUnavailable(f"Crossref returned HTTP {response.status_code}")
        try:
            response.raise_for_status()
            payload: Any = response.json()
            message = payload.get("message") if isinstance(payload, dict) else None
            returned_doi = normalize_doi(message.get("DOI")) if isinstance(message, dict) else None
            if returned_doi != normalized:
                raise CrossrefUnavailable("Crossref returned a mismatched DOI record")
            return CrossrefLookup(record_found=True, updates=parse_update_relations(payload))
        except CrossrefUnavailable:
            raise
        except (httpx.HTTPStatusError, ValueError, TypeError) as exc:
            raise CrossrefUnavailable("Crossref returned invalid metadata") from exc

    if client is not None:
        return await request(client)
    async with httpx.AsyncClient() as owned_client:
        return await request(owned_client)
