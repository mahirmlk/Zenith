-- Add stable Semantic Scholar targets for author and inbound-citation watches.
-- Existing topic watchlists remain topics via the additive default.
-- Rollback: DROP INDEX IF EXISTS public.idx_watchlists_semantic_target;
--           ALTER TABLE public.watchlists DROP CONSTRAINT IF EXISTS watchlists_target_shape;
--           ALTER TABLE public.watchlists DROP COLUMN IF EXISTS target_id;
--           ALTER TABLE public.watchlists DROP COLUMN IF EXISTS target_type;
BEGIN;

ALTER TABLE public.watchlists
  ADD COLUMN IF NOT EXISTS target_type TEXT NOT NULL DEFAULT 'topic',
  ADD COLUMN IF NOT EXISTS target_id TEXT;

ALTER TABLE public.watchlists
  DROP CONSTRAINT IF EXISTS watchlists_target_shape;
ALTER TABLE public.watchlists
  ADD CONSTRAINT watchlists_target_shape CHECK (
    (target_type = 'topic' AND target_id IS NULL)
    OR (target_type IN ('author', 'citation') AND target_id IS NOT NULL AND length(target_id) BETWEEN 1 AND 200)
  );

CREATE INDEX IF NOT EXISTS idx_watchlists_semantic_target
  ON public.watchlists (target_type, target_id)
  WHERE enabled AND target_type IN ('author', 'citation');

COMMIT;
