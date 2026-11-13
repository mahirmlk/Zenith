-- Disable NOTIFICATIONS_EMAIL_ENABLED and drain/stop the notification worker first.
BEGIN;
DROP FUNCTION IF EXISTS public.notification_email_set_preferences(UUID,BOOLEAN,TEXT,TEXT,TEXT);
DROP FUNCTION IF EXISTS public.notification_email_record_suppression(TEXT,TEXT,TEXT,UUID);
DROP FUNCTION IF EXISTS public.notification_email_unsubscribe(TEXT);
DROP FUNCTION IF EXISTS public.notification_email_finish(UUID,TEXT,TEXT,TEXT);
DROP FUNCTION IF EXISTS public.notification_email_claim(TEXT,INTEGER);
DROP TABLE IF EXISTS public.notification_email_outbox;
DROP TABLE IF EXISTS public.notification_email_unsubscribe_tokens;
DROP TABLE IF EXISTS public.notification_email_suppressions;
DROP TABLE IF EXISTS public.notification_email_consent_events;
DROP TABLE IF EXISTS public.notification_email_preferences;
COMMIT;
