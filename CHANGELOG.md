# Changelog

## Unreleased (2026-11-20)

### Research and discovery

- Added project-scoped PDF page retrieval, evidence maps, answers, and separately cited PDF evidence in heuristic project comparisons. Public retrieval and paper comparison rows remain abstract-based; uploaded PDFs are not attributed to a paper without an explicit relation.
- Added optional local OCR for a bounded number of scanned PDF pages. Native PDF extraction remains the default, and original PDF bytes are discarded.
- Added provisional, abstract-only cross-paper synthesis behind a disabled-by-default feature flag. Claims retain validated evidence citations; model review is not scientific verification.
- Added a bounded research-plan preview and queued execution behind a separate disabled-by-default feature flag, with durable run/checkpoint integration and spend metering.
- Added evidence-backed paper-to-code plans and Markdown export using public GitHub repository metadata. Candidates are unverified, and repository execution is refused.
- Added summary provenance so generated, preview, fallback, and unavailable states are distinct.

### Monitoring and collaboration

- Added topic, author, citation, DOI-backed Crossref update, and official Hugging Face benchmark leaderboard watches with in-app notifications and optional project-relevance hints. Benchmark alerts compare Zenith snapshots, cover the top 100 Hugging Face-verified entries, and report observation time; they do not claim scientific validity. Live provider behavior and calibrated alert quality remain unverified.
- Preserved Crossref's optional relation-level depositor source (`publisher` or `retraction-watch`) independently from the `crossref` registry label. Unknown values remain unknown in storage, API responses, UI, and notices.
- Added opt-in, gated Resend email digests with consent, unsubscribe, suppression, and an idempotent outbox. Live delivery is not verified; keep email delivery disabled until staging checks pass.
- Added project invitation inbox support for existing accounts, with verified-email acceptance and copyable pending invitation links. Membership still requires the atomic verified-email acceptance RPC.
- Added bounded project workspace, role-aware controls, PDF page sources, and account export/deletion workflows. Cross-service deletion behavior remains unverified in staging.
- Added annotations anchored to exact attached-paper abstract or extracted PDF page text, with stale-anchor detection and owner/editor mutation controls. Migration 0031 enforces project-scoped source relationships; backend async verification and staging RLS remain open.
- Added project-scoped saved-search configurations with creator/project role rules and fresh metered runs. Migration 0032 adds RLS and immutable project/creator scope; async API and staging behavior remain unverified.
- Added versioned user-authored project briefs with atomic append, expected-version conflict checks, exact source snapshots, and immutable revision history. Migration 0033 adds member-read RLS, API-only writes, role-checked RPCs, export/deletion handling, and rollback; async and staging verification remain open.

### Security, reliability, and operations

- Added migrations 0012–0034 for active-project RLS checks, project PDF pages, invitations, durable plan metadata, notification controls, spend metering, summary provenance, Crossref status/provenance, account-deletion lease renewal, watch relevance hints, legacy crawl-cache identity, project annotations, saved searches, versioned project briefs, and service-only benchmark snapshots.
- Changed SSE authentication to short-lived bearer tokens in the Authorization header and cursor-based event replay; removed query-token authentication and added abortable fetch-stream cleanup.
- Disabled hosted Firecrawl crawling and legacy cache reads/writes until redirect and egress controls can be enforced; removed the unused API-key setting.
- Restricted selectable models to verified spend-price entries and reject future registry/catalog mismatches.
- Added service-only database operations, provider-call budgets, request limits, bounded timeouts, durable account-deletion jobs, and Redis/Postgres-backed run recovery controls.
- Expanded deterministic retrieval, PDF evidence, synthesis-contract, research-plan, watchlist, invitation, and provider regression coverage.
- Updated repository lint/format commands and aligned this plan with the current capability matrix.

## Release status

These entries describe local implementation. Project annotations support attached-paper abstracts and uploaded PDF pages, saved searches support repeatable project queries, and briefs preserve user-authored revisions with source snapshots. Page-grounded public-paper evidence remains open. Production readiness is **not established**: current-head CI, Docker image verification, staging migrations/RLS, live providers and email, backup/restore, recovery, monitoring, and human quality review remain open. See [docs/STATUS.md](docs/STATUS.md) before deployment.
