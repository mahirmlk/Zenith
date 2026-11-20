import asyncio
import re
from datetime import timezone
from typing import Any, Optional

import arxiv
import httpx

from services.retry import async_retry
from services.arxiv_request_gate import ArxivGateUnavailable, arxiv_api_session

# Keep one API page per current caller and retain arxiv.Client's tested Atom
# parser, retries, and pagination semantics. The distributed gate below spans
# the complete results iteration, including any client-side retry/paging.
client = arxiv.Client(page_size=200, delay_seconds=3.0, num_retries=1)
ARXIV_API_URL = "https://export.arxiv.org/api/query"
ARXIV_API_PAGE_SIZE = 200
ARXIV_API_TIMEOUT_SECONDS = 15.0
MAX_ARXIV_API_RESPONSE_BYTES = 5 * 1024 * 1024
PaperRecord = dict[str, Any]
_VERSIONED_ARXIV_ID = re.compile(r"^(?P<base>.+?)(?:v(?P<version>[1-9][0-9]*))?$")


def _paper_record(result: arxiv.Result) -> PaperRecord:
    source_id = result.entry_id.split("/abs/", 1)[-1].split("?", 1)[0]
    match = _VERSIONED_ARXIV_ID.fullmatch(source_id)
    if not match:
        raise ValueError("arXiv returned a malformed paper identifier")
    version = match.group("version")
    # Preserve the historical papers.id representation: old archive IDs were
    # stored using only their final path component.
    paper_id = source_id.split("/")[-1]
    updated = result.updated
    if updated.tzinfo is None:
        updated = updated.replace(tzinfo=timezone.utc)
    return {
        "id": paper_id,
        "preprint_id": match.group("base"),
        "source_version": int(version) if version else None,
        "source_updated_at": updated.isoformat(),
        "title": result.title,
        "abstract": result.summary,
        "url": result.pdf_url or f"https://arxiv.org/abs/{source_id}",
        "authors": [author.name for author in result.authors],
        "published_at": result.published.isoformat(),
        "doi": result.doi or None,
    }


async def _search_papers(
    query: str,
    max_results: int,
    sort_by: arxiv.SortCriterion,
    *,
    http_client: httpx.AsyncClient | None = None,
) -> list[PaperRecord]:
    search = arxiv.Search(query=query, max_results=max_results, sort_by=sort_by)

    async def _fetch_async() -> list[PaperRecord]:
        if max_results <= 0:
            return []
        papers: list[PaperRecord] = []
        params = search._url_args()
        page_size = min(max_results, ARXIV_API_PAGE_SIZE)
        timeout_seconds = max(
            75.0,
            72.0 * ((max_results + ARXIV_API_PAGE_SIZE - 1) // ARXIV_API_PAGE_SIZE) + 10.0,
        )
        async with asyncio.timeout(timeout_seconds):
            async with arxiv_api_session() as gate:
                owned_http = http_client is None
                http = http_client or httpx.AsyncClient(
                    timeout=httpx.Timeout(ARXIV_API_TIMEOUT_SECONDS, connect=3.0),
                    follow_redirects=False,
                )
                try:
                    offset = 0
                    while offset < max_results:
                        await gate.before_request()
                        page_params = {
                            **params,
                            "start": str(offset),
                            "max_results": str(page_size),
                        }
                        async with http.stream(
                            "GET", ARXIV_API_URL, params=page_params, follow_redirects=False
                        ) as response:
                            if 300 <= response.status_code < 400:
                                raise httpx.HTTPStatusError(
                                    "Unexpected arXiv API redirect",
                                    request=response.request,
                                    response=response,
                                )
                            response.raise_for_status()
                            content_length = response.headers.get("content-length")
                            if content_length and int(content_length) > MAX_ARXIV_API_RESPONSE_BYTES:
                                raise ValueError("arXiv API response exceeds the size limit")
                            chunks: list[bytes] = []
                            size = 0
                            async for chunk in response.aiter_bytes():
                                size += len(chunk)
                                if size > MAX_ARXIV_API_RESPONSE_BYTES:
                                    raise ValueError("arXiv API response exceeds the size limit")
                                chunks.append(chunk)
                        feed = arxiv._feed.parse(b"".join(chunks))
                        if feed.malformed:
                            raise ValueError("arXiv returned malformed Atom data")
                        page = [_paper_record(result) for result in feed.results]
                        papers.extend(page)
                        if not page or offset + len(page) >= feed.header.total_results:
                            break
                        offset += len(page)
                        if len(papers) >= max_results:
                            break
                finally:
                    if owned_http:
                        await http.aclose()
        return papers[:max_results]

    try:
        return await async_retry(_fetch_async, max_retries=3, base_delay=1.0)
    except ArxivGateUnavailable:
        raise


async def search_arxiv(query: str, max_results: int = 20) -> list[PaperRecord]:
    return await _search_papers(query, max_results, arxiv.SortCriterion.SubmittedDate)


async def fetch_recently_updated_papers(
    categories: Optional[list[str]] = None, max_results: int = 200
) -> tuple[list[PaperRecord], bool]:
    """Fetch the newest arXiv versions for monitoring.

    `complete` is false when the result cap is reached. Callers must then keep
    monitoring cursors in place instead of claiming the update window is done.
    """
    cats = categories or ["cs.AI", "cs.LG", "cs.CL", "stat.ML"]
    query = " OR ".join(f"cat:{category}" for category in cats)
    records = await _search_papers(query, max_results, arxiv.SortCriterion.LastUpdatedDate)
    return records, len(records) < max_results


async def fetch_latest_papers(
    categories: Optional[list[str]] = None, max_results: int = 50
) -> list[PaperRecord]:
    cats = categories or ["cs.AI", "cs.LG", "cs.CL", "stat.ML"]
    query = " OR ".join(f"cat:{c}" for c in cats)
    return await search_arxiv(query, max_results)
