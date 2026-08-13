# ADR-009: Optional Langfuse Tracing and Sentry Error Tracking

**Status:** Accepted

## Context

Production deployments had no visibility into agent behaviour or application errors:

- LLM calls and LangGraph runs were opaque — no per-run tracing, token accounting, or latency breakdown.
- Unhandled exceptions surfaced only in container logs (if captured), with no centralised error tracking or release-scoped aggregation.
- The repo's plan review flagged missing observability as a deployment blocker (`SECURITY.md` and `docs/DEPLOYMENT.md` both call for monitoring).

Both tools are external paid services, so they must be **opt-in**: local/dev runs should never require them, and missing keys must not crash startup.

## Decision

Add `backend/services/observability.py` as the single integration point:

- **Langfuse:** `get_langfuse_handler()` returns a cached `CallbackHandler` only when `LANGFUSE_PUBLIC_KEY` and `LANGFUSE_SECRET_KEY` are set. `get_langfuse_config()` builds the `config` dict passed to `orchestrator.py`'s `ainvoke` call, tracing every graph run.
- **Sentry:** `init_sentry()` initialises the SDK only when `SENTRY_DSN` is set, wired into the FastAPI lifespan in `main.py`. It uses `SENTRY_TRACES_SAMPLE_RATE` (default `0.1`) and `APP_ENV` for environment tagging, with a release string `ai-paper-agent-backend`.
- Both functions swallow initialisation errors and log a warning — observability never blocks the app.

## Consequences

- **Positive:** Full trace visibility for agent runs (cost, latency, model used) when configured.
- **Positive:** Centralised error tracking with environment/release context; `APP_ENV` distinguishes dev/staging/prod.
- **Positive:** Zero footprint in local dev and CI (no keys → no-op).
- **Negative:** Adds two optional dependencies (`langfuse`, `sentry-sdk`) to `pyproject.toml`.
- **Negative:** Trace sampling is global (`0.1`); high-traffic deployments may want to tune it or set it to 1.0 for debugging.