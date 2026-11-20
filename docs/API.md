# API Reference

Base URL: `http://localhost:8000` in development, or the deployed backend URL.
FastAPI OpenAPI at `/docs` is the authoritative machine-readable contract.
This document describes current router behavior as of 2026-11-16; it does not
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

Returns `{"available":true,"default_model":"...","models":[{"id":"...","agents":[...]}]}` when the metered route is ready. The model list contains only entries with a verified pricing bound. Without OpenRouter, positive daily/monthly caps, service-role database access, or migration 0023, it returns `{"available":false,"default_model":null,"models":[]}`. `POST /api/search` returns `503` before enqueue if the meter readiness probe fails, and rejects a known but unpriced model with `422`.

## Papers and preferences

| Method and path | Auth | Behavior |
|---|---|---|
| `GET /api/papers` | Yes | List up to 50 papers; optional `q` title filter |
| `GET /api/papers/saved` | Yes | List papers saved by the caller |
| `GET /api/papers/{paper_id}` | Yes | Get paper details |
| `GET /api/papers/{paper_id}/public-evidence?query=...` | Yes | When `PUBLIC_PAPER_EVIDENCE_ENABLED=true`, returns up to five exact native-text page excerpts only for the stored latest arXiv version with exact CC BY 4.0 or CC0 1.0 rights; unsupported papers return `422`, stale version/identity returns `409`, and unapproved rights return `451` |
| `GET /api/papers/{paper_id}/status-watch` | Yes | Read caller's Crossref status-watch preference |
| `POST /api/papers/{paper_id}/status-watch` | Yes | Opt in to Crossref publication-update alerts; paper must have a valid DOI |
| `DELETE /api/papers/{paper_id}/status-watch` | Yes | Opt out of Crossref publication-update alerts |
| `POST /api/papers/{paper_id}/save` | Yes | Save or dismiss using `{"dismissed":false}` |
| `DELETE /api/papers/{paper_id}/save` | Yes | Remove from caller's saved list |
| `GET /api/papers/{paper_id}/code` | Yes | Bounded GitHub public repository search by paper DOI/arXiv identifier (title fallback when no strong identifier exists); rate-limited to 5 requests/minute per IP. Results are unverified candidates, and upstream failure returns an empty list with a source error |
| `GET /api/prefs` | Yes | Read caller's preferences |
| `POST /api/prefs` | Yes | Update `preferred_model` and `interests` |
| `GET /api/graph/{paper_id}` | Yes | Get citation graph; returns an empty graph when provider lookup fails |

Paper responses use the `Paper` schema in `backend/models/schemas.py`.
In addition to `summary_tldr`, they include `summary_status` (`generated`,
`abstract_preview`, or `unknown`) and nullable `summary_fallback_reason`
(`per_run_cap`, `spend_limit`, `billing_unavailable`,
`provider_unavailable`, or `invalid_output`). `generated` is set only after
provider usage/cost settlement and summary-output validation; historical rows
default to `unknown`. SSE search results use the same snake_case wire shape.
The frontend normalizes Paper payloads at the API boundary.

When available, Paper responses also include `doi` and Crossref publication
update provenance: `publication_update_type`, `publication_update_doi`,
`publication_update_label`, `publication_update_date`,
`publication_update_source`, `publication_update_deposit_source`, and
`publication_update_checked_at`. The source field identifies Crossref as the
metadata registry; the optional deposit-source field preserves the relation's
Crossref `source` when it is `publisher` or `retraction-watch`. Missing and
unrecognized deposit sources remain null. Update types
are limited to retraction, partial retraction, withdrawal, removal, and
expression of concern. The metadata comes from publisher/member-deposited
Crossref records, including Retraction Watch data; an empty Crossref relation
is not evidence that a paper has never been updated or retracted. Apply
migrations 0025 and 0029 before using the preference endpoints or status fields
in a deployed database.

