# ADR-005: Centralised Async Retry with Exponential Backoff

**Status:** Accepted

## Context

External dependencies (ArXiv, HuggingFace, Semantic Scholar, Firecrawl, Supabase, LLM providers) fail transiently — rate limits, 5xx, connection drops. The original code handled retries ad hoc: some callers wrapped calls in custom retry loops, others retried nothing, and the retry logic for LLM calls was duplicated. Transient failures thus surfaced as hard errors to users, and the daily ingestion could abort on a single burst of 429s.

## Decision

Provide a single retry utility in `backend/services/retry.py`:

- `async_retry(fn, max_retries, base_delay, ...)` — retries a coroutine with exponential backoff.
- `is_retriable()` classifies failures: built-in transient exceptions, `httpx.HTTPError`, and vendor SDK class-name fragments (`APIConnectionError`, `RateLimitError`, `InternalServerError`, `ServiceUnavailable`, `Unavailable`, etc.) so retries cover non-HTTP client errors like OpenAI/Anthropic connection errors without importing every SDK.
- Applied consistently to:
  - embedding generation (`services/embeddings.py`)
  - Supabase upserts/updates in the ingestion pipeline (`services/ingestion.py`)
  - summary-agent LLM calls
  - Firecrawl and citation fetches

## Consequences

- **Positive:** One retry policy instead of scattered loops; transient blips no longer fail user requests or abort ingestion.
- **Positive:** Classifier stays SDK-agnostic (name-fragment matching) so adding a provider needs no retry changes.
- **Negative:** Blind retry could amplify load during an outage — mitigated by exponential backoff and bounded `max_retries`.
- **Negative:** Name-fragment matching is fragile against vendor renames; a new SDK should be verified against `is_retriable()` (covered by `test_retry.py`).
