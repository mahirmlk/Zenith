-- Migration 0034: official HF benchmark watch snapshots and safe alert links.
-- Rollback: supabase/rollbacks/0034_official_benchmark_monitoring.sql.
BEGIN;

ALTER TABLE public.watchlists
  DROP CONSTRAINT IF EXISTS watchlists_target_shape;
ALTER TABLE public.watchlists
  ADD CONSTRAINT watchlists_target_shape CHECK (
    (target_type = 'topic' AND target_id IS NULL)
    OR (target_type IN ('author', 'citation') AND target_id IS NOT NULL AND length(target_id) BETWEEN 1 AND 200)
    OR (target_type = 'benchmark' AND target_id IS NOT NULL
      AND target_id ~ '^[A-Za-z0-9][A-Za-z0-9_.-]{0,95}/[A-Za-z0-9][A-Za-z0-9_.-]{0,95}$'
      AND query = target_id)
  );

CREATE INDEX IF NOT EXISTS idx_watchlists_enabled_benchmark
  ON public.watchlists (id)
  WHERE enabled AND target_type = 'benchmark';

CREATE TABLE IF NOT EXISTS public.benchmark_watch_snapshots (
  watchlist_id UUID PRIMARY KEY REFERENCES public.watchlists(id) ON DELETE CASCADE,
  snapshot JSONB NOT NULL CHECK (
    jsonb_typeof(snapshot) = 'array'
    AND jsonb_array_length(snapshot) <= 100
    AND pg_column_size(snapshot) <= 262144
  ),
  snapshot_hash TEXT NOT NULL CHECK (snapshot_hash ~ '^[0-9a-f]{64}$'),
  observed_at TIMESTAMPTZ NOT NULL
);
ALTER TABLE public.benchmark_watch_snapshots ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.benchmark_watch_snapshots FROM PUBLIC, anon, authenticated;
GRANT ALL ON public.benchmark_watch_snapshots TO service_role;

ALTER TABLE public.notifications
  ADD COLUMN IF NOT EXISTS source_url TEXT;
ALTER TABLE public.notifications
  DROP CONSTRAINT IF EXISTS notifications_source_url_check;
ALTER TABLE public.notifications
  ADD CONSTRAINT notifications_source_url_check CHECK (
    source_url IS NULL OR (
      kind = 'benchmark'
      AND source_url ~ '^https://huggingface[.]co/datasets/[A-Za-z0-9][A-Za-z0-9_.-]{0,95}/[A-Za-z0-9][A-Za-z0-9_.-]{0,95}$'
    )
  );
ALTER TABLE public.notifications
  DROP CONSTRAINT IF EXISTS notifications_reason_code_check;
ALTER TABLE public.notifications
  ADD CONSTRAINT notifications_reason_code_check
  CHECK (reason_code IS NULL OR reason_code IN (
    'topic_term_overlap', 'author_relation', 'citation_relation',
    'preprint_version_updated', 'publication_status_update', 'benchmark_result_observed'
  ));

COMMIT;
