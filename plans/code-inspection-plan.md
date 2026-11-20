# Code Inspection Implementation Plan
Project: Zenith | Stack: Next.js 15, FastAPI, LangGraph, Supabase/Postgres, Redis, Fly.io/Vercel
Inspected: 2026-11-20 | Domains: bug/logic, security, architecture, dependencies, deployment

## Deployment Verdict
BLOCKED
Local checks pass, but migrations 0001–0033, tenant isolation, recovery, provider billing, staging deployment, and current-head CI have no production-grade evidence. The default production build and standalone traces pass outside the Windows sandbox; four standalone routes return HTTP 200. A fresh local Docker Compose build completed for both production images, the frontend container returned HTTP 200, and production Compose binds ports to loopback, waits for backend health, and fails closed when required production settings are blank. Backend container readiness and full-stack integration remain unverified. The local Supabase public URL/key values remain empty. Local `HEAD` is `66d09c6`, while the remote branch is still `63f2f18`; the three latest local commits are unpublished and PR #3 remains draft. Backend CI failed one migration-path test (319 passed, 6 skipped) on the old remote SHA; no remote CI result covers the current local commit.

## Executive Summary
The current worktree contains meaningful security, metering, data-provenance, and product-flow hardening, including project annotations, saved searches, versioned briefs through migration 0033, and version/license-gated public arXiv page evidence. Repository-wide backend Ruff and strict mypy pass (86 source files); the full backend suite passes 455 tests with 6 skipped, and the frontend suite passes 97 tests with lint and typecheck. Production Compose now fails closed if essential API/Auth, Supabase, Redis, or Postgres settings are absent. A new observability privacy regression test passes (2/2). The production build passes outside the Windows sandbox and generates 13 static pages / 15 routes; four main routes returned HTTP 200 in a prior standalone smoke check. Both current Docker production images now build locally, and the frontend image returned HTTP 200. Shipment remains blocked by unavailable staging/provider configuration and current-head CI, so local checks cannot prove production behavior. Existing-account onboarding now uses email invitations and a verified-email inbox instead of requiring UUID knowledge; a global directory remains intentionally absent. Other incomplete requirements include benchmark and author/citation version monitoring, human-calibrated alert quality and synthesis, and reviewed paper-to-code isolation.

## P1 — High (fix before production launch)

### [P1-001] Staging database and tenant-security behavior are unverified
- **Location:** `docs/STATUS.md:19-23`; migrations `supabase/migrations/0001_*.sql` through `0033_*.sql`
- **Finding:** No migration has been applied to a live staging database. Static SQL assertions do not prove RPC behavior, direct PostgREST RLS boundaries, rollback, or backup restoration.
- **Evidence:** `docs/STATUS.md` lists staging application, owner/member/editor/viewer/outsider/anon checks, recovery, rollback, and restore as open.
- **Recommended Fix Strategy:** Apply migrations in order to staging, run the documented direct-role matrix and concurrency/recovery exercises, test rollback and restore from an actual backup, and retain logs/artifacts.
- **Estimated Effort:** L
- **Affected Files:** `supabase/migrations/`, `supabase/rollbacks/`, `docs/MIGRATIONS_RUNBOOK.md`, `docs/security/SECURITY_TEST_PLAN.md`

### [P1-002] Provider spend controls have no live invoice reconciliation
- **Location:** `backend/services/spend_meter.py`; `supabase/migrations/0023_provider_spend_metering.sql`; `docs/STATUS.md:30`
- **Finding:** The local implementation reserves and settles usage, but concurrent database behavior, provider usage metadata, unknown outcomes, provider-side limits, and charges against invoices have not been exercised in staging.
- **Evidence:** `docs/STATUS.md` and `update.md` §24.27 leave these gates open; both synthesis and plan execution are default-off.
- **Recommended Fix Strategy:** Configure per-user and system caps, apply migration 0023, exercise concurrency/retry/crash/day-boundary cases, reconcile ledger values to authoritative provider usage and invoices, and retain the result before enabling model-backed features.
- **Estimated Effort:** L
- **Affected Files:** `backend/services/spend_meter.py`, `backend/services/llm_router.py`, `supabase/migrations/0023_provider_spend_metering.sql`, `docs/STATUS.md`

