-- Service-only idempotent provider spend ledger and atomic UTC budget admission.
BEGIN;

CREATE TABLE IF NOT EXISTS public.model_spend_ledger (
  attempt_id UUID PRIMARY KEY,
  subject_id TEXT NOT NULL CHECK (char_length(subject_id) BETWEEN 1 AND 200),
  run_id UUID,
  operation_id UUID,
  operation TEXT NOT NULL CHECK (char_length(operation) BETWEEN 1 AND 120),
  requested_model TEXT NOT NULL CHECK (char_length(requested_model) BETWEEN 1 AND 200),
  catalog_version TEXT NOT NULL CHECK (char_length(catalog_version) BETWEEN 1 AND 100),
  status TEXT NOT NULL DEFAULT 'reserved' CHECK (status IN ('reserved', 'unknown', 'settled', 'over_budget')),
  reserved_cost_micros BIGINT NOT NULL CHECK (reserved_cost_micros >= 0),
  actual_cost_micros BIGINT CHECK (actual_cost_micros IS NULL OR actual_cost_micros >= 0),
  actual_model TEXT CHECK (actual_model IS NULL OR char_length(actual_model) <= 200),
  actual_provider TEXT CHECK (actual_provider IS NULL OR char_length(actual_provider) <= 120),
  openrouter_generation_id TEXT CHECK (openrouter_generation_id IS NULL OR char_length(openrouter_generation_id) <= 200),
  openrouter_request_id TEXT CHECK (openrouter_request_id IS NULL OR char_length(openrouter_request_id) <= 200),
  prompt_tokens BIGINT CHECK (prompt_tokens IS NULL OR prompt_tokens >= 0),
  completion_tokens BIGINT CHECK (completion_tokens IS NULL OR completion_tokens >= 0),
  unknown_reason TEXT CHECK (unknown_reason IS NULL OR char_length(unknown_reason) <= 120),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  settled_at TIMESTAMPTZ,
  CHECK (
    (status IN ('settled', 'over_budget') AND actual_cost_micros IS NOT NULL AND actual_model IS NOT NULL
      AND actual_provider IS NOT NULL AND prompt_tokens IS NOT NULL AND completion_tokens IS NOT NULL
      AND settled_at IS NOT NULL)
    OR (status <> 'settled' AND actual_cost_micros IS NULL AND settled_at IS NULL)
  )
);

ALTER TABLE public.model_spend_ledger ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.model_spend_ledger FROM PUBLIC, anon, authenticated;
-- Service callers must use the SECURITY DEFINER RPCs below. Direct table
-- writes would bypass the atomic reservation, settlement, and idempotency rules.
REVOKE ALL ON public.model_spend_ledger FROM service_role;

CREATE OR REPLACE FUNCTION public.model_spend_meter_ready()
RETURNS BOOLEAN
LANGUAGE SQL SECURITY DEFINER SET search_path = '' AS $$
  SELECT to_regclass('public.model_spend_ledger') IS NOT NULL
$$;

CREATE OR REPLACE FUNCTION public.reserve_model_spend(
  p_attempt_id UUID,
  p_subject_id TEXT,
  p_run_id UUID,
  p_operation_id UUID,
  p_operation TEXT,
  p_requested_model TEXT,
  p_catalog_version TEXT,
  p_reserved_micros BIGINT,
  p_daily_cap_micros BIGINT,
  p_monthly_cap_micros BIGINT
) RETURNS BOOLEAN
LANGUAGE plpgsql SECURITY DEFINER SET search_path = '' AS $$
DECLARE
  v_existing public.model_spend_ledger%ROWTYPE;
  v_day_start TIMESTAMPTZ := date_trunc('day', now() AT TIME ZONE 'UTC') AT TIME ZONE 'UTC';
  v_month_start TIMESTAMPTZ := date_trunc('month', now() AT TIME ZONE 'UTC') AT TIME ZONE 'UTC';
  v_daily_used BIGINT;
  v_monthly_used BIGINT;
