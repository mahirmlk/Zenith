# Baseline Audit — Zenith (Phase 0, update.md §2)

Date: 2026-11-05 · Branch: `audit/baseline-and-threat-model` · Auditor: automated code audit (backend + frontend subagents, read-only) + direct file inspection.
Baseline tests (2026-11-05, `backend/`, Python 3.13): **34 passed, 7 failed** — see §7. No production data, secrets, or live Supabase/Firecrawl/PWC APIs were accessed; PWC liveness and live RLS behaviour remain unverified (flagged below).

> ARCHITECTURE.md is a design snapshot, not proof of behaviour. Every row below was checked in code.

## 1. Evidence table (backend, update.md §2/§5–§7)

| # | Feature | Evidence (file:line) | Observation | Gap | Severity | Planned PR |
|---|---|---|---|---|---|---|
|1|JWT alg/aud/iss/kid|`services/jwt_validator.py:82-115`|Any non-HS256 alg accepted as candidate; `verify_aud:False`, no iss/aud check; unknown `kid` fails without JWKS refetch (`invalidate_jwks_cache` has zero callers); HS256 fallback unrestricted|Cross-project token acceptance; rotation outage up to 1h|High|`security/auth-rls-and-tenancy` — allowlist, iss/aud-when-present, refetch-on-unknown-kid (this session)|
|2|Service-role usage|`services/supabase_client.py:6-11`, callers `routers/papers.py`, `prefs.py`, `firecrawl.py`, `ingestion.py`, `memory_agent.py`|Single `@lru_cache` client with service-role key for **all** queries; bypasses RLS; `papers.list_papers` has no user filter (global by design, but via privileged client)|One missing `.eq(user_id)` = cross-tenant leak|Critical|Same PR: user-scoped client for user tables; service-role only for ingestion/admin|
|3|RLS|`supabase/schema.sql:1-102`|Zero `ENABLE ROW LEVEL SECURITY`, zero policies, zero grants; `match_papers` has no tenant filter / `search_path`|Anon/authenticated PostgREST can read/write other users' `user_papers`/`user_prefs`|Critical|Same PR: `supabase/migrations/0001_*` (this session)|
|4|SSE launches work|`routers/stream.py:47,92`, `agents/orchestrator.py:96`|Every `GET /api/stream/{run_id}` creates `run_orchestrator()` task; disconnect cancels it (`finally: task.cancel()`); no replay, no `Last-Event-ID`|Reconnect = duplicate LLM spend; refresh = lost work|Critical|`infra/durable-runs-and-sse` — start-once + persisted events + replay (core in this session)|
|5|Run ownership (IDOR)|`services/run_store.py:12-18`, `routers/stream.py:85-92`, `routers/search.py:18`|RunState has no owner; stream checks only "some valid session"; search discards identity (`get_optional_user`)|Any authed user with a `run_id` streams another's results|Critical|With #4: store `user_id` on run, 404 on mismatch (this session)|
|6|Redis fallback|`services/run_store.py:98-110`, `middleware/rate_limit.py:9-17`|Redis ping failure → silent in-memory fallback for runs **and** rate limits; in-memory = per-process dict|Multi-instance loses runs/splits limits; outage invisible|High|Fail-closed in prod via `/api/health` + `/api/ready`; Postgres as canonical store (migration drafted)|
|7|Run persistence/idempotency|`services/run_store.py:59-153`, `routers/search.py:20`|Fresh UUID per POST, no idempotency key; Redis `create` overwrites blindly, `update` read-modify-write race, `cleanup` no-op, `created_at` string round-trip corrupts type; `_run_store_future` caches a **coroutine** → `RuntimeError: cannot reuse already awaited coroutine` (seen in baseline `test_search_papers`)|Double-click = double billing; no resume|High|Idempotency-Key support + proxy fix in this session; durable Postgres runs in migration|
|8|CORS/headers|`main.py:62-73`|`allow_methods/headers=["*"]`, credentials on, no security headers|Over-permissive surface|Medium|Explicit allowlists + headers middleware (follow-up PR)|
|9|Rate limiting|`middleware/rate_limit.py:11-46`, `config.py:26`|IP-only key; post-hoc decorator wrapping silently `except: pass`; no per-user quota, concurrency, or spend budget (only `MAX_SUMMARIES_PER_RUN=20`)|Wallet-drain via IP rotation|High|Composite user+IP keys + budgets (follow-up)|
|10|SSRF (Firecrawl)|`services/firecrawl.py`|Original baseline allowed arbitrary remote fetches. Current crawl entry points fail closed, `is_available()` is always false, and neither crawling nor legacy cache access is enabled; no in-app call sites are present.|Resolved for current runtime; re-open only if crawling is re-enabled without per-hop URL and egress controls.|High|Keep hosted crawl disabled until a controlled fetch boundary is implemented and verified (2026-11-15)|
|11|SSRF (PWC repos)|`services/papers_with_code.py:19-22`|Follows upstream `repositories` URL with httpx, no validation|Second-order SSRF|Medium|Host allowlist (github.com / paperswithcode.com) (this session)|
|12|Model registry|`services/llm_router.py:5-11,89-114`, `schemas.py:27,31`|Hardcoded map; arbitrary user `model_override` passed through; frontend list is a superset (drift)|Retired/expensive models; no pricing/retirement control|High|Registry + allowlist validation (this session)|
|13|PWC liveness|`services/papers_with_code.py:1-35`|Hardcoded `paperswithcode.com/api/v1`; all failures → `{"repos":[]}` silently, no logging/liveness|Dead integration invisible — **needs live probe before replacing** (§8.3)|Medium|Probe + replace only with confirmed service (blocked: no live API access in audit)|
|14|Embeddings|`services/embeddings.py:6-7`, `schema.sql:13`, `ingestion.py:66-69`|Model/dim never persisted; embed failure inserts `embedding=None` rows, never retried|Silent model-swap corruption; unsearchable rows|Medium|Version columns + backfill job (migration drafted)|
|15|Health/readiness|`routers/health.py:6-11` vs `docs/API.md:45-58`|Unconditional `{status:ok}`; API.md documents `checks:{supabase,openrouter}` that doesn't exist (test `test_health` fails on this)|LB routes to dead backends|Medium|Add `checks` + `/api/ready` (this session)|
|16|CI|`/.github/workflows/ci.yml:3-7`| `workflow_dispatch` only; no secret/SCA/migration/eval gates; mypy `ignore_errors` on auth/LLM modules|PRs merge ungated|High|Add `pull_request`/`push` triggers (this session); full gates in `quality/ai-evals-and-ci`|
|17|Error leakage|`routers/papers.py:30,60,77,94,122`, `prefs.py:37`, `stream.py:60`|Raw `str(e)` (DB errors) to client; no correlation ID; `ErrorResponse` schema unused|Info disclosure; undebuggable prod|High|Generic 500 + correlation_id, server-side logging (this session)|
|18|Observability|`services/observability.py:15-62`|Langfuse traces full prompts incl. crawled text + Mem0 interests; no redaction, no cost/token metrics|PII exfiltration to tracing vendor|Medium|Redaction + metrics (follow-up)|
|19|Anonymous search|`routers/search.py:15-22`|Optional auth → anonymous caller triggers full LLM pipeline (≤20 summaries × 4096 tok); contradicts `SECURITY.md:62` / `API.md:25`. Anonymous run can never be streamed (stream needs session token)|Unauthenticated cost exhaustion|Critical|Require auth in follow-up PR after frontend compat check; run now bound to creator when authed (this session records `user_id`)|
|20|Internal ingest|`routers/internal.py:19-37`|Static `ADMIN_API_KEY` with `!=`; in-process `BackgroundTasks` (lost on restart, racy dedup)|Duplicate ingestion; no audit|Medium|Durable queue job + `secrets.compare_digest` (follow-up)|
|21|Retry|`services/retry.py:50-74`|No jitter, no deadline/DLQ, name-fragment classification|Retry storms|Low|Jitter + deadline (follow-up)|
|22|Prompt injection|`agents/summary_agent.py:18-36`, `papers.py:102-105`|Delimiters + "treat as data" (good); but saved-paper titles written verbatim to Mem0, then embedded as interests; no structured-output/citation validation|Stored injection via paper title|Medium|Sanitize titles before Mem0; structured output (Phase P0-B)|
|23|Input validation|`models/schemas.py:25-49`|Unbounded `model`, `interests`; `q` ilike wildcards not escaped; extra fields silently ignored|Search abuse; oversized payloads|Low|`extra="forbid"` + caps (Phase P0-B)|
|24|Docs drift|`SECURITY.md:60`, `API.md:45-58`, `ARCHITECTURE.md:101`|HS256-only claim outdated; health `checks` unimplemented; old product name in `main.py:42` / `llm_router.py:28`|Operators trust wrong posture|Low|Docs pass per-PR + `docs/STATUS.md` (this session)|

