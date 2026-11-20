-- Roll back migration 0034 only after operators have exported or deliberately
-- removed benchmark watches, alerts, and snapshots. Refuse to discard them.
BEGIN;
DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM public.watchlists WHERE target_type = 'benchmark')
     OR EXISTS (SELECT 1 FROM public.notifications WHERE kind = 'benchmark')
     OR EXISTS (SELECT 1 FROM public.benchmark_watch_snapshots) THEN
    RAISE EXCEPTION 'benchmark watches or observations exist; export/remove them before rollback';
  END IF;
END;
$$;

DROP TABLE public.benchmark_watch_snapshots;
ALTER TABLE public.notifications DROP CONSTRAINT IF EXISTS notifications_source_url_check;
ALTER TABLE public.notifications DROP COLUMN IF EXISTS source_url;
ALTER TABLE public.notifications DROP CONSTRAINT IF EXISTS notifications_reason_code_check;
ALTER TABLE public.notifications
  ADD CONSTRAINT notifications_reason_code_check
  CHECK (reason_code IS NULL OR reason_code IN (
    'topic_term_overlap', 'author_relation', 'citation_relation',
    'preprint_version_updated', 'publication_status_update'
  ));
DROP INDEX IF EXISTS public.idx_watchlists_enabled_benchmark;
ALTER TABLE public.watchlists DROP CONSTRAINT IF EXISTS watchlists_target_shape;
ALTER TABLE public.watchlists
  ADD CONSTRAINT watchlists_target_shape CHECK (
    (target_type = 'topic' AND target_id IS NULL)
    OR (target_type IN ('author', 'citation') AND target_id IS NOT NULL AND length(target_id) BETWEEN 1 AND 200)
  );
COMMIT;
