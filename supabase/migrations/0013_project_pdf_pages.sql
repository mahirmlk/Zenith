-- Migration 0013: store extracted page text for user-provided project PDFs.
-- Raw PDF bytes are never retained by the API; each extracted page remains
-- addressable by document UUID and 1-based page number for future citations.
-- Rollback: remove the page table first, then the document table.
BEGIN;

CREATE TABLE IF NOT EXISTS public.project_documents (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  project_id UUID NOT NULL REFERENCES public.projects(id) ON DELETE CASCADE,
  created_by UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  filename TEXT NOT NULL,
  page_count INTEGER NOT NULL CHECK (page_count BETWEEN 1 AND 500),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS public.project_document_pages (
  document_id UUID NOT NULL REFERENCES public.project_documents(id) ON DELETE CASCADE,
  page_number INTEGER NOT NULL CHECK (page_number BETWEEN 1 AND 500),
  text TEXT NOT NULL CHECK (char_length(text) <= 100000),
  PRIMARY KEY (document_id, page_number)
);

ALTER TABLE public.project_documents ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.project_document_pages ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS project_documents_select_access ON public.project_documents;
CREATE POLICY project_documents_select_access ON public.project_documents
  FOR SELECT TO authenticated USING (public.can_access_project(project_id));
DROP POLICY IF EXISTS project_documents_insert_writer ON public.project_documents;
CREATE POLICY project_documents_insert_writer ON public.project_documents
  FOR INSERT TO authenticated WITH CHECK (
    created_by = auth.uid() AND public.can_write_project(project_id)
  );
DROP POLICY IF EXISTS project_documents_delete_writer ON public.project_documents;
CREATE POLICY project_documents_delete_writer ON public.project_documents
  FOR DELETE TO authenticated USING (public.can_write_project(project_id));

DROP POLICY IF EXISTS project_document_pages_select_access ON public.project_document_pages;
CREATE POLICY project_document_pages_select_access ON public.project_document_pages
  FOR SELECT TO authenticated USING (
    EXISTS (
      SELECT 1 FROM public.project_documents d
      WHERE d.id = document_id AND public.can_access_project(d.project_id)
    )
  );
DROP POLICY IF EXISTS project_document_pages_insert_writer ON public.project_document_pages;
CREATE POLICY project_document_pages_insert_writer ON public.project_document_pages
  FOR INSERT TO authenticated WITH CHECK (
    EXISTS (
      SELECT 1 FROM public.project_documents d
      WHERE d.id = document_id
        AND d.created_by = auth.uid()
        AND public.can_write_project(d.project_id)
    )
  );

COMMIT;
