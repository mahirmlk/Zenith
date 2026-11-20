-- Migration 0033: immutable, source-snapshotted project brief versions.
-- Rollback: see supabase/rollbacks/0033_versioned_project_briefs.sql.
BEGIN;

CREATE TABLE IF NOT EXISTS public.project_briefs (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  project_id UUID NOT NULL REFERENCES public.projects(id) ON DELETE CASCADE,
  title TEXT NOT NULL CHECK (char_length(title) BETWEEN 1 AND 160 AND btrim(title) = title),
  created_by UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  current_version INTEGER NOT NULL DEFAULT 0 CHECK (current_version >= 0),
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_project_briefs_project_updated
  ON public.project_briefs (project_id, updated_at DESC, id);

CREATE TABLE IF NOT EXISTS public.project_brief_versions (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  brief_id UUID NOT NULL REFERENCES public.project_briefs(id) ON DELETE CASCADE,
  version INTEGER NOT NULL CHECK (version >= 1),
  content TEXT NOT NULL CHECK (char_length(content) BETWEEN 1 AND 50000 AND btrim(content) = content),
  source_snapshot JSONB NOT NULL DEFAULT '[]'::jsonb CHECK (
    jsonb_typeof(source_snapshot) = 'array' AND jsonb_array_length(source_snapshot) <= 50
  ),
  created_by UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  content_sha256 TEXT NOT NULL CHECK (content_sha256 ~ '^[0-9a-f]{64}$'),
  origin TEXT NOT NULL DEFAULT 'user_authored' CHECK (origin = 'user_authored'),
  UNIQUE (brief_id, version)
);

CREATE INDEX IF NOT EXISTS idx_project_brief_versions_brief_version
  ON public.project_brief_versions (brief_id, version DESC);
CREATE INDEX IF NOT EXISTS idx_project_brief_versions_created_by
  ON public.project_brief_versions (created_by);

ALTER TABLE public.project_briefs ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.project_brief_versions ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS project_briefs_select_access ON public.project_briefs;
CREATE POLICY project_briefs_select_access ON public.project_briefs
  FOR SELECT TO authenticated USING (public.can_access_project(project_id));
DROP POLICY IF EXISTS project_brief_versions_select_access ON public.project_brief_versions;
CREATE POLICY project_brief_versions_select_access ON public.project_brief_versions
  FOR SELECT TO authenticated USING (
    EXISTS (
      SELECT 1 FROM public.project_briefs b
      WHERE b.id = brief_id AND public.can_access_project(b.project_id)
    )
  );

-- All writes use the authenticated API and atomic RPCs. Version rows are
-- append-only to clients; account/project deletion still cascades as required.
REVOKE INSERT, UPDATE, DELETE ON public.project_briefs FROM PUBLIC, anon, authenticated;
REVOKE INSERT, UPDATE, DELETE ON public.project_brief_versions FROM PUBLIC, anon, authenticated;
GRANT SELECT ON public.project_briefs, public.project_brief_versions TO authenticated;

CREATE OR REPLACE FUNCTION public.validate_project_brief_sources(
  p_project_id UUID,
  p_source_snapshot JSONB
) RETURNS VOID
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $$
DECLARE
  v_item JSONB;
  v_source_text TEXT;
  v_start INTEGER;
  v_end INTEGER;
  v_quote TEXT;
  v_source_type TEXT;
  v_paper_source_id UUID;
  v_document_id UUID;
  v_page_number INTEGER;
BEGIN
  IF p_source_snapshot IS NULL
     OR jsonb_typeof(p_source_snapshot) IS DISTINCT FROM 'array' THEN
    RAISE EXCEPTION 'invalid_source_snapshot' USING ERRCODE = '22023';
  END IF;
  IF jsonb_array_length(p_source_snapshot) > 50 THEN
    RAISE EXCEPTION 'invalid_source_snapshot' USING ERRCODE = '22023';
  END IF;

  FOR v_item IN SELECT value FROM jsonb_array_elements(p_source_snapshot)
  LOOP
    IF jsonb_typeof(v_item) IS DISTINCT FROM 'object' THEN
      RAISE EXCEPTION 'invalid_source_locator' USING ERRCODE = '22023';
    END IF;
    v_source_type := v_item->>'source_type';
    v_start := (v_item->>'start_offset')::INTEGER;
    v_end := (v_item->>'end_offset')::INTEGER;
    v_quote := v_item->>'quote';
    IF v_start IS NULL OR v_end IS NULL OR v_start < 0 OR v_end <= v_start
       OR v_quote IS NULL OR char_length(v_quote) NOT BETWEEN 1 AND 4000
       OR char_length(v_quote) <> v_end - v_start THEN
      RAISE EXCEPTION 'invalid_source_locator' USING ERRCODE = '22023';
    END IF;

    IF v_source_type = 'paper_abstract' THEN
      v_paper_source_id := (v_item->>'paper_source_id')::UUID;
      SELECT p.abstract INTO v_source_text
      FROM public.project_sources ps
      JOIN public.papers p ON p.id = ps.paper_id
      WHERE ps.id = v_paper_source_id AND ps.project_id = p_project_id;
    ELSIF v_source_type = 'pdf_page' THEN
      v_document_id := (v_item->>'document_id')::UUID;
      v_page_number := (v_item->>'page_number')::INTEGER;
      SELECT page.text INTO v_source_text
      FROM public.project_documents d
      JOIN public.project_document_pages page ON page.document_id = d.id
      WHERE d.id = v_document_id
        AND d.project_id = p_project_id
        AND page.page_number = v_page_number;
    ELSE
      RAISE EXCEPTION 'invalid_source_type' USING ERRCODE = '22023';
    END IF;

    IF v_source_text IS NULL OR v_end > char_length(v_source_text)
       OR substring(v_source_text FROM v_start + 1 FOR v_end - v_start) <> v_quote THEN
      RAISE EXCEPTION 'source_quote_mismatch' USING ERRCODE = '22023';
    END IF;
  END LOOP;
END;
$$;

CREATE OR REPLACE FUNCTION public.create_project_brief(
  p_actor UUID,
  p_project_id UUID,
  p_title TEXT,
  p_content TEXT,
  p_source_snapshot JSONB,
  p_content_sha256 TEXT
) RETURNS JSONB
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $$
DECLARE
  v_brief public.project_briefs;
  v_version public.project_brief_versions;
BEGIN
  IF p_actor IS NULL OR p_title IS NULL OR char_length(p_title) NOT BETWEEN 1 AND 160
     OR btrim(p_title) <> p_title OR p_content IS NULL
     OR char_length(p_content) NOT BETWEEN 1 AND 50000 OR btrim(p_content) <> p_content
     OR p_content_sha256 IS NULL OR p_content_sha256 !~ '^[0-9a-f]{64}$' THEN
    RAISE EXCEPTION 'invalid_brief' USING ERRCODE = '22023';
  END IF;
  IF NOT EXISTS (
    SELECT 1 FROM public.projects p
    WHERE p.id = p_project_id AND p.deleted_at IS NULL
      AND (p.owner_id = p_actor OR EXISTS (
        SELECT 1 FROM public.project_members pm
        WHERE pm.project_id = p.id AND pm.user_id = p_actor AND pm.role IN ('owner', 'editor')
      ))
  ) THEN
    RAISE EXCEPTION 'project_write_denied' USING ERRCODE = '42501';
  END IF;
  PERFORM public.validate_project_brief_sources(p_project_id, p_source_snapshot);

  INSERT INTO public.project_briefs (project_id, title, created_by, current_version)
  VALUES (p_project_id, p_title, p_actor, 1)
  RETURNING * INTO v_brief;

  INSERT INTO public.project_brief_versions
    (brief_id, version, content, source_snapshot, created_by, content_sha256)
  VALUES (v_brief.id, 1, p_content, p_source_snapshot, p_actor, p_content_sha256)
  RETURNING * INTO v_version;

  RETURN jsonb_build_object('brief', to_jsonb(v_brief), 'version', to_jsonb(v_version));
END;
$$;

CREATE OR REPLACE FUNCTION public.append_project_brief_version(
  p_actor UUID,
  p_brief_id UUID,
  p_expected_current_version INTEGER,
  p_content TEXT,
  p_source_snapshot JSONB,
  p_content_sha256 TEXT
) RETURNS JSONB
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $$
DECLARE
  v_brief public.project_briefs;
  v_version public.project_brief_versions;
BEGIN
  SELECT * INTO v_brief
  FROM public.project_briefs b
  WHERE b.id = p_brief_id
  FOR UPDATE;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'brief_not_found' USING ERRCODE = 'P0002';
  END IF;
  IF p_actor IS NULL OR NOT EXISTS (
    SELECT 1 FROM public.projects p
    WHERE p.id = v_brief.project_id AND p.deleted_at IS NULL
      AND (p.owner_id = p_actor OR EXISTS (
        SELECT 1 FROM public.project_members pm
        WHERE pm.project_id = p.id AND pm.user_id = p_actor AND pm.role IN ('owner', 'editor')
      ))
  ) THEN
    RAISE EXCEPTION 'project_write_denied' USING ERRCODE = '42501';
  END IF;
  IF p_expected_current_version IS NULL
     OR p_expected_current_version <> v_brief.current_version THEN
    RAISE EXCEPTION 'brief_version_conflict' USING ERRCODE = '40001';
  END IF;
  IF p_content IS NULL OR char_length(p_content) NOT BETWEEN 1 AND 50000
     OR btrim(p_content) <> p_content OR p_content_sha256 IS NULL
     OR p_content_sha256 !~ '^[0-9a-f]{64}$' THEN
    RAISE EXCEPTION 'invalid_brief_version' USING ERRCODE = '22023';
  END IF;
  PERFORM public.validate_project_brief_sources(v_brief.project_id, p_source_snapshot);

  INSERT INTO public.project_brief_versions
    (brief_id, version, content, source_snapshot, created_by, content_sha256)
  VALUES (
    v_brief.id, v_brief.current_version + 1, p_content,
    p_source_snapshot, p_actor, p_content_sha256
  )
  RETURNING * INTO v_version;
  UPDATE public.project_briefs
  SET current_version = v_version.version, updated_at = NOW()
  WHERE id = v_brief.id;

  RETURN to_jsonb(v_version);
END;
$$;

-- Account deletion may remove one author's versions from a shared brief. Keep
-- the aggregate head aligned with the remaining immutable history.
CREATE OR REPLACE FUNCTION public.reconcile_project_brief_head_after_version_delete()
RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $$
BEGIN
  UPDATE public.project_briefs b
  SET current_version = COALESCE((
    SELECT max(v.version) FROM public.project_brief_versions v WHERE v.brief_id = OLD.brief_id
  ), 0),
  updated_at = NOW()
  WHERE b.id = OLD.brief_id;
  RETURN OLD;
END;
$$;

DROP TRIGGER IF EXISTS project_brief_head_after_version_delete ON public.project_brief_versions;
CREATE TRIGGER project_brief_head_after_version_delete
  AFTER DELETE ON public.project_brief_versions
  FOR EACH ROW EXECUTE FUNCTION public.reconcile_project_brief_head_after_version_delete();

REVOKE ALL ON FUNCTION public.validate_project_brief_sources(UUID, JSONB) FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION public.create_project_brief(UUID, UUID, TEXT, TEXT, JSONB, TEXT) FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION public.append_project_brief_version(UUID, UUID, INTEGER, TEXT, JSONB, TEXT) FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION public.reconcile_project_brief_head_after_version_delete() FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.validate_project_brief_sources(UUID, JSONB) TO service_role;
GRANT EXECUTE ON FUNCTION public.create_project_brief(UUID, UUID, TEXT, TEXT, JSONB, TEXT) TO service_role;
GRANT EXECUTE ON FUNCTION public.append_project_brief_version(UUID, UUID, INTEGER, TEXT, JSONB, TEXT) TO service_role;
GRANT EXECUTE ON FUNCTION public.reconcile_project_brief_head_after_version_delete() TO service_role;

COMMIT;
