-- Rollback migration 0033. This permanently deletes all versioned project briefs.
BEGIN;
DROP TRIGGER IF EXISTS project_brief_head_after_version_delete ON public.project_brief_versions;
DROP FUNCTION IF EXISTS public.append_project_brief_version(UUID, UUID, INTEGER, TEXT, JSONB, TEXT);
DROP FUNCTION IF EXISTS public.create_project_brief(UUID, UUID, TEXT, TEXT, JSONB, TEXT);
DROP FUNCTION IF EXISTS public.validate_project_brief_sources(UUID, JSONB);
DROP FUNCTION IF EXISTS public.reconcile_project_brief_head_after_version_delete();
DROP TABLE IF EXISTS public.project_brief_versions;
DROP TABLE IF EXISTS public.project_briefs;
DROP INDEX IF EXISTS public.idx_project_brief_versions_created_by;
DROP INDEX IF EXISTS public.idx_project_brief_versions_brief_version;
DROP INDEX IF EXISTS public.idx_project_briefs_project_updated;
COMMIT;