### [P1-003] Current worktree has no current-head remote CI or review evidence
- **Location:** `.github/workflows/ci.yml`; `docs/STATUS.md:18,41`; PR #3
- **Finding:** PR #3 is a draft at the remote branch head, but local commits `e6715e8`–`66d09c6` containing the reviewed worktree changes are not yet published to that branch. CI run #56 failed one backend migration-path test; its focused local fix passes, but has no remote result. Earlier workflow starts were blocked by account billing/spending limits.
- **Evidence:** Local HEAD is `66d09c6`; `origin/codex/shipment-readiness` remains at `63f2f18`. CI run #56 reported 319 passed, 6 skipped, and one failed backend migration test; frontend and Docker jobs passed. Current local suite and static checks pass, but no remote run covers `66d09c6`.
- **Recommended Fix Strategy:** Resolve GitHub Actions billing, publish the reviewed feature branch through the repository's approved workflow, run required PR checks on that exact SHA, complete human review, and merge without deployment until staging gates pass.
- **Estimated Effort:** M
- **Affected Files:** `.github/workflows/ci.yml`, `docs/STATUS.md`, commits `e6715e8`–`66d09c6`

### [P1-004] Runtime configuration is not verified for production
- **Location:** `.env.example`; `frontend/Dockerfile:12-25`; `docker-compose.prod.yml`
- **Finding:** The default production build passes outside the Windows sandbox, but this workspace has empty Supabase public URL/key values, so Auth cannot work until deployment configuration is supplied. Actual production values and callback/SMTP/provider settings are not evidenced here.
- **Evidence:** `CI=1 NEXT_TELEMETRY_DISABLED=1 npm run build` completed successfully with all 13 pages and standalone traces. The generated standalone server returned HTTP 200 for `/`, `/feed`, `/projects`, and `/watchlists`. In-sandbox builds still receive `EPERM` while writing standalone trace directories. The local `.env.local` contains empty Supabase public URL/key values; `docker-compose.prod.yml` consumes public build args and runtime secrets from environment.
- **Recommended Fix Strategy:** Set production frontend build-time Supabase/API values and backend runtime secrets in the deployment secret store; verify Auth redirects, TLS origins, readiness, invitation delivery, and provider behavior in staging.
- **Estimated Effort:** M
- **Affected Files:** `.env.example`, `frontend/Dockerfile`, `docker-compose.prod.yml`, `docs/DEPLOYMENT.md`

## P2 — Medium (complete before declaring the full product scope done)

