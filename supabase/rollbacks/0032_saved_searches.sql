-- Rollback migration 0032. Removes only saved query configurations.
BEGIN;
DROP TRIGGER IF EXISTS saved_searches_touch_updated_at ON public.saved_searches;
DROP FUNCTION IF EXISTS public.touch_saved_search_updated_at();
DROP TABLE IF EXISTS public.saved_searches;
COMMIT;
