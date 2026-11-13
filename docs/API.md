# API Reference

Base URL: `http://localhost:8000` in development, or the deployed backend URL.
FastAPI OpenAPI at `/docs` is the authoritative machine-readable contract.
This document describes current router behavior as of 2026-11-12; it does not
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
and Redis, a working Postgres run store, and a reachable LangGraph checkpoint
database. Production startup requires `DATABASE_URL` and initializes the
checkpointer schema. Development requires Supabase; Redis and `DATABASE_URL`
may be omitted for local single-process use.

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
existence. In production, Postgres `research_runs` and `run_events` are the
canonical run store; Redis Streams keeps jobs pending until acknowledged,
workers reclaim idle pending entries, and Redis holds short-lived run leases.
Local development uses an in-memory run store when Redis/Supabase are absent.
Production fails closed if the canonical schema/RPCs, Supabase, or Redis are
unavailable.

## Retrieval and research

All routes below require a user JWT.

| Method and path | Behavior |
|---|---|
| `POST /api/retrieval/search` | Hybrid keyword ranking; optional `project_id` restricts results to papers and uploaded PDF pages in an accessible project |
| `POST /api/research/plan` | Deterministic task classification (`feed`, `explain`, `compare`, `deep_research`) |
| `POST /api/research/compare` | Comparison rows for retrieved papers; optional `project_id` is owner/member authorized and source-scoped |
| `POST /api/research/answer` | Extractive answer: returns exact matching abstract sentences, and for project requests exact PDF page sentences with document/page citations; abstains when no sentence matches |
| `POST /api/research/evidence-map` | Bounded extractive evidence from a required accessible `project_id`; considers up to 10 attached papers and 10 uploaded documents/500 page rows, returning at most 5 combined exact spans |

Request body for these endpoints:

```json
{"query":"What method is used?","project_id":"<optional-project-uuid>"}
```

`/api/research/evidence-map` requires `project_id`. It returns `query`,
`project_id`, `source_ids`, `abstained`, an explanation, abstract `evidence`
entries with `paper_id`, `title`, exact `sentence`, and half-open character
offsets into the stored abstract, plus `pdf_evidence` entries with
`document_id`, `filename`, `page_number`, `citation_id`, exact `sentence`, and
page-local offsets. PDF citation IDs use `document_id:page:N`. The combined
response is capped at five evidence spans. It does not generate a cross-paper
synthesis. Outsiders receive `404` for inaccessible projects; only attached
papers and documents belonging to the accessible project are considered.

The answer and evidence-map endpoints perform keyword overlap selection. For a
project request, the answer checks up to 10 project documents/500 page rows and
returns at most five combined abstract/PDF claims; without `project_id`, it
remains abstract-only. Project-scoped general retrieval also ranks exact
matching PDF page sentences with attached-paper results, returns at most the
requested result limit, and gives each PDF result a stable
`document_id:page:N` citation and page-local offsets. It reads at most 10
documents/500 pages after project authorization. Public-corpus retrieval and
comparison still use paper metadata and abstracts only. These routes are not
LLM synthesis and do not verify scientific claims. PDF page offsets refer to
extracted page text, not byte positions in the original PDF.

Project-scoped search results discriminate `source_type: "paper"` and
`source_type: "pdf_page"`. PDF results include `citation_id`, `document_id`,
`filename`, `page_number`, an exact `snippet`, and half-open `start_offset` /
`end_offset` values into that page's extracted text. Result `id` equals the
stable page citation ID for PDF results. Paper rows expose only `id`, `title`,
and `abstract` as source fields; embedding vectors are never returned.

## Projects, watchlists, and notifications

All routes below require a user JWT. Project reads support owners and members;
mutations apply endpoint-specific authorization.

