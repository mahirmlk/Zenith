-- Explicitly distinguish provider-generated summaries from previews and unknown legacy rows.
BEGIN;

ALTER TABLE public.papers
  ADD COLUMN IF NOT EXISTS summary_status TEXT NOT NULL DEFAULT 'unknown',
  ADD COLUMN IF NOT EXISTS summary_fallback_reason TEXT;

ALTER TABLE public.papers
  DROP CONSTRAINT IF EXISTS papers_summary_status_check;
ALTER TABLE public.papers
  ADD CONSTRAINT papers_summary_status_check
  CHECK (summary_status IN ('generated', 'abstract_preview', 'unknown'));

ALTER TABLE public.papers
  DROP CONSTRAINT IF EXISTS papers_summary_fallback_reason_check;
ALTER TABLE public.papers
  ADD CONSTRAINT papers_summary_fallback_reason_check
  CHECK (
    summary_fallback_reason IS NULL OR summary_fallback_reason IN (
      'per_run_cap', 'spend_limit', 'billing_unavailable',
      'provider_unavailable', 'invalid_output'
    )
  );

ALTER TABLE public.papers
  DROP CONSTRAINT IF EXISTS papers_summary_provenance_pair_check;
ALTER TABLE public.papers
  ADD CONSTRAINT papers_summary_provenance_pair_check
  CHECK (
    (summary_status = 'abstract_preview' AND summary_fallback_reason IS NOT NULL)
    OR (summary_status IN ('generated', 'unknown') AND summary_fallback_reason IS NULL)
  );

COMMIT;
