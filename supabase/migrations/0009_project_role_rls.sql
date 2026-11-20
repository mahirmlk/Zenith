-- Migration 0009: align direct authenticated access with project roles.
-- The API still uses the service role and enforces the same policy in code;
-- these policies protect direct PostgREST access and future client paths.
BEGIN;

CREATE OR REPLACE FUNCTION public.is_project_owner(target_project uuid)
RETURNS boolean
LANGUAGE sql STABLE SECURITY DEFINER
SET search_path = ''
AS $$
  SELECT EXISTS (
    SELECT 1 FROM public.projects p
    WHERE p.id = target_project AND p.owner_id = auth.uid()
  );
$$;

CREATE OR REPLACE FUNCTION public.can_access_project(target_project uuid)
RETURNS boolean
LANGUAGE sql STABLE SECURITY DEFINER
SET search_path = ''
AS $$
  SELECT public.is_project_owner(target_project)
      OR EXISTS (
        SELECT 1 FROM public.project_members pm
        WHERE pm.project_id = target_project AND pm.user_id = auth.uid()
      );
$$;

CREATE OR REPLACE FUNCTION public.can_write_project(target_project uuid)
RETURNS boolean
LANGUAGE sql STABLE SECURITY DEFINER
SET search_path = ''
AS $$
  SELECT public.is_project_owner(target_project)
      OR EXISTS (
        SELECT 1 FROM public.project_members pm
        WHERE pm.project_id = target_project
          AND pm.user_id = auth.uid()
          AND pm.role IN ('owner', 'editor')
      );
$$;

REVOKE ALL ON FUNCTION public.is_project_owner(uuid) FROM PUBLIC;
REVOKE ALL ON FUNCTION public.can_access_project(uuid) FROM PUBLIC;
REVOKE ALL ON FUNCTION public.can_write_project(uuid) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION public.is_project_owner(uuid) TO authenticated;
GRANT EXECUTE ON FUNCTION public.can_access_project(uuid) TO authenticated;
GRANT EXECUTE ON FUNCTION public.can_write_project(uuid) TO authenticated;

-- Replace the owner-only all-actions policy with narrow policies. Owners
-- manage project metadata; members can read, while editors write via notes.
DROP POLICY IF EXISTS projects_owner ON public.projects;
DROP POLICY IF EXISTS projects_select_member ON public.projects;
DROP POLICY IF EXISTS projects_insert_owner ON public.projects;
DROP POLICY IF EXISTS projects_update_owner ON public.projects;
DROP POLICY IF EXISTS projects_delete_owner ON public.projects;
CREATE POLICY projects_select_member ON public.projects
  FOR SELECT TO authenticated
  USING (public.can_access_project(id));
CREATE POLICY projects_insert_owner ON public.projects
  FOR INSERT TO authenticated
  WITH CHECK (owner_id = auth.uid());
CREATE POLICY projects_update_owner ON public.projects
  FOR UPDATE TO authenticated
  USING (public.is_project_owner(id))
  WITH CHECK (public.is_project_owner(id));
CREATE POLICY projects_delete_owner ON public.projects
  FOR DELETE TO authenticated
  USING (public.is_project_owner(id));

-- Members may see the shared roster; only the owner can add, change, or
-- remove membership rows.
DROP POLICY IF EXISTS project_members_member ON public.project_members;
DROP POLICY IF EXISTS project_members_select_access ON public.project_members;
DROP POLICY IF EXISTS project_members_insert_owner ON public.project_members;
DROP POLICY IF EXISTS project_members_update_owner ON public.project_members;
DROP POLICY IF EXISTS project_members_delete_owner ON public.project_members;
CREATE POLICY project_members_select_access ON public.project_members
  FOR SELECT TO authenticated
  USING (public.can_access_project(project_id));
CREATE POLICY project_members_insert_owner ON public.project_members
  FOR INSERT TO authenticated
  WITH CHECK (public.is_project_owner(project_id));
CREATE POLICY project_members_update_owner ON public.project_members
  FOR UPDATE TO authenticated
  USING (public.is_project_owner(project_id))
  WITH CHECK (public.is_project_owner(project_id));
CREATE POLICY project_members_delete_owner ON public.project_members
  FOR DELETE TO authenticated
  USING (public.is_project_owner(project_id));

-- Notes and attached-source metadata are readable by every project member;
-- owners and editors may add rows as themselves. Direct update/delete is not
-- granted because the API currently exposes neither operation.
DROP POLICY IF EXISTS notes_owner ON public.notes;
DROP POLICY IF EXISTS notes_select_access ON public.notes;
DROP POLICY IF EXISTS notes_insert_writer ON public.notes;
CREATE POLICY notes_select_access ON public.notes
  FOR SELECT TO authenticated
  USING (public.can_access_project(project_id));
CREATE POLICY notes_insert_writer ON public.notes
  FOR INSERT TO authenticated
  WITH CHECK (
    created_by = auth.uid()
    AND public.can_write_project(project_id)
  );

DROP POLICY IF EXISTS sources_owner ON public.project_sources;
DROP POLICY IF EXISTS sources_select_access ON public.project_sources;
DROP POLICY IF EXISTS sources_insert_writer ON public.project_sources;
CREATE POLICY sources_select_access ON public.project_sources
  FOR SELECT TO authenticated
  USING (public.can_access_project(project_id));
CREATE POLICY sources_insert_writer ON public.project_sources
  FOR INSERT TO authenticated
  WITH CHECK (
    created_by = auth.uid()
    AND public.can_write_project(project_id)
  );

COMMIT;
