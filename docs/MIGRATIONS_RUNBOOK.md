# Migration Runbook (update.md §5.3, §16)

Migrations 0001–0013 live in `supabase/migrations/`. They are additive SQL migration files; policy replacements use `DROP POLICY IF EXISTS` for idempotent re-runs. Migration 0008 makes Postgres the canonical production run/event store and adds service-role-only atomic RPCs. Migration 0009 aligns direct authenticated project access with owner/editor/viewer roles. Migration 0010 enforces one paper attachment per project and intentionally fails if duplicate relations need reconciliation. Migration 0011 adds nullable project context to watchlist notifications. Migration 0012 updates the three project authorization helpers so direct PostgREST access also rejects soft-deleted projects. Migration 0013 adds project-scoped extracted PDF document/page text with RLS. These migrations have not been applied or exercised against a live Supabase project. Apply and verify in staging before production.

**Apply order:** staging first, then production. Never apply to production without staging verification.
**Status:** drafted and statically checked; NOT yet applied to any live database. The Postgres/RLS behavior, migration rollback, backups, and tenant isolation still need staging evidence (see [STATUS.md](STATUS.md)).

LangGraph's Postgres checkpointer uses `DATABASE_URL` to the same Supabase Postgres database as the run store. App startup calls the checkpointer's additive `setup()` migration and fails closed if it cannot initialize. Provision a dedicated least-privilege application connection with the required table DDL rights, verify the resulting `checkpoints`, `checkpoint_blobs`, `checkpoint_writes`, and `checkpoint_migrations` tables in staging, and include them in backups/restores. These library-owned tables are not part of migrations 0001–0012. Expired graph threads are deleted with their expired terminal run records; active runs are retained.

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

# 2. Verify RLS: run the owner/member/editor/viewer/outsider/anon matrix in
#    docs/security/SECURITY_TEST_PLAN.md, including project metadata, notes,
#    source rows, memberships, runs, and events. Include an active project and
#    a soft-deleted project for every role; deleted project reads and writes
#    must be denied for owners, members, editors, and viewers.

# 3. Do not use automatic down migrations. Roll back 0008–0012 only with a
#    reviewed recovery plan, exported run history, stopped workers, and a
#    tested restore. Never drop user data tables as a routine rollback.
```

**Current status (2026-11-12):** migrations 0001–0013 are drafted and statically checked but **not yet applied to any live database**. No live database credentials or staging environment were available in this workspace. This is a release blocker, not a routine post-deploy step.
