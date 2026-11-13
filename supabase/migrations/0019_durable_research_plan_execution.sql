-- Store immutable execution parameters beside the canonical research run.
-- The worker reads this service-only row and uses the existing queue, lease,
-- events, checkpoint, cancellation, and retention lifecycle.
BEGIN;

CREATE TABLE public.research_plan_executions (
  run_id UUID PRIMARY KEY REFERENCES public.research_runs(id) ON DELETE CASCADE,
  user_id UUID NOT NULL,
  query TEXT NOT NULL CHECK (char_length(query) BETWEEN 1 AND 500),
  project_id UUID,
  source_scope TEXT NOT NULL CHECK (source_scope IN ('public_corpus', 'project')),
  task_type TEXT NOT NULL CHECK (task_type IN ('feed', 'explain', 'compare', 'deep_research')),
  max_sources INTEGER NOT NULL CHECK (max_sources BETWEEN 1 AND 10),
  max_tool_calls INTEGER NOT NULL CHECK (max_tool_calls BETWEEN 1 AND 6),
  max_wall_clock_seconds INTEGER NOT NULL CHECK (max_wall_clock_seconds BETWEEN 1 AND 90),
  max_model_calls INTEGER NOT NULL CHECK (max_model_calls BETWEEN 0 AND 2),
  max_output_tokens INTEGER NOT NULL CHECK (max_output_tokens BETWEEN 0 AND 1800),
  synthesis_enabled BOOLEAN NOT NULL DEFAULT FALSE,
  deadline_at TIMESTAMPTZ NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT research_plan_scope_project_check
    CHECK ((source_scope = 'project') = (project_id IS NOT NULL))
);

CREATE INDEX research_plan_executions_user_created_idx
  ON public.research_plan_executions (user_id, created_at DESC);

ALTER TABLE public.research_plan_executions ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.research_plan_executions FROM PUBLIC, anon, authenticated;
GRANT ALL ON public.research_plan_executions TO service_role;

COMMENT ON TABLE public.research_plan_executions IS
  'Service-only immutable execution contract linked to the shared durable research run; run deletion cascades metadata cleanup.';

COMMIT;
