-- Roll back only after stopping the Crossref status poller and UI/API reads.
-- This removes stored provenance and user watch preferences introduced here.
BEGIN;

DROP INDEX IF EXISTS public.uq_notifications_user_key;
ALTER TABLE public.notifications
  DROP CONSTRAINT IF EXISTS notifications_reason_code_check;
-- Retain this allowed code so already-delivered status notifications remain valid.
ALTER TABLE public.notifications
  ADD CONSTRAINT notifications_reason_code_check
  CHECK (reason_code IS NULL OR reason_code IN (
    'topic_term_overlap', 'author_relation', 'citation_relation',
    'preprint_version_updated', 'publication_status_update'
  ));
ALTER TABLE public.notifications
  DROP CONSTRAINT IF EXISTS notifications_notification_key_length_check,
  DROP COLUMN IF EXISTS notification_key;

DROP TABLE IF EXISTS public.paper_status_watches;
DROP INDEX IF EXISTS public.idx_papers_crossref_status_due;
ALTER TABLE public.papers
  DROP CONSTRAINT IF EXISTS papers_publication_update_provenance_check,
  DROP CONSTRAINT IF EXISTS papers_publication_update_type_check,
  DROP CONSTRAINT IF EXISTS papers_doi_format_check,
  DROP COLUMN IF EXISTS publication_update_checked_at,
  DROP COLUMN IF EXISTS publication_update_source,
  DROP COLUMN IF EXISTS publication_update_date,
  DROP COLUMN IF EXISTS publication_update_label,
  DROP COLUMN IF EXISTS publication_update_doi,
  DROP COLUMN IF EXISTS publication_update_type,
  DROP COLUMN IF EXISTS doi;

COMMIT;
