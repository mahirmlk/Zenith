-- Track whether project PDF page text came from selectable text or local OCR.
-- Existing empty pages remain explicitly marked as having no extracted text.
-- RLS policies are unchanged and continue to inherit document/project scope.
BEGIN;

ALTER TABLE public.project_document_pages
  ADD COLUMN IF NOT EXISTS extraction_method TEXT NOT NULL DEFAULT 'native';

UPDATE public.project_document_pages
SET extraction_method = 'empty'
WHERE text = '' AND extraction_method = 'native';

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint
    WHERE conname = 'project_document_pages_extraction_method_check'
      AND conrelid = 'public.project_document_pages'::regclass
  ) THEN
    ALTER TABLE public.project_document_pages
      ADD CONSTRAINT project_document_pages_extraction_method_check
      CHECK (extraction_method IN ('native', 'ocr', 'empty', 'ocr_limit'));
  END IF;
END;
$$;

COMMENT ON COLUMN public.project_document_pages.extraction_method IS
  'native selectable text, local OCR text, no extracted text, or OCR skipped by a resource limit';

COMMIT;
