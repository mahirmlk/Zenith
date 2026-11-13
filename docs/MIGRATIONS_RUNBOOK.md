# Migration Runbook (update.md §5.3, §16)

Migrations 0001–0019 live in `supabase/migrations/`. They are additive SQL migration files; policy replacements use `DROP POLICY IF EXISTS` for idempotent re-runs. Migration 0008 makes Postgres the canonical production run/event store and adds service-role-only atomic RPCs. Migration 0009 aligns direct authenticated project access with owner/editor/viewer roles. Migration 0010 enforces one paper attachment per project and intentionally fails if duplicate relations need reconciliation. Migration 0011 adds nullable project context to watchlist notifications. Migration 0012 updates the three project authorization helpers so direct PostgREST access also rejects soft-deleted projects. Migration 0013 adds project-scoped extracted PDF document/page text with RLS. Migration 0014 adds owner-readable email invitations, a global active-email uniqueness rule, and a service-role-only atomic verified-email acceptance RPC; direct client writes are revoked. Migration 0015 adds stable Semantic Scholar author/citation target columns while retaining existing topic rows. Migration 0016 adds a service-only resumable account-deletion ledger, cross-replica leases, step progress, and 30-day completion-marker retention. Migration 0017 serializes per-user run creation with deletion requests to close the in-flight run snapshot race. Migration 0018 adds page extraction-source metadata without changing project RLS. Migration 0019 persists the plan configuration attached to existing durable run records; it adds no second queue. These migrations have not been applied or exercised against a live Supabase project. Apply and verify in staging before production.

**Apply order:** staging first, then production. Never apply to production without staging verification.
**Status:** drafted and statically checked; NOT yet applied to any live database. The Postgres/RLS behavior, migration rollback, backups, and tenant isolation still need staging evidence (see [STATUS.md](STATUS.md)).

LangGraph's Postgres checkpointer uses `DATABASE_URL` to the same Supabase Postgres database as the run store. App startup calls the checkpointer's additive `setup()` migration and fails closed if it cannot initialize. Provision a dedicated least-privilege application connection with the required table DDL rights, verify the resulting `checkpoints`, `checkpoint_blobs`, `checkpoint_writes`, and `checkpoint_migrations` tables in staging, and include them in backups/restores. These library-owned tables are not part of migrations 0001–0019. Expired graph threads are deleted with their expired terminal run records; active runs are retained.

