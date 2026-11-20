-- Store the auditable match basis for new watchlist notifications.
BEGIN;

ALTER TABLE public.notifications
  ADD COLUMN IF NOT EXISTS reason_code TEXT,
  ADD COLUMN IF NOT EXISTS reason_text TEXT;

ALTER TABLE public.notifications
  DROP CONSTRAINT IF EXISTS notifications_reason_code_check;
ALTER TABLE public.notifications
  ADD CONSTRAINT notifications_reason_code_check
  CHECK (reason_code IS NULL OR reason_code IN (
    'topic_term_overlap', 'author_relation', 'citation_relation'
  ));
ALTER TABLE public.notifications
  DROP CONSTRAINT IF EXISTS notifications_reason_text_length_check;
ALTER TABLE public.notifications
  ADD CONSTRAINT notifications_reason_text_length_check
  CHECK (reason_text IS NULL OR char_length(reason_text) <= 500);

COMMIT;
