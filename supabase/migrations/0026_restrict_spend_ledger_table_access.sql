-- Keep provider spend accounting behind its atomic SECURITY DEFINER RPCs.
-- This forward-only ACL correction also protects databases that already applied
-- an earlier draft of migration 0023 with direct service_role table grants.
BEGIN;

REVOKE ALL PRIVILEGES ON TABLE public.model_spend_ledger
  FROM PUBLIC, anon, authenticated, service_role;

CREATE INDEX IF NOT EXISTS idx_model_spend_ledger_subject_created_at
  ON public.model_spend_ledger (subject_id, created_at);

COMMIT;