```bash
# 1. Apply in order (Supabase dashboard SQL editor or psql)
psql "$STAGING_DATABASE_URL" -f supabase/migrations/0001_enable_rls_and_projects.sql
psql "$STAGING_DATABASE_URL" -f supabase/migrations/0002_projects_notes_sources.sql
psql "$STAGING_DATABASE_URL" -f supabase/migrations/0003_watchlists.sql
psql "$STAGING_DATABASE_URL" -f supabase/migrations/0004_notifications.sql
psql "$STAGING_DATABASE_URL" -f supabase/migrations/0005_rls_policies_completion.sql
psql "$STAGING_DATABASE_URL" -f supabase/migrations/0006_summary_contributions.sql
psql "$STAGING_DATABASE_URL" -f supabase/migrations/0007_watchlist_notification_dedupe.sql
psql "$STAGING_DATABASE_URL" -f supabase/migrations/0008_canonical_research_runs.sql
psql "$STAGING_DATABASE_URL" -f supabase/migrations/0009_project_role_rls.sql
psql "$STAGING_DATABASE_URL" -f supabase/migrations/0010_unique_project_paper_sources.sql
psql "$STAGING_DATABASE_URL" -f supabase/migrations/0011_notifications_project_scope.sql
psql "$STAGING_DATABASE_URL" -f supabase/migrations/0012_hide_deleted_projects_in_rls.sql
psql "$STAGING_DATABASE_URL" -f supabase/migrations/0013_project_pdf_pages.sql
psql "$STAGING_DATABASE_URL" -f supabase/migrations/0014_project_email_invitations.sql
psql "$STAGING_DATABASE_URL" -f supabase/migrations/0015_semantic_scholar_watch_targets.sql
psql "$STAGING_DATABASE_URL" -f supabase/migrations/0016_resumable_account_deletions.sql
psql "$STAGING_DATABASE_URL" -f supabase/migrations/0017_serialize_account_deletion_and_run_admission.sql
psql "$STAGING_DATABASE_URL" -f supabase/migrations/0018_pdf_page_extraction_method.sql
psql "$STAGING_DATABASE_URL" -f supabase/migrations/0019_durable_research_plan_execution.sql

# 2. Verify RLS: run the owner/member/editor/viewer/outsider/anon matrix in
#    docs/security/SECURITY_TEST_PLAN.md, including project metadata, notes,
#    source rows, memberships, invitations (owner-only SELECT; no anon or
#    authenticated writes), runs, and events. Test acceptance for matching
#    verified email, mismatch, unverified, expiry, revocation, deleted project,
#    duplicate acceptance, and an existing member/owner role that must not change.
#    Include an active project and
#    a soft-deleted project for every role; deleted project reads and writes
#    must be denied for owners, members, editors, and viewers.
#    Confirm account_deletion_jobs is unreadable to anon/authenticated and
#    writable only through service_role RPCs; verify a job survives Auth
#    deletion, resumes from completed_steps, and is pruned after 30 days.
#    Race two transactions around create_research_run_atomic and
#    request_account_deletion; confirm the run is snapshotted or rejected,
#    never omitted from external cleanup.
#    Build the production image, leave OCR_ENABLED=false and verify native
#    extraction; then enable it to verify scanned/mixed pages, extraction_method
#    reporting, the five-page/8M-pixel/6-second/20-second caps, and clear failure
#    when the local OCR runtime is missing.
#    Leave RESEARCH_PLAN_EXECUTION_ENABLED=false initially. Then enable it in
#    staging and verify the 202 request uses the existing run/queue/checkpoint
#    lifecycle; test public and project scope, membership revocation between
#    steps, ten-source and classifier-specific tool/time ceilings (2/3/4/6
#    tool calls and 20/30/45/90 seconds for feed/explain/compare/deep research),
#    the five-request/IP/minute limit, ten-execution/user/day budget exhaustion,
#    cancellation, worker restart at checkpoints, and at-least-once retries.
#    Confirm synthesis stays behind its separate two-call/1,800-token gate and
#    monetary cost remains explicitly untracked; do not enable in production before
#    quality review and recovery checks pass.

# 3. Migration 0017 rollback is only allowed after stopping API workers and
#    draining deletion jobs; restore its two prior RPC bodies with
#    supabase/rollbacks/0017_restore_unserialized_run_admission.sql.
#    Migration 0019 rollback requires RESEARCH_PLAN_EXECUTION_ENABLED=false,
#    stopped workers, and no active plan-backed runs; it removes only the
#    service-only plan metadata table after confirming retention/cascade state:
#    supabase/rollbacks/0019_disable_durable_research_plan_execution.sql.
#    Do not use automatic down migrations. Roll back 0008–0012 only with a
#    reviewed recovery plan, exported run history, stopped workers, and a
#    tested restore. Never drop user data tables as a routine rollback.
```

**Current status (2026-11-13):** migrations 0001–0018 are drafted and statically checked but **not yet applied to any live database**. No live database credentials or staging environment were available in this workspace. This is a release blocker, not a routine post-deploy step.

For email onboarding, set the Supabase “Invite user” template and SMTP provider,
allow the exact `APP_URL/projects/invitations/accept` URL in Auth redirect URLs,
and set the Auth invite link expiry to one hour to match the application state.
The `APP_URL` must be HTTPS in production. Verify delivery, callback/session
creation, acceptance, resend/revoke, and existing-account handling in staging.
