-- Preserve arXiv's versioned records and provider update timestamp.
-- Each version remains a separate public metadata row; prior versions are not overwritten.
BEGIN;

ALTER TABLE public.papers
  ADD COLUMN IF NOT EXISTS preprint_id TEXT,
  ADD COLUMN IF NOT EXISTS source_version INTEGER,
  ADD COLUMN IF NOT EXISTS source_updated_at TIMESTAMPTZ;

UPDATE public.papers
SET preprint_id = regexp_replace(id, 'v[1-9][0-9]*$', ''),
    source_version = substring(id FROM 'v([1-9][0-9]*)$')::INTEGER
WHERE source_version IS NULL
  AND id ~ '^(?:[A-Za-z.-]+/)?[0-9]{4}\.[0-9]{4,5}v[1-9][0-9]*$|^[A-Za-z.-]+/[0-9]{7}v[1-9][0-9]*$|^[0-9]{7}v[1-9][0-9]*$';

ALTER TABLE public.papers
  DROP CONSTRAINT IF EXISTS papers_source_version_positive_check;
ALTER TABLE public.papers
  ADD CONSTRAINT papers_source_version_positive_check
  CHECK (source_version IS NULL OR source_version > 0);

CREATE INDEX IF NOT EXISTS idx_papers_preprint_id_version
  ON public.papers (preprint_id, source_version DESC)
  WHERE preprint_id IS NOT NULL;

ALTER TABLE public.notifications
  DROP CONSTRAINT IF EXISTS notifications_reason_code_check;
ALTER TABLE public.notifications
  ADD CONSTRAINT notifications_reason_code_check
  CHECK (reason_code IS NULL OR reason_code IN (
    'topic_term_overlap', 'author_relation', 'citation_relation', 'preprint_version_updated'
  ));

COMMIT;
