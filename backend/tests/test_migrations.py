"""Migration verification (update.md §5.3, §16).

Static checks that run without a live DB: every migration enables RLS
on user-scoped tables, uses IF NOT EXISTS / additive patterns, and
never contains destructive statements.
"""
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parents[2]
MIGRATIONS = sorted((ROOT / "supabase" / "migrations").glob("*.sql"))

DESTRUCTIVE = re.compile(r"\b(DROP TABLE|TRUNCATE|DELETE FROM)\b", re.I)


def test_migrations_exist():
    assert len(MIGRATIONS) >= 4, [str(m) for m in MIGRATIONS]


def test_every_user_table_has_rls():
    text = " ".join(" ".join(m.read_text().split()) for m in MIGRATIONS)
    for table in (
        "user_papers", "user_prefs", "projects", "notes", "watchlists",
        "notifications", "project_documents", "project_document_pages",
        "saved_searches", "project_briefs", "project_brief_versions",
    ):
        assert f"ALTER TABLE public.{table} ENABLE ROW LEVEL SECURITY" in text, table
        assert f"{table}_owner" in text or "owner" in text
    assert "CREATE POLICY" in text


def test_saved_searches_are_project_scoped_and_have_rollback():
    migration = (ROOT / "supabase" / "migrations" / "0032_saved_searches.sql").read_text()
    normalized = " ".join(migration.lower().split())
    for expected in (
        "create table if not exists public.saved_searches",
        "alter table public.saved_searches enable row level security",
        "public.can_access_project(project_id)",
        "public.can_write_project(project_id)",
        "created_by = auth.uid()",
        "create trigger saved_searches_touch_updated_at",
    ):
        assert expected in normalized
    rollback = (ROOT / "supabase" / "rollbacks" / "0032_saved_searches.sql").read_text().lower()
    assert "drop table if exists public.saved_searches" in rollback


def test_no_destructive_statements():
    for m in MIGRATIONS:
        text = m.read_text()
        if m.name == "0016_resumable_account_deletions.sql":
            normalized = " ".join(text.lower().split())
            assert "where j.status = 'complete' and j.completed_at < now() - interval '30 days'" in normalized
            text = re.sub(
                r"create or replace function public\.prune_account_deletion_jobs\(\).*?\$\$;",
                "",
                text,
                flags=re.I | re.S,
            )
        text = "\n".join(line for line in text.splitlines() if not line.lstrip().startswith("--"))
        assert not DESTRUCTIVE.search(text), m.name


def test_migrations_are_additive():
    for m in MIGRATIONS:
        text = m.read_text()
        assert "BEGIN;" in text and "COMMIT;" in text, m.name


def test_project_role_migration_has_narrow_member_policies():
    migration = (ROOT / "supabase" / "migrations" / "0009_project_role_rls.sql").read_text()
    normalized = " ".join(migration.lower().split())
    assert "security definer" in normalized
    assert "set search_path = ''" in normalized
    assert "projects_select_member" in normalized
    assert "project_members_select_access" in normalized
    assert "notes_select_access" in normalized
    assert "notes_insert_writer" in normalized
    assert "created_by = auth.uid()" in normalized
    assert "pm.role in ('owner', 'editor')" in normalized
    assert "for delete to authenticated" in normalized
    assert "project_members_delete_owner" in normalized


def test_project_paper_sources_are_unique_and_migration_is_reversible():
    migration = (ROOT / "supabase" / "migrations" / "0010_unique_project_paper_sources.sql").read_text()
    normalized = " ".join(migration.lower().split())
    assert "create unique index if not exists idx_project_sources_project_paper" in normalized
    assert "on public.project_sources (project_id, paper_id)" in normalized
    assert "where paper_id is not null" in normalized
    assert "drop index if exists public.idx_project_sources_project_paper" in normalized


def test_notifications_can_retain_watchlist_project_context():
    migration = (ROOT / "supabase" / "migrations" / "0011_notifications_project_scope.sql").read_text()
    normalized = " ".join(migration.lower().split())
    assert "add column if not exists project_id uuid" in normalized
    assert "references public.projects(id) on delete set null" in normalized
    assert "drop index if exists public.idx_notifications_project" in normalized


