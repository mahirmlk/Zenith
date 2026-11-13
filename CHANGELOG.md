# Changelog

## Unreleased (2026-11-05, branches `audit/*`, `security/*`, `infra/*`, `feature/*`)
- Research: project-scoped hybrid search now mixes attached papers with exact matched PDF page sentences, stable page citations, and page-local offsets; public search never reads project PDFs.
- Research: project comparisons now include bounded, exact PDF page evidence beside abstract-based comparison rows; PDF evidence remains separately cited and extractive.
- Collaboration: project owners can invite email addresses as editors/viewers, resend/revoke pending invites, and accept via verified Supabase Auth sessions; new migration 0014 keeps invites separate from memberships and uses a service-role-only atomic acceptance RPC. Only one active invitation per email is permitted across projects to preserve Supabase's one-time confirmation token. Existing UUID roster management remains available. Staging email delivery is not yet verified.
- Research: project evidence maps, answers, searches, and project comparisons now include bounded exact PDF page spans with stable page citation IDs; project PDFs support owner/editor upload and member page viewing. OCR and cross-paper synthesis remain unavailable.
- Research: comparison columns now use exact abstract sentences selected by conservative keyword heuristics, with missing fields explicit and code status unverified.
- Evals: added `grounded_qa_v3` with 18 deterministic retrieval/grounding cases.
- Security: migration 0013 adds project-scoped extracted PDF documents/pages and RLS policies.
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
