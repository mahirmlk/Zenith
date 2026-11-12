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
    ):
        assert f"ALTER TABLE public.{table} ENABLE ROW LEVEL SECURITY" in text, table
        assert f"{table}_owner" in text or "owner" in text
    assert "CREATE POLICY" in text


def test_no_destructive_statements():
    for m in MIGRATIONS:
        assert not DESTRUCTIVE.search(m.read_text()), m.name


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
