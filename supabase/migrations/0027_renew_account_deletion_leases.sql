-- Renew account-deletion worker leases during long external cleanup steps.
BEGIN;

CREATE OR REPLACE FUNCTION public.renew_account_deletion_lease(
  p_job_id UUID,
  p_lease_owner TEXT,
  p_lease_seconds INTEGER DEFAULT 600
)
RETURNS BOOLEAN
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $$
DECLARE
  v_updated UUID;
BEGIN
  IF p_lease_seconds IS NULL OR p_lease_seconds NOT BETWEEN 60 AND 3600 THEN
    RAISE EXCEPTION 'invalid account deletion lease duration'
      USING ERRCODE = '22023';
  END IF;

  UPDATE public.account_deletion_jobs j
     SET lease_expires_at = now() + make_interval(secs => p_lease_seconds),
         updated_at = now()
   WHERE j.id = p_job_id
     AND j.status = 'processing'
     AND j.lease_owner = p_lease_owner
     AND j.lease_expires_at > now()
   RETURNING j.id INTO v_updated;
  RETURN v_updated IS NOT NULL;
END;
$$;

REVOKE ALL ON FUNCTION public.renew_account_deletion_lease(UUID, TEXT, INTEGER)
  FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.renew_account_deletion_lease(UUID, TEXT, INTEGER)
  TO service_role;

COMMIT;
