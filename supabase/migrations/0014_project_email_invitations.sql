-- Project email invitations. Membership is granted only by the atomic,
-- service-role-only acceptance function below.
BEGIN;

CREATE TABLE IF NOT EXISTS public.project_invitations (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  project_id UUID NOT NULL REFERENCES public.projects(id) ON DELETE CASCADE,
  invited_by UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  email TEXT NOT NULL,
  normalized_email TEXT NOT NULL,
  role TEXT NOT NULL CHECK (role IN ('editor', 'viewer')),
  status TEXT NOT NULL DEFAULT 'pending'
    CHECK (status IN ('pending', 'accepted', 'revoked', 'expired', 'delivery_failed')),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  expires_at TIMESTAMPTZ NOT NULL,
  email_sent_at TIMESTAMPTZ,
  accepted_at TIMESTAMPTZ,
  accepted_user_id UUID REFERENCES auth.users(id) ON DELETE SET NULL
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_project_invitations_active_email
  ON public.project_invitations (normalized_email)
  WHERE status IN ('pending', 'delivery_failed');
CREATE INDEX IF NOT EXISTS idx_project_invitations_project_created
  ON public.project_invitations (project_id, created_at DESC);

ALTER TABLE public.project_invitations ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS project_invitations_owner_select ON public.project_invitations;
CREATE POLICY project_invitations_owner_select ON public.project_invitations
  FOR SELECT TO authenticated
  USING (public.is_project_owner(project_id));

REVOKE ALL ON public.project_invitations FROM PUBLIC, anon;
REVOKE INSERT, UPDATE, DELETE ON public.project_invitations FROM authenticated;
GRANT SELECT ON public.project_invitations TO authenticated;
GRANT ALL ON public.project_invitations TO service_role;

CREATE OR REPLACE FUNCTION public.accept_project_invitation(
  p_invitation_id UUID,
  p_accepting_user_id UUID
)
RETURNS JSONB
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $$
DECLARE
  v_user_email TEXT;
  v_email_confirmed_at TIMESTAMPTZ;
  v_invitation public.project_invitations%ROWTYPE;
  v_project_title TEXT;
  v_member_role TEXT;
BEGIN
  SELECT lower(btrim(u.email)), u.email_confirmed_at
    INTO v_user_email, v_email_confirmed_at
    FROM auth.users u
    WHERE u.id = p_accepting_user_id;

  IF v_user_email IS NULL OR v_email_confirmed_at IS NULL THEN
    RETURN jsonb_build_object('status', 'email_unverified');
  END IF;

  SELECT i.* INTO v_invitation
    FROM public.project_invitations i
    WHERE i.id = p_invitation_id
    FOR UPDATE;
  IF NOT FOUND THEN
    RETURN jsonb_build_object('status', 'not_found');
  END IF;

  IF v_user_email <> v_invitation.normalized_email THEN
    RETURN jsonb_build_object('status', 'email_mismatch');
  END IF;

  SELECT p.title INTO v_project_title
    FROM public.projects p
    WHERE p.id = v_invitation.project_id AND p.deleted_at IS NULL
    FOR SHARE;
  IF NOT FOUND THEN
    RETURN jsonb_build_object('status', 'inactive_project');
  END IF;

  IF v_invitation.status = 'accepted' THEN
    IF v_invitation.accepted_user_id = p_accepting_user_id THEN
      SELECT pm.role INTO v_member_role
        FROM public.project_members pm
        WHERE pm.project_id = v_invitation.project_id
          AND pm.user_id = p_accepting_user_id;
      RETURN jsonb_build_object(
        'status', 'accepted', 'project_id', v_invitation.project_id,
        'project_title', v_project_title, 'role', COALESCE(v_member_role, v_invitation.role)
      );
    END IF;
    RETURN jsonb_build_object('status', 'not_found');
  END IF;

  IF v_invitation.status <> 'pending' THEN
    RETURN jsonb_build_object('status', v_invitation.status);
  END IF;

  IF v_invitation.expires_at <= now() THEN
    UPDATE public.project_invitations
      SET status = 'expired'
      WHERE id = v_invitation.id;
    RETURN jsonb_build_object('status', 'expired');
  END IF;

  INSERT INTO public.project_members (project_id, user_id, role)
    VALUES (v_invitation.project_id, p_accepting_user_id, v_invitation.role)
    ON CONFLICT (project_id, user_id)
    DO NOTHING
    RETURNING role INTO v_member_role;

  -- A pre-existing membership (especially owner) keeps its current role.
  IF v_member_role IS NULL THEN
    SELECT pm.role INTO v_member_role
      FROM public.project_members pm
      WHERE pm.project_id = v_invitation.project_id
        AND pm.user_id = p_accepting_user_id;
  END IF;

  UPDATE public.project_invitations
    SET status = 'accepted', accepted_user_id = p_accepting_user_id, accepted_at = now()
    WHERE id = v_invitation.id;

  RETURN jsonb_build_object(
    'status', 'accepted', 'project_id', v_invitation.project_id,
    'project_title', v_project_title, 'role', v_member_role
  );
END;
$$;

REVOKE ALL ON FUNCTION public.accept_project_invitation(UUID, UUID) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.accept_project_invitation(UUID, UUID) TO service_role;

COMMIT;
