# ADR-007: Supabase-Backed Citation and Crawl Cache

**Status:** Accepted

## Context

Two external data sources are expensive and aggressively rate-limited:

- **Semantic Scholar** public API (~100 requests per 5 minutes unshared). The citation graph endpoint hits it once per paper view; repeated views of the same paper burn the budget quickly.
- Historical context: Firecrawl full-text extraction was paid per page. Crawling the same paper URL repeatedly wasted quota and money. The current runtime disables hosted crawling and cache access until redirect and egress controls are enforced.

The original graph endpoint called S2 every request and the Firecrawl service re-crawled on every call, with no persistence.

## Decision

Add two Supabase tables and a small cache service:

**Tables (`supabase/schema.sql`):**
- `citations` — one row per citation edge: `paper_id`, `root_title`, `cited_id`, `cited_title`, `fetched_at`. Serves the citation graph.
- `crawled_content` — `paper_id`, `url`, `content`, `fetched_at`. Retains legacy Firecrawl extraction rows; the current runtime does not access them.
- `idx_user_papers_feed` — compound index on `user_papers` for feed queries.

**Services:**
- `backend/services/citation_cache.py` — `get_cached_citations()` / `store_citations()` with a 7-day TTL. `backend/routers/graph.py` serves cached edges first and upserts S2 results on a miss (never fabricates data on failure — returns an empty graph).
- Historical behavior: `backend/services/firecrawl.py` previously read and populated `crawled_content`. Current runtime behavior is fail-closed and does not read or write this table because hosted redirects and worker egress cannot be constrained.

## Consequences

- **Positive:** Citation graph and full-text extraction hit third-party APIs at most once per paper per TTL window.
- **Positive:** Cheaper, faster, and more reliable — the graph renders from the database, not a rate-limited API.
- **Positive:** Both caches degrade gracefully (read failure → fetch live).
- **Negative:** Cached data goes stale after 7 days; a fresh view of an old paper re-fetches (acceptable for citation graphs).
- **Negative:** Two more tables to keep in sync with `schema.sql`; schema changes now also touch `docs/SCHEMA.md`.
