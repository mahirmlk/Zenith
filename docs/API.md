# API Reference

Base URL: `http://localhost:8000` in development, or the deployed backend URL.
FastAPI OpenAPI at `/docs` is the authoritative machine-readable contract.
This document describes current router behavior as of 2026-11-08; it does not
assert that migrations have been applied to a live database.

## Authentication

User routes require a Supabase access token:

```http
Authorization: Bearer <supabase-access-token>
```

The API validates Supabase JWTs (ES256 JWKS, or HS256 for configured legacy
projects). Service-role tokens are rejected as user sessions. Public routes
are `GET /`, `GET /api/health`, `GET /api/ready`, and `GET /api/models`.
`POST /api/auth/token` validates a supplied token. `/api/internal/ingest` uses
`X-Admin-Key` instead of a user JWT.

### `POST /api/auth/token`

Request body: `{"token":"<supabase-access-token>"}`. Returns
`{"valid":true,"user_id":"..."}` for a valid token or
`{"valid":false,"user_id":null}` for an invalid token. It does not establish
a browser session; callers still send the Supabase access token to protected
routes.

## Health and model registry

### `GET /api/health`

Unauthenticated liveness endpoint. Returns service identity and whether key
dependencies are configured; it does not prove that they are reachable.

### `GET /api/ready`

Unauthenticated readiness probe. Performs bounded Supabase and Redis
reachability checks. Returns `503` and `{"status":"not_ready", "checks": ...}`
when a required dependency is unavailable. Production requires both Supabase
and Redis. Development requires Supabase; Redis may be omitted for local
single-process use.

### `GET /api/models`

Returns the backend model registry as `{"models":[{"id":"...","agents":[...]}]}`.

## Papers and preferences

| Method and path | Auth | Behavior |
|---|---|---|
| `GET /api/papers` | Yes | List up to 50 papers; optional `q` title filter |
| `GET /api/papers/saved` | Yes | List papers saved by the caller |
| `GET /api/papers/{paper_id}` | Yes | Get paper details |
| `POST /api/papers/{paper_id}/save` | Yes | Save or dismiss using `{"dismissed":false}` |
| `DELETE /api/papers/{paper_id}/save` | Yes | Remove from caller's saved list |
| `GET /api/papers/{paper_id}/code` | Yes | Papers With Code repository lookup; empty result on upstream failure |
| `GET /api/prefs` | Yes | Read caller's preferences |
| `POST /api/prefs` | Yes | Update `preferred_model` and `interests` |
| `GET /api/graph/{paper_id}` | Yes | Get citation graph; returns an empty graph when provider lookup fails |

Paper responses use the `Paper` schema in `backend/models/schemas.py`.

## Search, runs, and streaming

### `POST /api/search`

Creates an authenticated research run and enqueues it for a worker. It does
not start work from the SSE handler.

```http
POST /api/search
Authorization: Bearer <token>
Idempotency-Key: <optional-client-key>
Content-Type: application/json
```

```json
{"query":"diffusion models for image generation","model":"anthropic/claude-sonnet-4-5"}
```

`query` is 1–500 characters; `model` is optional and must be in the backend
registry. Response: `{"run_id":"<uuid>"}`. Repeating the same key and
request returns the original run. Reusing the key for a different query/model
returns `409`. New runs consume the caller's daily search budget.

### `POST /api/stream/session`

Requires a user JWT. Returns a short-lived signed `session_token` for browser
`EventSource`, which cannot set an Authorization header. The token is verified
statelessly by each API replica using the backend-only service-role key.

### `GET /api/stream/{run_id}?token=<session_token>`

Read-only SSE subscription. Checks run ownership, replays stored events, then
streams new events. Each event carries a monotonically increasing per-run SSE
`id`; the frontend deduplicates replayed IDs. The SSE handler never starts a
worker. Events include `agent_step`, `result`, `error`, and `cancelled`.

### Run lifecycle endpoints

