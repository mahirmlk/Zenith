-- Serialize account deletion intent with research-run admission per user.
-- A run is either committed before deletion snapshots it or is rejected after
-- the deletion job becomes visible. Both transactions take the same advisory
-- lock, closing the in-flight-auth race between the API dependency and RPC.
-- Rollback only after all deletion jobs are drained and workers are stopped:
-- restore the function bodies from migrations 0008 and 0016.
BEGIN;

CREATE OR REPLACE FUNCTION public.request_account_deletion(p_user_id UUID)
RETURNS UUID
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $$
DECLARE
  v_job_id UUID;
BEGIN
  PERFORM pg_catalog.pg_advisory_xact_lock(
    pg_catalog.hashtextextended(p_user_id::TEXT, 0)
  );

  INSERT INTO public.account_deletion_jobs (user_id, run_ids)
    SELECT p_user_id, COALESCE(array_agg(r.id), '{}')
    FROM public.research_runs r
    WHERE r.user_id = p_user_id
  ON CONFLICT (user_id) WHERE status IN ('pending', 'processing')
    DO NOTHING
  RETURNING id INTO v_job_id;

  IF v_job_id IS NULL THEN
    SELECT j.id INTO v_job_id
    FROM public.account_deletion_jobs j
    WHERE j.user_id = p_user_id AND j.status IN ('pending', 'processing')
    ORDER BY j.requested_at DESC
    LIMIT 1;
  END IF;
  RETURN v_job_id;
END;
$$;

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
  IF p_user_id IS NOT NULL THEN
    PERFORM pg_catalog.pg_advisory_xact_lock(
      pg_catalog.hashtextextended(p_user_id::TEXT, 0)
    );
    IF EXISTS (
      SELECT 1
      FROM public.account_deletion_jobs j
      WHERE j.user_id = p_user_id
        AND j.status IN ('pending', 'processing', 'complete')
    ) THEN
      RAISE EXCEPTION USING
        ERRCODE = 'P0001',
        MESSAGE = 'account_deletion_in_progress';
    END IF;
  END IF;

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

REVOKE ALL ON FUNCTION public.request_account_deletion(UUID) FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION public.create_research_run_atomic(UUID, UUID, TEXT, TEXT, TEXT, INTEGER) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.request_account_deletion(UUID) TO service_role;
GRANT EXECUTE ON FUNCTION public.create_research_run_atomic(UUID, UUID, TEXT, TEXT, TEXT, INTEGER) TO service_role;

COMMIT;
