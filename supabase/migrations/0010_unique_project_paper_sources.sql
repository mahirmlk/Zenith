-- Migration 0010: prevent duplicate paper attachments per project.
-- Additive and reversible. If earlier manual writes created duplicates, this
-- fails without deleting data; reconcile those rows before retrying.
-- Rollback: DROP INDEX IF EXISTS public.idx_project_sources_project_paper;
BEGIN;

CREATE UNIQUE INDEX IF NOT EXISTS idx_project_sources_project_paper
  ON public.project_sources (project_id, paper_id)
  WHERE paper_id IS NOT NULL;

COMMIT;
