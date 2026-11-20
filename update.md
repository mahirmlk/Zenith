# ZENITH — CODEBASE UPDATE & PRODUCT EVOLUTION PLAN

> **Document type:** Implementation instructions for an AI coding agent / engineering team  
> **Target:** 2026–2027 product evolution  
> **Source baseline:** Repository layout and behaviors described in `ARCHITECTURE.md` (provided November 2026)  
> **Priority order:** Security and reliability → evaluations and evidence quality → research workspace → research-to-engineering workflows → integrations and scale  
> **Status:** Proposed changes; **not** an assertion that any implementation has already been completed.

---

## 0. Instructions to the implementation agent — read first

Your mission is to evolve **Zenith** from an AI academic-paper feed into a **secure, trustworthy AI Research Intelligence & Engineering Workspace**. Preserve working features; add research projects, verifiable synthesis, robust evaluations and guardrails, paper-to-code workflows, proactive monitoring, and a scalable foundation.

**Hard requirements:**

1. **Audit the real repository first.** `ARCHITECTURE.md` is a design snapshot, not verified proof of current code behavior. Inspect files, dependency manifests, DB migrations, tests, CI, env templates, deployment configs, and actual endpoints. Record discrepancies before editing.
2. **Work exclusively in dedicated feature branches.** Never implement features directly on `main`. Open and merge reviewed PRs. **Keep feature branches both locally (if useful) and on the remote after merging.** Do **not** auto-delete merged branches or enable a repository auto-delete setting for this project. Do not force-push shared branches.
3. **Preserve users and data.** Use additive, reversible migrations and explicit backfill/rollback plans. Do not overwrite production data, rewrite history, rotate live secrets, or run destructive migrations without human authorization.
4. **Security is enforced in trusted code**, not just in prompts, a guardrail model, or UI restrictions. Deny by default; authorize every tool invocation and every data access.
5. **Evals are required for every AI behavior change.** Establish an initial measured baseline before selecting thresholds. Add regression, adversarial, and human-review coverage. A passing unit-test suite alone is insufficient.
6. **Deliver vertical slices**, including backend, frontend, schema, migration, tests, telemetry, documentation, and operational runbooks in the same PR where applicable.
7. **Remove dead code and stale ('cold') references** after safe dependency analysis, tests, and review. Do not delete a compatibility path solely because a search does not find its name.
8. **Do not claim success without proof.** List real tests run, actual outcomes, CI links, migrations, known risks, and remaining tasks. If you cannot access a repo, credential, provider, or environment, report a blocker and leave the dependent change unverified.
9. **Use feature flags** for risky user-facing releases. Keep existing paper feed, saved papers, login, and graph working until replacements are shipped and validated.
10. **Prefer maintainable engineering to agent proliferation.** Use deterministic code where an LLM adds no value. Do not introduce new libraries/services without a documented reason, ongoing cost, and rollback strategy.

### Non-goals for the first releases

- Do not rebuild the application from scratch or swap the entire stack.
- Do not promise autonomous scientific correctness or experimentally verified reproduction based on LLM text alone.
- Do not run arbitrary paper-provided code, install unknown dependencies on the API server, or let an LLM execute shell/database commands with production credentials.
- Do not launch organization-wide agent integrations, billing, or shared projects before tenant isolation and permission tests pass.

---

## 1. Target product and success criteria

**Positioning:** **Zenith — AI Research Intelligence & Engineering Workspace**  
**Promise:** Discover relevant work, understand and compare evidence, build reproducible implementations, and monitor developments—while showing where claims come from and what has not been verified.

### Primary workflows

1. **Discover:** Paper feed, interest- and project-aware ranking, metadata, novelty and status signals.
2. **Understand:** Explain a paper with section/page-grounded citations, figures/tables where permitted, limitations, and context.
3. **Synthesize:** Answer questions across selected papers; compare methods, datasets, results, contradictions, and evidence strength.
4. **Organize:** Research projects with source libraries, notes, annotations, saved searches, versioned briefs, and export.
5. **Implement:** Map a paper to existing code/datasets, produce an implementation plan, then optionally validate in a separately secured sandbox.
6. **Monitor:** Watch topics or projects; ingest changes and deliver meaningful, opt-in updates rather than repeating a generic feed.
7. **Collaborate (later):** Share projects and findings with explicit roles and audited permissions.

### Product measures

- Task completion: research question answered with usable source citations; comparison produced; implementation plan delivered.
- Trust: verified citation rate, source support, calibrated uncertainty, user-reported issues and corrections.
- Experience: p50/p95 run time, success/retry rate, onboarding completion, useful saves and return usage.
- Engineering: cost per completed task, budget overruns, job recovery rate, uptime and security findings.

**Do not optimize for total agent count, papers summarized, or model-token volume.**

---

## 2. Baseline from the architecture document: audit before changing

The supplied `ARCHITECTURE.md` describes:

- Next.js 15 + TypeScript, Tailwind, React Query, Zustand, Three.js.
- FastAPI, Supabase Auth/JWT, Redis-backed run state/rate limiting, SSE.
- LangGraph with sequential `Research → Summary → Memory` nodes.
- arXiv, Hugging Face Daily Papers, Semantic Scholar, Papers With Code, Mem0, OpenRouter, and direct-model fallbacks; Firecrawl is disabled in the current runtime.
- Supabase tables `papers`, `user_papers`, `user_prefs`, `citations`, `crawled_content`; pgvector embeddings.
- Fly.io backend + scheduled ingestion; Vercel frontend; CI described as manual-dispatch.

**Architecture-level risks to verify in code:**

| Observed from document | Check in implementation | Intended correction |
|---|---|---|
| `GET /api/stream/{run_id}` launches `orchestrator_graph.ainvoke()` | Can reconnect/duplicate requests start work twice? | Worker starts once on enqueue; streaming subscribes to existing run |
| Browser `EventSource` opens an endpoint described as bearer-JWT protected | How is auth actually sent? | Authenticated fetch-based SSE or secure cookie/session pattern |
| Redis silently falls back to in-memory | Does production permit loss of jobs/rate-limit coordination? | Fail closed/degrade explicitly for critical infra; health/readiness separate |
| Service-role Supabase client exists | Does every query enforce tenant ownership? | RLS + restricted grants + explicit server authorization; minimize service role |
| `papers.embedding` is 1536-dim | Are embeddings versioned and reindexable? | Embedding provenance, namespace/version, safe backfills |
| Full-text crawl exists | Are original source spans, pages and licenses tracked? | Chunk provenance, evidence spans, parser version and rights metadata |
| LLM model IDs and provider fallbacks are hardcoded | Are IDs supported, priced, and allowed by policy? | Capability registry, controlled fallback, version pinning and retirement checks |
| Manual-only GitHub CI | Are PR changes independently gated? | Required automated CI checks and deploy gates |
| Single-user saved-paper schema | Are projects, memberships and isolated retrieval supported? | Project-scoped data model + tenant authorization tests |
| Paper repo integration points to Papers With Code | Is this service/API currently functioning? | Validate source; replace or supplement only with confirmed supported service |

Create `docs/audits/BASELINE_AUDIT.md` with an **evidence table**: feature, actual file/line or endpoint, test, observation, gap, severity, planned PR. Flag undocumented or unimplemented features; never infer implementation just from a folder name.

---

## 3. Git branches, PR discipline, and version-control rules

### 3.1 Required branch policy

- Protect `main`: no direct pushes, status checks required, approvals required for sensitive changes, no force push.
- Branch names (examples):
  - `audit/baseline-and-threat-model`
  - `security/auth-rls-and-tenancy`
  - `security/guardrails-tool-policy`
  - `infra/durable-runs-and-sse`
  - `quality/ai-evals-and-ci`
  - `feature/research-workspaces`
  - `feature/hybrid-retrieval-evidence`
  - `feature/deep-research-synthesis`
  - `feature/paper-to-code-sandbox`
  - `feature/topic-monitoring`
  - `maintenance/dead-code-and-docs`
- Always start each new branch from updated `main` after the prior PR merges, unless a documented dependency requires a stacked PR.
- Commit logically and use a PR per independently reviewable vertical slice. Prefer merge commits where branch history is useful; document the repo's chosen merge policy.
- **After merging: retain the remote branch** and do not delete it with `git branch -d`, `git push --delete`, or GitHub's “Delete branch” button. Turn off automatic branch deletion. Keeping branches is a project requirement; Git commit history and tags remain the authoritative history.
- Use version tags (e.g. `zenith-v0.2-security`, `zenith-v0.3-workspaces`) for meaningful releases.
- If branch count grows large, propose (do not execute) an archival/retention policy for explicit human approval.
- Never commit secrets, uploaded private PDFs, user memories, database exports, or raw production traces.

### 3.2 Workflow for every work item

```bash
# Inspect before use; never discard or stash another person's uncommitted changes.
git status --short
git fetch origin
git switch main
git pull --ff-only origin main
git switch -c security/example-task
# implement + test + document
git add <specific-files>
git commit -m "security: describe tested change"
git push -u origin security/example-task
# Open PR; request review; merge only after required checks.
# Do NOT delete the merged branch.
```

If the working tree is dirty, stop and ask for instructions rather than force-resetting. After merge, ensure `main` is updated and the feature branch still exists remotely. Never automatically merge your own security-critical changes if review is available.

### 3.3 PR template — mandatory sections

- Objective and problem statement; linked audit/issue ID.
- Before/after behavior and affected endpoints/files.
- Data migration: forward path, rollback, backfill, verification.
- Security impact and tenant boundary review.
- Tests and AI evals run, metrics versus baseline, adversarial cases.
- Feature flag, rollout plan, monitoring, rollback trigger.
- Updated docs, API schemas, diagrams, env templates, and removed stale references.
- Screenshots or UX evidence if frontend changed.
- Reviewer sign-off and unresolved risks.

**Definition of Done:** code + tests + evals + documentation + observability + threat review (where applicable) + PR merged + remote branch retained + outdated references cleaned + no critical regressions.

---

## 4. Target architecture: evolve, do not rewrite

```text
Next.js Web App
  ├── Discovery feed / Paper detail / Citation graph (preserve)
  ├── Research projects / Library / Evidence viewer / Compare / Chat
  ├── Implementation workspace / Monitoring / Settings / Audit UI
  └── Authenticated API + streaming client
             │
FastAPI API / Policy Enforcement
  ├── Authn + Authz + membership + quotas + tool permissions
  ├── Projects, sources, search, notes, runs, evaluations, monitoring APIs
  ├── Durable task creation + read-only run status/events SSE
  └── Input/output validation + guardrails + structured auditing
             │
Job Queue + Worker(s) + Durable LangGraph Checkpoints
  ├── Deterministic ingestion / parsing / dedupe / enrichment
  ├── Research planner (conditional; only for complex tasks)
  ├── Retrieval → evidence collection → synthesis → verification
  ├── Paper-to-code planner → explicit approval → isolated runner
  └── Background monitoring + alerts
             │
Data & Services
  ├── Supabase Postgres + pgvector + RLS + migrations
  ├── Object storage (PDFs / permitted extracts / artifacts)
  ├── Redis (queue / cache / rate limiting; not source of truth)
  ├── Persistent LangGraph checkpointer (Postgres or supported durable store)
  ├── Provider connectors (arXiv / HF / OpenAlex / Crossref / S2 / code)
  ├── Versioned model registry + LLM gateway + embeddings
  └── Langfuse / Sentry / metrics / eval datasets / security audit trail
```

**Important separation:** Paper ingestion is data processing; evidence retrieval is retrieval; multi-step research may be agentic; ranking can be deterministic/model-assisted. Do not force all operations through a single LangGraph LLM agent.

---

## 5. Phase P0-A — Security baseline and threat model (first)

### 5.1 Inventory trust boundaries

Map: public client → FastAPI → DB/object store → Redis/queue → LLM providers → external paper pages/PDFs → future GitHub/MCP tools → sandbox runner. Document data classification, data retention, access paths, and external transfer of prompts/documents.

Add:

- `docs/security/THREAT_MODEL.md` (assets, actors, STRIDE/abuse cases, mitigations, residual risk).
- `docs/security/SECURITY_BASELINE.md` (controls, owners, evidence, testing cadence).
- `docs/security/INCIDENT_RESPONSE.md` (detect, contain, rotate, revoke, notify, recover).
- `docs/security/DATA_HANDLING.md` (content rights, consent, deletion, retention, provider sharing).
- `docs/security/SECURITY_TEST_PLAN.md` (penetration checks and regression cases).

### 5.2 Authentication, sessions and authorization

Inspect `backend/services/jwt_validator.py`, `backend/dependencies.py`, `backend/main.py`, all routers, `frontend/lib/auth.ts`, and Supabase clients.

- Verify JWT signature, `iss`, `aud`, `exp`, `nbf` (when present), accepted algorithms, JWKS `kid` selection and rotation. Reject `alg=none`, unsupported token types, expired/incorrect-audience tokens. Restrict legacy HS256 to environments/projects that actually require it; do not silently downgrade.
- Separate auth **identity** from auth **permission**: enforce resource ownership and project membership in every endpoint and worker task; never trust `user_id`, project ID, or role supplied in a JSON body.
- Choose **one documented** browser streaming auth design. If cookie-based, set Secure/HttpOnly/SameSite and CSRF defenses for state changes. If fetch-based streaming, attach bearer auth; do not assume native `EventSource` accepts Authorization headers.
- Make `run_id` unguessable and always check requester ownership/membership for status, stream, result, cancellation, and artifacts.
- Add session logout/revocation behavior where supported, avoid sensitive tokens in URLs and local logs.
- Give scheduled ingestion a scoped machine identity or securely managed admin secret; use secret rotation and dedicated rate limits. Never expose internal ingestion routes to the browser.

### 5.3 Database isolation and Supabase

Audit current `supabase/schema.sql`, live migration history, and `backend/services/supabase_client.py`.

- Add **versioned migrations** under `supabase/migrations/`; do not rely on a mutable `schema.sql` as the only schema history.
- Enable RLS on each user-/project-scoped table, with least-privilege SQL grants. Test `SELECT`, `INSERT`, `UPDATE`, `DELETE` for owner/member/outsider/anonymous contexts; include RPC and object storage policies.
- Use server-side checks even when RLS exists. A Supabase **service-role key bypasses RLS**; limit its use to explicitly privileged operations and strictly enforce tenant scopes in that path. Never ship the key via `NEXT_PUBLIC_*` or client bundles.
- For project sharing, use one canonical membership model (`owner`, `editor`, `viewer`); create policy tests for role changes, revoked membership, deleted projects, and forged cross-tenant IDs.
- Validate `match_papers()` and other `SECURITY DEFINER` functions for authorization, safe `search_path`, and intended global versus private data visibility. Avoid leaking document titles/snippets through vector queries.
- Encrypt data in transit, use provider-managed at-rest encryption, restrict backups, and set retention/deletion policies for uploaded PDFs, memories, prompts, traces, embeddings and artifacts.
- Add deletion/export endpoints that cover records in Postgres, storage, caches, queues and Mem0; document any unavoidable retention exceptions.

### 5.4 API and infrastructure hardening

- Restrict production CORS to exact configured origins; validate allowed headers and credentials settings.
- Enforce per-user and per-IP rate limits, concurrency limits, input lengths, upload quotas, maximum papers/chunks/tokens, timeouts, and **daily/monthly spend budgets**.
- Return stable error codes with correlation IDs, no stack traces or secrets to clients.
- Use Pydantic request/response models; reject unknown dangerous fields and validate IDs/URLs/enums. Use parameterized queries; never put LLM-generated strings into raw SQL or shell commands.
- Add security headers, strict content rendering/sanitization (including Markdown), CSRF protection where relevant, safe redirects, and dependency audits.
- Secrets from environment/secret manager only; secret scanning in CI, redaction in logs/traces, rotation procedure, minimal provider scopes.
- Isolate workers from public network access where possible; give API, workers and sandbox **different** service identities and least privileges.
- Dependency pinning/lockfiles, SBOM generation, SCA scanning, container scans, non-root containers, and regular patching.
- Prevent SSRF in Firecrawl/import paths and any URL-fetch feature: permit only approved protocols, block private/loopback/link-local/metadata addresses after DNS resolution and across redirects, bound downloads/redirects, and enforce egress restrictions. Block decompression bombs and malicious files.
- For PDF ingestion: validate type with content inspection, enforce size/page limits, malware scan or quarantine before processing, isolate parser processes, and respect source licenses/robots/access terms.

### 5.5 Security release gates

- No known **critical/high exploitable** findings in changed paths; documented exceptions require explicit human risk acceptance.
- Cross-user project, run, memory, artifact and vector-search access tests must show **zero unauthorized reads/writes**.
- All sensitive tool calls require server authorization; destructive/external write actions need explicit, fresh user approval.
- Threat-model changes and security tests must be included in the PR.

Reference frameworks: **OWASP ASVS 5.0**, **OWASP GenAI LLM Top 10 (2026)**, **OWASP Agentic Applications Top 10 (2026)**, **OWASP Agent Control Standard**, and **NIST AI RMF / GenAI Profile**. Map the implemented controls to relevant requirements instead of claiming blanket compliance.

---

## 6. Phase P0-B — Guardrails and agent/tool safety

**Goal:** Guardrails prevent unauthorized behavior, privacy breaches and misleading claims, without pretending a content filter makes the system secure.

### 6.1 Central policy layer

Introduce clear modules (adjust names to existing repository conventions):

```text
backend/
  security/
    authorization.py       # resource + membership + tool permission checks
    policies.py            # permitted actions, risk tiers, model/provider policy
    input_validation.py    # typed input constraints, URL restrictions
    prompt_injection.py    # detection/annotation; never sole defense
    output_validation.py   # schema, citations, rendering safety
    audit.py               # privacy-safe records of security decisions
  guardrails/
    pipeline.py            # entry, tool-call, and output enforcement
    action_approval.py     # verified user confirmations
```

Use rule-based policy enforcement in trusted Python for actual permissions. Optional model-based classifiers can flag suspicious content for further review; they are not authorization authorities.

### 6.2 Required guardrail checkpoints

