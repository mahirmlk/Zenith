-- Version the shared crawl cache so changed source URLs and parser behavior
-- invalidate old content without deleting it during rollout.
BEGIN;

ALTER TABLE public.crawled_content
  ADD COLUMN IF NOT EXISTS parser_version TEXT;

COMMIT;
