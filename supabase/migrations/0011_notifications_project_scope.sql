-- Migration 0011: retain project context for project-linked watchlist alerts.
-- Rollback: DROP INDEX IF EXISTS public.idx_notifications_project;
--           ALTER TABLE public.notifications DROP COLUMN IF EXISTS project_id;
BEGIN;

ALTER TABLE public.notifications
  ADD COLUMN IF NOT EXISTS project_id UUID
  REFERENCES public.projects(id) ON DELETE SET NULL;

CREATE INDEX IF NOT EXISTS idx_notifications_project
  ON public.notifications (user_id, project_id, created_at DESC)
  WHERE project_id IS NOT NULL;

COMMIT;
