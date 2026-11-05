-- Migration 0002: notes + project_sources (update.md §8.2, additive).
BEGIN;
CREATE TABLE IF NOT EXISTS public.notes (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  project_id UUID NOT NULL REFERENCES public.projects(id) ON DELETE CASCADE,
  created_by UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  source_id TEXT,
  content TEXT NOT NULL,
  created_at TIMESTAMPTZ DEFAULT now(),
  updated_at TIMESTAMPTZ DEFAULT now()
);
CREATE TABLE IF NOT EXISTS public.project_sources (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  project_id UUID NOT NULL REFERENCES public.projects(id) ON DELETE CASCADE,
  paper_id TEXT REFERENCES public.papers(id) ON DELETE SET NULL,
  source_type TEXT NOT NULL DEFAULT 'paper',
  created_by UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  created_at TIMESTAMPTZ DEFAULT now()
);
ALTER TABLE public.notes ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.project_sources ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS notes_owner ON public.notes;
CREATE POLICY notes_owner ON public.notes FOR ALL TO authenticated
  USING (EXISTS (SELECT 1 FROM public.projects p WHERE p.id = project_id AND p.owner_id = auth.uid()))
  WITH CHECK (EXISTS (SELECT 1 FROM public.projects p WHERE p.id = project_id AND p.owner_id = auth.uid()));
DROP POLICY IF EXISTS sources_owner ON public.project_sources;
CREATE POLICY sources_owner ON public.project_sources FOR ALL TO authenticated
  USING (EXISTS (SELECT 1 FROM public.projects p WHERE p.id = project_id AND p.owner_id = auth.uid()))
  WITH CHECK (EXISTS (SELECT 1 FROM public.projects p WHERE p.id = project_id AND p.owner_id = auth.uid()));
COMMIT;
