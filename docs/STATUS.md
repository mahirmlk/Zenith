# Status Matrix (update.md §18) — updated 2026-11-05

| Feature | State | Source | Tests | Limitations / Next PR |
|---|---|---|---|---|
| Paper feed/search/SSE | Working, hardened | `routers/search.py,stream.py,runs.py` | `test_search.py` | Durable queue + checkpointer next |
| Auth (Supabase JWT) | Working | `services/jwt_validator.py` | `test_jwt_validator.py`, `test_security.py` | Strict aud enforcement next |
| RLS/tenancy | Migration drafted (0001–0002), **not applied to live DB** | `supabase/migrations/` | staging test matrix TBD | Apply to staging + verify |
| Guardrails | Working (policy layer) | `backend/security/`, `backend/guardrails/` | `test_guardrails.py` | Durable approval store (Postgres) next |
| Research projects | API + list page | `routers/projects.py`, `app/projects/page.tsx` | policy tests | Sources/import/export next |
| Evals | Smoke harness | `evals/` | `run_evals.py` 3/3 | Full golden suite next |
| Paper-to-code / monitoring / MCP | Not started | — | — | Phases P3+, after sandbox review |

Infra identifiers (`ai-paper-agent-backend` Fly app / service id / package name) are **kept as compatibility** (update.md §17): renaming the Fly app would orphan the deployment. User-visible titles now say Zenith.
