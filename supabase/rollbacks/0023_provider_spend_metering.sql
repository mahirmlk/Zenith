-- Roll back provider spend metering after disabling metered model calls.
BEGIN;
CREATE OR REPLACE FUNCTION public.complete_account_deletion_step(
  p_job_id UUID, p_lease_owner TEXT, p_step TEXT
) RETURNS BOOLEAN
LANGUAGE plpgsql SECURITY DEFINER SET search_path = '' AS $$
DECLARE v_updated UUID;
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
     AND cardinality(j.completed_steps) = 8
   RETURNING j.id INTO v_updated;
  RETURN v_updated IS NOT NULL;
END;
$$;

DROP FUNCTION IF EXISTS public.model_spend_meter_ready();
DROP FUNCTION IF EXISTS public.anonymize_model_spend_subject(TEXT);
DROP FUNCTION IF EXISTS public.record_model_spend_reference(UUID, TEXT, TEXT);
DROP FUNCTION IF EXISTS public.settle_model_spend(UUID, TEXT, TEXT, BIGINT, BIGINT, BIGINT);
DROP FUNCTION IF EXISTS public.mark_model_spend_unknown(UUID, TEXT);
DROP FUNCTION IF EXISTS public.reserve_model_spend(UUID, TEXT, UUID, UUID, TEXT, TEXT, TEXT, BIGINT, BIGINT, BIGINT);
DROP TABLE IF EXISTS public.model_spend_ledger;
COMMIT;
