-- Rollback migration 0031. This permanently removes all project annotations.
BEGIN;
DROP TRIGGER IF EXISTS project_annotations_keep_anchor ON public.project_annotations;
DROP FUNCTION IF EXISTS public.keep_project_annotation_anchor_immutable();
DROP TABLE IF EXISTS public.project_annotations;
DROP INDEX IF EXISTS public.idx_project_sources_id_project;
DROP INDEX IF EXISTS public.idx_project_documents_id_project;
COMMIT;