| Method and path | Auth | Behavior |
|---|---|---|
| `GET /api/runs/{run_id}` | Yes, owner only | Run status and result count |
| `GET /api/runs/{run_id}/events` | Yes, owner only | Stored sequenced events |
| `POST /api/runs/{run_id}/cancel` | Yes, owner only | Mark run terminally cancelled; suppress late result publication |

Missing, ownerless, and non-owned runs return `404` to avoid leaking their
existence. Redis Streams keeps jobs pending until acknowledged and workers
can reclaim idle pending entries. Run state is still Redis/process-memory
backed; Postgres `research_runs` and `run_events` are not yet wired into runtime.

## Retrieval and research

All routes below require a user JWT.

| Method and path | Behavior |
|---|---|
| `POST /api/retrieval/search` | Hybrid keyword ranking; optional `project_id` restricts results to papers attached to an accessible project |
| `POST /api/research/plan` | Deterministic task classification (`feed`, `explain`, `compare`, `deep_research`) |
| `POST /api/research/compare` | Comparison rows for retrieved papers; optional `project_id` is owner/member authorized and source-scoped |
| `POST /api/research/answer` | Extractive answer: returns exact matching sentences from retrieved abstracts with paper ID citations; abstains when no sentence matches |

Request body for these endpoints:

```json
{"query":"What method is used?","project_id":"<optional-project-uuid>"}
```

The answer endpoint currently performs keyword overlap selection. It is not
LLM synthesis, does not verify scientific claims, and does not provide
claim-level page/section spans.

## Projects, watchlists, and notifications

All routes below require a user JWT. Project reads support owners and members;
mutations apply endpoint-specific authorization.

| Method and path | Behavior |
|---|---|
| `POST /api/projects` | Create a project (`title`, optional `description`) |
| `GET /api/projects` | List caller-owned projects |
| `GET /api/projects/{project_id}` | Read an accessible project |
| `PATCH /api/projects/{project_id}` | Update project fields |
| `DELETE /api/projects/{project_id}` | Soft-delete project |
| `POST /api/projects/{project_id}/members` | Add/update a project member by user ID and role |
| `POST /api/projects/{project_id}/notes` | Add a note, optionally linked to a project source |
| `GET /api/projects/{project_id}/notes` | List project notes |
| `POST /api/watchlists` | Create a daily/weekly watchlist, optionally project-scoped |
| `GET /api/watchlists` | List caller's watchlists |
| `PATCH /api/watchlists/{watch_id}` | Update enabled state or cadence |
| `DELETE /api/watchlists/{watch_id}` | Delete watchlist |
| `GET /api/notifications` | List up to 50 caller notifications |
| `POST /api/notifications/read` | Mark caller notifications as read |

Ingestion creates schema-compatible notifications with database-backed
watchlist/paper deduplication. A recurring scheduler is not enabled by this
repository; operators must configure the Fly cron process or an external
scheduler.

## Implementation planning and account

| Method and path | Auth | Behavior |
|---|---|---|
| `GET /api/implementations/{paper_id}/plan` | Yes | Create a non-executing implementation checklist |
| `GET /api/implementations/{paper_id}/export` | Yes | Export the plan as Markdown |
| `POST /api/implementations/{paper_id}/run` | Yes | Currently returns `not attempted`; execution is not an available product workflow |
| `GET /api/account/export` | Yes | Export caller-scoped account data |
| `DELETE /api/account` | Yes | Delete caller account data |
| `POST /api/internal/ingest` | Admin key | Start ingestion background task |

Paper-to-code run execution is not implemented as a secure isolated workflow;
keep `SANDBOX_ENABLED=false`.

## Errors and rate limits

FastAPI validation failures return `422`; authentication failures return
`401`; inaccessible resources return `404`; rate limits return `429`; and
readiness failures return `503`. Error messages are intentionally generic.

Production rate limiting uses Redis and fails closed when required shared
infrastructure is unavailable. Default and endpoint-specific limits are
defined in `backend/middleware/rate_limit.py`; search also enforces a shared
per-user daily budget when Redis is enabled.
