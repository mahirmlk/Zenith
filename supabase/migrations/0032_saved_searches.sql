-- Migration 0032: personal and project-scoped saved query configurations.
-- Rollback: see supabase/rollbacks/0032_saved_searches.sql.
BEGIN;

CREATE TABLE IF NOT EXISTS public.saved_searches (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  created_by UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  project_id UUID REFERENCES public.projects(id) ON DELETE CASCADE,
  name TEXT NOT NULL CHECK (char_length(name) BETWEEN 1 AND 120 AND btrim(name) = name),
  query TEXT NOT NULL CHECK (char_length(query) BETWEEN 1 AND 500 AND btrim(query) = query),
  model TEXT CHECK (model IS NULL OR char_length(model) <= 100),
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_saved_searches_creator_updated
  ON public.saved_searches (created_by, updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_saved_searches_project_updated
  ON public.saved_searches (project_id, updated_at DESC)
  WHERE project_id IS NOT NULL;

ALTER TABLE public.saved_searches ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS saved_searches_select_scope ON public.saved_searches;
CREATE POLICY saved_searches_select_scope ON public.saved_searches
  FOR SELECT TO authenticated
  USING (
    (project_id IS NULL AND created_by = auth.uid())
    OR (project_id IS NOT NULL AND public.can_access_project(project_id))
  );
DROP POLICY IF EXISTS saved_searches_insert_scope ON public.saved_searches;
CREATE POLICY saved_searches_insert_scope ON public.saved_searches
  FOR INSERT TO authenticated
  WITH CHECK (
    created_by = auth.uid()
    AND (project_id IS NULL OR public.can_write_project(project_id))
  );
DROP POLICY IF EXISTS saved_searches_update_scope ON public.saved_searches;
CREATE POLICY saved_searches_update_scope ON public.saved_searches
  FOR UPDATE TO authenticated
  USING (
    (project_id IS NULL AND created_by = auth.uid())
    OR (project_id IS NOT NULL AND public.can_access_project(project_id)
      AND (created_by = auth.uid() OR public.can_write_project(project_id)))
  )
  WITH CHECK (
    (project_id IS NULL AND created_by = auth.uid())
    OR (project_id IS NOT NULL AND public.can_access_project(project_id)
      AND (created_by = auth.uid() OR public.can_write_project(project_id)))
  );
DROP POLICY IF EXISTS saved_searches_delete_scope ON public.saved_searches;
CREATE POLICY saved_searches_delete_scope ON public.saved_searches
  FOR DELETE TO authenticated
  USING (
    (project_id IS NULL AND created_by = auth.uid())
    OR (project_id IS NOT NULL AND public.can_access_project(project_id)
      AND (created_by = auth.uid() OR public.can_write_project(project_id)))
  );

CREATE OR REPLACE FUNCTION public.touch_saved_search_updated_at()
RETURNS trigger
LANGUAGE plpgsql
SET search_path = ''
AS $$
BEGIN
  NEW.created_by := OLD.created_by;
  NEW.project_id := OLD.project_id;
  NEW.created_at := OLD.created_at;
  NEW.updated_at := NOW();
  RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS saved_searches_touch_updated_at ON public.saved_searches;
CREATE TRIGGER saved_searches_touch_updated_at
  BEFORE UPDATE ON public.saved_searches
  FOR EACH ROW EXECUTE FUNCTION public.touch_saved_search_updated_at();

COMMIT;
