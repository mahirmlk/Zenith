-- Migration 0007: watchlist notification delivery idempotency.
-- Existing notifications are retained: nullable watchlist_id values do not
-- collide under PostgreSQL's default UNIQUE NULLS DISTINCT semantics.
BEGIN;

ALTER TABLE public.notifications
  ADD COLUMN IF NOT EXISTS watchlist_id UUID
  REFERENCES public.watchlists(id) ON DELETE SET NULL;

CREATE UNIQUE INDEX IF NOT EXISTS uq_notifications_watchlist_paper
  ON public.notifications (user_id, watchlist_id, paper_id);

COMMIT;