1. **Before retrieval:** Validate user/project authorization, query and upload limits, and scope selection.
2. **On imported data:** Treat PDF text, metadata, HTML, GitHub README, OCR, external search snippets, and tool results as **untrusted data**. Keep source boundaries and provenance.
3. **Before each tool call:** Validate permitted tool, arguments, network domain, accessible tenant resources, read/write scope, spend budget, and user approval for high-risk actions.
4. **Before model context assembly:** Exclude inaccessible private content; minimize PII/secrets; never use retrieved text to grant permissions.
5. **After model output:** Validate structured output against Pydantic/JSON schemas, check citation IDs and source spans, sanitize rendered Markdown/HTML, label uncertainty and unknowns.
6. **Before external writes/execution:** Show exact intended effect and require a trusted-UI approval; scope tokens to that action; log outcome.

### 6.3 Defend specifically against

- Direct and indirect prompt injection (including instructions hidden in papers or tool descriptions).
- Retrieval poisoning, malicious/incorrect citations, forged publication claims and retracted work.
- Cross-tenant data leakage through search, summaries, cached results, embeddings and memories.
- Exfiltration to attacker URLs via tools, prompts, code execution or connector actions.
- Runaway loops, repeated API calls, token explosion, excessive tool permissions and budget abuse.
- Unsafe rendering, code injection, secrets in traces, unsupported claims and fabricated references.
- Tool-output schema tampering, MCP tool poisoning/rug pulls and cross-server privilege escalation (when MCP is added).

### 6.4 Approval and autonomy policy

| Action | Default | Authorization |
|---|---|---|
| Read public paper metadata | Allowed with quotas | User/session + source policy |
| Search private project library | Allowed only in authorized project | Server membership check |
| Generate comparison/implementation plan | Allowed with budgets | Project permission |
| Add annotations or modify private project | Scoped write | Editor/owner permission |
| Connect GitHub/Drive or MCP server | Disabled until consent | OAuth scopes + reviewed connector |
| Push GitHub commit, publish, send, or share externally | Off by default | Fresh explicit approval per action |
| Execute untrusted repository/notebook code | Off by default | Approved sandbox job with strict isolation |
| Delete project/data or change team roles | Sensitive | Re-auth/confirmation + audited permission |

**Never:** rely on an LLM saying “approved”; the approval must be recorded and checked by backend code.

---

## 7. Phase P0-C — Durable runs, SSE, observability, reliability

Inspect `backend/routers/search.py`, `stream.py`, `services/run_store.py`, `agents/orchestrator.py`, `services/retry.py`, Redis configuration, and frontend `StreamingResponse`.

### 7.1 Correct the execution lifecycle

```text
POST /api/research/runs {project_id, query, idempotency_key}
  → authenticate + authorize + check quota
  → create persistent queued run (one unique run per idempotency scope)
  → enqueue exactly one worker task; return 202 + run_id

Worker:
  → acquire lease / concurrency slot
  → load persisted LangGraph checkpoint/state
  → run bounded workflow and persist checkpoints + event sequence
  → write final result + status even if browser is disconnected

GET /api/research/runs/{id}
  → authorize → return status, progress, result reference, error class

GET /api/research/runs/{id}/events
  → authorize → subscribe/replay stored events; DOES NOT start work

POST /api/research/runs/{id}/cancel
  → authorize → request cooperative cancellation; record final status
```

- Retain old `/api/search` and `/api/stream/{run_id}` through a tested compatibility adapter until frontend rollout is complete; then deprecate through a documented timetable.
- Use a supported queue (`arq`, Dramatiq, Celery, or equivalent) chosen after deployment review. Redis may support delivery; Postgres retains canonical run metadata/results.
- Configure durable LangGraph checkpointer and stable `thread_id=run_id` or equivalent; checkpoint before/after side effects. Persist event sequence IDs for reconnect/replay (`Last-Event-ID` or cursor).
- Define state machine: `queued → running → succeeded|failed|cancelled|timed_out`, with safe retry transitions and audit timestamps.
- Use idempotency on ingestion, summarization, writes and external actions. A retried node must not duplicate chargeable requests, commits or notifications unless explicitly safe.
- Support worker heartbeat, lease expiry, retry with jitter and bounded attempts, dead-letter handling, timeout/deadline, cancellation, queue depth alarms.
- In production, **do not silently fail over to process memory** for essential run state or distributed rate limiting. Surface degraded readiness and fail safely.

### 7.2 Telemetry and SLOs

- Keep Langfuse + Sentry; add metrics, structured event schemas, trace IDs, queue latency, tool error rate, model/provider/cost/token telemetry, and alerting.
- Redact prompts/documents or use explicit opt-in for sensitive traces; restrict tracing dashboards by role; apply retention limits.
- Set baseline SLOs after measuring p50/p95, error rate, time-to-first-event, queue delay, recovery, and cost per successful task.
- Provide user-visible progress without leaking private filenames, external credentials, or internal prompts.

**Acceptance tests:** reconnect produces one run and replayed events; refresh does not cancel a job; worker restart resumes safely; unauthorized run ID is inaccessible; cancellation stops pending tool actions; queue outage does not create phantom success.

---

## 8. Phase P1 — Research projects, ingestion, retrieval and provenance

### 8.1 Workspace feature

Frontend additions (adapt folder conventions after inspection):

```text
frontend/app/projects/page.tsx
frontend/app/projects/[id]/page.tsx
frontend/app/projects/[id]/library/page.tsx
frontend/app/projects/[id]/research/page.tsx
frontend/app/projects/[id]/compare/page.tsx
frontend/app/projects/[id]/notes/page.tsx
frontend/components/research/{SourceViewer,EvidenceCitation,ComparisonTable,RunTimeline}.tsx
```

Backend routers/services:

```text
backend/routers/{projects,sources,research,notes,comparisons}.py
backend/services/{document_parser,retrieval,reranker,evidence_store,source_registry}.py
```

Minimum functionality: create project, add papers/upload legally held sources, remove a source, search within project, save notes, launch research, see evidence spans, export Markdown/BibTeX/CSV, and delete a project safely.

### 8.2 Data model (add through migrations)

**Suggested normalized tables:**

- `projects(id, owner_id, title, description, created_at, updated_at, deleted_at)`
- `project_members(project_id, user_id, role, joined_at)` (P2 collaboration; use schema/policies before sharing is enabled)
- `project_sources(id, project_id, paper_id nullable, object_key nullable, source_type, visibility, license, created_by, status)`
- `paper_identifiers(paper_id, namespace, external_id)` for DOI/arXiv/OpenAlex/Semantic Scholar canonicalization
- `document_versions(id, source_id, checksum, parser_version, content_license, ingested_at)`
- `paper_chunks(id, document_version_id, chunk_index, text, page_start, page_end, section, offsets, embedding, embedding_model, created_at)`
- `evidence_claims(id, run_id, claim_text, evidence_status, verification_method, created_at)`
- `evidence_links(claim_id, chunk_id, page_or_span, relation, confidence)`
- `research_runs(id, user_id, project_id, request_hash, idempotency_key, status, phase, model_config, cost, timestamps)`
- `run_events(id, run_id, sequence, kind, safe_payload, created_at)`
- `notes(id, project_id, created_by, source_id nullable, content, created_at, updated_at)`
- `research_artifacts(id, project_id, run_id, kind, storage_key, provenance, created_at)`
- `watchlists(id, user_id, project_id nullable, query, cadence, last_checked_at, enabled)`
- `audit_events(id, actor_id, resource_id, action, outcome, timestamp, redacted_metadata)`
- `evaluation_runs(id, suite_version, git_sha, model_config, metrics, artifact_key, created_at)`

Use FK constraints, uniqueness, useful composite indexes, project ownership constraints, pagination and retention. Do **not** automatically make all `papers` private: distinguish globally public metadata from project-owned uploaded content. Avoid duplicating full-text content needlessly.

### 8.3 Better ingestion and search

- Add OpenAlex/Crossref metadata and identifiers, retaining arXiv/HF/Semantic Scholar. Check live API licensing/limits and deployment permissions before enabling.
- Validate code-repository lookup; replace unsupported Papers With Code endpoints with a maintained source or verified GitHub/metadata search. Mark repository links as **unverified** until matched by evidence.
- Parse content by sections/pages, not only title+abstract; preserve exact source references and parser/version lineage. Prefer published source/PDF APIs over arbitrary HTML scraping when possible.
- Deduplicate by canonical identifiers plus title/author/date similarity with a manual ambiguity path; track corrections, withdrawn/retracted papers, preprint versus published versions.
- Use hybrid BM25/full-text + pgvector search, metadata filters (date, venue, domain, code, document type) and controlled reranking; avoid cross-project leakage from vector indexes.
- Version embedding configurations and provide re-embed/backfill procedures. Cache results by content version + model/prompt version + visibility scope.
- Implement incremental ingestion with retries and provider-specific quotas; do not rerun the entire corpus on each user search.

### 8.4 Evidence model

Every externally verifiable research answer should expose:

- The specific document/version, title, URL/DOI where available, author/date metadata.
- Citation anchor to a page, section, paragraph, or exact chunk span.
- Claim-to-source link (`supports`, `contradicts`, `mentions`, `not verified`).
- Clear distinction between **paper authors' claims**, **Zenith's synthesis**, and **independently reproduced results**.
- Transparent errors: no source, inaccessible source, partial parsing, possible retraction, conflicting evidence.

Never generate real-looking citation identifiers for sources that are not in the retrieved evidence set.

---

## 9. Phase P2 — Deep research and cross-paper synthesis

### 9.1 Workflow design

Replace the single hardwired `Research → Summary → Memory` path with **conditional task routing** while preserving the existing path for basic feed searches.

```text
Request + project + permissions
  → classify task (deterministic routing where possible)
  ├─ Feed lookup: discover → rank → present
  ├─ Paper explanation: retrieve exact document → explain → evidence check
  ├─ Comparison: retrieve N papers → structured extraction → compare → verify
  └─ Deep research: plan → retrieve → inspect gaps → bounded iteration
                  → synthesis → claim/source verification → result
```

- Introduce typed intermediate outputs: `ResearchPlan`, `SourceCandidate`, `EvidenceItem`, `Claim`, `ComparisonRow`, `ResearchAnswer`, `Citation`.
- Planner only for multi-step tasks; bounded loop by tool calls, depth, wall-clock time and spend. Distinguish no-data from task failure.
- Separate retrieval, extraction, verification, and narrative generation. Reuse evidence store; do not repeatedly summarize the same unchanged chunk.
- Cross-paper table: problem, methods, training/data, assumptions, metrics, baselines, compute, limitations, reported results, replication/code status, source citations.
- Contradiction handling: surface conflicting findings and domain differences instead of averaging incompatible results.
- Before output, validate every citation against retrieved anchors and verify that the cited span supports the specific claim; unsupported claims become flagged or removed.
- Display a confidence/quality **explanation**, not a fabricated numeric probability. Clearly flag unverified secondary sources.
- Add human feedback: citation incorrect, paper irrelevant, explanation wrong, helpful, report abuse; feed reports into curated eval datasets after review.

### 9.2 Memory and personalization redesign

- Keep Mem0 as **optional user preference memory**, not the source of authorization, factual truth, or private source access.
- Distinguish explicit interests, inferred interests, current project goals, saved/dismissed papers and recent interactions; permit inspecting, editing and forgetting inferred preferences.
- Project-scoped ranking + user profile + negative feedback + diversity/novelty; maintain query relevance so personalization does not override user intent.
- Avoid storing sensitive uploaded text, secrets, or whole conversations in memory by default.
- Remove redundant LLM calls for ranking where embeddings/deterministic scores suffice.

---

## 10. Phase P0/P2 — AI evaluation program (mandatory, incremental)

**Implement the eval harness in P0 before major prompt/workflow changes; expand suites as each new feature lands.** Evals must be reproducible, versioned, and tied to PR/commit and model settings.

### 10.1 Proposed repository layout

```text
evals/
  README.md
  datasets/
    discovery_v1.jsonl
    retrieval_v1.jsonl
    grounded_qa_v1.jsonl
    cross_paper_comparison_v1.jsonl
    abstention_v1.jsonl
    security_redteam_v1.jsonl
    paper_to_code_v1.jsonl
  rubrics/
    citation_support.md
    factuality.md
    comparison_completeness.md
    plan_quality.md
  runners/
    run_evals.py
    model_judges.py
    citation_checks.py
  reports/                 # sanitized artifacts; avoid committing secrets
backend/tests/
  unit/
  integration/
  security/
  contracts/
frontend/tests/
```

### 10.2 Required eval layers

| Layer | Examples | When |
|---|---|---|
| Deterministic unit/contract | Schemas, parser, auth, citation IDs, run state, costs | Every PR |
| Retrieval evaluation | Recall@k, nDCG@k, MRR, correct scope/filter, metadata consistency | Retrieval/data changes |
| Grounded answer evaluation | Claim support, citation precision, unsupported claim rate, correct abstention | Every LLM/prompt/workflow change |
| Research comparison evaluation | Correct extraction, missing baselines, contradiction recognition | Comparison changes |
| Agent execution evaluation | Task success, correct tool use, max steps, recovery, bounded cost | Orchestration changes |
| Safety/security red team | Prompt injection, data exfiltration, role escalation, secret leaks, malicious PDF/GitHub | Every guardrail/tool/security change |
| Operational evaluation | p95 time, spend/run, retry, resume, failure rate | Pre-release and staging |
| Human review | Blinded domain-expert review of factuality/usefulness | Sampled releases and periodic audits |

Use deterministic checks first; model-as-judge can assist nuanced grading but requires a **documented rubric, calibration against human labels, and awareness of judge bias**.

### 10.3 Dataset and methodology

- Start with curated, redistribution-safe public papers and synthetic private-tenant fixtures. Include ground-truth spans, expected source IDs and clear answerability labels.
- Include easy/hard, broad/narrow, contradiction, no-answer, outdated/retracted, metadata mismatch, very long papers, missing PDF, multilingual where supported, and malicious embedded instructions.
- Split development/test/holdout; prevent evaluated answers or holdout data from leaking into prompts or ranking tuning.
- Pin corpus snapshots, chunker, embedding version, retrieval config, prompt version, provider/model ID, parameters and evaluation code commit.
- Record cost and latency per case; rerun representative baseline under the same conditions for meaningful comparisons.
- Keep user production data **out** of eval exports unless explicit permission, minimization and retention controls exist.

**Example JSONL case (illustrative schema; implement and validate your own version):**

```json
{"id":"qa_no_evidence_001","task":"grounded_qa","project_fixture":"public_demo","question":"What does an unavailable paper conclusively prove?","expected":{"must_abstain":true,"allowed_source_ids":[]},"tags":["no_answer","hallucination"]}
```

### 10.4 Release gates and proposed targets

Establish measured baseline first. **The numbers below are proposed starting gates, not existing project performance or guarantees.** Adjust with human review, task risk and data quality.

- **Must-pass:** zero successful cross-tenant reads/writes; zero unauthorized high-risk tool actions; no known critical/high security regression.
- **Must-pass:** outputs referencing fake/unretrieved citation IDs = **0** in deterministic citation-ID tests.
- **Must-pass:** bounded agent budgets, cancellations and retries in deterministic chaos tests.
- **Initial quality targets:** ≥ 95% structurally valid answers; ≥ 90% supported cited claims on labeled QA set; ≥ 90% correct abstention on explicit no-answer cases. Recalibrate to a stricter release target once benchmark quality is proven.
- **Regression gate:** no statistically/operationally meaningful degradation in evidence support, authorization safety, or retrieval quality relative to last released baseline; any accepted exception must have written rationale.
- **Performance:** define per-tier p95 latency and cost ceilings based on real staging measurements; fail builds only for controlled comparable test conditions.

In PR CI, run fast deterministic/smoke evals. Run a bounded full golden suite on release candidates or a controlled cadence. Security tests should not depend solely on a nondeterministic judge score.

### 10.5 Eval observability

Attach `git_sha`, `prompt_version`, model/provider, index version, dataset version and per-run token/cost traces to evaluation reports. Add a protected `/admin/evals` view later if needed; no ordinary users or public API may browse test data containing sensitive payloads.

---

## 11. Phase P3 — Paper-to-code and reproducibility, safely

**Start with a non-executing implementation assistant.** Only add actual execution after security review and sandbox isolation.

1. Extract architecture, dependencies, datasets, metrics, training/evaluation steps and likely compute requirements from paper **with source citations**.
2. Find candidate repositories via verified links/GitHub search and show verification status; do not assume an arbitrary matching repository is official.
3. Generate implementation checklist, suggested project structure, compatibility notes, model/data card, and reproducibility gaps.
4. Export a plan or a **proposed** code patch to a user-owned workspace; provide diffs before changes.
5. Optional later: isolated disposable runner with no production secrets, network egress allowlist/off by default, read-only input mounts, CPU/GPU/time/memory/disk caps, no privileged Docker, syscall restrictions, non-root identity and artifact scanning.
6. Require explicit approval for cloning external code into a runner and for any GitHub write action; use minimum repo scopes, no automatic push/merge/publish.
7. Clearly report `not attempted`, `plan generated`, `tests passed`, `failed`, and `reproduced result` as separate states. An LLM plan is not experimental reproduction.
8. Capture environment, dependency lock, dataset version/license, hardware, command, outputs and test logs as a reproducibility artifact.

Candidate modules:

```text
backend/agents/implementation_planner.py
backend/services/repository_verifier.py
backend/services/sandbox_runner.py    # introduce only when sandbox infrastructure exists
backend/routers/implementations.py
frontend/app/projects/[id]/implement/page.tsx
```

---

## 12. Phase P3 — Watchlists, proactive monitoring and notifications

- Let users watch a topic/project/author/citation neighborhood with explicit cadence (daily or weekly), timezone and notification preference.
- Use scheduled durable jobs, incremental source cursors, dedupe, relevance threshold and delivery idempotency; no perpetual unbounded LLM polling.
- Explain **why** a new paper/change matters to the project; avoid resurfacing unchanged results.
- Add in-app notifications first; email/other channels only after consent, unsubscribe controls, bounce handling and anti-spam checks.
- Watch for new relevant papers, changes to existing preprint versions, retraction/withdrawal flags, new benchmark/results when supported by sources.
- Enforce user-level budgets and opt-out. Add monitoring-specific evals for precision and missed important updates.

