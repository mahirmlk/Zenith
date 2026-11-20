# Zenith Product Plan

> Current implementation and release evidence live in [docs/STATUS.md](docs/STATUS.md). This plan describes remaining work; [ARCHITECTURE.md](ARCHITECTURE.md) describes the runtime. Reviewed 2026-11-20.

## Product goal

Help researchers discover papers, inspect source-backed evidence, organize work in shared projects, and monitor relevant changes. Answers must preserve provenance and state uncertainty. A feature is not production-ready until its runtime, security, recovery, and quality gates have evidence.

## Current product state

| Capability | State | Scope and limit |
|---|---|---|
| Discovery and search | Implemented locally | arXiv and Hugging Face search, saved papers, ranking, and durable streamed runs; providers and production operation need staging validation. |
| Research workspace | Implemented locally, incomplete UX | Projects, roles, notes, paper attachments, PDF page evidence, source-anchored annotations, project-scoped saved searches, versioned user-authored briefs, exports, and email invitations exist. The product intentionally discards original PDF bytes after extraction; complete collaboration flows remain open. |
| Evidence and synthesis | Implemented with strict limits | Extractive answers and heuristic comparisons use exact citations. Synthesis is provisional, abstract-only, and disabled by default; it is not scientific verification. |
| Paper-to-code | Planning/export only | Exact abstract evidence and unverified public GitHub candidates support a reproducibility plan. Arbitrary repository execution is refused. |
| Watchlists | Implemented locally with bounded coverage | Topic, author, inbound-citation, DOI-backed Crossref status, and official Hugging Face benchmark result watches exist. Benchmark alerts compare Zenith snapshots and report observation time for the top 100 Hugging Face-verified entries. Author/citation version tracking, broader authoritative coverage, live provider behavior, and human-calibrated alert quality remain open. |
| Notifications | Implemented locally, delivery unverified | In-app alerts and opt-in, gated email digests exist. Live sender, webhook, suppression, retry, and delivery behavior need staging verification. |
| Account privacy | Implemented locally, cross-service behavior unverified | Export and durable deletion workflows exist; live deletion and recovery across services need staging exercises. |

See [docs/STATUS.md](docs/STATUS.md) for tests, limitations, and exact release gates. Do not infer production readiness from local tests or feature flags.

## Delivery roadmap

### 1. Close local product gaps

- [x] Uploaded-PDF retention policy: discard original bytes after bounded extraction; persist only project-scoped page text and document metadata. No original-file storage feature is planned.
- [x] Add source-anchored project annotations for attached-paper abstracts and uploaded PDF pages, with editor/owner write permissions and stable citation locators (implemented locally; staging RLS and end-to-end verification remain open).
- [x] Add project-scoped saved searches with validated query/model configuration, repeatable metered execution, and explicit ownership/role rules. Topic watchlists remain separate; staging RLS/runtime verification is open.
- [x] Add versioned user-authored project briefs with immutable revisions, exact attached-paper/PDF citations, provenance hashes, and optimistic conflict checks. Migration 0033 is implemented locally; staging RLS/RPC verification remains open.
- [x] Add a bounded, authenticated public-paper page-evidence path for exact-version arXiv papers with CC BY 4.0 or CC0 1.0 licensing; it remains disabled by default pending staging verification. Hosted Firecrawl and its legacy cache remain disabled.
- [ ] Complete collaboration onboarding and roster UX without exposing a global user directory; verify email changes, invitation expiry/revocation, and role transitions.
- [x] Add Crossref notice monitoring with depositor provenance and official Hugging Face leaderboard observation-based benchmark alerts; unknown status remains distinct from “no update.” Author/citation version changes, broader source coverage, and live-source quality evaluation remain open.
- [ ] Build labeled, human-reviewed datasets for project relevance, live-source precision/recall, missed important updates, and claim-level synthesis quality. Establish release thresholds before enabling model-backed features.
- [ ] Complete the paper-to-code isolation design before considering any execution feature; the current fail-closed runner is the expected behavior until an isolated execution environment is reviewed.

### 2. Verify service-backed behavior in staging

- [ ] Apply migrations 0001–0034 in order; test rollback procedures, row-level security, tenant isolation, and authorization against a real staging Supabase project.
- [ ] Exercise Redis queueing, Postgres run/checkpoint recovery, cancellation, retention, account-deletion leases, and multi-worker operation under failure and restart.
- [ ] Verify configured Auth redirects, SMTP invitation delivery, Resend digest consent and suppression, Svix signature handling, provider timeouts/retries, Crossref coverage, and spend reconciliation against provider usage reports.
- [ ] Test backup restore, deployment rollback, alerting, rate/budget enforcement, and incident response. Record evidence and owners in the release checklist.

### 3. Pass release gates

- [ ] Run CI on the exact release commit: backend lint/typecheck/tests/evals, frontend lint/typecheck/tests/build, and Docker Compose image build.
- [ ] Resolve all critical/high security findings and complete the security test plan, dependency/license review, and current-link/reference audit.
- [ ] Obtain human review of scientific quality thresholds, the threat model, operational runbooks, and known residual risks.
- [ ] Update [docs/STATUS.md](docs/STATUS.md), [CHANGELOG.md](CHANGELOG.md), and [update.md](update.md) with verified evidence. Deploy only after every required gate passes and rollback ownership is assigned.

## Architecture boundary

The system uses a Next.js client, FastAPI policy/API layer, LangGraph worker orchestration, and external providers/data services. See [ARCHITECTURE.md](ARCHITECTURE.md) for the checked-in topology and [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md) for deployment configuration. Frontend code does not access the database directly; private data access is authorized by the backend and database policies.

## Deferred by design

- Global account discovery and user search.
- Arbitrary execution of suggested paper repositories.
- Production enablement of provisional synthesis, research-plan execution, or external email until their documented gates pass.
- Claims that a preprint version change proves a journal retraction, or that missing provider metadata proves no update exists.
