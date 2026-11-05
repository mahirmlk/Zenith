# Status Matrix (update.md §18)

| Feature | State | Source | Tests | Limitations / Next PR |
|---|---|---|---|---|
| Paper feed/search/SSE | Working, being hardened | `routers/search.py,stream.py` | `test_search.py` | Start-once + replay core landed this session; durable queue next |
| Auth (Supabase JWT) | Working | `services/jwt_validator.py` | `test_jwt_validator.py`, `test_security.py` | iss/aud enforced when present; strict aud next |
| RLS/tenancy | **Absent in live DB** | `supabase/schema.sql` | — | Migration `0001` drafted; apply to staging + test matrix next |
| Research projects | Not started | — | — | Phase P1 |
| Evals | Harness skeleton | `evals/` | deterministic citation checks | Full golden suite in `quality/ai-evals-and-ci` |
| Paper-to-code / monitoring | Not started | — | — | Phases P3, after sandbox review |