---

## 13. Phase P4 — Collaboration, MCP and integrations (after controls are ready)

- Shared projects: invite, revoke, viewer/editor/owner roles; project-specific permissions and audit log.
- GitHub: read-only repository metadata first; write permissions just-in-time and human-approved.
- Zotero: reference import/export; avoid unnecessary full-account scopes.
- Google Drive: explicit file selection, per-document authorization and ingestion permissions; handle access revocation.
- Jupyter: export notebooks and reproducible environment manifests before offering remote execution.
- MCP: introduce a **trusted connector registry** and allowlist, signed/reviewed tool definitions where possible, per-server isolated credentials, strict schemas and egress constraints; detect changed definitions, log every call and require fresh consent for expanded scopes.
- A2A or external-agent collaboration only if a documented real use case needs it, with identity delegation, trust boundaries, rate limits, data minimization and protocol versioning.

Do not make arbitrary user-provided MCP servers generally executable by default.

---

## 14. File-by-file change map

The following paths are **candidates from the architecture**. Verify actual locations before modifying or adding files.

| Existing file/area | Intended update |
|---|---|
| `backend/main.py` | Auth/security middleware, routers, readiness endpoint, safe error handling |
| `backend/dependencies.py` | Typed principal, project permission dependencies, service identities |
| `backend/services/jwt_validator.py` | Correct JWT verification and issuer/audience/algorithm tests |
| `backend/routers/search.py` | Create durable idempotent runs; compatibility API |
| `backend/routers/stream.py` | Authenticated replay-only event stream; never launch orchestration |
| `backend/services/run_store.py` | Canonical run metadata persistence; worker state/lease/event storage |
| `backend/agents/orchestrator.py` | Conditional workflow routing, checkpoints, bounded tools and budgets |
| `backend/agents/research_agent.py` | Multi-source discovery and structured retrieval results |
| `backend/agents/summary_agent.py` | Evidence-grounded structured extraction, source-span validation |
| `backend/agents/memory_agent.py` | Project-aware opt-in preference scoring; no auth decisions |
| `backend/services/llm_router.py` | Model capability registry, privacy/cost policy, verified fallbacks |
| `backend/services/embeddings.py` | Versioned embeddings, batch caching, tenant-aware search |
| `backend/services/ingestion.py` | Incremental jobs, metadata versions, parsing, provenance and idempotency |
| `backend/services/firecrawl.py` | Hosted fetch and legacy cache access fail closed until redirect and egress controls exist |
| `backend/services/semantic_scholar.py` | Citation metadata validation, rate-limit handling, missing-data states |
| `backend/services/github_repositories.py`, `backend/routers/paper_code.py` | Search public GitHub repo metadata by paper identifiers; preserve unverified-candidate labeling |
| `backend/services/supabase_client.py` | Scope privileged client usage; authorization-safe queries |
| `backend/services/observability.py` | Traces, privacy redaction, metrics and eval tags |
| `frontend/lib/api.ts` | Typed API contracts, idempotency headers, auth-aware streaming |
| `frontend/components/StreamingResponse.tsx` | Reconnect, replay, cancel, accurate run statuses |
| `frontend/components/ModelSelector.tsx` | Dynamic supported-model registry; no hard-coded retired choices |
| `frontend/app/feed/*`, `paper/[id]/*` | Preserve current flows; add 'add to project' and evidence links |
| `frontend/app/graph/*` | Keep accessible as optional view; improve performance/accessibility |
| `supabase/schema.sql` | Keep as generated/reference snapshot; use migrations as source of truth |
| `.github/workflows/ci.yml` | Automatic PR checks, tests, scans, eval smoke, migration verification |
| `.github/workflows/daily_fetch.yml` | Reliable scheduler/invocation semantics; no duplicate jobs |
| `docs/API.md` | New/modified endpoints, auth, SSE event contract, error responses |
| `docs/DEVELOPER_GUIDE.md` | Local queue, tests, eval commands, branch and security process |
| `docs/DEPLOYMENT.md` | Workers, migrations, secrets, failover, rollback, restores and monitoring |
| `PLAN.md`, `ARCHITECTURE.md`, `README.md` | Align new product positioning, diagrams, actual behavior and phased status |

Avoid circular imports and duplicated business logic between agents and routers; keep policies and data-access utilities centralized.

---

## 15. APIs, contracts, and migration compatibility

**Proposed new endpoints** (final naming to be consistent with existing FastAPI conventions):

```text
POST   /api/projects
GET    /api/projects
GET    /api/projects/{project_id}
PATCH  /api/projects/{project_id}
DELETE /api/projects/{project_id}
POST   /api/projects/{project_id}/sources
GET    /api/projects/{project_id}/sources
DELETE /api/projects/{project_id}/sources/{source_id}
POST   /api/research/runs
GET    /api/research/runs/{run_id}
GET    /api/research/runs/{run_id}/events
POST   /api/research/runs/{run_id}/cancel
GET    /api/research/runs/{run_id}/artifacts
POST   /api/projects/{project_id}/comparisons
GET    /api/projects/{project_id}/notes
POST   /api/projects/{project_id}/notes
POST   /api/watchlists
GET    /api/watchlists
PATCH  /api/watchlists/{watch_id}
DELETE /api/watchlists/{watch_id}
```

- Define request/response schemas and publish OpenAPI. Generate TS client types if practical; add contract tests to prevent drift.
- Enforce pagination and resource caps on list/search routes. Avoid leaking resources through different error wording.
- Keep old endpoints working behind an adapter during migration, log deprecated usage safely, publish removal dates, then remove routes and references only after the compatibility window and tests.
- Store structured API errors and stable SSE event versions (`queued`, `step`, `source`, `partial`, `result`, `warning`, `error`, `heartbeat`) with monotonic event IDs. Never send fabricated success after downstream failure.

---

## 16. CI/CD, environments and operational discipline

### Required automated pull-request jobs

1. Format and lint Python/TS; type-check and frontend build.
2. Unit and integration tests with hermetic test DB/Redis; mocks for paid APIs.
3. Migration up/down or safe rollback review, schema drift and RLS policy tests.
4. Authn/authz, SSE reconnect, run idempotence and quota/security negative tests.
5. Secret scan, dependency/SBOM/container scan and checked lockfiles.
6. AI eval smoke suite (fixed datasets/config) with baseline comparison and artifacts.
7. License/copyright checks for bundled corpora and source attribution.
8. Static links/stale-doc references check and API schema diff.

**Optional scheduled/release jobs:** full end-to-end evals, red-team suite, larger performance tests, dependency updates and restore drills.

### Environments

- Separate dev/staging/prod Supabase projects/credentials/queues and model budgets. Never use production user content as ad hoc staging fixtures.
- Test additive schema migration against anonymized/reduced staging data; verify row counts, FK integrity, RLS and query plans.
- Roll out worker and schema changes in compatible order; support old/new clients during transition.
- Use feature flags and incremental rollout, observe error/budget/eval metrics, and maintain a written rollback procedure.
- Back up and **test restoring** database and object storage; test worker crash, provider outage, queue outage, rate limiting and network failure.
- Define `GET /api/health` for liveness and separate readiness for essential dependencies. Do not mask important failures behind an unconditional 200.

---

## 17. Dead code, cold/stale references and technical-debt cleanup

**This cleanup is required during every phase and in one dedicated final maintenance PR.** A “cold reference” means an outdated mention, link, identifier or configuration entry that no longer matches the functioning code/product.

### 17.1 Inventory first

Search for:

- Old project names: `AI Paper Research Agent`, `ai-paper-research-agent`, outdated marketing copy, URLs, screenshot text, package metadata, repo descriptions.
- Retired model IDs, stale OpenRouter/direct provider fallbacks, unused environment variables, unsupported integrations, stale API endpoints.
- Duplicate clients, unused imports, unreachable agent branches, obsolete prompts, superseded state stores and dead feature flags.
- References to deleted/moved files, old schema names, old diagrams, outdated architecture claims and broken internal/external links.
- Old scheduled workflows, duplicated cron definitions, stale Docker images/services, obsolete frontend components and unused dependencies.
- Tests/fixtures that encode obsolete behavior and README setup instructions that cannot run.

Suggested starting commands (not proof of dead code by themselves):

```bash
rg -n 'AI Paper Research Agent|ai-paper-research-agent|Papers With Code|gpt-4o|gemini-2.0|/api/stream|TODO|FIXME' .
rg -n 'deprecated|legacy|unused|fallback|experimental' backend frontend docs .github
# Then inspect import graphs, runtime routes, dynamic imports, migrations, API clients,
# scheduled jobs, stored user references, external integrations and test coverage.
```

Do not include private env files in scan output or commits. Confirm tool availability (`rg` etc.) first; use platform equivalents if missing.

### 17.2 Safe removal procedure

1. Identify candidate + all direct, dynamic, reflection, external client, DB, deployment and scheduled references.
2. Classify as **remove now / deprecate / keep compatibility / uncertain**; document decision.
3. Add/adjust tests and deprecation notices before removing externally referenced endpoints or persistent data.
4. Remove code, dependencies, env keys, tests, assets, prompts, flags, configs and docs **together**. Do not remove migrations needed to reconstruct existing installations.
5. Search again for old symbols and dead links; run full CI, eval smoke and security tests.
6. Update generated client types, OpenAPI, diagrams, examples, screenshots, environment template and deployment docs.
7. Report exactly what was removed and why, plus alternatives/compatibility impact.

**Never delete historical migrations, legal attribution, audit records, a public API, or persisted user data as 'dead' without separate review and a migration/retention plan.**

---

## 18. Documentation must evolve with implementation

Every merged PR must update affected docs, not defer all documentation until the end.

### Required files and responsibilities

| File | Requirement |
|---|---|
| `README.md` | Accurate product, quickstart, supported workflows, status, screenshots and links |
| `ARCHITECTURE.md` | Actual component topology, new data/control paths, security boundaries, queue/workers and runtime states |
| `PLAN.md` | Phase roadmap with completed/in-progress/not-started labels and dependencies |
| `update.md` | Keep this document as the change plan; check off implemented items with PR links/SHAs |
| `docs/API.md` | Complete current public API, auth, SSE, sample errors and deprecations |
| `docs/DEVELOPER_GUIDE.md` | Commands for local stack, migrations, tests, evals and branching |
| `docs/DEPLOYMENT.md` | Deployment order, secrets, workers, rollbacks, recovery and monitoring |
| `docs/EVALUATIONS.md` | Dataset sources, run commands, rubrics, baseline, gates, limitations |
| `docs/GUARDRAILS.md` | Inputs, tool policy, approvals, outputs, failures, adversarial tests |
| `docs/security/*` | Threat model, RLS, incident response, data handling and audit evidence |
| `docs/DECISIONS/ADR-*.md` | Nontrivial architecture decisions and rejected alternatives |
| `CHANGELOG.md` | User-visible changes, fixed security issues without exploitable specifics, deprecations |

Document the **implemented** state separately from the desired future state. Include a small `docs/STATUS.md` matrix with feature, state, source code, tests, limitations and next PR. Avoid claiming a feature is production-ready before it is verified.

---

## 19. Ordered delivery plan and PR acceptance

| Order | Suggested branch | Deliverable | Non-negotiable acceptance |
|---|---|---|---|
| 0 | `audit/baseline-and-threat-model` | Repo audit, documented threat model, baseline tests/evals, updated plan | Evidence-backed findings and current baseline recorded |
| 1 | `security/auth-rls-and-tenancy` | JWT/auth hardening, RLS/grants, resource scoping, security test matrix | No cross-tenant access in negative tests; old features still work |
| 2 | `infra/durable-runs-and-sse` | Queue workers, checkpoints, idempotency, stream replay, cancel | Refresh/reconnect/restart do not duplicate or lose work |
| 3 | `security/guardrails-tool-policy` | Central policy enforcement, trusted approvals, logging, upload/SSRF hardening | Injection cannot authorize privileged action; sensitive data isolated |
| 4 | `quality/ai-evals-and-ci` | Versioned eval suite, PR CI, metrics/gates, smoke red team | Reproducible eval baseline and enforced release gates |
| 5 | `feature/research-workspaces` | Project CRUD, library, notes, scoped storage | RLS + API/UX tests + lifecycle/delete tests |
| 6 | `feature/hybrid-retrieval-evidence` | Multi-source ingestion, chunk provenance, hybrid search | Grounded citations, source scope, retrieval eval quality |
| 7 | `feature/deep-research-synthesis` | Planning, cross-paper comparison, verification | Claim-level citations, abstention and comparison eval gates |
| 8 | `feature/paper-to-code-sandbox` | Plan/export first; isolated execution only after separate review | No production access from untrusted code; reproducible artifacts |
| 9 | `feature/topic-monitoring` | Watchlists, schedules, in-app alerts | Duplicate prevention, consent, delivery and quality tests |
| 10 | `feature/collaboration-integrations` | Shared roles, scoped external connectors | Strict tenant permissions and per-tool approvals |
| 11 | `maintenance/dead-code-and-docs` | Dead-code cleanup, stale references, status/docs audit | Full CI, eval smoke, links and compatibility checks pass |

**Dependency note:** Rows 1–4 are intertwined. Implement a minimal eval harness and automated checks as early as the audit/first security PR; the dedicated quality PR completes the program. Do not wait for row 4 to start security testing.

### PR-level exit checklist

- [ ] Actual repository state reviewed before editing; change matches issue scope.
- [ ] Feature branch created from updated `main`; no direct main changes.
- [ ] Backwards compatibility and relevant migrations planned/tested.
- [ ] Security: auth, tenant boundaries, permissions, threat cases, secrets reviewed.
- [ ] Unit, integration, contract and regression tests pass.
- [ ] Applicable AI quality, safety, red-team and cost evals run and compared.
- [ ] Telemetry, errors, quotas, feature flag and rollback are covered.
- [ ] README/architecture/API/developer/deployment/security/eval docs updated as relevant.
- [ ] Dead code, obsolete dependencies and cold references safely removed.
- [ ] PR reviewed and merged; **remote branch retained** after merge.
- [ ] `docs/STATUS.md`, `PLAN.md`, `CHANGELOG.md` and this `update.md` updated with actual completion evidence.

---

## 20. Final agent report format (required after each PR)

```text
PR title and link:
Branch name (confirm retained after merge):
Base/merge commits:
Scope delivered:
Files added/changed/removed:
Migrations/backfills and rollback:
Security checks and results:
Evals run, dataset versions, metrics and deltas:
Unit/integration/E2E checks and results:
Docs and references updated:
Operational/deployment changes:
Known limitations, blocked items and follow-up tasks:
```

At the end of the full program, produce a final architecture diagram matching the **actual** code, a completed versus pending capability matrix, recorded security/eval baselines, and a cleanup report. Do not hide incomplete deliverables.

---

## 21. Useful authoritative references

- OWASP **Top 10 for LLM Applications (2026)**: https://genai.owasp.org/resource/owasp-genai-llm-top-10-2026/
- OWASP **Top 10 for Agentic Applications (2026)**: https://genai.owasp.org/resource/owasp-top-10-for-agentic-applications-for-2026/
- OWASP **Agentic Security Initiative / Agent Control Standard**: https://genai.owasp.org/initiatives/agentic-security-initiative/
- OWASP **Application Security Verification Standard 5.0**: https://asvs.owasp.org/
- OWASP **MCP Security Cheat Sheet**: https://cheatsheetseries.owasp.org/cheatsheets/MCP_Security_Cheat_Sheet.html
- Supabase **Row Level Security**: https://supabase.com/docs/guides/database/postgres/row-level-security
- LangGraph **Persistence**: https://docs.langchain.com/oss/python/langgraph/persistence
- NIST **AI RMF / Generative AI Profile**: https://www.nist.gov/publications/artificial-intelligence-risk-management-framework-generative-artificial-intelligence

**Implementation caveat:** Check the latest vendor documentation, API behavior, model IDs, service availability, and library versions **at implementation time**. This document is a practical target plan, not a substitute for inspecting the repository or testing deployed infrastructure.

---

## 22. First instruction to execute

**Begin with phase 0, not a large unreviewed rewrite:** inspect the repository, make a branch `audit/baseline-and-threat-model`, produce a file-by-file audit and threat model, establish baseline test/eval results, identify the highest-risk authorization and SSE/job issues, open a PR, merge only with passing checks, **retain the merged branch**, then advance through the phases. For every subsequent branch, make code, tests, migrations, documentation and safe cleanup part of the same reviewed deliverable.

---

## 24. Shipment-readiness re-audit (2026-11-08)

The current tree on `codex/shipment-readiness` was checked against this plan and the runtime code. **Status: not production-ready.** The exact current capability matrix and release blockers are in [docs/STATUS.md](docs/STATUS.md).

Since the prior audit, production runs/events now use Supabase Postgres as the canonical store through atomic service-role RPCs (migration 0008); production readiness checks those RPCs and schema. Redis remains the job-delivery, budget, and lease layer. Daily watchlist polling and API/Fly/manual ingestion triggers use one shared Redis lease, with local retry, overlap, and lease-loss cancellation coverage. Migration 0009 adds direct authenticated project-role RLS policies. Research retrieval now filters common query terms, checks relevant entities and substantive evidence overlap, and drops instruction-like abstract sentences. The deterministic production-code eval has 12 hand-authored cases.

This follow-up adds a managed async Postgres LangGraph checkpointer, makes production fail closed without `DATABASE_URL`, resumes pending work from the latest node checkpoint, reuses completed state if a worker dies before run finalization, and rejects checkpoint/run identity mismatches. Strict msgpack deserialization is enabled before LangGraph imports. Readiness probes the actual checkpoint connection, and retention deletes expired checkpoints only for terminal runs before deleting their run records. Development keeps an in-memory saver when `DATABASE_URL` is omitted. A node interrupted mid-call may repeat external calls on recovery; provider-side idempotency and crash behavior still require staging validation.

