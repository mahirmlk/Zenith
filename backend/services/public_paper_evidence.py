"""Ephemeral, rights-gated page evidence for openly licensed arXiv papers."""
from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from contextlib import asynccontextmanager
from collections.abc import AsyncIterator, Sequence
from typing import Any
from urllib.parse import quote

import httpx

from services.arxiv_request_gate import ArxivGateUnavailable, arxiv_api_request
from services.pdf_ingestion import (
    MAX_PDF_BYTES,
    PdfIngestionError,
    extract_pdf_pages_async,
)
from security.prompt_injection import scan_untrusted

OAI_URL = "https://oaipmh.arxiv.org/oai"
ARXIV_ORIGIN = "https://arxiv.org"
CC_BY_4_URL = "https://creativecommons.org/licenses/by/4.0/"
CC0_1_URL = "https://creativecommons.org/publicdomain/zero/1.0/"
LICENSES = {
    "http://creativecommons.org/licenses/by/4.0/": (
        "Creative Commons Attribution 4.0 International", CC_BY_4_URL
    ),
    CC_BY_4_URL: ("Creative Commons Attribution 4.0 International", CC_BY_4_URL),
    "http://creativecommons.org/publicdomain/zero/1.0/": (
        "Creative Commons Zero 1.0 Universal", CC0_1_URL
    ),
    CC0_1_URL: ("Creative Commons Zero 1.0 Universal", CC0_1_URL),
}
MAX_OAI_BYTES = 256 * 1024
MAX_QUERY_CHARS = 256
MAX_EVIDENCE_ITEMS = 5
MAX_EXCERPT_CHARS = 2_000
MAX_SENTENCE_CHARS = 500
_ARXIV_ID = re.compile(r"(?:\d{4}\.\d{4,5}|[a-z-]+(?:\.[A-Z]{2})?/\d{7})\Z")
_VERSION = re.compile(r"v([1-9][0-9]*)\Z")
_TOKEN = re.compile(r"[a-z0-9]+", re.IGNORECASE)
_SENTENCE_END = re.compile(r"[.!?](?:[\"')\]]*)?(?:\s+|$)")
_VERSION_TERMS = frozenset({"a", "an", "and", "are", "as", "at", "be", "been", "being", "by", "can", "could", "did", "do", "does", "for", "from", "had", "has", "have", "how", "in", "into", "is", "it", "of", "on", "or", "our", "should", "that", "the", "their", "them", "these", "this", "those", "to", "was", "were", "what", "when", "where", "which", "who", "why", "will", "with", "would", "you", "your"})


class PublicEvidenceError(RuntimeError):
    """Error with a safe HTTP response status for public evidence requests."""

    def __init__(self, status_code: int, detail: str) -> None:
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _child_text(node: ET.Element, name: str) -> str | None:
    for child in node.iter():
        if _local_name(child.tag) == name and child.text:
            return child.text.strip()
    return None


def parse_arxiv_raw_metadata(xml_bytes: bytes) -> dict[str, Any]:
    """Extract the latest version and its license from one OAI arXivRaw record."""
    if b"<!DOCTYPE" in xml_bytes.upper() or b"<!ENTITY" in xml_bytes.upper():
        raise PublicEvidenceError(502, "arXiv OAI metadata used an unsupported XML declaration")
    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError as exc:
        raise PublicEvidenceError(502, "arXiv returned invalid OAI metadata") from exc
    if any(_local_name(node.tag) == "error" for node in root.iter()):
        raise PublicEvidenceError(404, "arXiv metadata record was not found")
    metadata = next((node for node in root.iter() if _local_name(node.tag) == "metadata"), None)
    if metadata is None:
        raise PublicEvidenceError(502, "arXiv OAI metadata is missing")
    raw = next((node for node in metadata if _local_name(node.tag) == "arXivRaw"), metadata)
    versions: list[int] = []
    for node in raw.iter():
        version_text = node.attrib.get("version")
        if version_text:
            match = _VERSION.fullmatch(version_text.strip())
            if match:
                versions.append(int(match.group(1)))
    if not versions:
        raise PublicEvidenceError(502, "arXiv did not provide a verifiable version history")
    licenses: list[tuple[int | None, str]] = []
    def collect_licenses(node: ET.Element, inherited_version: int | None = None) -> None:
        node_version = inherited_version
        version_text = node.attrib.get("version")
        if version_text:
            match = _VERSION.fullmatch(version_text.strip())
            if match:
                node_version = int(match.group(1))
        if _local_name(node.tag) == "license" and node.text:
            licenses.append((node_version, node.text.strip()))
        for child in node:
            collect_licenses(child, node_version)
    collect_licenses(raw)
    versioned_licenses = [(number, value) for number, value in licenses if number is not None]
    if versioned_licenses:
        latest_license_values = [value for number, value in versioned_licenses if number == max(versions)]
        license_url = latest_license_values[0] if len(set(latest_license_values)) == 1 else None
    elif len(licenses) == 1 and licenses[0][0] is None:
        # arXivRaw is the latest record; its root license applies to that latest
        # version. Multiple unversioned license values cannot be disambiguated.
        license_url = licenses[0][1]
    else:
        license_url = None
    title = _child_text(raw, "title")
    return {
        "version": max(versions),
        "license_url": license_url,
        "title": " ".join(title.split()) if title else None,
        "authors": _child_text(raw, "authors"),
    }


