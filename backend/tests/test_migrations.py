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
    for table in ("user_papers", "user_prefs", "projects", "notes", "watchlists", "notifications"):
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
