def crawl_paper(url: str) -> str:
    """Fail closed until redirect destinations can be validated at fetch time.

    Hosted Firecrawl performs URL fetching on remote workers. Validating the
    initial URL in this process cannot constrain DNS resolution or redirects
    on those workers, and the supported SDK has no per-hop redirect policy.
    """
    del url
    raise RuntimeError(
        "Full-text crawling is disabled until redirect and egress controls are enforced"
    )


async def crawl_paper_cached(paper_id: str, url: str) -> str:
    """Reject hosted crawl requests while fetch-time controls are unavailable."""
    del paper_id, url
    raise RuntimeError(
        "Full-text crawling is disabled until redirect and egress controls are enforced"
    )


def is_available() -> bool:
    """Hosted crawling is disabled until redirect and egress controls exist."""
    return False
