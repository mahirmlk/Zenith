-- Migration 0012: prevent direct authenticated access to soft-deleted projects.
-- API routes already reject deleted projects; these helpers also back direct
-- PostgREST policies, which must enforce the same lifecycle boundary.
-- Rollback: restore the three helper definitions from 0009_project_role_rls.sql.
BEGIN;

CREATE OR REPLACE FUNCTION public.is_project_owner(target_project uuid)
RETURNS boolean
LANGUAGE sql STABLE SECURITY DEFINER
SET search_path = ''
AS $$
  SELECT EXISTS (
    SELECT 1 FROM public.projects p
    WHERE p.id = target_project
      AND p.deleted_at IS NULL
      AND p.owner_id = auth.uid()
  );
$$;

CREATE OR REPLACE FUNCTION public.can_access_project(target_project uuid)
RETURNS boolean
LANGUAGE sql STABLE SECURITY DEFINER
SET search_path = ''
AS $$
  SELECT EXISTS (
    SELECT 1 FROM public.projects p
    WHERE p.id = target_project
      AND p.deleted_at IS NULL
      AND (
        p.owner_id = auth.uid()
        OR EXISTS (
          SELECT 1 FROM public.project_members pm
          WHERE pm.project_id = p.id AND pm.user_id = auth.uid()
        )
      )
  );
$$;

CREATE OR REPLACE FUNCTION public.can_write_project(target_project uuid)
RETURNS boolean
LANGUAGE sql STABLE SECURITY DEFINER
SET search_path = ''
AS $$
  SELECT EXISTS (
    SELECT 1 FROM public.projects p
    WHERE p.id = target_project
      AND p.deleted_at IS NULL
      AND (
        p.owner_id = auth.uid()
        OR EXISTS (
          SELECT 1 FROM public.project_members pm
          WHERE pm.project_id = p.id
            AND pm.user_id = auth.uid()
            AND pm.role IN ('owner', 'editor')
        )
      )
  );
$$;

COMMIT;