async def _read_limited(
    client: httpx.AsyncClient,
    url: str,
    *,
    params: dict[str, str] | None,
    max_bytes: int,
    gated: bool = False,
) -> bytes:
    @asynccontextmanager
    async def _no_gate() -> AsyncIterator[None]:
        yield

    try:
        gate = arxiv_api_request() if gated else _no_gate()
        async with gate:
            async with client.stream("GET", url, params=params, follow_redirects=False) as response:
                if 300 <= response.status_code < 400:
                    raise PublicEvidenceError(502, "arXiv attempted an unexpected redirect")
                response.raise_for_status()
                content_length = response.headers.get("content-length")
                if content_length:
                    try:
                        if int(content_length) > max_bytes:
                            raise PublicEvidenceError(413, "arXiv source exceeds the processing size limit")
                    except ValueError:
                        raise PublicEvidenceError(502, "arXiv returned an invalid content length")
                chunks: list[bytes] = []
                size = 0
                async for chunk in response.aiter_bytes():
                    size += len(chunk)
                    if size > max_bytes:
                        raise PublicEvidenceError(413, "arXiv source exceeds the processing size limit")
                    chunks.append(chunk)
                return b"".join(chunks)
    except PublicEvidenceError:
        raise
    except httpx.TimeoutException as exc:
        raise PublicEvidenceError(504, "arXiv request timed out") from exc
    except httpx.HTTPStatusError as exc:
        raise PublicEvidenceError(502, "arXiv source is temporarily unavailable") from exc
    except httpx.HTTPError as exc:
        raise PublicEvidenceError(502, "arXiv source could not be fetched") from exc
    except ArxivGateUnavailable as exc:
        raise PublicEvidenceError(503, "Shared arXiv request gate is unavailable") from exc


def _exact_sentences(page_text: str) -> list[tuple[int, int, str]]:
    """Return trimmed exact sentence slices with offsets into the page text."""
    found: list[tuple[int, int, str]] = []
    start = 0
    for match in _SENTENCE_END.finditer(page_text):
        end = match.end()
        left = start
        right = end
        while left < right and page_text[left].isspace():
            left += 1
        while right > left and page_text[right - 1].isspace():
            right -= 1
        if right > left and right - left <= MAX_SENTENCE_CHARS:
            found.append((left, right, page_text[left:right]))
        start = end
    if start < len(page_text):
        left = start
        right = len(page_text)
        while left < right and page_text[left].isspace():
            left += 1
        while right > left and page_text[right - 1].isspace():
            right -= 1
        if right > left and right - left <= MAX_SENTENCE_CHARS:
            found.append((left, right, page_text[left:right]))
    return found


