-- Persist optional, bounded lexical context for project-linked watch alerts.
-- This is explanatory metadata only; it does not assert scientific importance.
BEGIN;
ALTER TABLE public.notifications
  ADD COLUMN IF NOT EXISTS project_relevance_code TEXT,
  ADD COLUMN IF NOT EXISTS project_relevance_text TEXT;

ALTER TABLE public.notifications
  DROP CONSTRAINT IF EXISTS notifications_project_relevance_code_check;
ALTER TABLE public.notifications
  ADD CONSTRAINT notifications_project_relevance_code_check
  CHECK (project_relevance_code IS NULL OR project_relevance_code = 'project_term_overlap');

ALTER TABLE public.notifications
  DROP CONSTRAINT IF EXISTS notifications_project_relevance_text_length_check;
ALTER TABLE public.notifications
  ADD CONSTRAINT notifications_project_relevance_text_length_check
  CHECK (project_relevance_text IS NULL OR char_length(project_relevance_text) <= 500);
COMMIT;
