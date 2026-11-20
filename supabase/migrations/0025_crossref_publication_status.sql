-- Store DOI-backed, publisher-deposited Crossref update provenance and
-- support explicit per-user status watches with idempotent in-app alerts.
BEGIN;

ALTER TABLE public.papers
  ADD COLUMN IF NOT EXISTS doi TEXT,
  ADD COLUMN IF NOT EXISTS publication_update_type TEXT,
  ADD COLUMN IF NOT EXISTS publication_update_doi TEXT,
  ADD COLUMN IF NOT EXISTS publication_update_label TEXT,
  ADD COLUMN IF NOT EXISTS publication_update_date DATE,
  ADD COLUMN IF NOT EXISTS publication_update_source TEXT,
  ADD COLUMN IF NOT EXISTS publication_update_checked_at TIMESTAMPTZ;

ALTER TABLE public.papers
  DROP CONSTRAINT IF EXISTS papers_doi_format_check,
  DROP CONSTRAINT IF EXISTS papers_publication_update_type_check,
  DROP CONSTRAINT IF EXISTS papers_publication_update_provenance_check;
ALTER TABLE public.papers
  ADD CONSTRAINT papers_doi_format_check
    CHECK (doi IS NULL OR (char_length(doi) <= 255 AND doi ~ '^10\.[0-9]{4,9}/[^[:space:]]+$')),
  ADD CONSTRAINT papers_publication_update_type_check
    CHECK (publication_update_type IS NULL OR publication_update_type IN (
      'retraction', 'partial_retraction', 'withdrawal', 'removal', 'expression_of_concern'
    )),
  ADD CONSTRAINT papers_publication_update_provenance_check
    CHECK (
      (publication_update_type IS NULL AND publication_update_doi IS NULL
        AND publication_update_source IS NULL AND publication_update_label IS NULL
        AND publication_update_date IS NULL)
      OR (publication_update_type IS NOT NULL AND publication_update_doi IS NOT NULL
        AND publication_update_source = 'crossref')
    );

CREATE INDEX IF NOT EXISTS idx_papers_crossref_status_due
  ON public.papers (publication_update_checked_at NULLS FIRST)
  WHERE doi IS NOT NULL;

CREATE TABLE IF NOT EXISTS public.paper_status_watches (
  user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  paper_id TEXT NOT NULL REFERENCES public.papers(id) ON DELETE CASCADE,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  last_attempt_at TIMESTAMPTZ,
  PRIMARY KEY (user_id, paper_id)
);
ALTER TABLE public.paper_status_watches ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS paper_status_watches_select_own ON public.paper_status_watches;
CREATE POLICY paper_status_watches_select_own
  ON public.paper_status_watches FOR SELECT TO authenticated
  USING (user_id = auth.uid());
DROP POLICY IF EXISTS paper_status_watches_insert_own ON public.paper_status_watches;
CREATE POLICY paper_status_watches_insert_own
  ON public.paper_status_watches FOR INSERT TO authenticated
  WITH CHECK (user_id = auth.uid());
DROP POLICY IF EXISTS paper_status_watches_delete_own ON public.paper_status_watches;
CREATE POLICY paper_status_watches_delete_own
  ON public.paper_status_watches FOR DELETE TO authenticated
  USING (user_id = auth.uid());
CREATE INDEX IF NOT EXISTS idx_paper_status_watches_due
  ON public.paper_status_watches (last_attempt_at NULLS FIRST, created_at)
  INCLUDE (paper_id, user_id);

ALTER TABLE public.notifications
  ADD COLUMN IF NOT EXISTS notification_key TEXT;
ALTER TABLE public.notifications
  DROP CONSTRAINT IF EXISTS notifications_notification_key_length_check;
ALTER TABLE public.notifications
  ADD CONSTRAINT notifications_notification_key_length_check
  CHECK (notification_key IS NULL OR char_length(notification_key) <= 500);
CREATE UNIQUE INDEX IF NOT EXISTS uq_notifications_user_key
  ON public.notifications (user_id, notification_key)
  WHERE notification_key IS NOT NULL;

ALTER TABLE public.notifications
  DROP CONSTRAINT IF EXISTS notifications_reason_code_check;
ALTER TABLE public.notifications
  ADD CONSTRAINT notifications_reason_code_check
  CHECK (reason_code IS NULL OR reason_code IN (
    'topic_term_overlap', 'author_relation', 'citation_relation',
    'preprint_version_updated', 'publication_status_update'
  ));

COMMIT;
