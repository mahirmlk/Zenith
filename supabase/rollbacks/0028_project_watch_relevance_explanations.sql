-- Roll back only after the API/worker no longer reads or writes these fields.
BEGIN;
ALTER TABLE public.notifications
  DROP CONSTRAINT IF EXISTS notifications_project_relevance_code_check,
  DROP CONSTRAINT IF EXISTS notifications_project_relevance_text_length_check,
  DROP COLUMN IF EXISTS project_relevance_code,
  DROP COLUMN IF EXISTS project_relevance_text;
COMMIT;