def test_watchlist_notification_reasons_are_additive_and_bounded():
    migration = (ROOT / "supabase" / "migrations" / "0021_watchlist_notification_reasons.sql").read_text()
    normalized = " ".join(migration.lower().split())
    assert "add column if not exists reason_code text" in normalized
    assert "add column if not exists reason_text text" in normalized
    assert "'topic_term_overlap', 'author_relation', 'citation_relation'" in normalized
    assert "char_length(reason_text) <= 500" in normalized
    rollback = (ROOT / "supabase" / "rollbacks" / "0021_watchlist_notification_reasons.sql").read_text().lower()
    assert "drop column if exists reason_code" in rollback
    assert "drop column if exists reason_text" in rollback


def test_project_watch_relevance_explanations_are_optional_and_bounded():
    migration = (ROOT / "supabase" / "migrations" / "0028_project_watch_relevance_explanations.sql").read_text()
    normalized = " ".join(migration.lower().split())
    assert "add column if not exists project_relevance_code text" in normalized
    assert "add column if not exists project_relevance_text text" in normalized
    assert "project_relevance_code = 'project_term_overlap'" in normalized
    assert "char_length(project_relevance_text) <= 500" in normalized
    rollback = (ROOT / "supabase" / "rollbacks" / "0028_project_watch_relevance_explanations.sql").read_text().lower()
    assert "drop column if exists project_relevance_code" in rollback
    assert "drop column if exists project_relevance_text" in rollback


def test_arxiv_version_metadata_preserves_distinct_versions_and_adds_alert_reason():
    migration = (ROOT / "supabase" / "migrations" / "0022_arxiv_preprint_version_metadata.sql").read_text()
    normalized = " ".join(migration.lower().split())
    assert "add column if not exists preprint_id text" in normalized
    assert "add column if not exists source_version integer" in normalized
    assert "add column if not exists source_updated_at timestamptz" in normalized
    assert "regexp_replace(id, 'v[1-9][0-9]*$', '')" in normalized
    assert "idx_papers_preprint_id_version" in normalized
    assert "'preprint_version_updated'" in normalized
    assert "drop table" not in normalized
    rollback = (ROOT / "supabase" / "rollbacks" / "0022_arxiv_preprint_version_metadata.sql").read_text().lower()
    assert "drop column if exists source_version" in rollback
    assert "drop column if exists source_updated_at" in rollback


def test_crossref_status_watch_is_opt_in_provenanced_and_reversible():
    migration = (ROOT / "supabase" / "migrations" / "0025_crossref_publication_status.sql").read_text()
    normalized = " ".join(migration.lower().split())
    assert "add column if not exists doi text" in normalized
    assert "publication_update_source = 'crossref'" in normalized
    assert "create table if not exists public.paper_status_watches" in normalized
    assert "primary key (user_id, paper_id)" in normalized
    assert "alter table public.paper_status_watches enable row level security" in normalized
    assert "using (user_id = auth.uid())" in normalized
    assert "with check (user_id = auth.uid())" in normalized
    assert "uq_notifications_user_key" in normalized
    assert "'publication_status_update'" in normalized

    rollback = (ROOT / "supabase" / "rollbacks" / "0025_crossref_publication_status.sql").read_text().lower()
    assert "drop table if exists public.paper_status_watches" in rollback
    assert "drop column if exists notification_key" in rollback
    assert "drop column if exists publication_update_type" in rollback
    assert "drop column if exists doi" in rollback


def test_crossref_notice_deposit_source_is_optional_bounded_and_reversible():
    migration = (ROOT / "supabase" / "migrations" / "0029_crossref_notice_deposit_source.sql").read_text()
    normalized = " ".join(migration.lower().split())
    assert "add column if not exists publication_update_deposit_source text" in normalized
    assert "publication_update_deposit_source is null or publication_update_deposit_source in (" in normalized
    assert "'publisher', 'retraction-watch'" in normalized
    assert "publication_update_deposit_source is null)" in normalized
    assert "publication_update_source = 'crossref'" in normalized

    rollback = (ROOT / "supabase" / "rollbacks" / "0029_crossref_notice_deposit_source.sql").read_text().lower()
    assert "drop column if exists publication_update_deposit_source" in rollback
    assert "publication_update_source = 'crossref'" in rollback


def test_crawled_content_cache_version_is_additive_and_reversible():
    migration = (ROOT / "supabase" / "migrations" / "0030_crawled_content_cache_identity.sql").read_text()
    normalized = " ".join(migration.lower().split())
    assert "alter table public.crawled_content add column if not exists parser_version text" in normalized
    assert "drop table" not in normalized

    rollback = (ROOT / "supabase" / "rollbacks" / "0030_crawled_content_cache_identity.sql").read_text().lower()
    assert "drop column if exists parser_version" in rollback