## 2. Evidence table (frontend, update.md §5.2/§8/§14–§16)

| # | Feature | Evidence | Gap | Severity |
|---|---|---|---|---|
|F1|SSE auth|`lib/api.ts:170-186` JWT→`POST /api/stream/session`→`EventSource?token=`|Documented hybrid (good); token in query leaks to logs; no reconnect/replay/cancel|High|
|F2|API proxy|`app/api/[...path]/route.ts:27-58`|Blind header forwarding, buffers body (breaks SSE), no PATCH; appears dead — `lib/api.ts` calls `NEXT_PUBLIC_API_URL` directly|High|
|F3|Models|`ModelSelector.tsx:6-16`, `types/index.ts:38-47`, `useAppStore.ts:14`|Hardcoded in 3 places, no registry|Medium|
|F4|Projects pages|`app/**/page.tsx` glob|No `projects/`, library/research/compare/notes/implement pages|Medium (Phase P1)|
|F5|Frontend tests|`__tests__/` (3 files)|Only hooks/Skeleton/PaperCard; no api/auth/streaming/proxy/store tests|Medium|
|F6|Env leakage|Grep `NEXT_PUBLIC`|`NEXT_PUBLIC_API_URL` + Supabase anon key only (by design, RLS-dependent); no service-role in bundle|Low/Info|

