import logging

import httpx

logger = logging.getLogger(__name__)

PWC_API_URL = "https://paperswithcode.com/api/v1"


async def fetch_paper_repos(arxiv_id: str) -> dict:
    """Fetch GitHub repos for a paper from Papers With Code using arxiv_id."""
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            paper_resp = await client.get(f"{PWC_API_URL}/papers/", params={"arxiv_id": arxiv_id})
            if paper_resp.status_code == 404:
                return {"repos": []}
            paper_resp.raise_for_status()
            data = paper_resp.json()
            results = data.get("results", [])
            if not results:
                return {"repos": []}
            paper = results[0]
            repos_url = paper.get("repositories")
            if not repos_url:
                return {"repos": []}
            # SSRF: only follow upstream URLs on the PWC host.
            from services.ssrf import validate_public_url
            from urllib.parse import urlparse

            validate_public_url(repos_url)
            if urlparse(repos_url).hostname not in (
                "paperswithcode.com",
                "www.paperswithcode.com",
            ):
                return {"repos": []}
            repos_resp = await client.get(repos_url)
            repos_resp.raise_for_status()
            repos_data = repos_resp.json()
            repos = []
            for r in repos_data.get("results", []):
                repos.append({
                    "url": r.get("url", ""),
                    "stars": r.get("stars", 0),
                })
            return {"repos": repos}
    except httpx.HTTPStatusError as exc:
        # Liveness signal (update.md §8.3): a dead PWC API must be
        # visible in logs/metrics, not silently indistinguishable
        # from "no repositories".
        logger.warning("PWC API HTTP %s for %s — repos unavailable", exc.response.status_code, arxiv_id)
        return {"repos": [], "source_error": f"http_{exc.response.status_code}"}
    except Exception as exc:
        logger.warning("PWC API failed for %s: %s", arxiv_id, type(exc).__name__)
        return {"repos": [], "source_error": "unavailable"}
