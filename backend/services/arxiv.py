import asyncio
import re
from datetime import timezone
from typing import Any, Optional

import arxiv

from services.retry import async_retry

client = arxiv.Client()
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
        "preprint_id": match.group("base").split("/")[-1],
        "source_version": int(version) if version else None,
        "source_updated_at": updated.isoformat(),
        "title": result.title,
        "abstract": result.summary,
        "url": result.pdf_url or f"https://arxiv.org/abs/{source_id}",
        "authors": [author.name for author in result.authors],
        "published_at": result.published.isoformat(),
    }


async def _search_papers(query: str, max_results: int, sort_by: arxiv.SortCriterion) -> list[PaperRecord]:
    search = arxiv.Search(query=query, max_results=max_results, sort_by=sort_by)

    def _fetch() -> list[PaperRecord]:
        return [_paper_record(result) for result in client.results(search)]

    async def _fetch_async() -> list[PaperRecord]:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, _fetch)

    return await async_retry(_fetch_async, max_retries=3, base_delay=1.0)


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
