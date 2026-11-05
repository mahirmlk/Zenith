# Status Matrix (update.md §18) — updated 2026-11-05 (shipping)

| Feature | State | Source | Tests |
|---|---|---|---|
| Feed/search/SSE/runs | Working | `routers/search,stream,runs.py`, `services/job_queue.py` | 57+ passing |
| Auth/JWT/RLS | Working (migrations drafted, apply to staging) | `jwt_validator.py`, `supabase/migrations/0001-0003` | `test_security.py` |
| Guardrails | Working | `backend/security/`, `backend/guardrails/` | `test_guardrails.py` |
| Projects/notes/members | Working API + page | `routers/projects.py`, `app/projects/` | policy tests |
| Hybrid retrieval/evidence | Working | `services/retrieval.py`, `evidence_store.py` | `test_retrieval.py` |
| Deep research/compare | Working | `agents/research_types.py`, `routers/research.py` | `test_research.py` |
| Paper-to-code | Plan/export only (no exec) | `agents/implementation_planner.py` | `test_implementation.py` |
| Watchlists | Working API | `routers/watchlists.py` | — |
| Connectors | Registry (all disabled) | `services/connectors.py` | `test_connectors.py` |
| Evals/CI | Smoke + PR gate | `evals/`, `.github/workflows/ci.yml` | 3/3 PASS |

Infra IDs (`ai-paper-agent-backend`) kept for deployment compatibility (update.md §17).
