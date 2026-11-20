-- Disable RESEARCH_PLAN_EXECUTION_ENABLED and drain/cancel all plan-backed
-- pending or running runs before applying this rollback.
BEGIN;

DO $$
BEGIN
  IF EXISTS (
    SELECT 1
    FROM public.research_plan_executions p
    JOIN public.research_runs r ON r.id = p.run_id
    WHERE r.status IN ('pending', 'running')
  ) THEN
    RAISE EXCEPTION 'Cannot roll back while research plan runs are pending or running';
  END IF;
END;
$$;

DROP TABLE public.research_plan_executions;

COMMIT;
