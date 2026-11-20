-- Apply only after stopping API/workers using the cache-version contract.
-- Content and URL rows remain intact; the cache will revert to paper-ID-only reads.
BEGIN;

ALTER TABLE public.crawled_content
  DROP COLUMN IF EXISTS parser_version;

COMMIT;
