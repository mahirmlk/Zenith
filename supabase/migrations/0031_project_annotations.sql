-- Migration 0031: source-anchored project annotations with role-scoped RLS.
-- Rollback: see supabase/rollbacks/0031_project_annotations.sql.
BEGIN;

-- Composite uniqueness lets annotation foreign keys prove the source belongs
-- to the same project without trusting only the API's service-role checks.
CREATE UNIQUE INDEX IF NOT EXISTS idx_project_sources_id_project
  ON public.project_sources (id, project_id);
CREATE UNIQUE INDEX IF NOT EXISTS idx_project_documents_id_project
  ON public.project_documents (id, project_id);

CREATE TABLE IF NOT EXISTS public.project_annotations (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  project_id UUID NOT NULL REFERENCES public.projects(id) ON DELETE CASCADE,
  source_type TEXT NOT NULL CHECK (source_type IN ('paper_abstract', 'pdf_page')),
  paper_source_id UUID,
  document_id UUID,
  page_number INTEGER,
  start_offset INTEGER NOT NULL CHECK (start_offset >= 0),
  end_offset INTEGER NOT NULL CHECK (end_offset > start_offset),
  quote TEXT NOT NULL CHECK (
    char_length(quote) BETWEEN 1 AND 4000
    AND char_length(quote) = end_offset - start_offset
  ),
  quote_sha256 TEXT NOT NULL CHECK (quote_sha256 ~ '^[0-9a-f]{64}$'),
  content TEXT NOT NULL CHECK (
    char_length(content) BETWEEN 1 AND 5000
    AND btrim(content) = content
    AND btrim(content) <> ''
  ),
  created_by UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  CONSTRAINT project_annotations_anchor_shape CHECK (
    (source_type = 'paper_abstract'
      AND paper_source_id IS NOT NULL
      AND document_id IS NULL
      AND page_number IS NULL)
    OR
    (source_type = 'pdf_page'
      AND paper_source_id IS NULL
      AND document_id IS NOT NULL
      AND page_number BETWEEN 1 AND 500)
  ),
  CONSTRAINT project_annotations_paper_source_project_fk
    FOREIGN KEY (paper_source_id, project_id)
    REFERENCES public.project_sources (id, project_id) ON DELETE CASCADE,
  CONSTRAINT project_annotations_document_project_fk
    FOREIGN KEY (document_id, project_id)
    REFERENCES public.project_documents (id, project_id) ON DELETE CASCADE,
  CONSTRAINT project_annotations_document_page_fk
    FOREIGN KEY (document_id, page_number)
    REFERENCES public.project_document_pages (document_id, page_number) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_project_annotations_project_created
  ON public.project_annotations (project_id, created_at DESC, id);
CREATE INDEX IF NOT EXISTS idx_project_annotations_created_by
  ON public.project_annotations (created_by);

ALTER TABLE public.project_annotations ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS project_annotations_select_access ON public.project_annotations;
CREATE POLICY project_annotations_select_access ON public.project_annotations
  FOR SELECT TO authenticated
  USING (public.can_access_project(project_id));
DROP POLICY IF EXISTS project_annotations_insert_writer ON public.project_annotations;
CREATE POLICY project_annotations_insert_writer ON public.project_annotations
  FOR INSERT TO authenticated
  WITH CHECK (
    created_by = auth.uid()
    AND public.can_write_project(project_id)
  );
DROP POLICY IF EXISTS project_annotations_update_writer ON public.project_annotations;
CREATE POLICY project_annotations_update_writer ON public.project_annotations
  FOR UPDATE TO authenticated
  USING (public.can_write_project(project_id))
  WITH CHECK (public.can_write_project(project_id));
DROP POLICY IF EXISTS project_annotations_delete_writer ON public.project_annotations;
CREATE POLICY project_annotations_delete_writer ON public.project_annotations
  FOR DELETE TO authenticated
  USING (public.can_write_project(project_id));

-- Writes go through the API so exact quote/source validation cannot be bypassed
-- with a direct authenticated PostgREST insert or update.
REVOKE INSERT, UPDATE, DELETE ON public.project_annotations FROM PUBLIC, anon, authenticated;
GRANT SELECT ON public.project_annotations TO authenticated;

CREATE OR REPLACE FUNCTION public.keep_project_annotation_anchor_immutable()
RETURNS trigger
LANGUAGE plpgsql
SET search_path = ''
AS $$
BEGIN
  NEW.project_id := OLD.project_id;
  NEW.source_type := OLD.source_type;
  NEW.paper_source_id := OLD.paper_source_id;
  NEW.document_id := OLD.document_id;
  NEW.page_number := OLD.page_number;
  NEW.start_offset := OLD.start_offset;
  NEW.end_offset := OLD.end_offset;
  NEW.quote := OLD.quote;
  NEW.quote_sha256 := OLD.quote_sha256;
  NEW.created_by := OLD.created_by;
  NEW.created_at := OLD.created_at;
  NEW.updated_at := NOW();
  RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS project_annotations_keep_anchor ON public.project_annotations;
CREATE TRIGGER project_annotations_keep_anchor
  BEFORE UPDATE ON public.project_annotations
  FOR EACH ROW EXECUTE FUNCTION public.keep_project_annotation_anchor_immutable();

COMMIT;
