-- Roll back only after disabling arXiv version-change ingestion and notifications.
BEGIN;

DROP INDEX IF EXISTS public.idx_papers_preprint_id_version;
ALTER TABLE public.papers
  DROP CONSTRAINT IF EXISTS papers_source_version_positive_check,
  DROP COLUMN IF EXISTS preprint_id,
  DROP COLUMN IF EXISTS source_version,
  DROP COLUMN IF EXISTS source_updated_at;

ALTER TABLE public.notifications
  DROP CONSTRAINT IF EXISTS notifications_reason_code_check;
ALTER TABLE public.notifications
  ADD CONSTRAINT notifications_reason_code_check
  CHECK (reason_code IS NULL OR reason_code IN (
    'topic_term_overlap', 'author_relation', 'citation_relation'
  ));

COMMIT;
