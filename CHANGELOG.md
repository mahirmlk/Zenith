# Changelog

## Unreleased (2026-11-05, branches `audit/*`, `security/*`, `infra/*`, `feature/*`)
- Projects: project detail returns the caller's role; workspace hides source and note mutation controls from viewers.
- Collaboration: owners can list, add/update existing members by UUID, and remove members; membership mutations retain owner-only checks and audit logging.
- Monitoring: add per-notification read state, scoped to the authenticated caller.
- Security: migration 0012 applies active-project checks to owner/access/write helpers used by direct PostgREST RLS policies.
- Security: JWT alg allowlist + iss/aud checks; SSRF validator; model registry; RLS migrations 0001–0002; generic client errors; health checks + readiness.
- Runs: start-once SSE with replay, run ownership, idempotency keys, status/events/cancel endpoints.
- Guardrails: `backend/security/` + `backend/guardrails/` policy layer with backend-recorded approvals.
- Projects API: create/list/get/patch/soft-delete + notes (Supabase-backed, owner-enforced).
- Evals: deterministic smoke harness; CI now gated on PR/push with eval step.
- Fixed: run-store coroutine-reuse crash; health `checks` contract.
