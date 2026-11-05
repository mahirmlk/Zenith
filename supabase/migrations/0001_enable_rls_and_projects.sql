-- Migration 0001: RLS + projects/runs foundation (update.md §5.3, §8.2)
-- Additive & reversible. Apply to staging first; verify with the
-- owner/member/outsider/anon test matrix in docs/security/SECURITY_TEST_PLAN.md
-- before production. Rollback: drop the policies/objects added below.
BEGIN;

-- 1) Row Level Security on user-scoped tables -------------------------------
ALTER TABLE public.user_papers ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.user_prefs  ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS user_papers_owner ON public.user_papers;
CREATE POLICY user_papers_owner ON public.user_papers
  FOR ALL TO authenticated
  USING (user_id = auth.uid())
  WITH CHECK (user_id = auth.uid());

DROP POLICY IF EXISTS user_prefs_owner ON public.user_prefs;
CREATE POLICY user_prefs_owner ON public.user_prefs
  FOR ALL TO authenticated
  USING (user_id = auth.uid())
  WITH CHECK (user_id = auth.uid());

-- Public corpus: read-only for everyone, no writes via PostgREST.
ALTER TABLE public.papers ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS papers_public_read ON public.papers;
CREATE POLICY papers_public_read ON public.papers
  FOR SELECT TO anon, authenticated USING (true);

ALTER TABLE public.citations ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS citations_public_read ON public.citations;
CREATE POLICY citations_public_read ON public.citations
  FOR SELECT TO anon, authenticated USING (true);

ALTER TABLE public.crawled_content ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS crawled_public_read ON public.crawled_content;
CREATE POLICY crawled_public_read ON public.crawled_content
  FOR SELECT TO anon, authenticated USING (true);

REVOKE ALL ON public.user_papers, public.user_prefs FROM anon;
REVOKE INSERT, UPDATE, DELETE ON public.papers, public.citations, public.crawled_content FROM anon, authenticated;

-- 2) match_papers: no SECURITY DEFINER, pin search_path, keep global scope
--    (papers is a public corpus; per-user data is never in this function).
CREATE OR REPLACE FUNCTION public.match_papers(
  query_embedding VECTOR(1536), match_threshold FLOAT, match_count INT
)
RETURNS TABLE(id TEXT, title TEXT, abstract TEXT, authors JSONB, url TEXT,
              published_at TIMESTAMPTZ, summary_tldr TEXT, similarity FLOAT)
LANGUAGE SQL STABLE SECURITY INVOKER
SET search_path = public
AS $$
  SELECT p.id, p.title, p.abstract, p.authors, p.url, p.published_at,
         p.summary_tldr, 1 - (p.embedding <=> query_embedding) AS similarity
  FROM public.papers p
  WHERE p.embedding IS NOT NULL
    AND 1 - (p.embedding <=> query_embedding) > match_threshold
  ORDER BY similarity DESC LIMIT match_count;
$$;

-- 3) Embedding provenance (backfill: existing rows get 'unknown' then re-embed)
ALTER TABLE public.papers ADD COLUMN IF NOT EXISTS embedding_model TEXT;
ALTER TABLE public.papers ADD COLUMN IF NOT EXISTS embedding_version TEXT;

-- 4) Projects / runs foundation (Phase P1/P2, additive) --------------------
CREATE TABLE IF NOT EXISTS public.projects (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  owner_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  title TEXT NOT NULL,
  deleted_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ DEFAULT now(),
  updated_at TIMESTAMPTZ DEFAULT now()
);
CREATE TABLE IF NOT EXISTS public.project_members (
  project_id UUID NOT NULL REFERENCES public.projects(id) ON DELETE CASCADE,
  user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  role TEXT NOT NULL CHECK (role IN ('owner','editor','viewer')),
  PRIMARY KEY (project_id, user_id)
);
CREATE TABLE IF NOT EXISTS public.research_runs (
  id UUID PRIMARY KEY,
  user_id UUID REFERENCES auth.users(id) ON DELETE SET NULL,
  project_id UUID REFERENCES public.projects(id) ON DELETE SET NULL,
  idempotency_key TEXT,
  status TEXT NOT NULL DEFAULT 'queued',
  created_at TIMESTAMPTZ DEFAULT now()
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_runs_idempotency
  ON public.research_runs (user_id, idempotency_key) WHERE idempotency_key IS NOT NULL;
CREATE TABLE IF NOT EXISTS public.run_events (
  id BIGSERIAL PRIMARY KEY,
  run_id UUID NOT NULL REFERENCES public.research_runs(id) ON DELETE CASCADE,
  sequence INT NOT NULL,
  kind TEXT NOT NULL,
  safe_payload JSONB NOT NULL DEFAULT '{}',
  created_at TIMESTAMPTZ DEFAULT now(),
  UNIQUE (run_id, sequence)
);
ALTER TABLE public.projects ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.project_members ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.research_runs ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.run_events ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS projects_owner ON public.projects;
CREATE POLICY projects_owner ON public.projects FOR ALL TO authenticated
  USING (owner_id = auth.uid()) WITH CHECK (owner_id = auth.uid());

COMMIT;
