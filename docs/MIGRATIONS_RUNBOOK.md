# Migration Runbook (update.md §5.3, §16)

Migrations 0001–0006 live in `supabase/migrations/` (additive, reversible; 0005 uses DROP POLICY IF EXISTS for idempotent re-runs — verified by `backend/tests/test_migrations.py`).

**Apply order:** staging first, then production. Never apply to production without staging verification.
**Status:** drafted and statically verified; NOT yet applied to any live database. This is the one remaining manual step before production (see [STATUS.md](STATUS.md)).

```bash
# 1. Apply in order (Supabase dashboard SQL editor or psql)
psql "$STAGING_DATABASE_URL" -f supabase/migrations/0001_enable_rls_and_projects.sql
psql "$STAGING_DATABASE_URL" -f supabase/migrations/0002_projects_notes_sources.sql
psql "$STAGING_DATABASE_URL" -f supabase/migrations/0003_watchlists.sql
psql "$STAGING_DATABASE_URL" -f supabase/migrations/0004_notifications.sql
psql "$STAGING_DATABASE_URL" -f supabase/migrations/0005_rls_policies_completion.sql
psql "$STAGING_DATABASE_URL" -f supabase/migrations/0006_summary_contributions.sql

# 2. Verify RLS: as anon, SELECT on user_papers must return 0 rows;
#    as user A, user B's rows must be invisible (see SECURITY_TEST_PLAN).

# 3. Rollback (if needed): drop the policies/objects added above.
#    Never drop user data tables as a 'rollback'.
```

**Current status (2026-11-05):** migrations are drafted + statically verified but **not yet applied to any live database** (no DB credentials in the build sandbox). This is the one remaining manual step before production.