## 3. Verified strong (do not regress)

JWKS `kid` + ES256 verification; SSE session-token exchange instead of bearer-in-EventSource; summary fan-out cap (`MAX_SUMMARIES_PER_RUN`); delimited untrusted paper content; internal ingest fails closed (503) when admin key unset (`internal.py:21-22`).

## 4. Undocumented / unimplemented (per §2)

`docs/API.md` health `checks`; `SECURITY.md` HS256-only claim; project/workspace APIs (§8/§15) entirely absent; `evals/` harness absent (§10); durable queue/checkpointer absent (§7); guardrail modules absent (§6).

## 5. Baseline test results (2026-11-05)

34 passed, 7 failed: `test_agents` ×2 (needs `OPENAI_API_KEY`), `test_health` (expects `checks`, code doesn't return it — fixed this session), `test_papers` ×3 (needs live Supabase), `test_search_papers` (`cannot reuse already awaited coroutine` — run_store proxy bug, fixed this session).

## 6. Branch/PR plan (update.md §19)

`audit/baseline-and-threat-model` (this PR) → `security/auth-rls-and-tenancy` → `infra/durable-runs-and-sse` → `security/guardrails-tool-policy` → `quality/ai-evals-and-ci` → `feature/research-workspaces` → … Remote branches retained after merge; never edit `main` directly.
