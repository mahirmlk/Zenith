# Data Handling

## Data locations

- Public paper metadata, abstracts, and citations are stored in Supabase Postgres. Public paper corpus records are shared across users. Legacy Firecrawl-derived text may remain in `crawled_content`; the current application does not read or write that table, and rows remain until their paper row is deleted or an explicit retention cleanup is applied.
- Saved-paper rows, preferences, watchlists, notifications, projects, memberships, notes, project sources, source-anchored annotations, personal/project saved searches, versioned project briefs, uploaded PDF metadata, and extracted PDF page text are stored in Postgres and scoped by user/project authorization. Original PDF bytes are discarded after extraction; there is no object-storage copy.
- Research run metadata and events are stored in Postgres in production. Redis carries queue run IDs, temporary run state/idempotency indexes, and worker leases. LangGraph checkpoints are stored in the configured Postgres checkpointer.
- When `MEM0_API_KEY` is configured, user profiles are stored in Mem0 Platform under the authenticated user's ID.
- Project PDF page text remains private project content under the document/page RLS policies in migration 0013. The current retrieval, answer, evidence-map, and comparison routes select exact spans locally; they do not send private page text to configured LLM providers.

### Uploaded PDF policy

Product decision (2026-11-14): Zenith discards uploaded PDF bytes after bounded local extraction and does not retain an object-storage copy. The upload is read for extraction, then the request file is closed; only filename/page metadata and extracted page text are persisted in project-scoped Postgres tables. Page rows cascade with their document and project. Account export includes the caller's permitted extracted page text, not the original PDF. This policy avoids retaining a user's source file; users must keep their own copy if they need the original document.

## Export

`GET /api/account/export` returns the authenticated user's saved-paper links and the public metadata for papers referenced by those links or by the caller's scoped project sources, plus preferences, memberships, owned and accessible project records/content, personal and accessible project saved searches, source-anchored annotations, versioned brief metadata and revisions, extracted PDF document/page records, watchlists, notifications, research runs/events, and Mem0 memories when configured. For owned projects it exports project document content and all brief versions; in shared projects it exports only documents uploaded and brief versions authored by the caller, while including accessible brief metadata and caller-created project searches. Original PDF bytes are unavailable because they are not retained. Mem0 export errors fail the request instead of silently omitting configured memory data. It does not export unrelated public-corpus rows or other users' records.

## Deletion

`DELETE /api/account` uses the subject from the verified JWT; it does not accept a target user ID. It writes or resumes a service-only durable deletion job and returns `202 Accepted` with a receipt. A leased worker cancels active runs, waits until worker leases release, then removes Mem0 memories, LangGraph checkpoints, queue/run state, run events, user rows, personal/caller-authored saved searches, project-owned content, caller-created annotations and brief versions in shared projects, and finally the same subject through Supabase Auth Admin. Briefs created by the caller are removed with their aggregate through the Auth foreign key; when a caller-authored version is deleted from another user's shared brief, a database trigger reconciles the remaining version head. Each cleanup step is recorded only after success so retries and process restarts resume safely. The job's subject UUID is not linked by an Auth cascade; the recovery row remains after Auth deletion and is pruned 30 days after completion.

An active worker lease causes the deletion worker to defer destructive cleanup and retry after the lease releases. While deletion is pending, the authenticated-user dependency blocks other sessions with `423 Locked` so they cannot recreate data during cleanup; a repeated `DELETE /api/account` returns the same job receipt. A completed job also blocks still-valid access-token JWTs until the marker is pruned. The UI signs the user out once the intent is accepted. Cross-service cleanup is not a distributed transaction; failures leave a durable retryable job and only a sanitized step error code. `202 Accepted` means cleanup was queued, not that every external store has finished. Staging failure/restart tests remain required.

Deleting the Supabase Auth user revokes refresh sessions. Already-issued access-token JWTs remain cryptographically valid until expiration, so completed deletion markers block their use during the 30-day audit retention window. No object-storage cleanup is needed because raw PDF bytes are not retained.

## Provider sharing and retention

Paper abstracts and research queries may be sent to configured LLM providers as part of research runs. Private project PDF page text is not sent by current routes. Do not send private full-text material unless its license and provider handling are approved. Langfuse and Sentry are optional; verify trace redaction and retention settings before enabling them for private project content.

Research run records, Redis run state, and LangGraph checkpoints use a one-hour TTL; checkpoint cleanup only removes terminal runs. Redis queue entries contain run IDs only and are removed for account deletion where available. Failed worker/Redis cleanup can leave IDs pending until a worker recovers them. Crawled paper text is cached by paper and follows the configured database retention policy; global public corpus data is not deleted when one account is removed.

Respect arXiv/Hugging Face source terms and do not republish restricted full text.
