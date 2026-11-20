-- Apply only after stopping all API/worker instances that can renew leases.
BEGIN;
DROP FUNCTION IF EXISTS public.renew_account_deletion_lease(UUID, TEXT, INTEGER);
COMMIT;
