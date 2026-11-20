"""Bounded, unverified GitHub repository search for research papers."""
from __future__ import annotations

import logging
import re
import time
from typing import Any
from urllib.parse import urlsplit

import httpx

from config import get_settings

logger = logging.getLogger(__name__)
GITHUB_REPOSITORY_SEARCH_URL = "https://api.github.com/search/repositories"
_ARXIV_ID = re.compile(r"^(?:[a-z-]+/)?(?:\d{7}|\d{4}\.\d{4,5})(?:v[1-9][0-9]*)?$", re.IGNORECASE)
_DOI = re.compile(r"^10\.[0-9]{4,9}/[^\s]{1,220}$", re.IGNORECASE)
_TITLE_TOKEN = re.compile(r"[^A-Za-z0-9]+")
_CACHE_TTL_SECONDS = 15 * 60
_CACHE_MAX_ITEMS = 512
_CACHE: dict[str, tuple[float, list[dict[str, Any]], bool]] = {}


def _search_terms(paper: dict[str, Any]) -> tuple[str | None, str | None]:
    """Return a strong paper identifier and a sanitized title fallback."""
    doi = paper.get("doi")
    if isinstance(doi, str):
        candidate = doi.strip()
        if candidate.casefold().startswith("https://doi.org/"):
            candidate = candidate[len("https://doi.org/"):]
        if _DOI.fullmatch(candidate):
            strong = candidate
        else:
            strong = None
    else:
        strong = None

    arxiv_id = paper.get("preprint_id") or paper.get("arxiv_id")
    if not isinstance(arxiv_id, str):
        arxiv_id = paper.get("id")
    if not isinstance(arxiv_id, str):
        arxiv_id = ""
    arxiv_id = arxiv_id.strip()
    if not _ARXIV_ID.fullmatch(arxiv_id):
        paper_url = paper.get("url")
        if isinstance(paper_url, str):
            match = re.search(r"arxiv\.org/(?:abs|pdf)/([^?#]+)", paper_url, re.IGNORECASE)
            arxiv_id = match.group(1).removesuffix(".pdf") if match else ""
        else:
            arxiv_id = ""
    if len(arxiv_id) > 64:
        arxiv_id = ""
    if not strong and _ARXIV_ID.fullmatch(arxiv_id):
        strong = arxiv_id

    title_value = paper.get("title")
    title = ""
    if isinstance(title_value, str):
        # Remove search operators/punctuation from upstream paper metadata and
        # cap the title so imported metadata cannot expand a GitHub query.
        tokens = [part for part in _TITLE_TOKEN.split(title_value) if part][:18]
        title = " ".join(tokens)[:160]
    return strong, title or None


def _repository_url(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = urlsplit(value)
        parts = [part for part in parsed.path.strip("/").split("/") if part]
    except ValueError:
        return None
    if (
        parsed.scheme != "https"
        or parsed.hostname != "github.com"
        or parsed.username is not None
        or parsed.password is not None
        or len(parts) != 2
        or not all(re.fullmatch(r"[A-Za-z0-9_.-]+", part) for part in parts)
    ):
        return None
    repository = parts[1].removesuffix(".git")
    if not repository:
        return None
    return f"https://github.com/{parts[0]}/{repository}"


def _normalize_items(payload: object) -> list[dict[str, Any]]:
    if not isinstance(payload, dict) or not isinstance(payload.get("items"), list):
        raise ValueError("GitHub repository search returned an invalid response")
    candidates: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in payload["items"][:10]:
        if not isinstance(item, dict) or item.get("private") is True:
            continue
        url = _repository_url(item.get("html_url"))
        if not url or url in seen:
            continue
        seen.add(url)
        stars = item.get("stargazers_count")
        valid_stars = isinstance(stars, int) and not isinstance(stars, bool) and stars >= 0
        candidates.append({"url": url, "stars": stars if valid_stars else 0})
    return candidates


async def search_paper_repositories(
    paper: dict[str, Any], *, client: httpx.AsyncClient | None = None
) -> dict[str, Any]:
    """Search public GitHub repo metadata by DOI/arXiv ID or title.

    Search results are possible matches only. The function never claims that a
    repository is authored by the paper authors or is an official implementation.
    """
    strong_identifier, title = _search_terms(paper)
    if not strong_identifier and not title:
        return {"repos": [], "source": "github", "source_error": "paper_identifier_missing"}

    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "Zenith-Research-Workspace",
    }
    token = get_settings().github_token.strip()
    if token:
        headers["Authorization"] = f"Bearer {token}"

    cache_key = f"{strong_identifier or ''}|{title or ''}".casefold()
    cached = _CACHE.get(cache_key)
    if cached and cached[0] > time.monotonic():
        return {
            "repos": [repo.copy() for repo in cached[1]],
            "source": "github",
            "incomplete_results": cached[2],
        }
    if cached:
        _CACHE.pop(cache_key, None)
    owns_client = client is None
    active_client = client if client is not None else httpx.AsyncClient(
        timeout=httpx.Timeout(8.0, connect=3.0)
    )

    async def lookup(query: str) -> tuple[list[dict[str, Any]], bool]:
        response = await active_client.get(
            GITHUB_REPOSITORY_SEARCH_URL,
            params={"q": f'"{query}" is:public', "sort": "stars", "order": "desc", "per_page": 10},
            headers=headers,
        )
        response.raise_for_status()
        body = response.json()
        return _normalize_items(body), bool(isinstance(body, dict) and body.get("incomplete_results"))

    try:
        if owns_client:
            async with active_client:
                candidates, incomplete = await lookup(strong_identifier or title or "")
        else:
            candidates, incomplete = await lookup(strong_identifier or title or "")
        result = {
            "repos": candidates,
            "source": "github",
            "incomplete_results": incomplete,
        }
        if len(_CACHE) >= _CACHE_MAX_ITEMS:
            expired = [key for key, value in _CACHE.items() if value[0] <= time.monotonic()]
            for key in expired:
                _CACHE.pop(key, None)
            if len(_CACHE) >= _CACHE_MAX_ITEMS:
                _CACHE.pop(next(iter(_CACHE)))
        _CACHE[cache_key] = (time.monotonic() + _CACHE_TTL_SECONDS, candidates, incomplete)
        return result
    except httpx.HTTPStatusError as exc:
        logger.warning("GitHub repository search returned HTTP %s", exc.response.status_code)
        return {"repos": [], "source": "github", "source_error": f"http_{exc.response.status_code}"}
    except (httpx.HTTPError, ValueError, TypeError) as exc:
        logger.warning("GitHub repository search failed: %s", type(exc).__name__)
        return {"repos": [], "source": "github", "source_error": "unavailable"}
    finally:
        if owns_client and not active_client.is_closed:
            await active_client.aclose()