def test_project_annotations_are_project_scoped_and_role_protected():
    migration = (ROOT / "supabase" / "migrations" / "0031_project_annotations.sql").read_text()
    normalized = " ".join(migration.lower().split())
    for expected in (
        "create table if not exists public.project_annotations",
        "source_type in ('paper_abstract', 'pdf_page')",
        "foreign key (paper_source_id, project_id)",
        "references public.project_sources (id, project_id)",
        "foreign key (document_id, project_id)",
        "references public.project_documents (id, project_id)",
        "foreign key (document_id, page_number)",
        "references public.project_document_pages (document_id, page_number)",
        "revoke insert, update, delete on public.project_annotations from public, anon, authenticated",
        "grant select on public.project_annotations to authenticated",
        "alter table public.project_annotations enable row level security",
        "public.can_access_project(project_id)",
        "public.can_write_project(project_id)",
        "created_by = auth.uid()",
        "keep_project_annotation_anchor_immutable",
    ):
        assert expected in normalized

    rollback = (ROOT / "supabase" / "rollbacks" / "0031_project_annotations.sql").read_text().lower()
    assert "drop table if exists public.project_annotations" in rollback
    assert "drop function if exists public.keep_project_annotation_anchor_immutable" in rollback


def test_versioned_project_briefs_are_atomic_role_scoped_and_immutable():
    migration = (ROOT / "supabase" / "migrations" / "0033_versioned_project_briefs.sql").read_text()
    normalized = " ".join(migration.lower().split())
    for expected in (
        "create table if not exists public.project_briefs",
        "create table if not exists public.project_brief_versions",
        "alter table public.project_briefs enable row level security",
        "alter table public.project_brief_versions enable row level security",
        "create policy project_briefs_select_access",
        "create policy project_brief_versions_select_access",
        "unique (brief_id, version)",
        "origin text not null default 'user_authored'",
        "public.can_access_project(project_id)",
        "public.can_access_project(b.project_id)",
        "revoke insert, update, delete on public.project_briefs from public, anon, authenticated",
        "revoke insert, update, delete on public.project_brief_versions from public, anon, authenticated",
        "grant select on public.project_briefs, public.project_brief_versions to authenticated",
        "for update",
        "brief_version_conflict",
        "p_expected_current_version <> v_brief.current_version",
        "public.validate_project_brief_sources",
        "substring(v_source_text from v_start + 1 for v_end - v_start) <> v_quote",
        "join public.papers p on p.id = ps.paper_id",
        "public.project_document_pages page",
        "grant execute on function public.append_project_brief_version",
        "grant execute on function public.create_project_brief",
        "set search_path = ''",
        "public.project_document_pages page",
        "join public.papers p on p.id = ps.paper_id",
    ):
        assert expected in normalized

    rollback = (ROOT / "supabase" / "rollbacks" / "0033_versioned_project_briefs.sql").read_text().lower()
    assert "drop table if exists public.project_brief_versions" in rollback
    assert "drop function if exists public.append_project_brief_version" in rollback
    assert "drop function if exists public.reconcile_project_brief_head_after_version_delete" in rollback
    assert rollback.index("drop trigger if exists project_brief_head_after_version_delete") < rollback.index(
        "drop function if exists public.reconcile_project_brief_head_after_version_delete"
    )
    assert rollback.index("drop trigger if exists project_brief_head_after_version_delete") < rollback.index(
        "drop function if exists public.reconcile_project_brief_head_after_version_delete"
    )


def test_project_rls_helpers_reject_soft_deleted_projects():
    migration = (ROOT / "supabase" / "migrations" / "0012_hide_deleted_projects_in_rls.sql").read_text()
    normalized = " ".join(migration.lower().split())
    assert "create or replace function public.is_project_owner" in normalized
    assert "create or replace function public.can_access_project" in normalized
    assert "create or replace function public.can_write_project" in normalized
    assert normalized.count("p.deleted_at is null") == 3
    assert "pm.role in ('owner', 'editor')" in normalized
    assert "set search_path = ''" in normalized


def test_project_pdf_page_migration_is_scoped_and_page_bounded():
    migration = (ROOT / "supabase" / "migrations" / "0013_project_pdf_pages.sql").read_text()
    normalized = " ".join(migration.lower().split())
    assert "create table if not exists public.project_documents" in normalized
    assert "create table if not exists public.project_document_pages" in normalized
    assert "alter table public.project_documents enable row level security" in normalized
    assert "alter table public.project_document_pages enable row level security" in normalized
    assert "public.can_access_project(project_id)" in normalized
    assert "public.can_write_project(project_id)" in normalized
    assert "page_number integer not null check (page_number between 1 and 500)" in normalized
    assert "char_length(text) <= 100000" in normalized


