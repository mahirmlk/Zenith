-- Roll back summary provenance after stopping code that reads/writes these columns.
BEGIN;
ALTER TABLE public.papers
  DROP CONSTRAINT IF EXISTS papers_summary_provenance_pair_check,
  DROP CONSTRAINT IF EXISTS papers_summary_fallback_reason_check,
  DROP CONSTRAINT IF EXISTS papers_summary_status_check;
ALTER TABLE public.papers
  DROP COLUMN IF EXISTS summary_fallback_reason,
  DROP COLUMN IF EXISTS summary_status;
COMMIT;