BEGIN
  IF p_subject_id IS NULL OR char_length(p_subject_id) NOT BETWEEN 1 AND 200
    OR p_operation IS NULL OR char_length(p_operation) NOT BETWEEN 1 AND 120
    OR p_reserved_micros < 0 OR p_daily_cap_micros <= 0 OR p_monthly_cap_micros <= 0 THEN
    RAISE EXCEPTION 'invalid spend reservation parameters' USING ERRCODE = '22023';
  END IF;

  PERFORM pg_advisory_xact_lock(hashtextextended(p_subject_id, 0));
  SELECT * INTO v_existing FROM public.model_spend_ledger WHERE attempt_id = p_attempt_id;
  IF FOUND THEN
    IF v_existing.subject_id <> p_subject_id OR v_existing.run_id IS DISTINCT FROM p_run_id
      OR v_existing.operation_id IS DISTINCT FROM p_operation_id
      OR v_existing.operation <> p_operation OR v_existing.requested_model <> p_requested_model
      OR v_existing.catalog_version <> p_catalog_version
      OR v_existing.reserved_cost_micros <> p_reserved_micros THEN
      RAISE EXCEPTION 'attempt idempotency conflict' USING ERRCODE = '23505';
    END IF;
    RETURN TRUE;
  END IF;
  SELECT COALESCE(sum(CASE WHEN status IN ('settled', 'over_budget') THEN actual_cost_micros ELSE reserved_cost_micros END), 0)
    INTO v_daily_used
    FROM public.model_spend_ledger
   WHERE subject_id = p_subject_id AND created_at >= v_day_start;
  SELECT COALESCE(sum(CASE WHEN status IN ('settled', 'over_budget') THEN actual_cost_micros ELSE reserved_cost_micros END), 0)
    INTO v_monthly_used
    FROM public.model_spend_ledger
   WHERE subject_id = p_subject_id AND created_at >= v_month_start;

  IF v_daily_used + p_reserved_micros > p_daily_cap_micros
    OR v_monthly_used + p_reserved_micros > p_monthly_cap_micros THEN
    RETURN FALSE;
  END IF;

  INSERT INTO public.model_spend_ledger (
    attempt_id, subject_id, run_id, operation_id, operation, requested_model,
    catalog_version, reserved_cost_micros
  ) VALUES (
    p_attempt_id, p_subject_id, p_run_id, p_operation_id, p_operation, p_requested_model,
    p_catalog_version, p_reserved_micros
  );
  RETURN TRUE;
END;
$$;