| Method and path | Behavior |
|---|---|
| `POST /api/projects` | Create a project (`title`, optional `description`) |
| `GET /api/projects` | List owned and shared projects for the caller |
| `GET /api/projects/{project_id}` | Read an accessible project and caller `current_role` (`owner`, `editor`, or `viewer`) |
| `PATCH /api/projects/{project_id}` | Update project fields |
| `DELETE /api/projects/{project_id}` | Soft-delete project |
| `GET /api/projects/{project_id}/members` | List members of an accessible project |
| `POST /api/projects/{project_id}/members` | Add/update an existing account by user UUID and role (owner-only) |
| `DELETE /api/projects/{project_id}/members/{member_user_id}` | Remove a member (owner-only) |
| `GET /api/projects/{project_id}/invitations` | List up to 100 project invitations (owner-only) |
| `POST /api/projects/{project_id}/invitations` | Invite an email address with `editor` or `viewer` role (owner-only; Auth Admin email delivery) |
| `POST /api/projects/{project_id}/invitations/{invitation_id}/resend` | Resend a failed or expired invitation (owner-only) |
| `DELETE /api/projects/{project_id}/invitations/{invitation_id}` | Revoke a pending invitation (owner-only) |
| `POST /api/project-invitations/{invitation_id}/accept` | Accept an invitation for the caller's verified matching email; atomically creates membership |
| `GET /api/projects/{project_id}/sources?limit=&offset=` | List attached papers with metadata (maximum 200 per page) |
| `POST /api/projects/{project_id}/sources` | Attach an existing paper (`paper_id`); duplicate attachments are idempotent |
| `DELETE /api/projects/{project_id}/sources/{source_id}` | Remove an attached paper |
| `POST /api/projects/{project_id}/documents` | Owner/editor uploads a PDF as multipart `file`; extracts bounded page text and discards original bytes |
| `GET /api/projects/{project_id}/documents` | List up to 100 uploaded PDF document records for an accessible project |
| `GET /api/projects/{project_id}/documents/{document_id}/pages` | Read extracted page text and stable `document_id:page:N` citation IDs |
| `POST /api/projects/{project_id}/notes` | Add a note, optionally linked to a project source |
| `GET /api/projects/{project_id}/notes` | List project notes |
| `POST /api/watchlists` | Create a daily/weekly watchlist, optionally project-scoped |
| `GET /api/watchlists` | List caller's watchlists |
| `PATCH /api/watchlists/{watch_id}` | Update enabled state or cadence |
| `DELETE /api/watchlists/{watch_id}` | Delete watchlist |
| `GET /api/notifications` | List up to 50 caller notifications, including optional linked `project_id` |
| `POST /api/notifications/read` | Mark caller notifications as read |
| `POST /api/notifications/{notification_id}/read` | Mark one unread notification as read, scoped to the caller |

Ingestion creates schema-compatible notifications with database-backed
watchlist/paper deduplication. The backend starts a Redis-leased daily UTC
scheduler when Redis and Supabase are configured. Scheduled, Fly cron, and
admin-triggered ingestion must use the same lease path; see `docs/STATUS.md`
for current verification evidence and live-infrastructure limitations.

PDF upload accepts `application/pdf` (or generic binary content type after
checking the PDF signature), up to 20 MiB and 500 pages. It extracts selectable
text per page with per-page and total character limits; encrypted or malformed
files are rejected. Scanned pages have no OCR. Extracted text is project-scoped
and available in the document viewer, project-scoped retrieval, evidence map,
and answer route. Public-corpus retrieval and comparisons remain paper-metadata/
abstract only. The original PDF bytes are not retained. Migration 0013 creates the document and page tables;
it must be applied in staging before using these routes against a deployed database.

Email invitations are stored separately from memberships. The service sends
through Supabase Auth Admin and grants no membership until the invitee follows
the email link, establishes a verified session, and accepts. Invitations expire
after one hour in the application. Only one active email invitation per address
is allowed across projects, so a newer invite cannot invalidate an earlier
Supabase confirmation token. Existing accounts should continue to be added by
user UUID. Configure the Supabase invite email template,
SMTP, the exact `APP_URL/projects/invitations/accept` redirect allowlist entry,
and a one-hour Auth email expiry in each environment. Existing accounts should
continue to be added by user UUID. Migration 0014 creates the invitation table
and service-role-only atomic acceptance RPC; live application and email delivery
remain unverified until staging checks pass.

## Implementation planning and account

| Method and path | Auth | Behavior |
|---|---|---|
| `GET /api/implementations/{paper_id}/plan` | Yes | Return a non-executing brief with exact abstract evidence, source offsets, gaps, and unverified repository candidates |
| `GET /api/implementations/{paper_id}/export` | Yes | Export the brief as Markdown |
| `POST /api/implementations/{paper_id}/run` | Yes | Returns `not attempted`; execution is unavailable |
| `GET /api/account/export` | Yes | Export caller-scoped account data |
| `DELETE /api/account` | Yes | Delete caller account data |
| `POST /api/internal/ingest` | Admin key | Start ingestion background task |

Paper-to-code run execution always refuses to execute, including if a stale
`SANDBOX_ENABLED=true` setting is present. The brief only has abstract-level
evidence; verify the full paper and candidate repositories manually.

## Errors and rate limits

FastAPI validation failures return `422`; authentication failures return
`401`; inaccessible resources return `404`; rate limits return `429`; and
readiness failures return `503`. Error messages are intentionally generic.

Production rate limiting uses Redis and fails closed when required shared
infrastructure is unavailable. Default and endpoint-specific limits are
defined in `backend/middleware/rate_limit.py`; search also enforces a shared
per-user daily budget when Redis is enabled.
