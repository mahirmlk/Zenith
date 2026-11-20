-- Run only after stopping API/workers that read or write notice deposit sources.
-- Previously collected relation-level source values are discarded by this rollback.
BEGIN;

ALTER TABLE public.papers
  DROP CONSTRAINT IF EXISTS papers_publication_update_provenance_check,
  DROP CONSTRAINT IF EXISTS papers_publication_update_deposit_source_check,
  DROP COLUMN IF EXISTS publication_update_deposit_source;

ALTER TABLE public.papers
  ADD CONSTRAINT papers_publication_update_provenance_check
    CHECK (
      (publication_update_type IS NULL AND publication_update_doi IS NULL
        AND publication_update_source IS NULL AND publication_update_label IS NULL
        AND publication_update_date IS NULL)
      OR (publication_update_type IS NOT NULL AND publication_update_doi IS NOT NULL
        AND publication_update_source = 'crossref')
    );

COMMIT;