Paper responses expose nullable `preprint_id` and `source_version` when the
record has verified arXiv provenance. Public evidence requires a supported ID
and positive stored version. It checks the current OAI `arXivRaw` version and
license before fetching that exact PDF from fixed arXiv hosts; redirects,
unknown/ambiguous licenses, unsupported IDs, and mismatched paper identity are
rejected. Only exact CC BY 4.0 and CC0 1.0 metadata is accepted. The response
contains source and license URLs, attribution, citation IDs, and page-local
text offsets. PDFs and excerpts are not persisted. OAI/PDF size and request
timeouts are bounded; the shared Redis gate serializes arXiv API requests with
three seconds between starts. Keep the feature disabled until the staging
checks in `docs/STATUS.md` pass.

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
{"query":"diffusion models for image generation","model":"anthropic/claude-sonnet-5.5"}
```

`query` is 1–500 characters; `model` is optional and must be in the backend
registry. Response: `{"run_id":"<uuid>"}`. Repeating the same key and
request returns the original run. Reusing the key for a different query/model
returns `409`. New runs consume the caller's daily search budget.

### `POST /api/stream/session`

Requires a user JWT. Returns a short-lived signed `session_token` for browser
streaming. The token is verified statelessly by each API replica using the
backend-only service-role key. Send it as a bearer credential to the stream
endpoint; do not put it in a URL.

### `GET /api/stream/{run_id}`

Requires `Authorization: Bearer <session_token>`. The optional `Last-Event-ID`
header is a nonnegative integer; the server replays only events with a larger
sequence. Missing cursor starts from the beginning. A malformed or negative
cursor returns `400`.

Read-only SSE subscription. Checks run ownership, replays stored events, then
streams new events. Each event carries a monotonically increasing per-run SSE
`id`; the frontend deduplicates replayed IDs. The SSE handler never starts a
worker. Events include `agent_step`, `result`, `error`, and `cancelled`.
Query-string tokens are not accepted. Browser clients must use a streaming
transport that can send the bearer header.

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
| `POST /api/research/plan` | Deterministic non-executing preview with typed steps and fixed tool/source/time/token bounds; project scope is membership-checked |
| `POST /api/research/execute` | When `RESEARCH_PLAN_EXECUTION_ENABLED=true`, queues a bounded durable plan on the existing research-run lifecycle and returns `202` with `run_id`; project membership is rechecked before reads |
| `POST /api/research/compare` | Heuristic paper rows plus separate project-PDF comparison fields with exact page citations; global requests stay PDF-free |
| `POST /api/research/answer` | Extractive answer: returns exact matching abstract sentences, and for project requests exact PDF page sentences with document/page citations; abstains when no sentence matches |
| `POST /api/research/evidence-map` | Bounded extractive evidence from a required accessible `project_id`; considers up to 10 attached papers and 10 uploaded documents/500 page rows, returning at most 5 combined exact spans |
| `GET /api/research/capabilities` | Returns enabled research UI capabilities for the authenticated user |
| `POST /api/research/synthesize` | Bounded provisional claims from up to six exact abstract sentences; project requests require membership and never include private PDF text in provider input |

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

The answer, evidence-map, and comparison endpoints perform keyword overlap
selection. For a project request, the answer checks up to 10 project
documents/500 page rows and returns at most five combined abstract/PDF claims;
without `project_id`, it remains abstract-only. Project comparisons preserve
their abstract-derived structured paper rows and include up to five separately
cited exact PDF page spans as source context. `pdf_comparisons` groups supported
problem/method/dataset/metric/limitation fields by uploaded document, each with
its exact sentence, page citation, and page-local offsets. These PDF rows remain
separate because project documents have no paper association. Unsupported fields
remain null. Global comparisons return an empty `pdf_comparisons` list and never
query project PDF tables.
Project-scoped general retrieval also ranks exact
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

`/api/research/synthesize` uses the same request shape and requires matching
sentences from at least two distinct papers. It selects at most six exact
abstract sentences with server-created `E1`-style evidence IDs, drafts no more
than five claims, and sends a second bounded provider request to review
supporting and contradicting sources. Responses include each claim's
`supported`, `conflicting`, or `uncertain` status and the exact evidence items
with paper ID, title, and half-open abstract offsets. Unknown evidence IDs are
rejected; single-source support and unsupported conflict labels are downgraded
to uncertain. These statuses are model-reviewed and provisional, not
independent scientific verification. At most 10 synthesis requests per user
per UTC day are allowed; production requires shared Redis. Provider requests
are limited to 900 output tokens and 20 seconds each. Uploaded PDF text is not
read by this route or sent to providers. Provider failure returns 503 and
malformed or fabricated-anchor output returns 502.
The route returns `404` while `RESEARCH_SYNTHESIS_ENABLED=false` (the default).
`GET /api/research/capabilities` returns
`{"research_synthesis_enabled":false}` so the frontend can hide the disabled
mode; API-side enforcement remains authoritative.

`POST /api/research/plan` returns the compatible `query`, `task_type`,
`max_tool_calls`, and `max_sources` fields plus proposed steps, source scope,
depth/time/model-call/output-token bounds, feature availability, and execution
metadata. A project-scoped preview verifies membership before responding and
does not read paper or PDF source rows. Public and project previews are
provider-free. `execution_available` is always false in the preview and the
displayed limits are explicitly preview-only. Executed search, synthesis,
plan synthesis, and embeddings reserve against daily/monthly per-subject caps
in integer USD micros. `estimated_cost_usd` remains null on a preview because
it does not make a provider request. When enabled, `/api/research/execute`
returns `202` and a `run_id`; the existing run event stream eventually carries
a terminal result. Project comparison terminal results include `pdf_comparisons`
grouped by uploaded document, with exact dimension sentences, page citations,
and offsets; these sources remain separate from paper rows.

### Provider spend configuration

Set positive integer `LLM_DAILY_SPEND_CAP_USD_MICROS` and
`LLM_MONTHLY_SPEND_CAP_USD_MICROS` values for each user and the shared
`system` subject used by ingestion/operator jobs. Both default to zero, which
disables metered calls. Chat routes only through OpenRouter and requires a
priced model in the dated catalog snapshot. Embeddings use OpenAI's direct
embedding API and settle from returned token usage and the dated official
price snapshot. Migration 0023 must be applied before models are exposed. Apply migration 0024 for the Paper summary provenance fields documented above.
Mem0 model-backed reads/writes remain disabled until
`MEM0_PROVIDER_SPEND_LIMIT_CONFIRMED=true`; account export distinguishes
withheld memories. OpenRouter credit-purchase fees are not part of per-request
inference usage and must be reconciled separately.

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
| `GET /api/projects/{project_id}/invitations` | List up to 100 project invitations (owner-only; does not expose delivery timestamps) |
| `POST /api/projects/{project_id}/invitations` | Invite an email address with `editor` or `viewer` role (owner-only; sends Auth email for new accounts, keeps existing-account invites pending for inbox acceptance) |
| `POST /api/projects/{project_id}/invitations/{invitation_id}/resend` | Resend a failed or expired invitation (owner-only) |
| `DELETE /api/projects/{project_id}/invitations/{invitation_id}` | Revoke a pending invitation (owner-only) |
| `GET /api/project-invitations/received` | List up to 50 non-expired invitations for the caller's current Auth-confirmed email; deleted-project invitations are omitted |
| `POST /api/project-invitations/{invitation_id}/accept` | Accept an invitation for the caller's verified matching email; atomically creates membership |
| `GET /api/projects/{project_id}/sources?limit=&offset=` | List attached papers with metadata (maximum 200 per page) |
| `POST /api/projects/{project_id}/sources` | Attach an existing paper (`paper_id`); duplicate attachments are idempotent |
| `DELETE /api/projects/{project_id}/sources/{source_id}` | Remove an attached paper |
| `POST /api/projects/{project_id}/documents` | Owner/editor uploads a PDF as multipart `file`; extracts bounded page text and discards original bytes |
| `GET /api/projects/{project_id}/documents` | List up to 100 uploaded PDF document records for an accessible project |
| `GET /api/projects/{project_id}/documents/{document_id}/pages` | Read extracted page text and stable `document_id:page:N` citation IDs |
| `POST /api/projects/{project_id}/notes` | Add a note, optionally linked to a project source |
| `GET /api/projects/{project_id}/notes` | List project notes |
| `GET /api/projects/{project_id}/annotations?limit=&offset=` | List up to 100 source-anchored annotations for an accessible project; each row includes `source_label` and `is_stale` |
| `POST /api/projects/{project_id}/annotations` | Create an annotation on an attached paper abstract or extracted PDF page; owner/editor only, exact quote and half-open character offsets are verified |
| `PATCH /api/projects/{project_id}/annotations/{annotation_id}` | Change annotation `content` only; owner/editor only |
| `DELETE /api/projects/{project_id}/annotations/{annotation_id}` | Delete an annotation; owner/editor only; returns `{"status":"ok"}` |
Direct authenticated PostgREST clients may read project annotations under RLS,
but table insert/update/delete privileges are revoked. Mutations must use these
API routes so source, quote, and actor checks run in the backend.
| `GET /api/saved-searches` | List up to 100 personal searches and searches from projects the caller can access |
| `POST /api/saved-searches` | Create a personal search, or a project search when owner/editor; accepts `name`, `query`, optional `model`, and optional immutable `project_id` |
| `GET /api/saved-searches/{saved_search_id}` | Read one personal or accessible project search |
| `PATCH /api/saved-searches/{saved_search_id}` | Update name/query/model; personal creator, or project creator/owner/editor while a current project member |
| `DELETE /api/saved-searches/{saved_search_id}` | Delete a saved configuration; personal creator, or project creator/owner/editor while a current project member |
| `POST /api/saved-searches/{saved_search_id}/run` | Start a new metered search run from the saved query; any current project member or personal creator |
| `GET /api/projects/{project_id}/briefs` | List versioned brief metadata for an accessible project |
| `POST /api/projects/{project_id}/briefs` | Create a user-authored brief and immutable version 1 atomically; owner/editor only; 20/minute |
| `GET /api/projects/{project_id}/briefs/{brief_id}` | Read brief metadata after project membership check |
| `GET /api/projects/{project_id}/briefs/{brief_id}/versions?limit=&offset=` | List immutable versions with their validated source snapshots |
| `POST /api/projects/{project_id}/briefs/{brief_id}/versions` | Append a new user-authored version; owner/editor only, 20/minute, requires `expected_current_version` (409 on conflict) |
| `POST /api/watchlists` | Create a daily/weekly topic, Semantic Scholar author/citation, or official Hugging Face benchmark watch, optionally project-scoped |
| `GET /api/watchlists` | List caller's watchlists |
| `PATCH /api/watchlists/{watch_id}` | Update enabled state or cadence |
| `DELETE /api/watchlists/{watch_id}` | Delete watchlist |
| `GET /api/notifications` | List up to 50 caller notifications, including optional linked `project_id`, watch `reason_text`, and project `project_relevance_text` |
| `POST /api/notifications/read` | Mark caller notifications as read |
| `POST /api/notifications/{notification_id}/read` | Mark one unread notification as read, scoped to the caller |

Annotation creation accepts one anchor shape: `paper_abstract` with
`paper_source_id`, or `pdf_page` with `document_id` and `page_number`. Both
payloads include `start_offset`, `end_offset`, `quote`, and `content`. Offsets
are zero-based Unicode character offsets into current source text, with
`end_offset` exclusive. The API rejects quotes unless the selected source
slice exactly matches. `quote_sha256` is computed server-side and anchor
fields stay immutable after creation. Project members may read; owners and
editors may write. Deleting an attached source or document cascades its
annotations. The stale flag means current source text no longer matches the
saved quote and fingerprint.

Saved searches retain configuration only (`name`, `query`, optional model, and
optional project scope); results are not persisted in the saved-search row.
Each explicit `run` creates a fresh idempotency key and uses the normal metered
search admission path. Watchlists remain separate recurring notifications.

Brief creation accepts `title`, `content`, and up to 50 source locators. New
versions accept `content`, `source_snapshot`, and `expected_current_version`.
Each locator identifies an attached paper abstract or a project PDF page with
zero-based, half-open Unicode offsets and an exact quote. The API normalizes
each locator with source identity and quote/source SHA-256 fingerprints, then
the atomic database RPC rechecks current project membership and that each exact
quote still matches the same project's current source. Briefs are manually
authored; no LLM generation or scientific validation is implied. Versions
cannot be edited or deleted through the API.

Ingestion creates schema-compatible notifications with database-backed
watchlist/paper deduplication. The backend starts a Redis-leased daily UTC
scheduler when Redis and Supabase are configured. Scheduled, Fly cron, and
admin-triggered ingestion must use the same lease path; see `docs/STATUS.md`
for current verification evidence and live-infrastructure limitations.
Crossref checks are separately opted in per paper and user, bounded to 100
watches per ingestion run with five concurrent lookups. Repeated delivery of
the same notice is idempotent per user; provider failures preserve the last
verified status and retry after a backoff. Alerts are in-app only.
Benchmark watches use `target_type: "benchmark"` and an exact public Hugging
Face dataset ID in `target_id` (`namespace/dataset`). The dataset must be
ungated and tagged `benchmark:official`. Zenith polls the fixed Hugging Face
dataset and leaderboard endpoints during daily ingestion, checks no more than
50 due benchmark watches per run with at most three concurrent requests, caps
each response at 2 MiB and snapshots at the 100 highest-ranked verified
entries. The first successful poll silently seeds the baseline. Later alerts
report newly observed verified entries or score/rank changes, with the old and
new values, leaderboard link, and Zenith observation time. Failed or malformed
responses do not advance the snapshot or last-checked cursor. Hugging Face does
not provide a change timestamp through this leaderboard response, and its
`verified` flag does not establish scientific validity. The monitored API is
documented in the [Hugging Face leaderboard guide](https://huggingface.co/docs/hub/leaderboard-data-guide).
Migration 0034 adds service-only per-watch snapshots and a constrained
`source_url` notification field; apply it before creating benchmark watches.
For project-linked watchlists, `project_relevance_text` is an optional lexical
hint based on shared title/abstract and project/source-title terms. It is
returned only while the watch owner still has project access and is not a
claim of scientific importance. The separate `reason_text` explains why the
paper matched the watch itself.

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
