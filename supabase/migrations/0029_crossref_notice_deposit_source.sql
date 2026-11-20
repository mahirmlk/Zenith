-- Preserve the depositor/source attached to each Crossref update relation.
-- Existing rows remain NULL because their relation-level source was not stored.
BEGIN;

ALTER TABLE public.papers
  ADD COLUMN IF NOT EXISTS publication_update_deposit_source TEXT;

ALTER TABLE public.papers
  DROP CONSTRAINT IF EXISTS papers_publication_update_deposit_source_check,
  DROP CONSTRAINT IF EXISTS papers_publication_update_provenance_check;
ALTER TABLE public.papers
  ADD CONSTRAINT papers_publication_update_deposit_source_check
    CHECK (publication_update_deposit_source IS NULL OR publication_update_deposit_source IN (
      'publisher', 'retraction-watch'
    )),
  ADD CONSTRAINT papers_publication_update_provenance_check
    CHECK (
      (publication_update_type IS NULL AND publication_update_doi IS NULL
        AND publication_update_source IS NULL AND publication_update_label IS NULL
        AND publication_update_date IS NULL AND publication_update_deposit_source IS NULL)
      OR (publication_update_type IS NOT NULL AND publication_update_doi IS NOT NULL
        AND publication_update_source = 'crossref')
    );

COMMIT;
