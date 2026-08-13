# ADR-008: Summary Fan-Out Capped Per Run

**Status:** Accepted

## Context

The daily ingestion pipeline can find hundreds of new papers. Each gets an LLM summary (TL;DR, key contributions, difficulty rating). Without a ceiling, a single large ingestion run can trigger hundreds of LLM calls in one burst — an unpredictable cost spike and a long-running background job. The original pipeline summarised every new paper unconditionally.

## Decision

Cap summary generation per run in `backend/agents/summary_agent.py`:

- The summary agent accepts a `max_summaries` parameter (default: `get_settings().max_summaries_per_run`, which is `20`).
- Papers beyond the cap are not sent to the LLM. They get `_apply_fallback()` — an abstract-based preview (first ~X characters of the abstract) with no LLM call — so the pipeline still completes quickly and cheaply.
- The cost guardrail is part of the agent contract, so callers that want the full set (e.g., the interactive search path with a small result set) can override it, while the ingestion path inherits the safe default.

## Consequences

- **Positive:** Ingestion cost is bounded per run (`MAX_SUMMARIES_PER_RUN` × per-call cost) and completes faster.
- **Positive:** The interactive search path is unaffected (fewer papers, no need to cap).
- **Positive:** Fallback summaries still give users something useful instead of nothing.
- **Negative:** On very large ingestion days, papers beyond the cap receive non-LLM summaries and may be re-summarised on a later run.
- **Follow-up:** Tune `MAX_SUMMARIES_PER_RUN` based on observed spend; consider a per-day cumulative budget rather than a per-run one.