def test_provider_spend_migration_is_service_only_atomic_and_reversible():
    migration = (ROOT / "supabase" / "migrations" / "0023_provider_spend_metering.sql").read_text()
    normalized = " ".join(migration.lower().split())
    assert "create table if not exists public.model_spend_ledger" in normalized
    assert "enable row level security" in normalized
    assert "revoke all on public.model_spend_ledger from public, anon, authenticated" in normalized
    assert "revoke all on public.model_spend_ledger from service_role" in normalized
    assert "grant select, insert, update on public.model_spend_ledger to service_role" not in normalized
    assert "grant execute on function public.reserve_model_spend" in normalized
    assert "pg_advisory_xact_lock(hashtextextended(p_subject_id, 0))" in normalized
    assert "date_trunc('day', now() at time zone 'utc')" in normalized
    assert "date_trunc('month', now() at time zone 'utc')" in normalized
    assert "'settled', 'over_budget'" in normalized
    assert "openrouter_generation_id" in normalized
    assert "openrouter_request_id" in normalized
    assert "anonymize_model_spend_subject" in normalized
    assert "'run_events', 'model_spend', 'user_rows', 'auth_user'" in normalized
    assert "cardinality(j.completed_steps) = 9" in normalized
    rollback = (ROOT / "supabase" / "rollbacks" / "0023_provider_spend_metering.sql").read_text().lower()
    assert "drop function if exists public.reserve_model_spend" in rollback
    assert "drop function if exists public.record_model_spend_reference" in rollback
    assert "drop table if exists public.model_spend_ledger" in rollback
    assert "cardinality(j.completed_steps) = 8" in rollback


def test_spend_ledger_acl_correction_revokes_direct_service_role_access():
    migration = (ROOT / "supabase" / "migrations" / "0026_restrict_spend_ledger_table_access.sql").read_text()
    normalized = " ".join(migration.lower().split())
    assert "revoke all privileges on table public.model_spend_ledger from public, anon, authenticated, service_role" in normalized
    assert "create index if not exists idx_model_spend_ledger_subject_created_at on public.model_spend_ledger (subject_id, created_at)" in normalized
    assert "security definer" in (ROOT / "supabase" / "migrations" / "0023_provider_spend_metering.sql").read_text().lower()


def test_summary_provenance_migration_defaults_legacy_rows_to_unknown():
    migration = (ROOT / "supabase" / "migrations" / "0024_summary_provenance.sql").read_text()
    normalized = " ".join(migration.lower().split())
    assert "add column if not exists summary_status text not null default 'unknown'" in normalized
    assert "add column if not exists summary_fallback_reason text" in normalized
    assert "'generated', 'abstract_preview', 'unknown'" in normalized
    assert "'per_run_cap', 'spend_limit', 'billing_unavailable', 'provider_unavailable', 'invalid_output'" in normalized
    assert "summary_status = 'abstract_preview' and summary_fallback_reason is not null" in normalized
    assert "summary_status in ('generated', 'unknown') and summary_fallback_reason is null" in normalized
    rollback = (ROOT / "supabase" / "rollbacks" / "0024_summary_provenance.sql").read_text().lower()
    assert "drop column if exists summary_status" in rollback
    assert "drop column if exists summary_fallback_reason" in rollback


def test_summary_provenance_fields_have_unknown_defaults_and_no_new_rls_surface():
    schema = (ROOT / "supabase" / "schema.sql").read_text().lower()
    assert "add column if not exists summary_status text not null default 'unknown'" in schema
    assert "summary_fallback_reason text" in schema


def test_project_email_invitation_migration_is_atomic_and_service_only():
    migration = (ROOT / "supabase" / "migrations" / "0014_project_email_invitations.sql").read_text()
    normalized = " ".join(migration.lower().split())
    assert "create table if not exists public.project_invitations" in normalized
    assert "on public.project_invitations (normalized_email)" in normalized
    assert "on public.project_invitations (project_id, normalized_email)" not in normalized
    assert "alter table public.project_invitations enable row level security" in normalized
    assert "for select to authenticated" in normalized
    assert "public.is_project_owner(project_id)" in normalized
    assert "revoke all on public.project_invitations from public, anon" in normalized
    assert "revoke insert, update, delete on public.project_invitations from authenticated" in normalized
    assert "security definer" in normalized and "set search_path = ''" in normalized
    assert "u.email_confirmed_at" in normalized
    assert "v_user_email <> v_invitation.normalized_email" in normalized
    assert "p.deleted_at is null" in normalized
    assert "on conflict (project_id, user_id)" in normalized
    assert "do nothing returning role into v_member_role" in normalized
    assert "select pm.role into v_member_role" in normalized
    assert "do update set role = excluded.role" not in normalized
    assert "grant execute on function public.accept_project_invitation(uuid, uuid) to service_role" in normalized


