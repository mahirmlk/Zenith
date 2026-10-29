# ADR-004: Daily Ingestion Triggered via Internal Authenticated Endpoint

**Status:** Accepted

## Context

The original `backend/scripts/daily_fetch.py` was a standalone CLI script intended to run as a cron job. That had three problems:

1. **No HTTP trigger** — schedulers (Fly machines, GitHub Actions, cron) had to execute the script inside the container, which is awkward for containers that run only an HTTP server.
2. **No access control** — if exposed as an endpoint, anyone could trigger an expensive ingestion run (unbounded LLM spend).
3. **Logic duplicated with no test seam** — the fetch/embed/upsert/summarise pipeline was only callable as a script.

## Decision

Extract the pipeline into `backend/services/ingestion.py` (`run_daily_fetch()`), and expose it via a new **internal** router `backend/routers/internal.py`:

- `POST /api/internal/ingest` triggers `run_daily_fetch()`.
- The endpoint is protected by an `X-Admin-Key` header that must equal `ADMIN_API_KEY` (returns `401` otherwise; `503` if unconfigured).
- The work runs on FastAPI `BackgroundTasks` so the scheduler call returns immediately.
- The CLI script `daily_fetch.py` is now a thin wrapper around the same service, so local runs and scheduled runs share one code path.

Two scheduler options are supported and documented (`docs/DEPLOYMENT.md`):

- **Fly.io scheduled machines:** a `cron` process group in `fly.toml` (`fly m run ... --process-group cron` and `fly m update <machine-id> --schedule "daily"`). This is the active scheduler.
- **GitHub Actions:** `.github/workflows/daily_fetch.yml` curls the internal endpoint on manual dispatch. The 04:30 UTC cron was removed to control GitHub Actions costs (2026-10-29).

## Consequences

- **Positive:** One code path for manual, cron, and HTTP-triggered ingestion; easily testable (`test_internal.py`).
- **Positive:** Admin-key gate prevents unauthorised trigger and runaway cost.
- **Positive:** Scheduler health is visible (the endpoint is HTTP, so it can be health-checked).
- **Negative:** `ADMIN_API_KEY` must be provisioned in production environments.
- **Negative:** Background execution means the scheduler gets `200` before work completes; operators monitor via logs/observability rather than the HTTP response.
