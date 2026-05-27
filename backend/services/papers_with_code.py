import httpx

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
    except httpx.HTTPStatusError:
        return {"repos": []}
    except Exception:
        return {"repos": []}
