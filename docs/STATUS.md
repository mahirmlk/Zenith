# Status Matrix (update.md §18) — updated 2026-11-05 (final)

| Feature | State | Source | Tests |
|---|---|---|---|
| Feed/search/SSE/runs | Working, auth-required | `routers/search,stream,runs.py`, `services/job_queue.py` (Redis path) | 79+ passing |
| Auth/JWT/RLS + budgets + headers | Working | `jwt_validator.py`, `services/budget.py`, `main.py` headers | `test_security.py` |
| Migrations 0001–0006 | Drafted + statically verified; **apply via runbook** | `supabase/migrations/`, `docs/MIGRATIONS_RUNBOOK.md` | `test_migrations.py` |
| Guardrails | Working | `backend/security/`, `backend/guardrails/` | `test_guardrails.py` |
| Projects/notes/members | Working API + page | `routers/projects.py`, `app/projects/` | policy tests |
| Hybrid retrieval/evidence | Working | `services/retrieval.py`, `evidence_store.py` | `test_retrieval.py` |
| Deep research/compare | Working | `agents/research_types.py`, `routers/research.py` | `test_research.py` |
| Paper-to-code | Plan/export; sandbox gated (`SANDBOX_ENABLED=false`) | `agents/implementation_planner.py`, `services/sandbox_runner.py` | `test_implementation.py` |
| Watchlists + notifications | Working (in-app only) | `routers/watchlists,notifications.py` | — |
| Account export/delete | Working | `routers/account.py` | — |
| Model registry | Working (API + UI fetch) | `routers/models.py`, `ModelSelector.tsx` | — |
| Connectors | Registry (all disabled) | `services/connectors.py` | `test_connectors.py` |
| Evals/CI | Smoke + PR gate | `evals/`, `ci.yml` | 3/3 PASS |

Infra IDs (`ai-paper-agent-backend`) kept for deployment compatibility (update.md §17).
