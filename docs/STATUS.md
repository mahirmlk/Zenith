# Shipment Readiness Status

Reviewed 2026-11-08 against `update.md` and the runtime code. **Release status: not ready for production.** The application has a working local feature set, but the evidence and operational controls do not support a production-ready claim.

| Capability | Verified state | Evidence / remaining gap |
|---|---|---|
| Paper feed, auth, and search | Implemented; latest backend verification incomplete | Authenticated search, distributed per-user UTC daily budgets, hashed idempotency keys, and run queueing exist. Production run state remains Redis, not the canonical Postgres tables. |
| Streaming and run lifecycle | Improved; durable Postgres state remains open | Redis Streams keep jobs pending until ack and reclaim abandoned work; run leases prevent concurrent execution; cancellation suppresses late results; the UI deduplicates replay and supports cancel. Production startup requires shared Redis for rate limits and budgets. |
| Tenant security | Partial; production unverified | JWT validation and RLS migration files exist. Project access is owner/member scoped, viewers are read-only, editors can write, and only owners can invite/delete. Migration application, RLS behavior, and negative isolation tests remain unverified against staging/live Supabase. |
| Projects | Partial | CRUD, notes, member-role authorization, and project listing for owners and members exist alongside a basic list/create page. Invitation delivery and a complete collaboration UX are not implemented. |
| Retrieval and evidence | Partial | Project answer/compare now authorize members and limit to attached sources; answer returns exact abstract sentences with IDs and abstains without keyword overlap. This is extractive and does not synthesize cross-paper evidence; generic retrieval route also authorizes project members. |
| Paper-to-code | Planning only | Runner is feature gated. The API passes no code to it; execution path is not a complete approval-and-isolation workflow. Keep disabled. |
| Watchlists and notifications | API/storage implemented; recurring operation unverified | Migration 0007 adds watchlist linkage and deduplication; cadence and enabled state are honored. Scheduled monitoring is not enabled as an operational service. |
| Health and production controls | Implemented locally; production unverified | Readiness checks bounded Supabase and Redis connectivity; production rate limits and search budgets fail closed without Redis. Live dependency behavior and alerting have not been verified. |
| Evals | Deterministic code-path smoke; not a product quality gate | Runner invokes production hybrid ranking and extractive claim selection on a two-case fixed corpus. It lacks a sufficiently broad quality baseline and does not test a deployed service. |
| CI | Automated workflow exists; full gate not verified here | CI runs on pushes and PRs. Compose build previously required a missing `.env`; workflow now creates a secret-free empty file before build. No CI run/link is available from this workspace. |
| Frontend checks | Passed locally | `npm run lint`, `npm run typecheck`, and `npm run test` passed (18 tests across 4 files); `npm run build` passed after running with elevated filesystem access. |
| Deployment and migrations | Not production verified | No staging deployment, live dependency/readiness test, migration application, backup restore, or operational monitoring evidence was available. |

## Release blockers

1. Store canonical run metadata/events and state in Postgres; integration-test Redis recovery and run replay across process restarts.
2. Apply/verify RLS migrations against staging with negative tenant-isolation tests and validate the new project role rules against real Supabase policies.
3. Extend extractive research preview to evaluated synthesis only after adding claim-level evidence spans; current endpoint labels itself as extractive.
4. Expand the real-code-path eval smoke into a versioned quality suite and record measured baselines before gates.
5. Complete the implementation-plan approval flow and keep arbitrary execution disabled until the isolated runner is independently reviewed.
6. Enable and verify scheduled monitoring; test readiness and fail-closed rate limits against reachable and unavailable shared dependencies.
7. Obtain passing CI/build evidence, deploy to staging, verify migration and rollback procedures, and complete restore/security/eval gates from `update.md` §16 and §19.

The feature branches and local migration files are not evidence that these items have shipped. Do not describe Zenith as production-ready until the blockers above have test and deployment evidence.

## Validation evidence

- Frontend lint: passed using ESLint on source/config paths.
- Frontend typecheck: passed.
- Frontend tests: passed, 18 tests across 4 files.
- Frontend production build: passed with elevated filesystem access after ordinary sandboxed builds failed with `EPERM` creating `.next` output directories.
- Backend Ruff: passed (`python -m ruff check .`) on the current working tree.
- Backend pytest: an earlier run passed 111 tests with 6 skipped before the latest role, health, orchestration, and rate-limit request edits. The latest full-suite attempt returned no result; a verbose targeted run reached `test_health` and stalled on its TestClient request. A separate `langchain_core` import diagnostic was also unusually slow. Current changes therefore do not have a fresh full-suite pass.
- CI: not run remotely. Docker image build: not run because the local Docker daemon is unavailable. Live/staging database, migrations, provider access, and deployment: not run.
