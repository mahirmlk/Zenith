# Data Handling

## Data locations

- Public paper metadata, abstracts, citations, and crawled text are stored in Supabase Postgres. Public paper corpus records are shared across users.
- Saved-paper rows, preferences, watchlists, notifications, projects, memberships, notes, project sources, uploaded PDF metadata, and extracted PDF page text are stored in Postgres and scoped by user/project authorization. Original PDF bytes are discarded after extraction; there is no object-storage copy.
- Research run metadata and events are stored in Postgres in production. Redis carries queue run IDs, temporary run state/idempotency indexes, and worker leases. LangGraph checkpoints are stored in the configured Postgres checkpointer.
- When `MEM0_API_KEY` is configured, user profiles are stored in Mem0 Platform under the authenticated user's ID.
- Project PDF page text remains private project content under the document/page RLS policies in migration 0013. The current retrieval, answer, evidence-map, and comparison routes select exact spans locally; they do not send private page text to configured LLM providers.

## Export

`GET /api/account/export` returns the authenticated user's saved papers, preferences, memberships, owned and accessible project records/content, extracted PDF document/page records, watchlists, notifications, research runs/events, and Mem0 memories when configured. For owned projects it exports project document content; in shared projects it exports only documents uploaded by the caller. Original PDF bytes are unavailable because they are not retained. Mem0 export errors fail the request instead of silently omitting configured memory data. Public paper records and unrelated users' rows are not exported as private account data.

## Deletion

`DELETE /api/account` uses the subject from the verified JWT; it does not accept a target user ID. It removes scoped Postgres rows, project-owned content, research runs/events, queued run IDs, temporary Redis run/index/lease keys, and LangGraph checkpoint threads, then deletes the same subject through Supabase Auth Admin. Project PDF rows are removed through project/document and creator foreign-key cascades. If Mem0 is configured, its user memories are deleted before database cleanup; Mem0 errors return `502` and prevent reporting success.

An active worker lease causes the request to mark that run cancelled and return `409`; retry after the worker releases its lease. This avoids deleting a checkpoint while a worker is still writing to it. Cross-service cleanup is not a distributed transaction: an infrastructure failure can leave a partially completed deletion. The endpoint returns an error in that case so the caller can retry; operators should investigate persistent failures.

Deleting the Supabase Auth user revokes refresh sessions, but already-issued access-token JWTs remain cryptographically valid until their expiration because API JWT verification is stateless. Configure a short access-token lifetime for sensitive deployments or add session-revocation checks before claiming immediate access revocation. No object-storage cleanup is needed because raw PDF bytes are not retained.

## Provider sharing and retention

Paper abstracts and research queries may be sent to configured LLM providers as part of research runs. Private project PDF page text is not sent by current routes. Do not send private full-text material unless its license and provider handling are approved. Langfuse and Sentry are optional; verify trace redaction and retention settings before enabling them for private project content.

Research run records, Redis run state, and LangGraph checkpoints use a one-hour TTL; checkpoint cleanup only removes terminal runs. Redis queue entries contain run IDs only and are removed for account deletion where available. Failed worker/Redis cleanup can leave IDs pending until a worker recovers them. Crawled paper text is cached by paper and follows the configured database retention policy; global public corpus data is not deleted when one account is removed.

Respect arXiv/Hugging Face source terms and do not republish restricted full text.
