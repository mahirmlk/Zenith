-- Optional, consent-based watchlist digest delivery. All records are service-only.
-- Rollback after disabling NOTIFICATIONS_EMAIL_ENABLED and draining the outbox:
--   DROP FUNCTION IF EXISTS public.notification_email_record_suppression(TEXT,TEXT,TEXT,UUID);
--   DROP FUNCTION IF EXISTS public.notification_email_set_preferences(UUID,BOOLEAN,TEXT,TEXT,TEXT);
--   DROP FUNCTION IF EXISTS public.notification_email_unsubscribe(TEXT);
--   DROP FUNCTION IF EXISTS public.notification_email_claim(TEXT,INTEGER);
--   DROP FUNCTION IF EXISTS public.notification_email_finish(UUID,TEXT,TEXT,TEXT);
--   DROP TABLE public.notification_email_outbox, public.notification_email_unsubscribe_tokens,
--     public.notification_email_suppressions, public.notification_email_consent_events,
--     public.notification_email_preferences;
BEGIN;

CREATE TABLE public.notification_email_preferences (
  user_id UUID PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
  email_opt_in BOOLEAN NOT NULL DEFAULT FALSE,
  email_frequency TEXT NOT NULL DEFAULT 'daily' CHECK (email_frequency IN ('daily','weekly')),
  timezone TEXT NOT NULL DEFAULT 'UTC',
  recipient_hash TEXT,
  suppressed BOOLEAN NOT NULL DEFAULT FALSE,
  consented_at TIMESTAMPTZ,
  unsubscribed_at TIMESTAMPTZ,
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE public.notification_email_consent_events (
  id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  user_id UUID REFERENCES auth.users(id) ON DELETE CASCADE,
  action TEXT NOT NULL CHECK (action IN ('opt_in','opt_out','unsubscribe','suppressed')),
  recipient_hash TEXT,
  source TEXT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Retain only a keyed, one-way recipient hash after account deletion so a known
-- hard bounce/complaint cannot be re-contacted by creating another account.
CREATE TABLE public.notification_email_suppressions (
  recipient_hash TEXT PRIMARY KEY,
  reason TEXT NOT NULL CHECK (reason IN ('bounce','complaint')),
  provider_event_id TEXT NOT NULL UNIQUE,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE public.notification_email_unsubscribe_tokens (
  token_hash TEXT PRIMARY KEY,
  user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  expires_at TIMESTAMPTZ NOT NULL,
  consumed_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE public.notification_email_outbox (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  window_start TIMESTAMPTZ NOT NULL,
  scheduled_at TIMESTAMPTZ NOT NULL,
  frequency TEXT NOT NULL CHECK (frequency IN ('daily','weekly')),
  status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending','processing','sent','suppressed','failed')),
  attempts INTEGER NOT NULL DEFAULT 0 CHECK (attempts >= 0),
  next_attempt_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  lease_owner TEXT,
  lease_expires_at TIMESTAMPTZ,
  provider_message_id TEXT,
  last_error_code TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  sent_at TIMESTAMPTZ,
  UNIQUE(user_id, window_start)
);
CREATE INDEX notification_email_outbox_due_idx
  ON public.notification_email_outbox(next_attempt_at, created_at)
  WHERE status IN ('pending','processing');

CREATE OR REPLACE FUNCTION public.notification_email_set_preferences(
  p_user_id UUID, p_email_opt_in BOOLEAN, p_email_frequency TEXT,
  p_timezone TEXT, p_recipient_hash TEXT
) RETURNS public.notification_email_preferences
LANGUAGE plpgsql SECURITY DEFINER SET search_path = '' AS $$
DECLARE v_old public.notification_email_preferences; v_new public.notification_email_preferences;
BEGIN
  SELECT * INTO v_old FROM public.notification_email_preferences WHERE user_id=p_user_id FOR UPDATE;
  INSERT INTO public.notification_email_preferences(
    user_id,email_opt_in,email_frequency,timezone,recipient_hash,suppressed,
    consented_at,unsubscribed_at,updated_at
  ) VALUES (
    p_user_id,p_email_opt_in,p_email_frequency,p_timezone,
    CASE WHEN p_email_opt_in THEN p_recipient_hash ELSE v_old.recipient_hash END,
    CASE WHEN p_email_opt_in THEN FALSE ELSE COALESCE(v_old.suppressed,FALSE) END,
    CASE WHEN p_email_opt_in AND (
      NOT COALESCE(v_old.email_opt_in,FALSE) OR v_old.recipient_hash IS DISTINCT FROM p_recipient_hash
    ) THEN now() ELSE v_old.consented_at END,
    CASE WHEN NOT p_email_opt_in AND COALESCE(v_old.email_opt_in,FALSE) THEN now() ELSE v_old.unsubscribed_at END,
    now()
  ) ON CONFLICT (user_id) DO UPDATE SET
    email_opt_in=EXCLUDED.email_opt_in,email_frequency=EXCLUDED.email_frequency,
    timezone=EXCLUDED.timezone,recipient_hash=EXCLUDED.recipient_hash,
    suppressed=EXCLUDED.suppressed,consented_at=EXCLUDED.consented_at,
    unsubscribed_at=EXCLUDED.unsubscribed_at,updated_at=now()
  RETURNING * INTO v_new;
  IF COALESCE(v_old.email_opt_in,FALSE) IS DISTINCT FROM p_email_opt_in
     OR (p_email_opt_in AND v_old.recipient_hash IS DISTINCT FROM p_recipient_hash) THEN
    INSERT INTO public.notification_email_consent_events(user_id,action,recipient_hash,source)
      VALUES(p_user_id,CASE WHEN p_email_opt_in THEN 'opt_in' ELSE 'opt_out' END,v_new.recipient_hash,'settings');
  END IF;
  RETURN v_new;
END; $$;

ALTER TABLE public.notification_email_preferences ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.notification_email_consent_events ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.notification_email_suppressions ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.notification_email_unsubscribe_tokens ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.notification_email_outbox ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.notification_email_preferences, public.notification_email_consent_events,
  public.notification_email_suppressions, public.notification_email_unsubscribe_tokens,
  public.notification_email_outbox FROM PUBLIC, anon, authenticated;
GRANT ALL ON public.notification_email_preferences, public.notification_email_consent_events,
  public.notification_email_suppressions, public.notification_email_unsubscribe_tokens,
  public.notification_email_outbox TO service_role;
GRANT USAGE, SELECT ON SEQUENCE public.notification_email_consent_events_id_seq TO service_role;

CREATE OR REPLACE FUNCTION public.notification_email_claim(p_lease_owner TEXT, p_limit INTEGER)
RETURNS SETOF public.notification_email_outbox LANGUAGE plpgsql SECURITY DEFINER SET search_path = '' AS $$
BEGIN
  -- Recover a worker that died while owning its final permitted attempt.
  -- Without this cleanup the row would remain processing forever because it
  -- can no longer satisfy the attempts < 5 claim predicate.
  UPDATE public.notification_email_outbox
    SET status='failed', lease_owner=NULL, lease_expires_at=NULL,
        last_error_code='attempts_exhausted'
    WHERE status='processing' AND attempts >= 5 AND lease_expires_at < now();

  RETURN QUERY
  WITH due AS (
    SELECT id FROM public.notification_email_outbox
    WHERE (status = 'pending' OR (status = 'processing' AND lease_expires_at < now()))
      AND next_attempt_at <= now() AND attempts < 5
    ORDER BY scheduled_at, created_at
    FOR UPDATE SKIP LOCKED LIMIT LEAST(GREATEST(p_limit, 1), 5)
  )
  UPDATE public.notification_email_outbox o
  SET status='processing', attempts=o.attempts+1, lease_owner=p_lease_owner,
      lease_expires_at=now()+interval '2 minutes'
  FROM due WHERE o.id=due.id RETURNING o.*;
END; $$;

CREATE OR REPLACE FUNCTION public.notification_email_finish(
  p_id UUID, p_lease_owner TEXT, p_status TEXT, p_message_id TEXT DEFAULT NULL
) RETURNS BOOLEAN LANGUAGE plpgsql SECURITY DEFINER SET search_path = '' AS $$
BEGIN
  UPDATE public.notification_email_outbox
  SET status=p_status, provider_message_id=p_message_id,
      sent_at=CASE WHEN p_status='sent' THEN now() ELSE sent_at END,
      lease_owner=NULL, lease_expires_at=NULL, last_error_code=NULL
  WHERE id=p_id AND lease_owner=p_lease_owner AND status='processing';
  RETURN FOUND;
END; $$;

CREATE OR REPLACE FUNCTION public.notification_email_unsubscribe(p_token_hash TEXT)
RETURNS BOOLEAN LANGUAGE plpgsql SECURITY DEFINER SET search_path = '' AS $$
DECLARE v_user_id UUID;
BEGIN
  UPDATE public.notification_email_unsubscribe_tokens
    SET consumed_at=COALESCE(consumed_at, now())
    WHERE token_hash=p_token_hash AND expires_at>now()
    RETURNING user_id INTO v_user_id;
  IF v_user_id IS NULL THEN RETURN FALSE; END IF;
  UPDATE public.notification_email_preferences
    SET email_opt_in=FALSE, unsubscribed_at=now(), updated_at=now()
    WHERE user_id=v_user_id AND email_opt_in=TRUE;
  IF FOUND THEN
    INSERT INTO public.notification_email_consent_events(user_id,action,source)
      VALUES(v_user_id,'unsubscribe','one_click');
  END IF;
  RETURN TRUE;
END; $$;

CREATE OR REPLACE FUNCTION public.notification_email_record_suppression(
  p_recipient_hash TEXT, p_reason TEXT, p_event_id TEXT, p_user_id UUID DEFAULT NULL
) RETURNS BOOLEAN LANGUAGE plpgsql SECURITY DEFINER SET search_path = '' AS $$
BEGIN
  INSERT INTO public.notification_email_suppressions(recipient_hash,reason,provider_event_id)
    VALUES(p_recipient_hash,p_reason,p_event_id) ON CONFLICT DO NOTHING;
  WITH changed AS (
    UPDATE public.notification_email_preferences
      SET suppressed=TRUE, email_opt_in=FALSE, updated_at=now()
      WHERE recipient_hash=p_recipient_hash AND suppressed=FALSE
      RETURNING user_id
  )
  INSERT INTO public.notification_email_consent_events(user_id,action,recipient_hash,source)
    SELECT user_id,'suppressed',p_recipient_hash,'resend_webhook' FROM changed;
  RETURN TRUE;
END; $$;

REVOKE ALL ON FUNCTION public.notification_email_claim(TEXT,INTEGER),
  public.notification_email_finish(UUID,TEXT,TEXT,TEXT), public.notification_email_unsubscribe(TEXT),
  public.notification_email_record_suppression(TEXT,TEXT,TEXT,UUID),
  public.notification_email_set_preferences(UUID,BOOLEAN,TEXT,TEXT,TEXT) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.notification_email_claim(TEXT,INTEGER),
  public.notification_email_finish(UUID,TEXT,TEXT,TEXT), public.notification_email_unsubscribe(TEXT),
  public.notification_email_record_suppression(TEXT,TEXT,TEXT,UUID),
  public.notification_email_set_preferences(UUID,BOOLEAN,TEXT,TEXT,TEXT) TO service_role;
COMMIT;
