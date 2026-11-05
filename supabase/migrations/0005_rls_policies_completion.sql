-- Migration 0005: complete RLS policies (security audit H1).
-- project_members / research_runs / run_events had RLS enabled with
-- no policies (deny-all for direct API). Add owner/member policies.
BEGIN;
DROP POLICY IF EXISTS project_members_member ON public.project_members;
CREATE POLICY project_members_member ON public.project_members
  FOR ALL TO authenticated
  USING (EXISTS (SELECT 1 FROM public.projects p WHERE p.id = project_id AND p.owner_id = auth.uid()))
  WITH CHECK (EXISTS (SELECT 1 FROM public.projects p WHERE p.id = project_id AND p.owner_id = auth.uid()));

DROP POLICY IF EXISTS runs_owner ON public.research_runs;
CREATE POLICY runs_owner ON public.research_runs
  FOR ALL TO authenticated
  USING (user_id = auth.uid()) WITH CHECK (user_id = auth.uid());

DROP POLICY IF EXISTS run_events_owner ON public.run_events;
CREATE POLICY run_events_owner ON public.run_events
  FOR ALL TO authenticated
  USING (EXISTS (SELECT 1 FROM public.research_runs r WHERE r.id = run_id AND r.user_id = auth.uid()))
  WITH CHECK (EXISTS (SELECT 1 FROM public.research_runs r WHERE r.id = run_id AND r.user_id = auth.uid()));
COMMIT;
