-- Migration 0008: make Postgres the canonical research run/event store.
-- Redis remains the recoverable work queue and short-lived worker lease store.
-- Apply to staging first and exercise run creation, replay, cancellation, and
-- event recovery before production. See docs/security/SECURITY_TEST_PLAN.md.
--
-- Rollback (only after stopping workers and exporting required run history):
-- DROP FUNCTION IF EXISTS public.append_run_event_atomic(UUID, TEXT, JSONB);
-- DROP FUNCTION IF EXISTS public.update_research_run_atomic(UUID, TEXT, JSONB, BOOLEAN);
-- DROP FUNCTION IF EXISTS public.create_research_run_atomic(UUID, UUID, TEXT, TEXT, TEXT);
-- ALTER TABLE public.research_runs DROP COLUMN IF EXISTS started;
-- ALTER TABLE public.research_runs DROP COLUMN IF EXISTS updated_at;
-- ALTER TABLE public.research_runs DROP COLUMN IF EXISTS results;
-- ALTER TABLE public.research_runs DROP COLUMN IF EXISTS model;
-- ALTER TABLE public.research_runs DROP COLUMN IF EXISTS query;

BEGIN;

ALTER TABLE public.research_runs
  ADD COLUMN IF NOT EXISTS query TEXT,
  ADD COLUMN IF NOT EXISTS model TEXT,
  ADD COLUMN IF NOT EXISTS results JSONB NOT NULL DEFAULT '[]'::JSONB,
  ADD COLUMN IF NOT EXISTS started BOOLEAN NOT NULL DEFAULT FALSE,
  ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ NOT NULL DEFAULT now();

UPDATE public.research_runs SET status = 'pending' WHERE status = 'queued';
UPDATE public.research_runs SET status = 'complete' WHERE status = 'completed';
UPDATE public.research_runs SET status = 'failed' WHERE status IN ('error', 'errored');
ALTER TABLE public.research_runs ALTER COLUMN status SET DEFAULT 'pending';

CREATE INDEX IF NOT EXISTS idx_research_runs_created_at
  ON public.research_runs (created_at);
CREATE OR REPLACE FUNCTION public.create_research_run_atomic(
  p_run_id UUID,
  p_user_id UUID,
  p_query TEXT,
  p_model TEXT,
  p_idempotency_key TEXT,
  p_ttl_seconds INTEGER DEFAULT 3600
)
RETURNS SETOF public.research_runs
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public, pg_temp
AS $$
DECLARE
  v_run public.research_runs%ROWTYPE;
BEGIN
  IF p_idempotency_key IS NULL THEN
    INSERT INTO public.research_runs
      (id, user_id, query, model, results, idempotency_key, status, started)
    VALUES
      (p_run_id, p_user_id, p_query, p_model, '[]'::JSONB, NULL, 'pending', FALSE)
    RETURNING * INTO v_run;
    RETURN NEXT v_run;
    RETURN;
  END IF;

  UPDATE public.research_runs SET idempotency_key = NULL
  WHERE user_id IS NOT DISTINCT FROM p_user_id
    AND idempotency_key = p_idempotency_key
    AND created_at < now() - make_interval(secs => GREATEST(p_ttl_seconds, 1));

  INSERT INTO public.research_runs
    (id, user_id, query, model, results, idempotency_key, status, started)
  VALUES
    (p_run_id, p_user_id, p_query, p_model, '[]'::JSONB, p_idempotency_key, 'pending', FALSE)
  ON CONFLICT (user_id, idempotency_key) WHERE idempotency_key IS NOT NULL
  DO NOTHING;

  IF FOUND THEN
    SELECT * INTO v_run FROM public.research_runs WHERE id = p_run_id;
  ELSE
    SELECT * INTO v_run
    FROM public.research_runs
    WHERE user_id IS NOT DISTINCT FROM p_user_id
      AND idempotency_key = p_idempotency_key;
  END IF;

  IF v_run.id IS NULL THEN
    RAISE EXCEPTION 'Could not resolve idempotent research run';
  END IF;

  RETURN NEXT v_run;
END;
$$;

CREATE OR REPLACE FUNCTION public.update_research_run_atomic(
  p_run_id UUID,
  p_status TEXT DEFAULT NULL,
  p_results JSONB DEFAULT NULL,
  p_started BOOLEAN DEFAULT FALSE
)
RETURNS BOOLEAN
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public, pg_temp
AS $$
DECLARE
  v_updated UUID;
BEGIN
  IF p_status IS NOT NULL AND p_status NOT IN ('pending', 'running', 'complete', 'failed', 'cancelled') THEN
    RAISE EXCEPTION 'Invalid research run status';
  END IF;

  UPDATE public.research_runs
  SET status = COALESCE(p_status, status),
      results = COALESCE(p_results, results),
      started = started OR p_started OR COALESCE(p_status = 'running', FALSE),
      updated_at = now()
  WHERE id = p_run_id
    AND (status NOT IN ('complete', 'failed', 'cancelled') OR p_status = status)
  RETURNING id INTO v_updated;

  RETURN v_updated IS NOT NULL;
END;
$$;

CREATE OR REPLACE FUNCTION public.append_run_event_atomic(
  p_run_id UUID,
  p_kind TEXT,
  p_payload JSONB DEFAULT '{}'::JSONB
)
RETURNS TABLE(sequence INTEGER, kind TEXT, safe_payload JSONB, created_at TIMESTAMPTZ)
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public, pg_temp
AS $$
DECLARE
  v_next INTEGER;
BEGIN
  PERFORM 1 FROM public.research_runs WHERE id = p_run_id FOR UPDATE;
  IF NOT FOUND THEN
    RETURN;
  END IF;

  SELECT COALESCE(MAX(e.sequence), 0) + 1 INTO v_next
  FROM public.run_events e WHERE e.run_id = p_run_id;

  RETURN QUERY
  INSERT INTO public.run_events (run_id, sequence, kind, safe_payload)
  VALUES (p_run_id, v_next, p_kind, COALESCE(p_payload, '{}'::JSONB))
  RETURNING run_events.sequence, run_events.kind, run_events.safe_payload, run_events.created_at;
END;
$$;

REVOKE ALL ON FUNCTION public.create_research_run_atomic(UUID, UUID, TEXT, TEXT, TEXT, INTEGER) FROM PUBLIC;
REVOKE ALL ON FUNCTION public.update_research_run_atomic(UUID, TEXT, JSONB, BOOLEAN) FROM PUBLIC;
REVOKE ALL ON FUNCTION public.append_run_event_atomic(UUID, TEXT, JSONB) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION public.create_research_run_atomic(UUID, UUID, TEXT, TEXT, TEXT, INTEGER) TO service_role;
GRANT EXECUTE ON FUNCTION public.update_research_run_atomic(UUID, TEXT, JSONB, BOOLEAN) TO service_role;
GRANT EXECUTE ON FUNCTION public.append_run_event_atomic(UUID, TEXT, JSONB) TO service_role;

COMMIT;