### [P2-001] Scientific monitoring scope and quality are incomplete; Crossref status alerts are a bounded first slice
- **Location:** `docs/STATUS.md:14,23`; `update.md` §12 and §24.22–24.35
- **Finding:** Migration 0025 and local code now support opt-in DOI-based Crossref Crossmark alerts for retraction, partial retraction, withdrawal, removal, and expression of concern. This does not cover works missing Crossref deposits, benchmark changes, author/citation version changes, human-calibrated project-relevance evaluation, or calibrated live-source precision/missed-important-update quality.
- **Evidence:** The local provider validates the Crossref DOI response and update direction, bounds concurrency and watch count, preserves prior status during failures, and stores the Crossref source, notice DOI, type, label, date, and checked time. Unit/API/migration/UI tests pass. Crossref says metadata reflects member deposits and is complemented by trusted sources such as Retraction Watch; absence must remain unknown. See [Crossref REST API](https://www.crossref.org/documentation/retrieve-metadata/rest-api) and [Crossmark update types](https://support.crossref.org/hc/en-us/articles/115000108983-Getting-started). Live Crossref behavior, migration/RLS application, and human calibration are not verified.
- **Recommended Fix Strategy:** Apply migration 0025 in staging; test authenticated opt-in/opt-out boundaries, source coverage, false-direction records, timeout/backoff, duplicate and distinct notice delivery, and rollback. Then select authoritative sources for remaining change types and establish a blinded human-labeled live-source evaluation before describing monitoring as complete.
- **Estimated Effort:** L
- **Affected Files:** `backend/services/ingestion.py`, `backend/services/semantic_scholar.py`, `backend/routers/watchlists.py`, `evals/`, `docs/STATUS.md`

### [P2-002] Paper-to-code execution remains incomplete; existing-account invite onboarding needs staging proof
- **Location:** `docs/STATUS.md:10,13,23`; `backend/services/sandbox_runner.py`; `frontend/app/projects/[id]/page.tsx`
- **Finding:** Paper-to-code only exports an evidence-backed abstract plan and always refuses execution. The project roster still uses UUIDs, but email invitations now support both new users and existing Auth accounts through a verified-email inbox and the existing atomic acceptance RPC. A global account directory remains intentionally absent to avoid account enumeration.
- **Evidence:** API tests verify Auth-confirmed-email inbox scoping, expiry/deleted-project filtering, and pending state for existing-account invites; frontend tests cover inbox acceptance. Staging delivery, RLS, and role-boundary behavior remain unverified.
- **Recommended Fix Strategy:** Design and review an isolated, network-restricted, resource-limited execution service before implementing code execution. Verify invite delivery and inbox/acceptance behavior in staging; add a global directory only after a privacy policy and anti-enumeration controls are defined.
- **Estimated Effort:** L
- **Affected Files:** `backend/services/sandbox_runner.py`, `backend/routers/projects.py`, `frontend/app/projects/[id]/page.tsx`, `docs/STATUS.md`

### [P2-003] Product quality claims exceed current evaluation evidence
- **Location:** `docs/STATUS.md:17,23`; `evals/runners/run_evals.py`; `evals/runners/run_watchlist_evals.py`
- **Finding:** Deterministic fixtures verify extractive support and API contracts, but they do not establish live scientific correctness, human-calibrated synthesis, provider relation precision/recall, or deployed recovery behavior.
- **Evidence:** The status and eval documentation explicitly characterize the existing sets as smoke/contract gates.
- **Recommended Fix Strategy:** Expand blinded domain-expert datasets, define quality thresholds from human judgments, evaluate the deployed provider and source integrations, and monitor corrections, missed alerts, cost, and recovery rates.
- **Estimated Effort:** L
- **Affected Files:** `evals/`, `docs/EVALUATIONS.md`, `docs/STATUS.md`

## P3 — Low (reproducibility hardening)

### [P3-001] Backend dependency resolution is locked; production image build is locally verified
- **Location:** `backend/pyproject.toml:6-38`; `backend/Dockerfile:13`; `.github/workflows/ci.yml`
- **Finding:** This gap is implemented locally with `backend/uv.lock`, pinned uv, and locked CI/Docker sync commands. Both production images build locally. Current-head CI and backend container readiness remain unverified.
- **Evidence:** Locked sync completed under Python 3.12 as part of a successful `docker compose build`; the frontend production image returned HTTP 200. The current backend suite passes 455 tests with 6 skipped; repository-wide Ruff and strict mypy pass (86 source files), as do the current deterministic evaluations. CI run #56 failed one backend test on the remote SHA; the current local fixes have no remote result.
- **Recommended Fix Strategy:** Validate the exact locked install on current-head GitHub Actions and verify backend container readiness in configured staging before release.
- **Estimated Effort:** M
- **Affected Files:** `backend/pyproject.toml`, `backend/Dockerfile`, `.github/workflows/ci.yml`

## Implementation Roadmap

### Phase 1: Production proof
- [ ] P1-001: Stage migrations and prove tenant isolation, recovery, rollback, and restore.
- [ ] P1-002: Reconcile real provider charges and prove spend-meter recovery behavior.
- [ ] P1-003: Obtain current-head CI and required review/merge evidence.
- [ ] P1-004: Verify production configuration and critical user flows in staging.

### Phase 2: Product completeness and quality
- [ ] P2-001: Deliver source-backed monitoring with human-calibrated evaluations.
- [x] P2-002 onboarding slice: Existing accounts can receive and accept email-based invitations without the inviter knowing a UUID; global user search remains intentionally absent.
- [ ] P2-002 release gate: Verify invitation delivery/inbox/RLS in staging and approve a safe isolated execution design before implementing execution.
- [ ] P2-003: Establish deployed quality and reliability baselines.

### Phase 3: Reproducibility
- [x] P3-001: Add the Python lock and wire locked syncs into CI and production image construction; local locked install, backend suite, static analysis, and evals pass. Both production images now build locally and the frontend image returns HTTP 200; current-head CI and backend runtime validation remain pending.

## Deployment Readiness Checklist
- [ ] Staging migrations, direct RLS matrix, rollback, and backup restore verified.
- [ ] Real Redis/Postgres recovery and provider metering/invoice reconciliation verified.
- [ ] Required current-head CI, review, and merge complete.
- [ ] Production Auth/API values, redirects, secrets, and readiness verified in staging.
- [ ] Docker image builds and runtime OCR path verified.
- [ ] Monitoring/alerting and provider spend limits configured.
- [ ] Scientific quality evaluation and remaining scoped product requirements reviewed.

## Summary Table
| ID | Severity | Domain | Location | Title | Effort |
|---|---|---|---|---|---|
| P1-001 | High | Deployment/security | `supabase/migrations/` | Staging RLS, migration, recovery and restore proof missing | L |
| P1-002 | High | Reliability/cost | `backend/services/spend_meter.py` | Live spend reconciliation missing | L |
| P1-003 | High | CI/review | `.github/workflows/ci.yml` | Current-head CI and review missing | M |
| P1-004 | High | Deployment | `.env.example` | Production configuration unverified | M |
| P2-001 | Medium | Product/evaluation | `update.md` §12 | Scientific monitoring and calibrated quality remain incomplete | L |
| P2-002 | Medium | Product/security | `docs/STATUS.md` | Invite staging proof and safe paper-to-code execution incomplete | L |
| P2-003 | Medium | Evaluation | `evals/` | Human-calibrated quality evidence missing | L |
| P3-001 | Low | Dependencies | `backend/uv.lock` | Locked install works locally; current-head CI and backend runtime validation pending | M |


Deployment Verdict: BLOCKED
