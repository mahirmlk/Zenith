import httpx
from config import get_settings
from services.retry import async_retry
from typing import Any
from datetime import datetime, timezone
from urllib.parse import quote

S2_API_URL = "https://api.semanticscholar.org/graph/v1"

# Shared async client with connection pooling
_http_client: httpx.AsyncClient | None = None


def _get_client() -> httpx.AsyncClient:
    global _http_client
    if _http_client is None or _http_client.is_closed:
        _http_client = httpx.AsyncClient(timeout=30.0, limits=httpx.Limits(max_connections=5))
    return _http_client


async def get_paper_citations(paper_id: str, limit: int = 20) -> dict[str, Any]:
    settings = get_settings()
    headers: dict[str, str] = {}
    if settings.semantic_scholar_api_key:
        headers["x-api-key"] = settings.semantic_scholar_api_key

    async def _fetch() -> Any:
        client = _get_client()
        r = await client.get(
            f"{S2_API_URL}/paper/{paper_id}",
            params={"fields": "title,authors,year,citationCount,references,paperId", "limit": limit},
            headers=headers,
        )
        r.raise_for_status()
        return r.json()

    return await async_retry(_fetch, max_retries=3, base_delay=1.0)


def _headers() -> dict[str, str]:
    key = get_settings().semantic_scholar_api_key
    return {"x-api-key": key} if key else {}


async def validate_watch_target(target_type: str, target_id: str) -> str:
    """Validate a stable Semantic Scholar author or paper identifier."""
    encoded_id = quote(target_id, safe="")
    path = f"author/{encoded_id}" if target_type == "author" else f"paper/{encoded_id}"
    fields = "name" if target_type == "author" else "title"

    async def _fetch() -> Any:
        response = await _get_client().get(
            f"{S2_API_URL}/{path}", params={"fields": fields}, headers=_headers()
        )
        response.raise_for_status()
        return response.json()

    data = await async_retry(_fetch, max_retries=2, base_delay=0.5)
    label = str(data.get("name" if target_type == "author" else "title") or "").strip()
    if not label:
        raise ValueError("Semantic Scholar returned no display name for this target")
    return label


def _paper_record(raw: dict[str, Any]) -> dict[str, Any] | None:
    paper_id = str(raw.get("paperId") or "").strip()
    if not paper_id:
        return None
    external_ids = raw.get("externalIds") or {}
    arxiv_id = external_ids.get("ArXiv")
    # Use the same key as arXiv ingestion when possible, so a provider result
    # enriches an existing row instead of creating a duplicate.
    canonical_id = str(arxiv_id or paper_id)
    publication = raw.get("publicationDate")
    if not publication and raw.get("year"):
        publication = f"{raw['year']}-01-01T00:00:00+00:00"
    elif publication:
        publication = f"{publication}T00:00:00+00:00" if len(str(publication)) == 10 else publication
    authors = [
        str(author.get("name") or "").strip()
        for author in raw.get("authors") or []
        if isinstance(author, dict) and author.get("name")
    ]
    return {
        "id": canonical_id,
        "title": str(raw.get("title") or "Untitled paper"),
        "abstract": str(raw.get("abstract") or ""),
        "authors": authors,
        "url": str(raw.get("url") or f"https://www.semanticscholar.org/paper/{paper_id}"),
        "published_at": publication,
    }


async def fetch_watch_papers(
    target_type: str, target_id: str, since: datetime, *, max_pages: int = 5
) -> list[dict[str, Any]]:
    """Fetch bounded recent papers for a stable author or inbound-citation target.

    A provider failure propagates to the caller so its watch cursor is not
    advanced. Pagination is deliberately bounded to protect the public API.
    """
    if target_type == "author":
        path = f"author/{quote(target_id, safe='')}/papers"
        fields = "title,abstract,authors,year,publicationDate,url,externalIds"
    elif target_type == "citation":
        path = f"paper/{quote(target_id, safe='')}/citations"
        fields = "citingPaper.title,citingPaper.abstract,citingPaper.authors,citingPaper.year,citingPaper.publicationDate,citingPaper.url,citingPaper.externalIds"
    else:
        raise ValueError("Unsupported Semantic Scholar watch target")

    start_date = since.astimezone(timezone.utc).date().isoformat()
    collected: list[dict[str, Any]] = []
    page_size = 100
    for page in range(max_pages):
        offset = page * page_size

        async def _fetch() -> Any:
            response = await _get_client().get(
                f"{S2_API_URL}/{path}",
                params={
                    "fields": fields,
                    "publicationDateOrYear": f"{start_date}:",
                    "limit": page_size,
                    "offset": offset,
                },
                headers=_headers(),
            )
            response.raise_for_status()
            return response.json()

        result = await async_retry(_fetch, max_retries=2, base_delay=0.5)
        rows = result.get("data") or []
        for row in rows:
            raw = row.get("citingPaper") if target_type == "citation" else row
            if isinstance(raw, dict) and (paper := _paper_record(raw)):
                collected.append(paper)
        if len(rows) < page_size:
            return collected
    raise RuntimeError("Semantic Scholar watch poll exceeded its pagination bound")