-- The ledger anonymization is a new idempotent account-deletion step.
CREATE OR REPLACE FUNCTION public.complete_account_deletion_step(
  p_job_id UUID, p_lease_owner TEXT, p_step TEXT
) RETURNS BOOLEAN
LANGUAGE plpgsql SECURITY DEFINER SET search_path = '' AS $$
DECLARE v_updated UUID;
BEGIN
  IF p_step NOT IN (
    'cancel_runs', 'memories', 'checkpoints', 'queue', 'run_store',
    'run_events', 'model_spend', 'user_rows', 'auth_user'
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

CREATE OR REPLACE FUNCTION public.finish_account_deletion_job(
  p_job_id UUID, p_lease_owner TEXT
) RETURNS BOOLEAN
LANGUAGE plpgsql SECURITY DEFINER SET search_path = '' AS $$
DECLARE v_updated UUID;
BEGIN
  UPDATE public.account_deletion_jobs j
     SET status = 'complete', last_error_code = NULL, lease_owner = NULL,
         lease_expires_at = NULL, completed_at = now(), updated_at = now()
   WHERE j.id = p_job_id AND j.status = 'processing' AND j.lease_owner = p_lease_owner
     AND cardinality(j.completed_steps) = 9
   RETURNING j.id INTO v_updated;
  RETURN v_updated IS NOT NULL;
END;
$$;

CREATE OR REPLACE FUNCTION public.mark_model_spend_unknown(
  p_attempt_id UUID, p_reason TEXT
) RETURNS BOOLEAN
LANGUAGE plpgsql SECURITY DEFINER SET search_path = '' AS $$
BEGIN
  UPDATE public.model_spend_ledger
     SET status = 'unknown', unknown_reason = left(COALESCE(p_reason, 'unknown'), 120)
   WHERE attempt_id = p_attempt_id AND status = 'reserved';
  IF FOUND THEN RETURN TRUE; END IF;
  RETURN EXISTS (
    SELECT 1 FROM public.model_spend_ledger
    WHERE attempt_id = p_attempt_id AND status IN ('unknown', 'settled', 'over_budget')
  );
END;
$$;

CREATE OR REPLACE FUNCTION public.record_model_spend_reference(
  p_attempt_id UUID, p_generation_id TEXT, p_request_id TEXT
) RETURNS BOOLEAN
LANGUAGE plpgsql SECURITY DEFINER SET search_path = '' AS $$
BEGIN
  UPDATE public.model_spend_ledger
     SET openrouter_generation_id = COALESCE(p_generation_id, openrouter_generation_id),
         openrouter_request_id = COALESCE(p_request_id, openrouter_request_id)
   WHERE attempt_id = p_attempt_id AND status IN ('reserved', 'unknown', 'settled', 'over_budget')
     AND (p_generation_id IS NULL OR char_length(p_generation_id) <= 200)
     AND (p_request_id IS NULL OR char_length(p_request_id) <= 200);
  RETURN FOUND;
END;
$$;

CREATE OR REPLACE FUNCTION public.settle_model_spend(
  p_attempt_id UUID,
  p_actual_model TEXT,
  p_actual_provider TEXT,
  p_prompt_tokens BIGINT,
  p_completion_tokens BIGINT,
  p_actual_cost_micros BIGINT
) RETURNS BOOLEAN
LANGUAGE plpgsql SECURITY DEFINER SET search_path = '' AS $$
DECLARE
  v_row public.model_spend_ledger%ROWTYPE;
BEGIN
  IF p_actual_model IS NULL OR char_length(p_actual_model) NOT BETWEEN 1 AND 200
    OR p_actual_provider IS NULL OR char_length(p_actual_provider) NOT BETWEEN 1 AND 120
    OR p_prompt_tokens < 0 OR p_completion_tokens < 0 OR p_actual_cost_micros < 0 THEN
    RAISE EXCEPTION 'invalid spend settlement parameters' USING ERRCODE = '22023';
  END IF;
  SELECT * INTO v_row FROM public.model_spend_ledger WHERE attempt_id = p_attempt_id FOR UPDATE;
  IF NOT FOUND THEN RETURN FALSE; END IF;
  IF v_row.status IN ('settled', 'over_budget') THEN
    RETURN v_row.actual_model = p_actual_model AND v_row.actual_provider = p_actual_provider
      AND v_row.prompt_tokens = p_prompt_tokens AND v_row.completion_tokens = p_completion_tokens
      AND v_row.actual_cost_micros = p_actual_cost_micros;
  END IF;
  UPDATE public.model_spend_ledger
     SET status = CASE WHEN p_actual_cost_micros > v_row.reserved_cost_micros THEN 'over_budget' ELSE 'settled' END,
         actual_cost_micros = p_actual_cost_micros,
         actual_model = p_actual_model, actual_provider = p_actual_provider,
         prompt_tokens = p_prompt_tokens, completion_tokens = p_completion_tokens,
         settled_at = now(), unknown_reason = NULL
   WHERE attempt_id = p_attempt_id;
  RETURN TRUE;
END;
$$;

CREATE OR REPLACE FUNCTION public.anonymize_model_spend_subject(p_subject_id TEXT)
RETURNS BOOLEAN
LANGUAGE plpgsql SECURITY DEFINER SET search_path = '' AS $$
BEGIN
  UPDATE public.model_spend_ledger
     SET subject_id = 'deleted:' || md5(p_subject_id), run_id = NULL, operation_id = NULL
   WHERE subject_id = p_subject_id;
  RETURN TRUE;
END;
$$;

REVOKE ALL ON FUNCTION public.reserve_model_spend(UUID, TEXT, UUID, UUID, TEXT, TEXT, TEXT, BIGINT, BIGINT, BIGINT) FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION public.model_spend_meter_ready() FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION public.mark_model_spend_unknown(UUID, TEXT) FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION public.record_model_spend_reference(UUID, TEXT, TEXT) FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION public.settle_model_spend(UUID, TEXT, TEXT, BIGINT, BIGINT, BIGINT) FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION public.anonymize_model_spend_subject(TEXT) FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION public.complete_account_deletion_step(UUID, TEXT, TEXT) FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION public.finish_account_deletion_job(UUID, TEXT) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.reserve_model_spend(UUID, TEXT, UUID, UUID, TEXT, TEXT, TEXT, BIGINT, BIGINT, BIGINT) TO service_role;
GRANT EXECUTE ON FUNCTION public.model_spend_meter_ready() TO service_role;
GRANT EXECUTE ON FUNCTION public.mark_model_spend_unknown(UUID, TEXT) TO service_role;
GRANT EXECUTE ON FUNCTION public.record_model_spend_reference(UUID, TEXT, TEXT) TO service_role;
GRANT EXECUTE ON FUNCTION public.settle_model_spend(UUID, TEXT, TEXT, BIGINT, BIGINT, BIGINT) TO service_role;
GRANT EXECUTE ON FUNCTION public.anonymize_model_spend_subject(TEXT) TO service_role;
GRANT EXECUTE ON FUNCTION public.complete_account_deletion_step(UUID, TEXT, TEXT) TO service_role;
GRANT EXECUTE ON FUNCTION public.finish_account_deletion_job(UUID, TEXT) TO service_role;

COMMIT;
