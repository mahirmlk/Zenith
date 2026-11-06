-- Migration 0006: summary_contributions column (was only in schema.sql).
-- Additive and reversible.
BEGIN;
ALTER TABLE public.papers
  ADD COLUMN IF NOT EXISTS summary_contributions text;
COMMIT;