def test_semantic_scholar_watch_targets_preserve_topic_rows_and_add_bounds():
    migration = (ROOT / "supabase" / "migrations" / "0015_semantic_scholar_watch_targets.sql").read_text()
    normalized = " ".join(migration.lower().split())
    assert "add column if not exists target_type text not null default 'topic'" in normalized
    assert "add column if not exists target_id text" in normalized
    assert "target_type in ('author', 'citation')" in normalized
    assert "length(target_id) between 1 and 200" in normalized
    assert "drop column if exists target_id" in normalized


def test_account_deletion_jobs_are_durable_service_only_and_resumable():
    migration = (ROOT / "supabase" / "migrations" / "0016_resumable_account_deletions.sql").read_text()
    normalized = " ".join(migration.lower().split())
    assert "create table if not exists public.account_deletion_jobs" in normalized
    assert "user_id uuid not null," in normalized
    assert "user_id uuid not null references auth.users" not in normalized
    assert "enable row level security" in normalized
    assert "revoke all on public.account_deletion_jobs from public, anon, authenticated" in normalized
    assert "for update skip locked" in normalized
    assert "on public.account_deletion_jobs (user_id) where status in ('pending', 'processing')" in normalized
    assert "cardinality(j.completed_steps) = 8" in normalized
    assert "completed_at < now() - interval '30 days'" in normalized
    assert "grant execute on function public.claim_account_deletion_job(text, integer) to service_role" in normalized


def test_account_deletion_is_serialized_with_research_run_admission():
    migration = (
        ROOT
        / "supabase"
        / "migrations"
        / "0017_serialize_account_deletion_and_run_admission.sql"
    ).read_text()
    normalized = " ".join(migration.lower().split())
    assert normalized.count("pg_advisory_xact_lock(") == 2
    assert "hashtextextended(p_user_id::text, 0)" in normalized
    assert "j.status in ('pending', 'processing', 'complete')" in normalized
    assert "message = 'account_deletion_in_progress'" in normalized
    assert "grant execute on function public.request_account_deletion(uuid) to service_role" in normalized
    assert "grant execute on function public.create_research_run_atomic(uuid, uuid, text, text, text, integer) to service_role" in normalized
    rollback = (
        ROOT
        / "supabase"
        / "rollbacks"
        / "0017_restore_unserialized_run_admission.sql"
    ).read_text()
    assert "create or replace function public.request_account_deletion" in rollback.lower()
    assert "create or replace function public.create_research_run_atomic" in rollback.lower()
    assert "pg_advisory_xact_lock" not in rollback.lower()


def test_account_deletion_lease_renewal_is_owner_bound_and_service_only():
    migration = (ROOT / "supabase" / "migrations" / "0027_renew_account_deletion_leases.sql").read_text()
    normalized = " ".join(migration.lower().split())
    assert "create or replace function public.renew_account_deletion_lease" in normalized
    assert "j.lease_owner = p_lease_owner" in normalized
    assert "j.lease_expires_at > now()" in normalized
    assert "p_lease_seconds not between 60 and 3600" in normalized
    assert "revoke all on function public.renew_account_deletion_lease(uuid, text, integer) from public, anon, authenticated" in normalized
    assert "to service_role" in normalized
    rollback = (ROOT / "supabase" / "rollbacks" / "0027_renew_account_deletion_leases.sql").read_text().lower()
    assert "drop function if exists public.renew_account_deletion_lease(uuid, text, integer)" in " ".join(rollback.split())


def test_pdf_page_extraction_method_is_additive_and_scope_preserving():
    migration = (
        ROOT / "supabase" / "migrations" / "0018_pdf_page_extraction_method.sql"
    ).read_text()
    normalized = " ".join(migration.lower().split())
    assert "add column if not exists extraction_method text not null default 'native'" in normalized
    assert "where text = '' and extraction_method = 'native'" in normalized
    assert "check (extraction_method in ('native', 'ocr', 'empty', 'ocr_limit'))" in normalized
    assert "enable row level security" not in normalized