def select_page_evidence(
    pages: Sequence[dict[str, int | str]], query: str, paper_id: str, version: int
) -> list[dict[str, int | str]]:
    terms = {
        token.casefold() for token in _TOKEN.findall(query)
        if len(token) > 2 and token.casefold() not in _VERSION_TERMS
    }
    if not terms:
        return []
    ranked: list[tuple[int, int, int, int, str]] = []
    for page in pages:
        page_number = page.get("page_number")
        page_text = page.get("text")
        if not isinstance(page_number, int) or not isinstance(page_text, str):
            continue
        for start, end, sentence in _exact_sentences(page_text):
            overlap = len(terms.intersection(token.casefold() for token in _TOKEN.findall(sentence)))
            if (
                overlap
                and overlap / len(terms) >= 0.34
                and not scan_untrusted(sentence)
            ):
                ranked.append((overlap, -page_number, -start, end - start, sentence))
    ranked.sort(reverse=True)
    result: list[dict[str, int | str]] = []
    total_chars = 0
    for overlap, negative_page, negative_start, length, sentence in ranked:
        del overlap
        if len(result) >= MAX_EVIDENCE_ITEMS or total_chars + len(sentence) > MAX_EXCERPT_CHARS:
            continue
        page_number = -negative_page
        start = -negative_start
        result.append({
            "page_number": page_number,
            "citation_id": f"arxiv:{paper_id}v{version}:page:{page_number}",
            "sentence": sentence,
            "start_offset": start,
            "end_offset": start + length,
        })
        total_chars += len(sentence)
    result.sort(key=lambda item: (int(item["page_number"]), int(item["start_offset"])))
    return result


async def fetch_public_paper_evidence(
    paper: dict[str, Any],
    query: str,
    *,
    client: httpx.AsyncClient | None = None,
) -> dict[str, Any]:
    """Fetch license-verified exact-version PDF pages without persisting content."""
    if len(query) > MAX_QUERY_CHARS:
        raise PublicEvidenceError(422, "Query is too long")
    raw_id = paper.get("preprint_id")
    if not isinstance(raw_id, str) or not _ARXIV_ID.fullmatch(raw_id):
        raise PublicEvidenceError(422, "Paper does not have a supported arXiv identifier")
    version = paper.get("source_version")
    if not isinstance(version, int) or version < 1:
        raise PublicEvidenceError(409, "Paper version is unavailable; refresh its metadata first")
    paper_id = paper.get("id")
    expected_paper_id = f"{raw_id.split('/')[-1]}v{version}"
    if not isinstance(paper_id, str) or paper_id != expected_paper_id:
        raise PublicEvidenceError(409, "Paper identity does not match its stored version; refresh its metadata")

    owned_client = client is None
    active_client = client or httpx.AsyncClient(
        timeout=httpx.Timeout(15.0, connect=3.0),
        limits=httpx.Limits(max_connections=1, max_keepalive_connections=0),
        follow_redirects=False,
    )
    safe_id = quote(raw_id, safe="/.")
    try:
        oai_bytes = await _read_limited(
            active_client,
            OAI_URL,
            params={
                "verb": "GetRecord",
                "identifier": f"oai:arXiv.org:{raw_id}",
                "metadataPrefix": "arXivRaw",
            },
            max_bytes=MAX_OAI_BYTES,
            gated=True,
        )
        metadata = parse_arxiv_raw_metadata(oai_bytes)
        if metadata["version"] != version:
            raise PublicEvidenceError(409, "Paper version is no longer the latest arXiv version")
        license_url = metadata["license_url"]
        if license_url not in LICENSES:
            raise PublicEvidenceError(451, "This paper does not have an approved open license")

        pdf_url = f"{ARXIV_ORIGIN}/pdf/{safe_id}v{version}.pdf"
        pdf_bytes = await _read_limited(
            active_client, pdf_url, params=None, max_bytes=MAX_PDF_BYTES
        )
        try:
            pages = await extract_pdf_pages_async(pdf_bytes, ocr_enabled=False)
        except PdfIngestionError as exc:
            raise PublicEvidenceError(502, "arXiv PDF could not be processed as text") from exc
        title = metadata.get("title") or str(paper.get("title") or "")
        source_url = f"{ARXIV_ORIGIN}/abs/{safe_id}v{version}"
        attribution_title = " ".join(title.split())[:300]
        authors = " ".join(str(metadata.get("authors") or "").split())[:300]
        attribution = f"{authors + '. ' if authors else ''}{attribution_title}. arXiv:{raw_id}v{version}."
        return {
            "paper_id": paper_id,
            "preprint_id": raw_id,
            "version": version,
            "title": attribution_title,
            "source_url": source_url,
            "license_url": LICENSES[license_url][1],
            "license_name": LICENSES[license_url][0],
            "attribution": attribution,
            "evidence": select_page_evidence(pages, query, raw_id, version),
        }
    except ArxivGateUnavailable as exc:
        raise PublicEvidenceError(503, "Shared arXiv request gate is unavailable") from exc
    finally:
        if owned_client:
            await active_client.aclose()
