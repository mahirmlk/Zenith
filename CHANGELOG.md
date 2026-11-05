# Changelog

## Unreleased (2026-11-05, branches `audit/*`, `security/*`, `infra/*`, `feature/*`)
- Security: JWT alg allowlist + iss/aud checks; SSRF validator; model registry; RLS migrations 0001–0002; generic client errors; health checks + readiness.
- Runs: start-once SSE with replay, run ownership, idempotency keys, status/events/cancel endpoints.
- Guardrails: `backend/security/` + `backend/guardrails/` policy layer with backend-recorded approvals.
- Projects API: create/list/get/patch/soft-delete + notes (Supabase-backed, owner-enforced).
- Evals: deterministic smoke harness; CI now gated on PR/push with eval step.
- Fixed: run-store coroutine-reuse crash; health `checks` contract.
