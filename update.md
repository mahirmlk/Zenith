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
- arXiv, Hugging Face Daily Papers, Firecrawl, Semantic Scholar, Papers With Code, Mem0, OpenRouter, direct-model fallbacks.
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
| `backend/services/firecrawl.py` | Safe external fetching, SSRF defenses, source rights and cache versioning |
| `backend/services/semantic_scholar.py` | Citation metadata validation, rate-limit handling, missing-data states |
| `backend/services/papers_with_code.py` | Audit availability; replace/fallback if stale; remove dead endpoints |
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
- [x] Local validation: backend 178 passed / 6 skipped; Ruff passed; strict mypy passed for 70 application files; deterministic eval 12/12; frontend lint, typecheck, and 18 tests passed. Local Next.js production build attempts were blocked by Windows `EPERM` while creating protected output directories; run #48 had passed the production build on the earlier pushed revision. The run #50 retry-clock failure is fixed and pushed in `3d2a2c3`; run #52 did not start jobs because GitHub reports an account payment/spending-limit block, so current-head CI remains unverified.
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
- [ ] Public retrieval remains public-metadata-only by design; project comparison still uses paper abstracts only. OCR, cross-paper synthesis/claim verification, and staging RLS/operational gates remain open.

**Current status remains not production-ready.** See [docs/STATUS.md](docs/STATUS.md) for the full release gates.
