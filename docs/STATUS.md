# Shipment Readiness Status

Reviewed 2026-11-11 against `update.md`, the current code, migrations, local checks, and PR #3 CI. **Release status: not ready for production.** The branch's CI is green; staging evidence and several requested product capabilities are still missing.

| Capability | Verified state | Evidence / remaining gap |
|---|---|---|
| Paper feed, auth, and search | Implemented locally | Authenticated search, distributed per-user UTC budgets, hashed idempotency keys, queueing, and shared Redis leases exist. Provider behavior and distributed operation have not been tested against staging services. |
| Run lifecycle and persistence | Postgres run store and graph checkpoints implemented; deployment unverified | Production requires `DATABASE_URL` and initializes an async Postgres LangGraph checkpointer with strict msgpack decoding. Recovery resumes pending graph nodes and terminal checkpoints without rerunning completed work; checkpoint retention follows terminal run TTL. Node-local external calls can repeat after a crash. Live restart/retention behavior is unverified. |
| Tenant security | Code and migrations implemented; production unverified | JWT validation and migrations 0001–0009 exist. Project owner/member/editor/viewer rules and narrow direct-auth RLS policies are present. SQL has only static tests; migration application and negative tenant-isolation tests against Supabase remain open. |
| Projects | Partial | CRUD, notes, membership/role authorization, source attachment, and owner/shared project listing exist. Invitation delivery and a complete collaboration UX are not implemented. |
| Retrieval and evidence | Bounded extractive evidence map + preview; synthesis incomplete | The project-scoped `/api/research/evidence-map` endpoint requires membership, selects only attached papers, caps work at 10 papers/5 exact abstract spans, verifies offsets against source text, filters instruction-like sentences, and abstains on no support. Project answers/comparisons remain extractive. There is no cross-paper synthesis or broad claim-support evaluation. |
| Paper-to-code | Evidence-backed plan and Markdown export implemented locally; execution disabled | The plan extracts exact abstract sentences with paper ID and offsets, reports missing details as gaps, and labels GitHub matches as unverified candidates. The paper page has an authenticated export action. The runner now always refuses execution pending a reviewed isolation design. This is not a reproduction workflow and does not validate repositories or code. |
| Watchlists and notifications | Scheduled code implemented; live operation unverified | Daily 02:00 UTC polling and API/Fly/manual ingestion triggers share one Redis lease. Retry, overlap, lease-loss, and cancellation behavior have local tests. Live Redis coordination, scheduler uptime, delivery, and alerting are unverified. |
| Health and production controls | Implemented locally; production unverified | Readiness checks bounded Supabase and Redis connectivity, verifies production run-store schema/RPCs, and probes the live graph checkpoint connection. Startup fails closed without durable checkpoints in production. Production budgets fail closed without Redis. No live dependency, alerting, or outage exercise was run. |
| Evals | Deterministic regression gate passes | 12 hand-authored cases run the production ranker and extractive selector; all 12 pass and the fabricated-citation negative control passes. This does not establish broad scientific quality or deployed-provider behavior. |
| CI and local checks | PR CI green on `24a725e` | GitHub Actions run #48 passed backend (Ruff, mypy, pytest, eval), frontend (lint, typecheck, tests, build), and Docker Compose image builds. Local backend suite: 163 passed, 6 skipped; eval: 12/12. CI validates this branch's code, not live service behavior. |
| Deployment and migrations | Not production verified | Migrations 0001–0009 have not been applied to staging/live. Staging deployment, migration/rollback, backup restore, tenant isolation against Supabase, provider behavior, and operational monitoring evidence are unavailable. |

## Release blockers

1. Apply migrations 0001–0009 in staging; verify Postgres RPC behavior, RLS with owner/member/editor/viewer/outsider/anon cases, rollback, and backup restore.
2. Exercise Redis queue recovery, scheduler/API/Fly overlap, lease loss, cancellation, checkpoint resume, and retention behavior with real shared Redis and Supabase services. A crash within a graph node can repeat that node's external calls, so validate provider/idempotency behavior.
3. Deploy to a staging environment; verify readiness, provider integration, migrations, alerts, and recovery under dependency outages. PR CI and Docker image builds passed on the current branch but do not replace this gate.
4. Expand the small hand-authored eval corpus and add deployed-service/provider tests. Keep research output extractive until claim-level evidence spans and synthesis quality are evaluated.
5. Complete the implementation-plan approval and isolated execution workflow before enabling paper-to-code execution; keep arbitrary execution disabled until that review is complete.
6. Complete invitation delivery and collaboration UX if they are required for the release scope.
The code and local migrations are not evidence that staging or production behavior is safe. Do not describe Zenith as production-ready until the release blockers have verified evidence.

## Validation evidence

- Frontend lint, typecheck, tests (18 across 4 files), and production build passed on the current tree. The build tracing root is pinned to the frontend project, so Next.js no longer selects an unrelated parent lockfile.
- Backend Ruff: passed on the current working tree.
- Backend pytest: 163 passed, 6 skipped (`python -m pytest -q` from `backend`), including project evidence-map authorization, source scoping, exact offsets, abstention, and result limits, plus a real LangGraph `MemorySaver` crash/resume check. The sync Starlette TestClient was replaced by an in-process HTTPX ASGI adapter because its local socket pair hung in this Windows sandbox.
- Eval: `python evals/runners/run_evals.py` passed 12/12 cases with abstention accuracy, citation validity, exact support, claim coverage, Recall@5, and MRR@5 each at 1.000; fabricated-citation negative control passed.
- Mypy: `python -m mypy .` passed with no issues across 70 application source files. `tests/` and `scripts/` are excluded; the CI workflow runs this strict gate as blocking.
- Paper-to-code tests cover exact abstract offsets, unsupported-summary exclusion, instruction-like text filtering, missing-detail gaps, repository candidate allowlisting, Markdown escaping, and the fail-closed runner (including with `SANDBOX_ENABLED=true`).
- Evidence-map tests cover project membership/source scope, exact source offsets, prompt-injection filtering, abstention, and the 10-paper/5-span cap.
- Remote CI: GitHub Actions run #48 passed on PR #3 HEAD `24a725e` (backend, frontend, Docker). Docker image build is verified in CI. Staging/live dependencies, migrations, provider access, backup restore, and deployment remain unverified.
