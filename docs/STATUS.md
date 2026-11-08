# Shipment Readiness Status

Reviewed 2026-11-08 against `update.md` and the runtime code. **Release status: not ready for production.** The application has a working local feature set, but the evidence and operational controls do not support a production-ready claim.

| Capability | Verified state | Evidence / remaining gap |
|---|---|---|
| Paper feed, auth, and search | Implemented; local backend suite not yet verified in this review | Authenticated search and API endpoints exist. Run state is process memory or Redis, not the canonical Postgres tables. |
| Streaming and run lifecycle | Partial | SSE exposes events and ownership checks. Redis jobs use `BRPOP` without ack/requeue; cancellation is not enforced by the running task; reconnect replay can duplicate frontend progress. |
| Tenant security | Partial; production unverified | JWT validation and RLS migration files exist. Migrations 0001–0006 have not been verified against staging/live Supabase; project membership is inconsistently honored by retrieval. |
| Projects | Partial | CRUD/notes APIs and a basic list/create page exist. The landing page advertises invitations/collaboration that the UI does not deliver. |
| Retrieval and evidence | Partial | Hybrid ranking and evidence storage exist. Deep-research answer/compare ignore `project_id`; answer currently emits generic relevance statements rather than claim-level source synthesis. |
| Paper-to-code | Planning only | Runner is feature gated. The API passes no code to it; execution path is not a complete approval-and-isolation workflow. Keep disabled. |
| Watchlists and notifications | API/storage implemented; recurring operation unverified | In-app notification code exists, but scheduled monitoring is not enabled as an operational service. |
| Evals | Smoke harness only; not a product quality gate | Current runner derives retrieved sources and citations from expected fixture values. Its pass count does not measure retrieval, synthesis, or abstention behavior. |
| CI | Automated workflow exists; full gate not verified here | CI runs on pushes and PRs. Compose build previously required a missing `.env`; workflow now creates a secret-free empty file before build. No CI run/link is available from this workspace. |
| Frontend checks | Passed locally | `npm run lint`, `npm run typecheck`, and `npm run test` passed (16 tests); `npm run build` passed after running with elevated filesystem access. |
| Deployment and migrations | Not production verified | No staging deployment, live dependency/readiness test, migration application, backup restore, or operational monitoring evidence was available. |

## Release blockers

1. Wire durable run metadata/events and recoverable queue semantics; make cancellation and reconnect behavior correct across process restarts.
2. Enforce project membership consistently and apply/verify RLS migrations against staging with negative tenant-isolation tests.
3. Replace placeholder research answers with evidence-grounded synthesis or clearly label the endpoint as a retrieval preview; honor project scope.
4. Replace the synthetic eval with a runner that invokes the actual retrieval/answer path and records a baseline on versioned cases.
5. Complete the implementation-plan approval flow and keep arbitrary execution disabled until the isolated runner is independently reviewed.
6. Enable and verify scheduled monitoring; test readiness against dependency reachability, not only environment configuration.
7. Obtain passing CI/build evidence, deploy to staging, verify migration and rollback procedures, and complete restore/security/eval gates from `update.md` §16 and §19.

The feature branches and local migration files are not evidence that these items have shipped. Do not describe Zenith as production-ready until the blockers above have test and deployment evidence.

## Validation run in this review

- Frontend lint: passed (Next reports the `next lint` deprecation and detects an unrelated parent-level lockfile).
- Frontend typecheck: passed.
- Frontend tests: passed, 16 tests across 3 files.
- Frontend production build: passed with elevated filesystem access after ordinary sandboxed builds failed with `EPERM` creating `.next` output directories.
- Backend Ruff: passed (`python -m ruff check .`).
- Backend pytest: passed, 81 passed and 6 skipped (`python -m pytest -q`).
- CI, Docker image build, live/staging database, migrations, provider access, and deployment: not run.