The prior backend suite passed (153 passed, 6 skipped in 17.12 seconds), Ruff and diff checks passed, and strict mypy passed across 70 application source files with `tests/` and `scripts/` excluded; CI now blocks on mypy. The eval passed 12/12 cases, with all reported metrics at 1.000 and the fabricated-citation negative control passing. Frontend lint, typecheck, 18 tests, and production build passed on the current tree after pinning Next.js tracing to the frontend project. Docker build, remote CI, live/staging migration and RLS verification, checkpoint restart/retention verification, backup restore, provider integration, and deployment remain unverified. No live database or deployment was changed.

---

## 23. Implementation addendum (2026-11-05, verified by re-audit)

Honest status — **not everything in this document is implemented yet.** See [docs/STATUS.md](docs/STATUS.md) for the live matrix.

- [x] §2/P0 audit + threat model (`audit/baseline-and-threat-model`, `c172cfd`)
- [x] §5 JWT allowlist/iss-aud, SSRF, model registry, RLS migrations 0001–0002 (drafted, **not applied to live DB**), generic errors, health/ready (`security/auth-rls-and-tenancy`, `1abdf87`)
- [x] §7 start-once SSE + replay + run ownership + idempotency (`infra/durable-runs-and-sse`, `a8b0aa1`); run status/events/cancel endpoints added
- [x] §6 guardrails policy layer (`backend/security/`, `backend/guardrails/`, `test_guardrails.py`)
- [x] §8 projects API (CRUD + notes) + `/projects` page; §10 eval smoke harness in CI; §18 docs (GUARDRAILS/EVALUATIONS/CHANGELOG/STATUS)
- [~] §7 Redis queue/worker, Postgres-canonical run/event store, and durable LangGraph checkpoints implemented; live cross-process replay and retention validation remain open.
- [~] §8 hybrid retrieval and extractive selection implemented; broader claim-level evaluation remains open. §9 has a bounded project-scoped extractive evidence map, but deep research planning, synthesis, and claim verification remain incomplete. §13 collaboration/MCP remains incomplete. §11 has an evidence-backed implementation brief and Markdown export, but is not a reproduction workflow; repository associations are unverified and execution remains disabled. §12 daily watchlist scheduler is implemented but live operation is unverified.
- [~] PR: draft [PR #3](https://github.com/mahirmlk/Zenith/pull/3) exists, and earlier revisions of `codex/shipment-readiness` were pushed. At the current 2026-11-12 local re-audit, the branch is ten commits ahead of its tracked remote (`0` behind, `10` ahead); the latest member roster, notification, RLS, PDF, answer, and eval updates are local and have not been pushed. A previous push attempt was rejected by automatic approval review as sensitive egress. Do not describe the current HEAD as pushed or merged. PR #3 aggregates 36 earlier commits / 105 files and still needs review of scope/PR organization and the remaining staging gates.

### §11 follow-up — evidence-backed implementation brief (2026-11-08)

- [x] Extract implementation facts from exact abstract sentences with source offsets and paper IDs; model-generated summaries are not treated as evidence.
- [x] Add an authenticated paper implementation page and Markdown export with source evidence, explicit missing-detail gaps, candidate repository labeling, and no execution control.
- [x] Fail closed in the sandbox runner regardless of `SANDBOX_ENABLED`; arbitrary execution remains unavailable pending a separate isolation review.
- [x] Backend targeted tests: 9 passed. Full backend suite: 159 passed, 6 skipped. Ruff, strict mypy (70 application source files), and 12/12 deterministic eval cases passed. Frontend lint/typecheck, 18 tests, and production build passed (frontend commits `04abf89` and `1451e9d`).
- [~] This is a source-grounded planning slice only. PDF/page-level evidence, code/dataset validation, approval flow, secure execution, and end-to-end reproduction remain incomplete.

This follow-up does not change the shipment status in `docs/STATUS.md`: migrations, RLS, durable worker/checkpoint recovery, provider behavior, Docker, deployment, monitoring, backup restore, and remote CI still require staging or remote evidence.

### §9 follow-up — bounded project evidence map (2026-11-08)

- [x] Add authenticated `POST /api/research/evidence-map`, requiring a project ID and using the existing project membership and attached-source authorization path.
- [x] Cap selection at 10 attached papers and 5 exact abstract spans; verify returned offsets against source text, filter instruction-like sentences, and abstain when no supported evidence is found.
- [x] Tests cover member/outsider access, attached-source scope, offsets, injection filtering, abstention, and caps. Full backend suite: 163 passed, 6 skipped; Ruff and strict mypy passed.
- [~] The endpoint is extractive evidence collection only. It does not plan multi-step research, synthesize or reconcile cross-paper findings, or establish scientific claim correctness. Broader retrieval and claim-support evaluations remain required.

### §24.1 CI and documentation follow-up (2026-11-11)

- [x] The first draft-PR run identified strict-mypy errors in Redis adapter typing and a Docker-only npm peer-resolution mismatch. Redis factory typing/shutdown were corrected, and the frontend Docker dependency stage now copies its `.npmrc`.
- [x] GitHub Actions run #48 passed on HEAD `24a725ea368855f6a446acf8bd462bdb12e64ddf`: backend, frontend, and Docker jobs all succeeded. The full backend suite in the approved Windows execution context passed 163 tests with 6 skips; Ruff, strict mypy (70 application files), 12-case eval, frontend lint/typecheck/18 tests/build passed.
- [x] Updated `README.md`, `docs/API.md`, and `docs/STATUS.md` to reflect implemented scope and current CI evidence.
- [ ] Review and merge PR #3 after human review. Do not deploy until staging migrations/RLS, provider behavior, recovery, backup restore, monitoring, and deployment gates are demonstrated.

**Current status remains not production-ready.** Green CI proves the code passed those automated jobs; it does not prove staging or production service behavior. PR #3 is a draft aggregate and needs reviewer direction on splitting the accumulated vertical slices.

### §24.2 Final local shipment audit (2026-11-11)

- [x] Re-audited implemented APIs, account cleanup, project authorization, CORS configuration, migrations, frontend routes, tests, and PR CI against this plan.
- [x] Fixed retry scheduling to use the injected scheduler clock consistently; this addresses run #50's failure on historical-time test input.
- [x] Fixed an editor authorization gap: project metadata updates are owner-only, consistent with migration 0009; added a regression test.
- [x] Account deletion now cancels owned pending runs before lease checks and deletes run events in 200-ID chunks. Account export and deletion backend tests cover pagination, active lease handling, scoped cleanup, and large histories.
- [x] Split `CORS_ORIGINS` from canonical `APP_URL`, validate exact origins, and cover the configuration with focused tests.
- [x] Local validation: backend 178 passed / 6 skipped; Ruff passed; strict mypy passed for 70 application files; deterministic eval 12/12; frontend lint, typecheck, and 18 tests passed. Local Next.js production build attempts were blocked by Windows `EPERM` while creating protected output directories; run #48 had passed the production build on the earlier pushed revision. The run #50 retry-clock failure was fixed in `3d2a2c3`; the 2026-11-13 audit confirms that commit is local and unpushed (the earlier “pushed” wording was incorrect). Run #52 did not start jobs because GitHub reports an account payment/spending-limit block, so current-head CI remains unverified.
- [ ] Product completion remains open against this plan: project detail/workspace UX, watchlist and notifications UI, account export/delete controls, page-level evidence citations, synthesis and claim verification, and complete collaboration/invitation UX are missing or partial.
- [ ] Production release remains blocked on staging migration/RLS checks, real Supabase/Redis/provider and recovery exercises, backup restore, deployment, alerting, reviewer approval, and successful CI on the current fixes. No live data or deployment was changed.

### §24.3 Project workspace, monitoring, and privacy follow-up (2026-11-11)

- [x] Implemented project detail workspaces with project-scoped evidence/answer/compare, notes, paginated source attach/list/remove, and Markdown/CSV/BibTeX exports. Added migration 0010 for per-project paper uniqueness; duplicate attachment requests are idempotent. Export handling neutralizes spreadsheet formulas, escapes Markdown titles, and omits unsafe URL schemes.
- [x] Added soft-deleted-project checks to project source operations, retrieval, research, and watchlist creation. Project source listing batches paper metadata rather than issuing per-source queries. Owners and editors can change sources; viewers can read only.
- [x] Added migration 0011 and notification project context. Topic watchlists can optionally link a project, and notifications link to the paper/project. The linked project is context; it does not filter topic matching to that project's sources. Author and citation-neighborhood watch targets remain unimplemented.
- [x] Added watchlist create/pause/resume/delete and notification read/list screens, plus authenticated account export and typed-confirmation deletion controls.
- [x] Current frontend lint and typecheck passed; all 28 tests across 7 files passed; production build completed with all 14 routes reported. Backend full suite: 189 passed, 6 skipped; Ruff, strict mypy for 70 application files, and 12/12 deterministic eval passed. The pytest rerun required the approved Windows execution context because sandboxed asyncio could not create its local socket pair.
- [x] Updated README, security guidance, API reference, migration runbook, and `docs/STATUS.md` for migrations 0010–0011 and the local capability scope.
- [ ] Product completion remains open: legally held PDF upload/parsing and page/section citations, cross-paper synthesis and claim verification, invitation delivery and fuller collaboration, broader watch targets, and expanded scientific-quality evaluations.
- [ ] Production release remains blocked on applying migrations 0001–0011 in staging, real RLS/tenant isolation and rollback/restore verification, shared Redis/Postgres/provider recovery exercises, alerting/monitoring, deployment evidence, current-head CI (GitHub billing prevents job start), and human review/merge. No live data or deployment was changed.

**Current status remains not production-ready.** See [docs/STATUS.md](docs/STATUS.md) for the capability matrix and release gates. Local checks establish code-level confidence only; they do not establish staging or production behavior.

### §24.4 Soft-deleted project RLS and viewer UX (2026-11-12)

- [x] Closed a direct PostgREST authorization gap: migration 0012 replaces `is_project_owner`, `can_access_project`, and `can_write_project` so all require `projects.deleted_at IS NULL`; static migration tests assert each helper enforces the lifecycle check. The migration is additive, transactional, and includes rollback instructions.
- [x] `GET /api/projects/{id}` now returns `current_role`; project workspace mutation controls are hidden from viewer members while backend role checks remain authoritative.
- [x] Re-ran backend tests (192 passed, 6 skipped), frontend tests (29 passed), frontend lint/typecheck/build, Ruff, strict mypy (70 files), and 12/12 deterministic eval cases; results are recorded in `docs/STATUS.md`.
- [ ] Apply migration 0012 in staging and test direct PostgREST access for deleted owner/member/editor/viewer/outsider/anon. Static SQL assertions are not a substitute for the database role matrix.
- [ ] Production remains blocked on the staging, provider/recovery, backup/restore, monitoring, deployment, current-head CI, human-review, and remaining full-product scope listed in §§24.3 and `docs/STATUS.md`.

**Current status remains not production-ready.**

### §24.5 RLS lifecycle hardening (2026-11-12)

- [x] Added migration 0012 to make direct PostgREST access apply the same soft-deleted-project boundary as the API. It replaces owner, read, and write helper functions; each requires an active project row and preserves owner/editor role rules.
- [x] Added a static regression test for all three helper functions, updated the migration runbook and security test plan, and documented the current-role API response.
- [x] Project details now serialize caller role. The workspace shows source/note write controls to owners/editors and read-only guidance to viewers; frontend coverage verifies viewer visibility and hidden mutations.
- [x] Validation: backend 192 passed / 6 skipped; targeted backend checks 16 passed; frontend 29 passed; frontend lint, typecheck, and production build passed; Ruff passed; strict mypy passed for 70 application files; deterministic eval passed 12/12 with negative citation control.
- [ ] Apply migrations 0001–0012 in staging; execute the active/deleted owner/member/editor/viewer/outsider/anon direct-RLS matrix, rollback, and backup-restore exercise.
- [ ] Product gaps and production gates from §24.3 remain open, including PDF/page evidence, synthesis and claim verification, complete collaboration/invitation delivery, expanded watch targets, provider/recovery tests, monitoring, deployment, and current-head CI.

**Current status remains not production-ready.**

### §24.7 Existing-account project roster management (2026-11-12)

- [x] Added owner-controlled roster listing and member removal endpoints. Existing `POST /members` now validates UUID inputs and supports add/role update; owners cannot add or remove themselves as a member row. Roster mutations keep backend authorization and audit logging.
- [x] Added project-owner UI to add/update existing accounts by UUID, view roles, and remove members. The UI clearly states that email invitations and account discovery are not configured; non-owners do not see roster mutation controls.
- [x] Validation: backend 198 passed / 6 skipped; frontend 31 passed; lint/typecheck/build passed; Ruff and strict mypy passed; deterministic eval 12/12 passed.
- [ ] Complete email invitation delivery, member account discovery, and onboarding/acceptance flow. Do not claim invitation support from UUID-based membership alone.
- [ ] Staging migration/RLS, provider/recovery, backup/restore, monitoring, deployment, current-head CI, human review, and the remaining PDF/synthesis/evaluation scope remain open.

**Current status remains not production-ready.**

### §24.6 Per-notification read state (2026-11-12)

- [x] Added an authenticated per-notification read route that scopes updates to both the notification ID and caller ID, and only changes unread rows. The operation is idempotent and does not reveal whether another user's ID exists.
- [x] Added the per-item “Mark as read” control and API/backend/frontend regression tests.
- [x] Refreshed `ARCHITECTURE.md` with the actual current routes, browser/API/data/queue/worker/checkpoint/scheduler flows, and project/monitoring/privacy pages.
- [x] Validation: backend 193 passed / 6 skipped, frontend 30 passed, lint/typecheck/build passed, Ruff and strict mypy passed, deterministic eval 12/12 passed.
- [ ] Staging RLS, provider/recovery, backup/restore, monitoring, deployment, current-head CI, human review, and the remaining full-product gaps remain open.

**Current status remains not production-ready.**

### §24.8 PDF page extraction, comparison accuracy, and eval expansion (2026-11-12)

- [x] Added owner/editor-only project PDF upload, bounded selectable-text extraction (20 MiB, 500 pages, per-page and total character caps), persistent project document/page records, and member-readable page text with stable `document_id:page:N` citation IDs. Original PDF bytes are not retained; encrypted/malformed files are rejected.
- [x] Added migration 0013 with project-scoped document/page RLS, page/character constraints, and staging runbook instructions. Added project UI for upload, persisted document listing, and page viewing. Project evidence maps and project answers search up to 10 documents/500 page rows and return exact page-local sentence spans with stable `document:page:N` IDs, alongside abstract evidence. Non-project answers, general search, and comparisons remain abstract/metadata based; scanned PDFs require OCR.
- [x] Replaced misleading comparison placeholders: the comparison now uses exact abstract sentences selected by category heuristics, leaves absent fields null, excludes generated summaries as evidence, and labels results as heuristic/unverified in the UI.
- [x] Expanded deterministic evals from 12 to 18 versioned cases, adding causality wording, numeric evidence, multi-source results, injection-only abstention, and acronym/entity/benchmark disambiguation. `grounded_qa_v3`: 18/18 passed; all six metrics were 1.000; fabricated-citation negative control passed.
- [x] Current local validation after project-answer integration: backend full suite 213 passed / 6 skipped; frontend 32 tests across 7 files; frontend lint and typecheck passed; Ruff passed; strict mypy passed for 71 application files; production build completed all 12 static pages and route tracing. The local build reports missing public Supabase configuration, expected because this environment does not contain deployment auth values.
- [ ] Apply migration 0013 and verify project document RLS, upload limits, cleanup/rollback, and backup restore in staging. Current branch remains ahead of its tracked remote; current-head CI cannot run until the previously rejected push is authorized and GitHub billing is restored.
- [ ] Product completion remains open: integrate PDF page evidence into general retrieval and comparisons, add OCR if scanned-source support is required, deliver invitation and onboarding flow, cross-paper scientific synthesis/claim verification, expanded watch targets, and broader service-backed quality/reliability baselines. Provider, recovery, monitoring, and deployment gates remain unverified.

**Current status remains not production-ready.** See [docs/STATUS.md](docs/STATUS.md) for current evidence and release blockers.

### §24.9 Email invitations and verified project onboarding (2026-11-12)

- [x] Added owner-only project email invitation create/list/resend/revoke APIs, editor/viewer roles, rate limits, privacy-safe audit events, and Supabase Auth Admin delivery. A global active-email uniqueness guard prevents concurrent project invites from invalidating Supabase's one-time confirmation token. Existing UUID-based membership administration remains available for existing accounts.
- [x] Added migration 0014 with owner-only invitation reads, revoked anon/public access and authenticated write privileges, and a service-role-only atomic acceptance RPC. The RPC checks that the Auth account is verified, the normalized email matches, the project remains active, and the invite remains pending/unexpired. Membership is granted only on acceptance, idempotently; an existing member's role is preserved.
- [x] Added owner invitation UI and acceptance callback for Supabase invite sessions, validated UUID-only login/OAuth return context, optional password setup, and React StrictMode-safe one-time verification. Storage/provider errors avoid logging invitation email/token values.
- [x] Local verification: backend full suite 223 passed / 6 skipped; focused invitation API tests 9/9; frontend suite 40 tests across 8 files; frontend lint/typecheck and production build pass; Ruff and strict mypy pass for 73 application files. Direct Supabase RLS/RPC and actual SMTP delivery still need staging verification.
- [ ] Apply migration 0014 in staging; configure Supabase invite email template, SMTP, one-hour link expiry, and exact `APP_URL/projects/invitations/accept` redirect allowlist; verify delivery, callback, acceptance, expiry, revoke, and role-preserving repeat acceptance.
- [ ] Product/release gaps remain: PDF general retrieval and comparison, OCR for scanned sources, broad cross-paper synthesis and claim verification, expanded watch targets, larger deployed-service quality/reliability evaluations, staging migration/RLS and backup restore, provider/recovery exercises, monitoring, current-head CI, and human review.

**Current status remains not production-ready.** See [docs/STATUS.md](docs/STATUS.md) for verified local evidence and remaining release gates.

### §24.10 Project-scoped PDF retrieval (2026-11-13)

- [x] Extended authenticated `/api/retrieval/search` so a verified project request searches only that project's attached papers and up to 10 uploaded documents/500 page rows. Public-corpus search never queries project-document tables.
- [x] PDF results contain one exact matching sentence per page, stable `document_id:page:N` citation IDs, verified page-local offsets, and a discriminated `source_type`; BM25 scores are calculated across the combined result corpus. Paper responses now select an explicit metadata field allowlist instead of returning embedding vectors.
- [x] Project UI renders mixed paper/PDF search results with offsets and citations. No LLM summary is added; PDFs remain untrusted source text and matching injection-like sentences are filtered.
- [x] Regression coverage verifies authorized member scope, outsider/deleted-project rejection before PDF reads, PDF-only projects, global-search exclusion, exact spans, deterministic mixed-source ranking, read caps, result limits, and UI citations. Local validation: backend full suite 227 passed / 6 skipped; focused retrieval 11/11; frontend 40 tests across 8 files with lint/typecheck/build passing; Ruff passed; strict mypy passed for 73 files.
- [ ] Public retrieval remains public-metadata-only by design; comparison dimensions still use paper abstracts, with PDF spans returned separately as source evidence. OCR, cross-paper synthesis/claim verification, and staging RLS/operational gates remain open.

**Current status remains not production-ready.** See [docs/STATUS.md](docs/STATUS.md) for the full release gates.

### §24.11 PDF evidence in project comparisons (2026-11-13)

- [x] Project comparisons now return up to five exact, injection-filtered PDF page spans after the existing membership/deleted-project authorization check. Structured comparison rows remain abstract-derived; PDF sentences are returned separately with stable citations and page-local offsets, not interpreted into comparison dimensions.
- [x] Global comparisons return an empty PDF evidence list and never query project-document tables. PDF-only projects can return useful evidence even when there are no paper comparison rows.
- [x] Added backend coverage for project member access, PDF-only comparisons, exact citations/offsets, instruction filtering, bounded page/document reads, deleted/outsider denial, and global comparison exclusion; frontend renders the evidence next to comparison results. Local verification: backend suite 230 passed / 6 skipped; research route tests 26/26; frontend 40 tests across 8 files, lint, typecheck, and production build pass; Ruff and strict mypy pass for 73 files.
- [ ] The standalone eval now covers PDF evidence selection, but does not measure the project-comparison response wrapper or broad page-level quality. OCR, cross-paper synthesis/claim verification, expanded watch targets, and all staging/CI/operational gates remain open.

### §24.12 PDF evidence quality gate (2026-11-13)

- [x] Extended the existing CI eval runner with versioned `pdf_evidence_v1` fixtures for supported method/benchmark evidence, injection-only abstention, entity mismatch, exact whitespace-sensitive offsets, and multiple matching pages.
- [x] The gate checks citation IDs/order, exact expected sentences, page-local substring offsets, abstention, and forbidden instruction-like text; all six cases pass and all four PDF metrics equal 1.000. The existing `grounded_qa_v3` remains 18/18 with its six metrics at 1.000.
- [ ] The synthetic eval is a focused selector regression gate; it does not establish broad PDF extraction quality, project-comparison quality, scientific synthesis, deployed-provider behavior, or tenant isolation. Staging and release blockers remain open.

**Current status remains not production-ready.** See [docs/STATUS.md](docs/STATUS.md) for release gates.

### §24.13 PDF data portability (2026-11-13)

- [x] Account export includes PDF document metadata and extracted page text for projects the caller owns, and only the caller's uploads in shared projects. Original PDF bytes are not retained. Export regression coverage checks that unrelated projects and other shared-project members' documents/pages are excluded.
- [x] Updated data-handling and evaluation documentation to match current PDF storage/export behavior and the current `grounded_qa_v3` / `pdf_evidence_v1` eval gates.
- [ ] Apply and verify migrations/RLS and account export/deletion cascades against staging. Cross-paper synthesis and claim verification, OCR, broader reliability/quality validation, current-head CI, and other production gates remain open.

**Current status remains not production-ready.** See [docs/STATUS.md](docs/STATUS.md) for release gates.

### §24.14 Bounded project-scoped cross-paper synthesis (2026-11-13)

- [x] Added `POST /api/research/synthesize`. It authorizes project membership before reading attached papers, selects up to six exact abstract sentences from distinct papers, validates local character offsets, and returns stable server-created evidence IDs. It does not query uploaded PDF tables or send private PDF text to providers.
- [x] Added bounded two-stage provider flow through `llm_router.py`: claim drafting and separate support/conflict/uncertainty review, each capped at 900 output tokens and 20 seconds. The endpoint limits each user to 10 daily synthesis requests using the shared Redis budget namespace and fails closed if production Redis is unavailable.
- [x] Validates strict response schemas, rejects unknown or single-source evidence references, downgrades single-paper support and unsubstantiated conflict to uncertain, and returns exact cited abstract sentences with titles and offsets. UI labels statuses as model-reviewed and provisional. This is not independent scientific verification.
- [x] Added backend, budget, service, and frontend regression coverage plus `cross_paper_synthesis_v1` mocked-provider contract fixtures for opposing findings, weak-support downgrade, and fabricated evidence-ID rejection.
- [x] Local validation: backend 237 passed / 6 skipped; frontend 40 tests across 8 files; frontend lint/typecheck/build pass; Ruff passed; strict mypy passed for 74 application files; evals 18/18 paper, 6/6 PDF, 3/3 synthesis contract fixtures passed.
- [ ] Current-head CI, staging provider/budget/recovery checks, blinded domain-expert review, and calibrated claim-level quality evaluation remain required. The small mocked eval does not establish model output quality.

**Current status remains not production-ready.** See [docs/STATUS.md](docs/STATUS.md) for verified local evidence and release gates.

**Current status remains not production-ready.** See [docs/STATUS.md](docs/STATUS.md) for verified local evidence and release gates.

### §24.15 Synthesis rollout gate (2026-11-13)

- [x] Added backend-owned `RESEARCH_SYNTHESIS_ENABLED`, defaulting to false, and an authenticated minimal capabilities endpoint. The API rejects synthesis while disabled before reading project or source data; the UI only exposes the mode when the backend reports it enabled.
- [x] Added backend tests for default-off capability reporting and disabled-route rejection before data access, plus frontend visibility coverage. Documented configuration and the fail-closed rollout behavior.
- [x] Local validation: backend 239 passed / 6 skipped; frontend 41 tests across 8 files; frontend lint/typecheck/build, Ruff, strict mypy (74 files), and deterministic evals pass.
- [ ] Keep the feature disabled in production until blinded human review, calibrated claim-level evaluation, and staging provider/budget/recovery checks pass. This flag is a rollout gate, not evidence that synthesis quality has been established.

**Current status remains not production-ready.** See [docs/STATUS.md](docs/STATUS.md) for verified local evidence and release gates.

### §24.16 Deterministic bounded research-plan preview (2026-11-13)

- [x] Replaced the keyword-only plan response with a typed, provider-free preview that preserves existing fields and adds task steps, public/project source scope, source/tool/depth/time/model/token ceilings, cost-tracking availability, and explicit non-execution metadata.
- [x] Corrected classifier substring false positives with word-boundary intent rules and explicit precedence. Project-scoped previews authorize active project membership before returning; they do not read papers or PDF rows.
- [x] Added project-workspace preview UI and shared TypeScript response types. The interface labels every step proposed, distinguishes `Preview plan` from `Run research`, and says current limits do not constrain separate requests. Dollar cost is shown as unmeasured.
- [x] Added backend scope/contract tests and versioned `research_plan_v1` deterministic cases for task selection, feature-gated steps, ceilings, and false-positive queries.
- [x] Local validation: backend 253 passed / 6 skipped; frontend 42 tests across 8 files; lint, typecheck, and production build passed; Ruff and strict mypy (75 files) passed; all eval suites passed (18 paper, 6 PDF, 3 synthesis-contract, 5 plan-preview cases).
- [x] At this phase the endpoint was preview-only; durable bounded execution was added in §24.21. Cross-run spend metering and broader domain/human quality review remain open, as do the production infrastructure gates.

**Current status remains not production-ready.** See [docs/STATUS.md](docs/STATUS.md) for verified local evidence and release gates.

### §24.17 Stable author and inbound-citation watchlists (2026-11-13)

- [x] Expanded watchlists with Semantic Scholar author-ID and citing-paper targets. Existing topic rows remain topic watches through migration 0015's additive default.
- [x] Validate provider targets at creation; fetch author publications or papers citing a selected paper with bounded five-page polling. Provider failures and truncated result sets do not advance the watch cursor.
- [x] Persist discovered paper metadata with conflict-ignore behavior so notification links work without overwriting existing paper rows or embeddings. Added UI target selection and source-specific labels.
- [x] Added offline tests for target validation, canonical IDs, incoming-citation direction, author lookup, pagination bounds, provider-discovered notification flow, and migration shape.
- [ ] Apply migration 0015 in staging and verify user RLS, provider rate limits/outages, dedupe, notifications, and rollback/backup restore. Semantic Scholar API behavior and alert quality have not been exercised live; `SEMANTIC_SCHOLAR_API_KEY` is optional but recommended.
- [x] Local validation: backend suite 261 passed / 6 skipped; Ruff, strict mypy (75 source files), frontend lint/typecheck, 43 tests across 8 files, and production build passed. Provider contract tests are mocked; no staging migration or live Semantic Scholar poll was run.
- [ ] Existing production gates in [docs/STATUS.md](docs/STATUS.md) remain open.

**Current status remains not production-ready.** See [docs/STATUS.md](docs/STATUS.md) for verified local evidence and release gates.

### §24.18 Resumable account deletion and portable export (2026-11-13)

- [x] Added migration 0016 with a service-role-only durable deletion ledger, unique active request per user, cross-replica leases, persisted step progress, retry scheduling, and 30-day completion-marker retention. The ledger has no Auth foreign key so it survives Auth deletion.
- [x] `DELETE /api/account` now persists intent and returns 202 with a request receipt. A background worker cancels runs, waits for active leases, cleans Mem0/checkpoints/queues/run storage and user-owned rows, deletes Auth last, and resumes safely after a worker restart. Authenticated requests are blocked while deletion is pending or complete; this lock is enforced when Supabase is configured and fails closed if the configured ledger cannot be read.
- [x] Account export now includes only public metadata for papers referenced by the caller's saved papers and project sources. Updated settings/login UX and the migration, security, and architecture documentation.
- [x] Fixed author/citation watchlist ingestion to trust the provider's target-specific result filter instead of dropping valid results that lack a title/query token match.
- [x] Local validation: backend 266 passed / 6 skipped; Ruff and strict mypy passed for 76 application files; frontend lint/typecheck and 43 tests across 8 files passed; Next.js production build completed all 13 static pages. Build output reports missing public Supabase configuration in this local environment. `git diff --check` passes.
- [ ] Apply migrations through 0016 and verify deletion recovery, active-run deferral, service-role RPC permissions, export scope, account-lock behavior, and Auth deletion in staging. Local fakes/static migration checks do not prove cross-service cleanup against live Supabase, Redis, checkpoints, or Mem0.
- [ ] Production release remains blocked on current-head CI, staging migrations/RLS, restore and provider/recovery exercises, monitoring and deployment verification, and remaining product/evaluation gates in `docs/STATUS.md`.

**Current status remains not production-ready.** See [docs/STATUS.md](docs/STATUS.md) for verified local evidence and release gates.

### §24.19 Serialize deletion with research-run admission (2026-11-13)

- [x] Closed an in-flight request race: migration 0017 takes the same per-user transaction advisory lock in `request_account_deletion` and `create_research_run_atomic`. A run is therefore either committed before deletion snapshots its IDs or rejected after the deletion marker exists.
- [x] Mapped the database admission rejection to HTTP 423 and refunded the reserved search budget. Added migration contract, run-store, and route regression tests plus an explicit rollback SQL file that restores the pre-0017 function bodies while preserving the deletion ledger.
- [x] Local validation: backend suite 269 passed / 6 skipped; Ruff and strict mypy passed for 76 application files. The 43 frontend tests, lint, typecheck, and production build remain green from the immediately preceding full frontend validation; frontend files did not change in this slice. `git diff --check` passes.
- [ ] Apply migrations through 0017 in staging and race run creation against deletion requests on PostgreSQL; verify transaction ordering, service-role permissions, rejection mapping, and rollback. No PostgreSQL runtime or running Docker engine is available in this workspace, so SQL execution remains unverified.
- [ ] Full product and production blockers remain open as recorded in [docs/STATUS.md](docs/STATUS.md).

**Current status remains not production-ready.** See [docs/STATUS.md](docs/STATUS.md) for verified local evidence and release gates.

### §24.20 Bounded local OCR for scanned project PDFs (2026-11-13)

- [x] Added opt-in `OCR_ENABLED` (default false). Native `pypdf` extraction remains unchanged; scanned pages can use local PyMuPDF rasterization and Tesseract with no PDF sent to an OCR provider.
- [x] Bound OCR to five scanned pages per upload, 1.4 render scale, 8M pixels/page, 6 seconds/page, and 20 seconds total. Resource-limited pages are stored as `ocr_limit`; native/OCR/empty provenance is preserved per page. Uploads have a 3/minute rate limit.
- [x] Added migration 0018 for extraction provenance without changing existing RLS, English Tesseract runtime in the production Docker image, `.env.example`/architecture/runbook guidance, and UI labels for native, OCR, empty, and page-limit results.
- [x] Local validation: backend 280 passed / 6 skipped; Ruff and strict mypy passed for 76 application files; frontend lint/typecheck and 44 tests across 8 files passed; production build completed all 13 static pages; all four deterministic eval suites passed (18 paper, 6 PDF, 3 synthesis-contract, 5 plan-preview cases).
- [ ] Verify migration 0018, Docker image build, installed Tesseract language data, native-only behavior, scanned/mixed extraction quality, caps/timeouts, missing-runtime 503, and page provenance in staging. Local OCR quality and image runtime are not verified here.
- [ ] Other product/release gaps remain as documented in [docs/STATUS.md](docs/STATUS.md): staging verification of research-plan execution, external notification controls, broader quality/reliability evidence, current-head CI, restore, monitoring, and deployment verification.

**Current status remains not production-ready.** See [docs/STATUS.md](docs/STATUS.md) for verified local evidence and release gates.

### §24.21 Durable bounded research-plan execution (2026-11-13)

- [x] Added `RESEARCH_PLAN_EXECUTION_ENABLED=false` as the default. `/api/research/plan` remains a provider-free preview; the authenticated `/api/research/execute` endpoint accepts work only when the execution flag is enabled and returns a durable run receipt.
- [x] Runs use the existing Redis Streams queue, leases, Postgres run/event store, LangGraph Postgres checkpoint lifecycle, SSE progress, cancellation, retention, and account-deletion cascade. Migration 0019 adds service-role-only plan metadata linked to the canonical run row; startup fails closed if execution is enabled before the migration/schema cache is ready.
- [x] Added a bounded graph for retrieval, exact evidence extraction, comparison, gap reporting, and separately gated provisional synthesis. Enforced limits include 10 sources, classifier-specific logical tool ceilings, 20/30/45/90-second deadlines, 10 executions/user/day, and 5 endpoint requests/IP/minute. Project membership and active-project state are rechecked before each project data read. Provider work is at-least-once if a crash occurs before its node checkpoint; dollar spend remains untracked.
- [x] Added project-workspace execution UX for progress, exact evidence/citations, comparison, provisional claims, gaps, errors, and cancellation, including the race where a server cancellation arrives over SSE. Compare preview steps now match graph topology. Added focused API/queue/caps/idempotency/cascade tests and updated the deterministic plan fixture.
- [x] Local validation: backend 289 passed / 6 skipped; Ruff passed; strict mypy passed for 77 application files; frontend 48 tests across 9 files, lint, typecheck, and production build passed; deterministic evals passed (18 paper, 6 PDF, 3 synthesis-contract, 5 plan cases). The build completed all 13 static pages; Supabase public build variables are not configured in this environment.
- [ ] Apply migration 0019 and exercise public/project execution, membership revocation, daily and IP limits, cancel/restart/checkpoint recovery, rate-limit behavior, result access, and migration rollback against staging Redis/Supabase/Postgres. Keep execution disabled in production until staging recovery and quality review pass. Current-head GitHub CI is still blocked by the account billing/spending limit; no Docker daemon or staging services are available here.
- [ ] Other release gates remain: backup/restore and tenant isolation evidence, live provider behavior and monitoring, staging verification of opt-in external notifications, broader reliability and domain-quality review, and deployment verification. See [docs/STATUS.md](docs/STATUS.md).

**Current status remains not production-ready.** See [docs/STATUS.md](docs/STATUS.md) for verified local evidence and release gates.

### §24.22 Opt-in watchlist email notifications (2026-11-13)

- [x] Added `NOTIFICATIONS_EMAIL_ENABLED=false`; external sends require the flag plus `RESEND_API_KEY`, a Resend-verified `NOTIFICATIONS_FROM_EMAIL`, `RESEND_WEBHOOK_SECRET`, and stable `NOTIFICATIONS_UNSUBSCRIBE_SECRET`. Missing configuration keeps delivery unavailable.
- [x] Added preference API and settings controls for explicit opt-in, daily/weekly frequency, and validated IANA time zone. Opt-in requires the current Auth Admin-confirmed email; consent changes are recorded. Digests send at 08:00 local time and contain only generic watchlist-update counts/links, with no private project or watch text.
- [x] Added migration 0020 with service-only preferences, consent events, unsubscribe tokens, recipient suppressions, and a deduplicated per-user/digest-window outbox. Auth deletion cascades account-scoped records while retaining keyed recipient suppression to avoid re-contacting bounced/complaining addresses.
- [x] Added one-click unsubscribe with token hashes, send-time consent/recipient/suppression checks, Resend idempotency, 30-second worker polling with at most five messages per tick, five total send attempts (initial plus four exponential retries at 30/60/120/240 seconds, capped at one hour), and Svix-signed bounce/complaint handling deduplicated by event and recipient. Bounce/complaint recipients are permanently suppressed; settings cannot clear them. Preference, unsubscribe, and webhook endpoints have 10/minute/IP, 20/minute/IP, and 120/minute/IP limits respectively. Production Docker/Fly Uvicorn commands use `--no-access-log` because one-click unsubscribe tokens appear in query strings.
- [x] Local validation: backend suite 304 passed / 6 skipped (including 15 notification email checks), Ruff and strict mypy across 78 source files passed; frontend 52 tests across 9 files, lint, and typecheck passed; production build generated all 13 pages. The build needed a temporary output directory because the existing `.next` directory denies writes under this Windows environment; the normal config was restored. Deterministic evals passed 18 paper, 6 PDF, 3 synthesis-contract, and 5 plan cases.
- [ ] Remaining update.md §12 scope: project-value explanations, preprint-version/retraction/withdrawal/benchmark tracking where sources support it, and human-calibrated live-source precision/missed-important-update evaluation. The offline smoke corpus in §24.23 does not establish these behaviors or release-quality thresholds.
- [ ] Apply migration 0020 and verify verified-sender delivery, preference/RLS boundaries, consent and timezone behavior, 08:00 daily/weekly scheduling, unsubscribe, valid/invalid/duplicate Svix events, suppression, retry/restart/idempotency, secret handling, and no outbound sends while disabled in staging. Keep external email delivery disabled in production until the full verification passes.
- [ ] Zenith does not meter Resend spend; configure provider-side usage monitoring and billing limits before enabling email delivery.
- [ ] During `NOTIFICATIONS_UNSUBSCRIBE_SECRET` rotation, retain prior keys in `NOTIFICATIONS_UNSUBSCRIBE_SECRET_PREVIOUS` to preserve matching for historical consent and suppression hashes. Stored SHA-256 unsubscribe-token hashes preserve issued links across key rotation; keep old HMAC keys configured as long as those records must remain valid.

### §24.23 Watchlist match explanations and offline evaluation (2026-11-13)

- [x] New watchlist notifications persist a bounded reason code and human-readable match basis: lexical term overlap in title/abstract, provider-returned author relation, or provider-reported citation relation. The notification page labels this “Why you received this.” This explains why the result matched; it does not claim scientific importance or why it matters to a project.
- [x] Deduplicate provider candidate IDs before notification upsert so duplicate source rows cannot cause a repeated conflict in one batch.
- [x] Added additive migration 0021 and rollback SQL. Legacy notification rows remain valid with null reason fields.
- [x] Added `watchlist_notifications_v1` offline fixtures and CI runner using the production topic matcher. It reports precision, recall, false positives, missed labeled-important updates, and duplicate candidate counts by target type; incomplete-source cases are excluded from recall. Provider fixtures model already-returned provider records and do not measure live Semantic Scholar quality. Thresholds are smoke checks, not human-calibrated release targets.
- [x] Local validation: focused backend ingestion/migration tests 25 passed; Ruff and mypy passed for changed Python; focused frontend monitoring suite 9 passed; frontend lint and typecheck passed; watchlist eval passed (topic precision 0.750/recall 1.000; author and citation fixture precision 0.500/recall 1.000).
- [ ] Apply migration 0021 and verify schema compatibility, RLS-preserved response visibility, and rollback in staging. Live provider precision/recall, project-specific value, author/citation version changes, retraction/withdrawal/benchmark tracking, and calibrated missed-important-update evaluation remain open.

**Current status remains not production-ready.** See [docs/STATUS.md](docs/STATUS.md) for verified local evidence and release gates.

### §24.24 Source-attributed arXiv version alerts (2026-11-13)

- [x] Added a bounded arXiv poll sorted by `lastUpdatedDate`, preserving versioned paper IDs, versionless preprint IDs in the existing paper-key format, version numbers, and arXiv's per-entry `updated` timestamp. The API documents version-specific IDs, `<updated>`, and `lastUpdatedDate` ordering ([arXiv API manual](https://info.arxiv.org/help/api/user-manual.html)).
- [x] Migration 0022 backfills version metadata from known versioned arXiv IDs and keeps each new version as a distinct `papers` row, preserving older observations. No table-level RLS policy changed.
- [x] Topic/project watches can alert when a matching paper advances beyond a previously stored arXiv version. The reason says which source-reported versions changed and when; it does not claim scientific importance. Author/citation watch version changes are not included because those polling responses do not yet provide a verified update-version contract.
- [x] Bounded candidate-ID and preprint-ID lookups avoid relying on an unbounded full-table select. A failed or saturated arXiv update poll pauses only topic-watch cursors whose window is not covered by the returned time range; author/citation watches keep their independent provider cursor.
- [x] Local validation: backend 320 passed / 6 skipped; focused backend Ruff and strict mypy passed; frontend 52 tests, lint and typecheck passed; existing evals passed (18 paper, 6 PDF, 3 synthesis-contract, 5 plan); watchlist eval passed; current-head production frontend build completed all 13 pages and route traces.
- [ ] Apply migration 0022 and verify version transitions, retries, cursor behavior, notification visibility, and rollback against staging. The update poll is capped at 200 records per run and pauses topic-watch cursors when the cap does not cover their window; live feed volume, completeness and alert quality remain unverified.
- [ ] Retraction/withdrawal and benchmark-change monitoring are not implemented. Do not treat an arXiv version update as a journal retraction; source-supported status needs separate provenance and evaluation. Project-value explanations and human-calibrated live-source precision/missed-important-update evaluation also remain open.

**Current status remains not production-ready.** See [docs/STATUS.md](docs/STATUS.md) for verified local evidence and release gates.

### §24.25 Provider spend metering release gate (2026-11-13)

- [x] Audited the model-backed execution path against §5.4 and §6.2. The existing per-user daily execution/synthesis request counters and model output-token ceilings constrain request volume and response size; they do not enforce a daily or monthly USD budget or provide a durable per-run charge trace. Synthesis calls currently discard provider usage metadata, and the research-run schema has no provider usage ledger.
- [ ] Implement provider-call-level controls before enabling either model-backed flag. A partial character/token estimate is misleading as a dollar cap: tokenization differs by provider/model, model aliases and OpenRouter/direct-provider routing can change the actual billing identity, retries/fallback attempts may each be billed, and timeout/crash paths can lose usage metadata after a provider accepted a request.
- [ ] The complete contract must include a versioned provider/model price registry with source, currency/unit, and effective date; resolution of actual provider and model for each attempt; authoritative input/output usage capture; an idempotent per-attempt usage ledger; and atomic UTC daily and monthly per-user dollar reservations and settlement. Unknown pricing, unavailable usage, budget-service/RPC failures, and ambiguous possibly-billed calls must fail closed or retain a conservative reservation. Keep `RESEARCH_SYNTHESIS_ENABLED=false` and `RESEARCH_PLAN_EXECUTION_ENABLED=false` until the call path covers every provider call, retry, and fallback.
- [ ] Staging gates: verify concurrent reservations and both budget ceilings; repeated callbacks/settlements; actual provider fallback pricing; retry, timeout, cancellation, worker-crash/restart and unknown-usage behavior; UTC day/month boundaries; service-only database access; migration rollback; and reconciliation of recorded usage/cost against provider invoices or authoritative usage reports. Configure provider-side billing alerts/limits as a separate safeguard. No invoice-reconciled implementation or staging evidence exists at this audit.

**Current status remains not production-ready.** See [docs/STATUS.md](docs/STATUS.md) for verified local evidence and release gates.

### §24.26 Current model lifecycle and provider routing (2026-11-13)

- [x] Re-audited the selectable model catalog against provider lifecycle documentation. Anthropic retired Claude Opus 4 and Sonnet 4 on 2026-06-15; defaults now use currently active Claude Opus 5.5 / Sonnet 5.5 OpenRouter IDs, with native direct-provider IDs `claude-opus-5-5` and `claude-sonnet-5-5` ([Anthropic lifecycle](https://docs.anthropic.com/en/docs/about-claude/model-deprecations), [Anthropic Messages API](https://docs.anthropic.com/en/api/messages)). Google shut down Gemini 2.0 Flash on 2026-06-01; the selectable/default fast model now uses `google/gemini-3.6-flash` ([Gemini model status](https://ai.google.dev/gemini-api/docs/models/gemini-2.0-flash), [current Gemini models](https://ai.google.dev/gemini-api/docs/models)).
- [x] Removed the retired Mistral Large 2 alias (`mistral-large-2407`) from the selectable catalog; Mistral lists it as retired and recommends Large 3 for new integrations ([Mistral Large 2 lifecycle](https://docs.mistral.ai/models/mistral-large-2-0-24-07)). Gemini 2.5 Pro was also removed pending confirmed access for new projects. Old persisted selections fail model validation; the server does not silently remap retired or unavailable IDs.
- [x] Fixed namespaced provider routing: OpenRouter is the only chat route because the shared spend meter requires authoritative usage/cost metadata. Direct provider chat helpers are removed; missing OpenRouter configuration fails closed instead of falling through to another provider. The effective `/api/models` contract is completed in §24.27.
- [x] Anthropic requests omit the `temperature` parameter, including OpenRouter requests, because Anthropic removed it from current API versions ([Anthropic parameter lifecycle](https://docs.anthropic.com/en/docs/about-claude/model-deprecations)). Other supported providers retain their configured temperature.
- [x] Focused backend routing/catalog tests: 13 passed. Full current local backend suite passes 349 with 6 skipped; strict mypy passes across 80 application source files and Ruff passes. Frontend suite passes 65 tests across 11 files with lint/typecheck passing. The production build completes all 13 static pages and route traces using an isolated `NEXT_DIST_DIR`.
- [ ] OpenRouter live calls, actual provider usage metadata, configured Auth, and model availability remain staging checks. The local build warns because Supabase public URL/key are absent from this environment. See [docs/STATUS.md](docs/STATUS.md) for migration, staging, CI, spend-metering, and product-quality gates.
- [ ] Revalidate the selected catalog against provider lifecycle changes before each release and confirm configured account access and actual provider usage/charges in staging. The local constructor tests do not establish live credentials or model availability.

**Current status remains not production-ready.** See [docs/STATUS.md](docs/STATUS.md) for verified local evidence and release gates.

### §24.27 Provider spend metering implementation (2026-11-13)

- [x] Added a versioned OpenRouter pricing snapshot (`openrouter-models-2026-11-13`) sourced from [`/api/v1/models`](https://openrouter.ai/api/v1/models). Prices are USD/token and converted with decimal ceiling to integer USD micros. Model IDs absent from the verified snapshot, including DeepSeek R1 in this snapshot, are unavailable. OpenRouter requests set provider `max_price` from the snapshot; catalog reservation uses the enforced serialized-message UTF-8 byte bound plus framing and output ceiling.
- [x] All chat attempts now use OpenRouter and the shared meter. Summary application retries reserve unique attempts; both synthesis stages, including direct synthesis and plan synthesis, carry subject/run/operation identity. Chat SDK retries are disabled; application retries are metered. `/api/search` rejects submissions if OpenRouter, positive per-subject UTC caps, service-role storage, or migration 0023 is unavailable. `/api/models` reports `{available, default_model, models}` and returns an empty list/null default unless the complete admission prerequisites are configured.
- [x] Raw OpenAI embeddings are separately metered on each retry using returned token usage and the dated OpenAI `text-embedding-3-small` price snapshot ([OpenAI model pricing](https://developers.openai.com/api/docs/models/text-embedding-3-small)). Memory-agent calls are user/run scoped; scheduled ingestion and operator jobs use `system`. Mem0 model-backed reads/writes fail closed until `MEM0_PROVIDER_SPEND_LIMIT_CONFIRMED=true`; account export reports memories withheld when credentials exist without this confirmation. Account deletion anonymizes ledger subject/run/operation identifiers and its 9-step RPC changes are reversible.
- [x] Migration 0023 adds a service-only per-attempt ledger, atomic UTC daily/monthly reserve RPC, idempotent settlement/reference/unknown RPCs, a meter readiness probe, over-budget settlement state, and rollback. `usage.cost` plus token/model metadata is preferred; OpenRouter metadata response endpoints identify the selected provider. Generation lookup is retried briefly when a valid `gen-*` ID is available. Missing metadata, timeout, settlement/store failure, or provider-reference lookup failure retains the reservation for reconciliation. Rows with no provider ID require manual OpenRouter Activity review.
- [ ] Configure positive `LLM_DAILY_SPEND_CAP_USD_MICROS` and `LLM_MONTHLY_SPEND_CAP_USD_MICROS` for the desired per-user and `system` limits, apply migration 0023, and run Postgres concurrency/idempotency/day-boundary tests in staging. Reconcile ledger totals against OpenRouter/OpenAI invoices and usage reports before enabling model-backed synthesis or plan execution. OpenRouter credit-purchase/platform fees are outside per-request inference usage and remain a separate reconciliation category; no account-plan fee factor is invented.
- [x] Local validation after metering integration: full backend suite 349 passed / 6 skipped; focused routing/catalog/migration and spend-meter tests pass; Ruff and strict mypy pass. Frontend suite 65 passed across 11 files; lint/typecheck pass; production frontend build generated all 13 pages and standalone traces using `NEXT_DIST_DIR=.next-release-check`.
- [ ] Live provider metadata, SQL RPC concurrency/recovery, migration application/rollback, invoice reconciliation, provider-side billing limits, and platform-fee reconciliation remain unverified without staging services. Keep model-backed synthesis and plan execution disabled until these gates pass.

**Current status remains not production-ready.** See [docs/STATUS.md](docs/STATUS.md) for verified local evidence and release gates.

### §24.28 Summary provenance and API wire normalization (2026-11-13)

- [x] Added `summary_status` (`generated`, `abstract_preview`, `unknown`) and a bounded `summary_fallback_reason` to the Paper API/database contract through migration 0024 and its rollback. Existing rows default to `unknown`; no historical text is inferred to be model-generated.
- [x] Summary status becomes `generated` only after metered provider settlement and output validation. Spend-limit, billing-service, provider, invalid-output, and per-run-cap fallbacks carry distinct reason codes, omit model-derived difficulty, and remain explicitly marked as abstract previews.
- [x] The frontend now normalizes backend snake_case Paper/search/SSE payloads into its camelCase view model. Feed, saved-paper, detail, and streamed search routes share the mapper. Cards and detail pages label generated summaries, abstract previews, fallback reasons, and legacy unknown provenance; papers without summary content do not receive an empty status block.
- [x] Local validation: full backend suite 349 passed / 6 skipped, Ruff and strict mypy passed; frontend suite 65 passed across 11 files, lint/typecheck passed, and production build completed all 13 pages and standalone traces. Added backend fallback/migration/orchestrator and frontend API/SSE/UI regression tests.
- [ ] Apply migration 0024 and verify legacy defaults, stored preview/generated statuses, and frontend/API behavior against staging. Product-wide release blockers remain as listed in [docs/STATUS.md](docs/STATUS.md).

**Current status remains not production-ready.** See [docs/STATUS.md](docs/STATUS.md) for verified local evidence and release gates.


### §24.29 PDF-aware comparison sources and paper-detail error handling (2026-11-13)

- [x] `/api/research/compare` and durable plan execution now return additive `pdf_comparisons` rows grouped by uploaded document. Dimension fields contain the exact selected sentence, page citation, page number, and page-local offsets. Existing heuristic paper rows remain unchanged. Documents stay separate because the schema does not connect them to individual papers; unsupported dimensions remain null. Public comparison requests return no PDF rows.
- [x] The project workspace and plan-execution result panel render those PDF fields as independent cited sources and retain the existing abstract paper table and general PDF evidence list.
- [x] Paper detail now distinguishes true 404s from authentication/access/network/server errors. Authentication errors link to sign-in; transient errors offer retry and feed navigation. Added regression tests for 404, 401, 503, and retry success.
- [x] Updated the synthesis evaluation fixtures to mock the metered invocation boundary and provide a billing identity, keeping deterministic evaluations independent of live database credentials.
- [x] Local validation: backend 352 passed / 6 skipped; frontend 69 passed across 12 files; Ruff, strict mypy (80 source files), frontend lint/typecheck, `grounded_qa_v3` (18/18), `pdf_evidence_v1` (6/6), `cross_paper_synthesis_v1` (3/3), `research_plan_v1` (5/5), `watchlist_notifications_v1` smoke gate, and production frontend build passed. The build emitted the expected warning because local Supabase public configuration is absent.
- [ ] Migration/RLS staging, provider billing and invoice reconciliation, backup restore, live invite/notification delivery, current-head CI, monitoring, human-calibrated synthesis/watch quality, retraction/withdrawal/benchmark alerts, and complete project account discovery remain release gaps; see [docs/STATUS.md](docs/STATUS.md).

**Current status remains not production-ready.** See [docs/STATUS.md](docs/STATUS.md) for external release gates and remaining product scope.

### §24.30 Locked backend dependencies and build inputs (2026-11-13)

- [x] Generated `backend/uv.lock` for Python 3.12+ with 164 exact package resolutions and artifact hashes; pinned uv 0.12.7 in `pyproject.toml`. `uv lock --check --offline` passed after resolution; `uv export --locked --no-dev --no-emit-project` produced a hash-pinned runtime requirements set.
- [x] CI now installs the pinned uv version and syncs/tests/evaluates with `--locked`. The production backend Dockerfile uses the pinned official uv image, syncs runtime-only locked dependencies into a virtual environment, and carries only that environment to the runtime stage. `backend/.dockerignore` now excludes local uv caches and tests.
- [x] Updated contributor, developer, README, and Makefile installation/check commands to use the committed lock and `npm ci`.
- [x] Locked Python 3.12 environment installed successfully; backend suite passed (352 passed, 6 skipped), Ruff/mypy passed, and deterministic evals passed (18/18 grounded QA, 6/6 PDF, 3/3 synthesis, 5/5 plan, plus watchlist smoke).
- [ ] Docker image build could not be verified because Docker Desktop's Linux engine is unavailable. Current-head GitHub CI has not run; production staging and provider/database behavior still need verification.

**Current status remains not production-ready.** See [docs/STATUS.md](docs/STATUS.md) and [plans/code-inspection-plan.md](plans/code-inspection-plan.md).

### §24.31 DOI-based Crossref publication-status watches (2026-11-13)

- [x] arXiv ingestion now stores source DOI metadata. The Crossref provider validates the requested DOI and returned record, accepts only deposited `retraction`, `partial_retraction`, `withdrawal`, `removal`, and `expression_of_concern` relations, bounds relation count and request timeout, and preserves publisher-provided notice DOI, label, type, and date.
- [x] Added migration 0025 and rollback for DOI/update provenance, an RLS-protected per-user paper-status watch table, and per-user notification idempotency keys. Paper detail exposes opt-in/opt-out controls and labels any Crossref notice with its source and linked DOI. Scheduled ingestion checks at most 100 watches per run with five concurrent lookups; provider failures preserve the last verified state and retry after a six-hour backoff.
- [x] Local focused validation: Crossref parsing, provider failure/mismatch, watch isolation, retry/persistence/idempotency, arXiv DOI, duplicate-DOI propagation, and migration assertions passed. The current complete backend suite passes 381 tests with 6 skipped; Ruff and strict mypy pass across 82 source files. Frontend validation passes 71 tests across 12 files, lint/typecheck pass, and the production build generated all 13 static pages (15 routes reported).
- [ ] Apply migration 0025 in staging; verify direct RLS, rollback, Crossref response/coverage, provider timeouts/rate limits, user opt-in/out, distinct notice delivery and recovery. Crossref data depends on publisher/member deposits: empty metadata is not evidence of no update. This slice does not complete benchmark changes, author/citation version changes, project-value explanations, or human-calibrated alert quality. See [Crossref REST API](https://www.crossref.org/documentation/retrieve-metadata/rest-api) and [Crossmark update types](https://support.crossref.org/hc/en-us/articles/115000108983-Getting-started).

**Current status remains not production-ready.** See [docs/STATUS.md](docs/STATUS.md) for external release gates and remaining product scope.

### §24.32 Spend-ledger privilege hardening (2026-11-13)

- [x] Removed direct `service_role` SELECT/INSERT/UPDATE grants on `model_spend_ledger`. Metering and deletion code already use the `SECURITY DEFINER` RPC contract; direct table writes could bypass atomic reservation, settlement, and idempotency rules.
- [x] Added migration 0026 to revoke all direct table privileges for fresh or previously migrated environments, added the `(subject_id, created_at)` index used by UTC cap accounting, strengthened static migration assertions, and documented forward-only ACL behavior and 0023–0025 rollback preconditions.
- [ ] Apply and verify migration 0026 in staging: `service_role` must be denied direct SELECT/INSERT/UPDATE/DELETE while authorized RPCs continue to work; inspect function ownership/bypass behavior on the target Supabase project. No live database is configured in this workspace.

**Current status remains not production-ready.** See [docs/STATUS.md](docs/STATUS.md) for staging, CI, and product-quality gates.



### §24.33 Maintained public code-repository discovery and provider bounds (2026-11-13)

- [x] Replaced the Papers With Code HTTP dependency with the documented GitHub REST repository search endpoint. Searches use a DOI or arXiv identifier when available and otherwise a sanitized title; the query is restricted to `is:public`, returns at most ten validated `github.com` URLs, and never labels a match official.
- [x] Preserved `/api/papers/{paper_id}/code` and implementation-plan response compatibility, renamed the route/service modules, added optional `GITHUB_TOKEN` documentation, a short public-result cache, bounded HTTP timeout, and endpoint request limits.
- [x] Added source tests for query selection/sanitization, public-only enforcement, URL filtering, optional token use, upstream failure, and candidate provenance. Summary provider calls now pass a 30-second application timeout; timeouts retain unknown spend reservations under the metering contract. Full backend validation passes 381 tests with 6 skipped; all 82 source files pass Ruff and strict mypy; frontend validation passes 71 tests, lint, and typecheck.
- [ ] Verify public GitHub search quota/latency and repository relevance with a configured deployment token, and review candidate precision with human labels. Verify provider timeout/retry behavior and spend accounting in staging before enabling model-backed features.

**Current status remains not production-ready.** See [docs/STATUS.md](docs/STATUS.md) for staging, CI, and product-quality gates.

### §24.34 Durable account-deletion lease renewal (2026-11-13)

- [x] Added service-only migration 0027 with an owner-bound lease-renewal RPC that refuses renewal after lease expiry and bounds requested lease duration. The deletion worker renews a 600-second lease every 200 seconds while cleanup is in progress; failed renewal cancels the worker so another replica cannot overlap destructive steps.
- [x] Added a failure-injection test proving cleanup stops when lease renewal fails, a migration/RPC boundary assertion, and a rollback script with stop-worker preconditions. The current full backend suite passes 381 tests with 6 skipped; Ruff and strict mypy pass across 82 source files.
- [ ] Apply migration 0027 in staging and exercise multi-replica renewal, expiry, wrong-owner, renewal-RPC outage, cancellation, and long-running external cleanup behavior. The live worker/recovery behavior remains unverified without staging services.

**Current status remains not production-ready.** See [docs/STATUS.md](docs/STATUS.md) for staging, CI, and product-quality gates.

### §24.35 Project-linked watch relevance hints (2026-11-13)

- [x] Project-linked watch notifications now carry a separate, optional relevance hint when the candidate title/abstract shares at least two distinctive words with the project title or one of up to 20 attached paper titles. The text names the observed terms and reference title and explicitly says this is not a scientific-importance assessment.
- [x] Project context is read only while the watch owner remains the project owner/member and the project is active. Deleted projects, revoked members, absent references, insufficient overlap, and project-read failures leave the hint empty; the independently valid watch alert still goes through.
- [x] Added additive migration 0028 and rollback, API type/UI rendering, ingestion/migration tests, and runbook coverage. This closes the local feature gap for observable project relevance; human-calibrated relevance/alert-quality evaluation and live RLS/provider behavior remain release gates.
- [x] The current backend suite passes 386 tests with 6 skipped, including async project-linked watch integration. Migration assertions and pure relevance tests pass (25 tests); Ruff and strict mypy pass across all 82 source files. Frontend suite passes 71 tests; lint and typecheck pass.
- [x] A fresh production frontend build passed in an isolated output directory and generated all 13 static pages. The local build warns that public Supabase Auth values are absent.
- [x] Current deterministic evals pass: 18/18 grounded QA, 6/6 PDF evidence, 6/6 synthesis-contract, and 5/5 research-plan cases. These remain smoke/contract checks, not expert validation of scientific correctness.
- [ ] Apply migration 0028 in staging and verify membership revocation, deleted projects, source bounds, notification visibility, rollback, and representative false-positive/false-negative rates with human labels. Do not treat lexical overlap as project value or scientific significance.

### §24.36 Existing-account project invitation inbox (2026-11-14)

- [x] Email invitations now handle existing Auth accounts without requiring the inviter to know a user UUID. The invite remains pending, owners can copy a pending acceptance link to share, and the recipient can accept from the projects page while signed in with the current Auth-confirmed email; membership still flows through the existing atomic verified-email RPC.
- [x] Added a bounded inbox query scoped to that verified email. It omits expired invites and deleted projects, returns only project title/role/expiry needed for acceptance, and leaves the database invitation row service-role-only. Owner-facing create/list/resend responses no longer expose email delivery timestamps that could reveal whether an address already has an account.
- [x] Added regression coverage for existing-account invite handling, generic provider failure, verified-email isolation, expired/deleted-project exclusion, unauthenticated email exclusion, frontend acceptance, and copy/open invitation links. Full local backend suite passes 389 tests with 6 skipped; Ruff passes, strict mypy passes across 75 application files and the eval runner, frontend passes 72 tests across 13 files with lint/typecheck green, and the fresh production build generated all 13 static pages.
- [ ] Verify migration 0014/RLS, existing-account inbox access, new-account Auth invitation delivery, email changes, unverified accounts, expiry/revoke races, and role preservation against staging. The project roster continues to show UUIDs; no global account directory is exposed. This improves invite onboarding but does not verify all collaboration UX or live email delivery.

**Current status remains not production-ready.** See [docs/STATUS.md](docs/STATUS.md) for staging, CI, provider, recovery, and quality gates.

### §24.37 Reliable repository lint and format entry points (2026-11-14)

- [x] Added the missing aggregate `make lint` and `make format` targets, included all declared targets in `.PHONY`, and made frontend lint invoke the TypeScript typecheck so the local aggregate matches the CI checks. Backend formatting now runs both Ruff autofixes and Ruff formatting.
- [ ] The Windows environment used for this review does not have GNU Make installed, so Make target execution could not be verified here. The equivalent backend/frontend checks were run directly and passed in §24.36.

**Current status remains not production-ready.** See [docs/STATUS.md](docs/STATUS.md) for staging, CI, provider, recovery, and quality gates.

### §24.38 Product plan and changelog aligned with runtime (2026-11-14)

- [x] Replaced the stale scaffold-era `PLAN.md` with a current capability summary and a staged roadmap that links to the runtime architecture and evidence-backed release status. It distinguishes implemented local behavior from partial product scope and external verification gates.
- [x] Updated the unreleased changelog to reflect the current OCR, provisional synthesis, gated plan execution, spend metering, Crossref watches, email/invitation flows, and their documented limits. Removed claims that OCR and synthesis are unavailable.
- [x] Checked every local Markdown link in both files and ran `git diff --check` on the documentation and Makefile changes; checks passed.
- [ ] Current-head CI, staging/runtime verification, remaining product-quality scope, and all production release gates in [docs/STATUS.md](docs/STATUS.md) remain open.

**Current status remains not production-ready.** See [docs/STATUS.md](docs/STATUS.md) for external gates and remaining product scope.

### §24.39 Crossref notice deposit provenance (2026-11-14)

- [x] The Crossref parser now preserves the optional relation-level `source` value when it is `publisher` or `retraction-watch`; missing and unrecognized values remain null. This field is separate from the existing `publication_update_source='crossref'` registry field.
- [x] Added nullable `publication_update_deposit_source` through migration 0029 and rollback, Paper API/type normalization, paper detail display, and notification text. Existing records remain unknown; the UI only labels the notice source when Crossref reports one.
- [x] Backend Ruff and strict mypy pass for the changed services/schema. Thirty-three synchronous parser/migration tests pass; 8 async tests were deselected because pytest's Windows event-loop socket-pair setup stalls before the tests start. Frontend suite passes 73 tests across 13 files; lint and typecheck pass.
- [ ] A fresh Next.js build compiled and generated all 13 static pages but failed standalone trace copying with Windows `EPERM`; run the production build in CI/Linux. Apply and verify migration 0029, live Crossref coverage, notice idempotency, and source display in staging. This provenance does not establish the correctness of a notice or complete Crossref coverage.

**Current status remains not production-ready.** See [docs/STATUS.md](docs/STATUS.md) for release blockers.

### §24.40 Original uploaded PDF retention policy (2026-11-14)

- [x] Product decision: discard original PDF bytes after bounded extraction. The upload route reads the bounded payload, closes the request file, and persists only document metadata plus project-scoped extracted page text; no object-storage copy is created. Existing export behavior returns only caller-authorized extracted page content.
- [x] Recorded the policy in [PLAN.md](PLAN.md), [docs/STATUS.md](docs/STATUS.md), and [docs/security/DATA_HANDLING.md](docs/security/DATA_HANDLING.md). This resolves the original-file retention question; it does not resolve staging RLS, deployment verification, OCR runtime quality, or collaboration UX gaps.
- [ ] Verify temporary upload cleanup, RLS, export/deletion cascade, and OCR behavior in staging. Keep the upload UI explicit that source bytes are not retained.

**Current status remains not production-ready.** See [docs/STATUS.md](docs/STATUS.md) for remaining product and release gates.

### §24.41 CI migration-test path correction (2026-11-14)

- [x] Read current PR #3 CI run #56: frontend and Docker passed; backend Ruff/mypy passed, then 319 tests passed and 6 were skipped, with one failure. The failure used repository-root-relative migration paths while Actions' working directory is `backend/`.
- [x] The current worktree resolves the migration and service files from `Path(__file__).resolve().parents[2]`; the failing CI test passes when run locally from the backend directory.
- [x] Corrected two invalid regex-string escape warnings reported by that CI run. `tests/test_cors.py` passes all 9 tests with Python `SyntaxWarning` promoted to an error.
- [ ] This test fix is uncommitted and has no remote CI result. PR #3 is still a draft; verify a successful full run on a remote commit before treating CI as green. No remote branch was changed in this step.

**Current status remains not production-ready.** See [docs/STATUS.md](docs/STATUS.md) for the remaining CI, staging, and product gates.

### §24.42 Compose configuration validation (2026-11-14)

- [x] `docker compose config --quiet` passes when run with a temporary empty root `.env`, matching CI's secret-free Compose validation setup. The temporary file was removed immediately afterward.
- [ ] The local Docker engine is still unavailable, so the current worktree's images were not built locally. Run the Docker job on a remote commit containing these changes.

**Current status remains not production-ready.** See [docs/STATUS.md](docs/STATUS.md) for remaining release gates.

### §24.43 Shipment-readiness cross-check and crawl-cache identity (2026-11-14)

- [x] Re-audited the current implementation against this file with parallel backend, frontend, and infrastructure reviews. The audit confirmed the documented partial scope: project annotations, saved searches, versioned briefs, and section/page-grounded public-paper evidence are not implemented; the current project PDFs remain separate extractive sources. Frontend route tests pass, but these roadmap capabilities are not shipment-complete.
- [x] Fixed the migration runbook omission for 0029 and stale model-provider/cost guidance. Added migration 0030 to version the legacy Firecrawl cache schema with URL/parser identity. Hosted crawling is now fully disabled; cache reads/writes are also disabled. Added rollback, schema snapshot, tests, and runbook instructions.
- [x] The backend and frontend now use fetch-based SSE with the short-lived token in `Authorization`, strict numeric `Last-Event-ID` cursors, bounded reconnects with fresh exchange tokens, and abortable cleanup. The backend rejects query-token authentication and includes the cursor header in CORS. Both Firecrawl entry points fail closed, report unavailable, and do not access the legacy cache. Deployment docs no longer ask operators to configure an unused Firecrawl key.
- [x] Verification: frontend tests pass (73/73 across 13 files); backend migration and CORS tests pass (33/33); deterministic watchlist smoke eval completes; targeted cache identity tests, Ruff, strict mypy, and `git diff --check` pass. The new async cache integration cases and full backend batch could not complete in the Windows pytest environment because of the known event-loop socket-pair stall.
- [ ] Apply migration 0030 and all prior migrations in staging; complete RLS, backup/restore, provider, billing, email, OCR, recovery, and monitoring checks. Keep Firecrawl crawling unavailable until redirect and egress controls are verified; verify deployed proxy Authorization-header redaction; obtain successful full CI on the current worktree. See [docs/STATUS.md](docs/STATUS.md).

**Current status remains not production-ready.** No local test suite or static audit substitutes for staging, external-provider, and release-gate evidence.

### §24.44 SSE bearer-header and cursor replay (2026-11-15)

- [x] Replaced the EventSource query-token flow with authenticated fetch streaming. Stream tokens are sent only in the Authorization header; the backend rejects query-only auth. The UI preserves the latest sequence across its bounded retries and requests a fresh five-minute SSE token for each connection.
- [x] Added strict nonnegative ASCII cursor parsing, replay-after-cursor behavior, terminal-event deduplication, `Last-Event-ID` CORS support, incremental SSE parsing for split CRLF/multiline frames, and synchronous abort cleanup during session exchange or streaming.
- [x] Local verification: the full frontend suite passes (79 tests across 13 files), with lint and TypeScript typecheck green. Backend Ruff, strict mypy for `routers/stream.py`, and CORS plus migration checks (35 tests) pass. Ten pure cursor-parser tests also pass with pytest-asyncio disabled. The ASGI endpoint and async replay test batch still stalls in this Windows sandbox; manual endpoint/proxy verification and remote CI remain outstanding. The frontend production build compiled and generated 13 static pages but Windows failed standalone trace copying with `EPERM`, so it is not counted as a successful build.
- [ ] Verify stream endpoint integration, retry/replay with real shared Redis/Postgres across replicas, and Authorization-header redaction in staging/proxy logs; obtain full current-head CI. Keep the hosted Firecrawl crawl helper unavailable until its remote redirect behavior can be constrained and verified.

**Current status remains not production-ready.** See [docs/STATUS.md](docs/STATUS.md).

### §24.45 Crawl shutdown and backend app startup fixes (2026-11-15)

- [x] Closed the legacy-cache bypass: `crawl_paper_cached()` now fails before cache access, `is_available()` always returns false, and the unused Firecrawl API key setting/example and SDK construction path were removed. Deployment, developer, flow, schema, and baseline-audit docs now describe the retained cache as legacy and inactive. The SDK dependency remains declared and locked because lock regeneration needs unavailable package-index artifacts; it is not imported or invoked by application code.
- [x] Focused test import exposed SlowAPI startup errors for new rate-limited paper status-watch and repository-code handlers. Added FastAPI `Request` parameters to those handlers. Focused Firecrawl tests pass (4/4); repository-wide Ruff and strict mypy on the changed routes/services pass; app import succeeds through pytest collection.
- [ ] Run the full backend suite and current-head CI, then complete staging migrations, RLS/provider/deployment/recovery verification. The full local pytest run and focused watch/repository tests produced no output for 120 and 60 seconds respectively in the Windows runner and were stopped. `asyncio.run(asyncio.sleep(0))` also hangs in this environment, confirming the async test blockage is runner-level but leaving application async integration unverified. The local production build still fails Windows standalone trace copying with `EPERM`; Docker and staging services remain unavailable.

**Current status remains not production-ready.** See [docs/STATUS.md](docs/STATUS.md).

### §24.46 Release documentation and selectable model pricing alignment (2026-11-15)

- [x] Reconciled stale migration ranges in `PLAN.md`, `README.md`, and the LangGraph checkpointer note with migrations 0001–0030. Updated the README and CHANGELOG release snapshots to the latest verified CI/frontend/build state and corrected security/data-flow descriptions to reflect that user-controlled URL fetching is disabled and legacy crawl rows remain inactive.
- [x] Removed DeepSeek R1 from the selectable model registry and TypeScript model union because the verified spend-price catalog has no bound for it. `validate_model()` now also rejects any registry entry without a verified price, preventing future catalog drift from reaching preferences or search admission.
- [x] Verification: backend model-router tests pass (13/13); frontend ModelSelector tests pass (4/4); repository-wide Ruff passes; strict mypy on the changed router passes. Fresh audits found no additional unpriced registry entries.
- [ ] Full async backend tests remain unverified because this Windows Python 3.13 runner hangs on even `asyncio.run(asyncio.sleep(0))`; obtain Linux CI, stage all migrations and integrations, and complete the remaining scope and operational release gates.

**Current status remains not production-ready.** See [docs/STATUS.md](docs/STATUS.md).

### §24.47 Source-anchored project annotations (2026-11-15)

- [x] Added project annotations anchored to exact attached-paper abstract or extracted PDF page text. The API validates the selected text slice and stores a SHA-256 fingerprint; list responses identify stale anchors; updates can change annotation content but cannot move the source anchor.
- [x] Enforced owner/editor writes and member reads in the API and migration 0031 RLS. Composite foreign keys bind paper/document sources to the same project. Account export includes annotations, and account deletion removes caller-created annotations from shared projects.
- [x] Added project workspace UI for creating annotations from abstract/PDF evidence, listing citations/stale state, and editing/deleting for writers. Frontend workspace tests pass (15/15), and TypeScript typecheck passes. Migration static assertion passes (1/1).
- [ ] Backend async endpoint tests remain unverified: pytest hangs in the local Windows event-loop setup; no live Supabase project is configured for applying migration 0031 and testing owner/editor/viewer/outsider RLS. Verify staging before release.

**Current status remains not production-ready.** Project saved searches, versioned briefs, public-paper page-grounded evidence, CI on the current head, and service-backed release gates remain open. See [docs/STATUS.md](docs/STATUS.md).

### §24.48 Project-scoped saved searches (2026-11-15)

- [x] Added personal and project-scoped saved-search configurations through migration 0032 with rollback. Project scope and creator identity are immutable at the database layer; project members can read/run, project creators can manage their own while members, and owner/editor roles can manage all project searches. Personal searches are creator-only.
- [x] Added authenticated list/create/read/update/delete/run API routes. Each explicit run revalidates project membership and starts a new metered search with a fresh idempotency key; results are not stored on the saved-search row. Model choices are validated against the spend-priced registry.
- [x] Added project workspace UI for creating, editing, deleting, and running saved searches, with streamed progress/results and role-aware controls. Personal searches do not appear in the project panel. Frontend workspace tests pass (17/17), ESLint on changed files passes, and TypeScript typecheck passes. Backend Ruff, strict mypy on changed modules, saved-search schema validation, and migration static tests pass.
- [ ] Backend async route tests are authored but blocked by the local Windows event-loop hang. Migration 0032, RLS, repeat-run behavior, quotas and provider spend still need staging verification. Watchlists remain recurring subscriptions with alert cadence, not saved searches.

**Current status remains not production-ready.** Versioned briefs, public-paper page-grounded evidence, CI on the current head, and service-backed release gates remain open. See [docs/STATUS.md](docs/STATUS.md).

### §24.49 Versioned project briefs and lazy-router rate limits (2026-11-15)

- [x] Added project brief metadata and immutable user-authored versions with exact abstract/PDF-page source snapshots, quote/source/content SHA-256 fingerprints, expected-version concurrency checks, and clear manual authorship provenance. Migration 0033 adds member-read RLS, revoked direct mutation grants, and service-only RPCs that recheck owner/editor role and exact source text. Brief creation/version append are atomic; stale writes return 409.
- [x] Added authenticated list/create/read/version APIs, source citation capture from project evidence, history/conflict UI, project/account export, and deletion handling. Migration 0033 includes rollback and runbook verification steps. Original PDF bytes remain discarded; snapshots refer to extracted page text and do not claim model-generated correctness.
- [x] Fixed rate-limit registration for current FastAPI lazy-included routers. `apply_rate_limits()` now recursively finds included APIRoutes so configured SlowAPI limits apply after router inclusion. New brief mutations are limited to 20/minute. Regression tests cover direct and included-router mutations.
- [x] Verification: full frontend suite passes (86 tests across 14 files), lint and typecheck pass. Backend Ruff and strict mypy pass on changed modules; rate-limit tests pass (2/2), focused migration/contract checks pass (5/5), migration 0033 static assertions pass, and app import plus wrapped-route inspection pass.
- [ ] Async brief route/account-export tests remain unverified because the local Windows runner hangs during asyncio setup. Migration 0033/RPC/RLS and rollback have not been applied or exercised against staging; obtain full CI on the current branch and complete the migration, tenant-isolation, concurrency, backup/restore, and operational checks before release.

### §24.50 Current production-build and CI evidence refresh (2026-11-15)

- [x] Re-audited the current requirements in §§24.47–24.49 against backend routes, frontend clients/workspace UI, migrations 0031–0033, rate-limit registration, and related tests. Those local features are present; the remaining unchecked items are staging, async CI/runtime, data-source, and human-calibrated quality gates.
- [x] Re-ran the default frontend production build with `CI=1`: compilation, TypeScript validation, and all 13 static pages passed, but standalone trace collection failed with Windows `EPERM` creating a nested `.next/standalone` directory. A clean alternate `NEXT_DIST_DIR` attempt failed during trace copying too. One retry passed after pre-creating its failing directory, but this was not reproducible and does not count as a successful build. Generated `next-env.d.ts` and `tsconfig.json` drift was restored.
- [x] Read PR #3 checks for exact remote head `63f2f18d17a182cbce84b513b685d8f743bf9130`. Frontend and Docker checks passed; backend Ruff/mypy passed, then pytest reported 319 passed, 6 skipped, and one migration-path failure. The local test now resolves paths from `__file__`; the focused test passes from both repository root and CI's `backend/` working directory. The fix is uncommitted and has no remote CI result.
- [x] Current repository-wide backend Ruff and strict mypy pass locally; mypy checked 84 source files. Full async integration tests remain unverified in this Windows runner.
- [x] Current frontend suite passes again: 86 tests across 14 files. Direct synchronous evaluation slices pass: 18/18 grounded QA, 6/6 PDF evidence, and 5/5 research-plan cases; watchlist smoke eval passes five cases (one incomplete source). The full evaluation runner stalls when it reaches the async synthesis fixtures in this Windows environment; the historical 6/6 synthesis result still needs current Linux CI revalidation.
- [x] Updated [README.md](README.md), [docs/STATUS.md](docs/STATUS.md), and [plans/code-inspection-plan.md](plans/code-inspection-plan.md) to reflect the non-reproducible standalone trace failure and current CI evidence.
- [ ] Release remains blocked: run clean production builds on Linux with configured public Auth values; publish a reviewed current worktree revision and obtain green current-head CI; exercise migrations 0001–0033, RLS, rollback, tenant isolation, provider behavior, spend reconciliation, recovery, backup/restore, and monitoring in staging. Public-paper full-text sourcing and broader human-reviewed research-quality evidence remain open.

**Current status remains not production-ready.** Public-paper section/page-grounded evidence, current-head CI, staging migration/RLS, and provider/recovery/quality release gates remain open. See [docs/STATUS.md](docs/STATUS.md).

### §24.51 Unrestricted production build and full local verification (2026-11-15)

- [x] Ran the default Next.js production build outside the Windows sandbox with `CI=1` and telemetry disabled. It completed compilation, lint/type validation, all 13 static pages, and standalone trace collection. The sandboxed build still fails with `EPERM` during trace copying; this is an environment restriction, not a source/configuration workaround.
- [x] Started the generated standalone server and smoke-tested `/`, `/feed`, `/projects`, and `/watchlists` over loopback; each returned HTTP 200. The server was stopped after the requests. Auth warned because `.env.local` has empty Supabase URL/key values.
- [x] Ran the full backend suite outside the sandbox with provider credentials cleared. The first run exposed five stale direct-route test calls/fixtures; corrected them without weakening quote integrity or authorization assertions. The complete rerun passes **425 tests, 6 skipped**. Repository-wide Ruff and strict mypy pass (84 source files).
- [x] Re-ran frontend tests (**86/86**) and the full deterministic eval runner outside the sandbox: grounded QA 18/18, PDF evidence 6/6, mocked-provider synthesis 6/6, and research plan 5/5. The watchlist smoke evaluation passes five cases, with one incomplete source excluded from recall.
- [x] Updated [README.md](README.md), [docs/EVALUATIONS.md](docs/EVALUATIONS.md), [docs/STATUS.md](docs/STATUS.md), and [plans/code-inspection-plan.md](plans/code-inspection-plan.md) to reflect current local evidence.
- [ ] Current-head remote CI still needs to run with the local test fixes; the remote head remains `63f2f18` and the worktree is uncommitted. Docker image build, production Supabase/Auth configuration, staging migrations 0001–0033, direct RLS/tenant-isolation checks, rollback/restore, provider spend reconciliation, live notifications/OCR, operational monitoring, public-paper section/page evidence, and human-reviewed scientific quality remain open before release.

**Current status remains not production-ready.** Local build, full test, and deterministic eval evidence now pass, but remote CI and production service-backed gates are still open. See [docs/STATUS.md](docs/STATUS.md).

### §24.52 PDF temporary-file cleanup and final cross-layer audit (2026-11-16)

- [x] Confirmed the selected retention policy is already implemented: PDF bytes are read with a bounded limit, closed before extraction, and never persisted; only project-scoped metadata and extracted page text are stored. The UI tells users the original is not retained.
- [x] Hardened cleanup so the upload stream closes in a `finally` path when authorization/content-type validation or reading fails. Added regression cases for rejected content types and read errors; focused PDF ingestion tests pass (17/17), and the complete backend suite passes (427 passed, 6 skipped).
- [x] Ran parallel read-only backend, frontend, and release-infrastructure audits against this plan. They confirmed the current PDF policy and identified no release-safe way to infer reuse rights for arbitrary public-paper full text. Public-paper section/page evidence, expert-calibrated scientific quality, and fuller account discovery remain product gaps.
- [x] Corrected release documentation to reconcile current local suite/build/eval results with historical CI run #56, and updated the migration range and evaluation baseline.
- [ ] Production release remains blocked on a green current-head CI run, Docker build for the current revision, configured Auth/Supabase and staging services, migrations/RLS/rollback/restore verification, live provider and spend reconciliation, monitoring/recovery exercises, and the remaining product/quality scope. Do not mark production-ready based on local checks alone.

**Current status remains not production-ready.** See [docs/STATUS.md](docs/STATUS.md) for the exact locally verified state and external release gates.

### §24.53 CI workflow supply-chain hardening (2026-11-16)

- [x] Pinned checkout, setup-python, and setup-node to full immutable commit SHAs for their verified releases. The already pinned setup-uv action remains pinned. Upstream references: [checkout v4.2.2](https://github.com/actions/checkout/releases/tag/v4.2.2), [setup-python v5.6.0](https://github.com/actions/setup-python/releases/tag/v5.6.0), and [setup-node v4.4.0](https://github.com/actions/setup-node/releases/tag/v4.4.0).
- [x] Set the workflow token to read-only repository contents and cancel superseded workflow runs for the same branch or pull request.
- [ ] Validate this workflow on the current remote head. The existing references preserve the current action majors; evaluate Node 20 action-runtime migration separately before changing majors.

**Current status remains not production-ready.** A local workflow edit does not replace current-head CI evidence or the staging and product-quality gates in [docs/STATUS.md](docs/STATUS.md).

### §24.54 Version- and license-gated public arXiv page evidence (2026-11-16)

- [x] Implemented authenticated `GET /api/papers/{paper_id}/public-evidence` and capability-gated paper UI. The service validates the stored paper ID/arXiv ID/version relationship, checks the latest `arXivRaw` OAI record, allows only exact CC BY 4.0 or CC0 1.0 license URIs, and returns at most five exact native-text page sentences with page-local offsets, source/license links, and attribution. Unknown/ambiguous rights fail closed; stale or mismatched versions return a conflict.
- [x] PDFs and excerpts are processed ephemerally and never persisted. OAI/PDF responses and request time are bounded, redirects and unsupported IDs are rejected, PDF parsing runs off the event loop, and a shared Redis owner-token gate serializes arXiv API traffic with at least three seconds between requests. Production fails closed if the shared gate is unavailable; development uses a process-local gate.
- [x] Frontend only offers evidence search when the capability and validated arXiv ID/version are present. Unsupported sources, stale metadata, and denied reuse receive distinct guidance. The feature remains disabled by default. Docs, API schemas, Paper metadata, environment examples, and deployment instructions were updated.
- [x] Validation: focused backend tests 62/62; complete backend suite 450 passed / 6 skipped; Ruff and strict mypy passed (82 source files); frontend suite 97/97, lint and typecheck passed; production build generated 13 static pages and 15 routes. Deterministic evals passed: grounded QA 18/18, PDF evidence 6/6, mocked synthesis 6/6, research plan 5/5, and watchlist smoke 5 cases (one incomplete source excluded from recall). `git diff --check` passed.
- [ ] Keep `PUBLIC_PAPER_EVIDENCE_ENABLED=false` until staging verifies live OAI version/license associations, allowed and denied licenses, exact-version PDF retrieval, shared Redis pacing under concurrent replicas, and excerpt/log/cache behavior. Current-head CI, Docker build, migrations/RLS/rollback/restore, configured production Auth, provider reconciliation, monitoring, and human-reviewed product-quality gates remain open.

**Current status remains not production-ready.** This local feature and validation evidence do not replace staging or current-head CI. See [docs/STATUS.md](docs/STATUS.md).

### §24.55 Production-gate re-audit and documentation consistency (2026-11-16)

- [x] Rechecked current external state: PR #3 remains open/draft at `63f2f18`; the local worktree is also at `63f2f18` with uncommitted changes, so there is no reviewable remote revision containing the current code and no current-worktree CI evidence. The authenticated GitHub connector confirmed the PR state; local `gh` credentials are invalid and cannot start or inspect Actions runs.
- [x] Docker Compose configuration parses with a temporary empty root `.env`. Docker CLI is present, but the Docker Desktop Linux engine pipe is absent, so no current image build or container runtime verification was possible.
- [x] Reconciled stale test counts in README/release notes and corrected `docs/SCHEMA.md` so it identifies migrations `0001`–`0033` as the source of truth and labels `supabase/schema.sql` as an incomplete legacy baseline.
- [ ] Production remains blocked on a current reviewed remote revision and green CI, Docker image/runtime validation, configured staging Supabase/Auth/Redis/Postgres/provider services, applying and verifying migrations/RLS/rollback/restore, live spend/provider/recovery checks, operational monitoring, and human-reviewed scientific and monitoring quality gates. These require external service state and review; local regression tests cannot substitute for them.

**Current status remains not production-ready.** See [docs/STATUS.md](docs/STATUS.md) and [plans/code-inspection-plan.md](plans/code-inspection-plan.md).

### §24.56 Fresh release-state verification after goal resumed (2026-11-20)

- [x] Rechecked current state rather than relying on the prior block: local and remote branch HEAD remain `63f2f18`; 155 paths are changed/untracked; PR #3 is still open/draft and last updated 2026-11-14. The connected GitHub integration can read PR metadata and reports only historical CI run #56; local `gh` auth remains invalid.
- [x] Rechecked deployment configuration without exposing secret values: root/backend `.env` files are absent and `frontend/.env.local` has no required Supabase/Auth/provider settings. Docker Desktop is installed but its process exits and neither headless nor desktop launch exposed a window or Linux engine. Docker Compose configuration still parses with a temporary empty `.env`.
- [ ] Production readiness remains blocked on a reviewable remote revision, current-head CI, Docker image/runtime verification, configured staging services, migrations/RLS/rollback/restore, live provider/recovery/monitoring checks, and human-reviewed quality gates. Local worktree validation remains green but cannot prove these production conditions.

**Current status remains not production-ready.** Recheck these external gates after GitHub authentication, Docker Desktop, or staging configuration changes.

### §24.57 Local production image build and health checks (2026-11-20)

- [x] Recovered Docker Desktop's Linux engine through the Docker CLI after the earlier availability check. Replaced the GHCR-only `ghcr.io/astral-sh/uv:0.12.7` stage with a PyPI install pinned to `uv==0.12.7`, matching CI while keeping `uv sync --locked --no-dev --no-install-project` for runtime dependencies. This avoids the GHCR OAuth token denial observed on this host without weakening dependency locking.
- [x] `docker compose build` completed successfully for both `zenith-backend` and `zenith-frontend`. The frontend image completed Next production compile, static page generation, and standalone trace steps. Production Compose config parses with the existing empty `.env`; the production frontend now has an HTTP health check alongside the backend readiness check. `git diff --check` passes.
- [x] Ran a frontend container smoke check; the root route returned HTTP 200. The new frontend Compose healthcheck uses the Node 20 runtime's built-in `fetch` against the local root route. Backend container startup/readiness and end-to-end frontend-to-backend behavior have not been smoke-tested.
- [ ] No staging Supabase/Auth/Redis/Postgres/provider credentials are configured, so migrations/RLS, OCR/Tesseract behavior, recovery, provider integration, and deployed monitoring remain unverified. Current-head CI is still outstanding because these worktree changes are uncommitted and PR #3 remains at `63f2f18`.

**Current status remains not production-ready.** Local image construction closes the prior Docker build verification gap only; see [docs/STATUS.md](docs/STATUS.md) for all remaining release gates.

### §24.58 Production Compose exposure and startup ordering (2026-11-20)

- [x] Bound frontend/backend host ports to loopback because the documented single-host deployment uses nginx for TLS and proxy controls. This prevents direct public access to plaintext app ports.
- [x] Changed frontend `depends_on` to wait for the backend `/api/ready` healthcheck before starting. Added static regression tests for loopback binding and readiness ordering.
- [x] Verified parsed production Compose output has `host_ip=127.0.0.1` for both published ports and `service_healthy` for the frontend dependency. The full backend suite passes 454 tests with 6 skipped; repository-wide Ruff and strict mypy pass (86 source files); frontend passes 97 tests, lint, and typecheck. `git diff --check` passes.
- [ ] Backend container readiness remains unverified without production dependency configuration. Current-head CI, staging migration/RLS/rollback/restore, provider reconciliation, operational recovery/monitoring, and human-reviewed scientific-quality gates remain required.

**Current status remains not production-ready.** This hardens the documented single-host Compose topology; it does not replace configured staging or current-head CI. See [docs/STATUS.md](docs/STATUS.md).
