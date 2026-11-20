-- Durable, service-only account deletion intents.
-- The subject intentionally has no auth.users FK so the recovery record
-- survives successful Auth deletion. Completed records are retained 30 days.
-- Rollback only after pending jobs are drained:
--   DROP FUNCTION IF EXISTS public.prune_account_deletion_jobs();
--   DROP FUNCTION IF EXISTS public.finish_account_deletion_job(UUID, TEXT);
--   DROP FUNCTION IF EXISTS public.release_account_deletion_job(UUID, TEXT, TEXT, INTEGER);
--   DROP FUNCTION IF EXISTS public.complete_account_deletion_step(UUID, TEXT, TEXT);
--   DROP FUNCTION IF EXISTS public.claim_account_deletion_job(TEXT, INTEGER);
--   DROP FUNCTION IF EXISTS public.request_account_deletion(UUID);
--   remove the table only after all pending jobs are drained and backed up.
BEGIN;

CREATE TABLE IF NOT EXISTS public.account_deletion_jobs (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID NOT NULL,
  run_ids UUID[] NOT NULL DEFAULT '{}',
  completed_steps TEXT[] NOT NULL DEFAULT '{}',
  status TEXT NOT NULL DEFAULT 'pending'
    CHECK (status IN ('pending', 'processing', 'complete')),
  attempts INTEGER NOT NULL DEFAULT 0 CHECK (attempts >= 0),
  last_error_code TEXT,
  next_attempt_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  lease_owner TEXT,
  lease_expires_at TIMESTAMPTZ,
  requested_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  completed_at TIMESTAMPTZ
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_account_deletion_jobs_active_user
  ON public.account_deletion_jobs (user_id)
  WHERE status IN ('pending', 'processing');
CREATE INDEX IF NOT EXISTS idx_account_deletion_jobs_claim
  ON public.account_deletion_jobs (next_attempt_at, requested_at)
  WHERE status = 'pending';
CREATE INDEX IF NOT EXISTS idx_account_deletion_jobs_expired_lease
  ON public.account_deletion_jobs (lease_expires_at)
  WHERE status = 'processing';

ALTER TABLE public.account_deletion_jobs ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.account_deletion_jobs FROM PUBLIC, anon, authenticated;
GRANT ALL ON public.account_deletion_jobs TO service_role;

CREATE OR REPLACE FUNCTION public.request_account_deletion(p_user_id UUID)
RETURNS UUID
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $$
DECLARE
  v_job_id UUID;
BEGIN
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

CREATE OR REPLACE FUNCTION public.claim_account_deletion_job(
  p_lease_owner TEXT,
  p_lease_seconds INTEGER DEFAULT 600
)
RETURNS SETOF public.account_deletion_jobs
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $$
DECLARE
  v_job_id UUID;
BEGIN
  SELECT j.id INTO v_job_id
  FROM public.account_deletion_jobs j
  WHERE (j.status = 'pending' AND j.next_attempt_at <= now())
     OR (j.status = 'processing' AND j.lease_expires_at < now())
  ORDER BY j.requested_at
  LIMIT 1
  FOR UPDATE SKIP LOCKED;

  IF v_job_id IS NULL THEN
    RETURN;
  END IF;

  RETURN QUERY
  UPDATE public.account_deletion_jobs j
  SET status = 'processing',
      attempts = j.attempts + 1,
      lease_owner = p_lease_owner,
      lease_expires_at = now() + make_interval(secs => greatest(60, least(p_lease_seconds, 3600))),
      updated_at = now()
  WHERE j.id = v_job_id
  RETURNING j.*;
END;
$$;

CREATE OR REPLACE FUNCTION public.complete_account_deletion_step(
  p_job_id UUID,
  p_lease_owner TEXT,
  p_step TEXT
)
RETURNS BOOLEAN
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $$
DECLARE
  v_updated UUID;
BEGIN
  IF p_step NOT IN (
    'cancel_runs', 'memories', 'checkpoints', 'queue', 'run_store',
    'run_events', 'user_rows', 'auth_user'
  ) THEN
    RAISE EXCEPTION 'Invalid account deletion step';
  END IF;

  UPDATE public.account_deletion_jobs j
  SET completed_steps = CASE
        WHEN p_step = ANY(j.completed_steps) THEN j.completed_steps
        ELSE array_append(j.completed_steps, p_step)
      END,
      updated_at = now()
  WHERE j.id = p_job_id AND j.status = 'processing'
    AND j.lease_owner = p_lease_owner AND j.lease_expires_at > now()
  RETURNING j.id INTO v_updated;
  RETURN v_updated IS NOT NULL;
END;
$$;

CREATE OR REPLACE FUNCTION public.release_account_deletion_job(
  p_job_id UUID,
  p_lease_owner TEXT,
  p_error_code TEXT,
  p_delay_seconds INTEGER
)
RETURNS BOOLEAN
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $$
DECLARE
  v_updated UUID;
BEGIN
  UPDATE public.account_deletion_jobs j
  SET status = 'pending',
      last_error_code = left(p_error_code, 80),
      next_attempt_at = now() + make_interval(secs => greatest(5, least(p_delay_seconds, 86400))),
      lease_owner = NULL,
      lease_expires_at = NULL,
      updated_at = now()
  WHERE j.id = p_job_id AND j.status = 'processing' AND j.lease_owner = p_lease_owner
  RETURNING j.id INTO v_updated;
  RETURN v_updated IS NOT NULL;
END;
$$;

CREATE OR REPLACE FUNCTION public.finish_account_deletion_job(
  p_job_id UUID,
  p_lease_owner TEXT
)
RETURNS BOOLEAN
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $$
DECLARE
  v_updated UUID;
BEGIN
  UPDATE public.account_deletion_jobs j
  SET status = 'complete',
      last_error_code = NULL,
      lease_owner = NULL,
      lease_expires_at = NULL,
      completed_at = now(),
      updated_at = now()
  WHERE j.id = p_job_id AND j.status = 'processing' AND j.lease_owner = p_lease_owner
    AND cardinality(j.completed_steps) = 8
  RETURNING j.id INTO v_updated;
  RETURN v_updated IS NOT NULL;
END;
$$;

CREATE OR REPLACE FUNCTION public.prune_account_deletion_jobs()
RETURNS INTEGER
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $$
DECLARE
  v_deleted INTEGER;
BEGIN
  DELETE FROM public.account_deletion_jobs j
  WHERE j.status = 'complete' AND j.completed_at < now() - interval '30 days';
  GET DIAGNOSTICS v_deleted = ROW_COUNT;
  RETURN v_deleted;
END;
$$;

REVOKE ALL ON FUNCTION public.request_account_deletion(UUID) FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION public.claim_account_deletion_job(TEXT, INTEGER) FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION public.complete_account_deletion_step(UUID, TEXT, TEXT) FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION public.release_account_deletion_job(UUID, TEXT, TEXT, INTEGER) FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION public.finish_account_deletion_job(UUID, TEXT) FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION public.prune_account_deletion_jobs() FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.request_account_deletion(UUID) TO service_role;
GRANT EXECUTE ON FUNCTION public.claim_account_deletion_job(TEXT, INTEGER) TO service_role;
GRANT EXECUTE ON FUNCTION public.complete_account_deletion_step(UUID, TEXT, TEXT) TO service_role;
GRANT EXECUTE ON FUNCTION public.release_account_deletion_job(UUID, TEXT, TEXT, INTEGER) TO service_role;
GRANT EXECUTE ON FUNCTION public.finish_account_deletion_job(UUID, TEXT) TO service_role;
GRANT EXECUTE ON FUNCTION public.prune_account_deletion_jobs() TO service_role;

COMMIT;
