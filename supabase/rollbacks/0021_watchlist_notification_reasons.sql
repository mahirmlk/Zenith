-- Apply only after deploying code that no longer writes notification reasons.
BEGIN;

ALTER TABLE public.notifications
  DROP CONSTRAINT IF EXISTS notifications_reason_code_check,
  DROP CONSTRAINT IF EXISTS notifications_reason_text_length_check,
  DROP COLUMN IF EXISTS reason_code,
  DROP COLUMN IF EXISTS reason_text;

COMMIT;
