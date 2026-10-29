# Project Context

> Who this project is for, what problem it solves, and the operating constraints that shape every decision in this repo.

---

## What this project is

The **AI Paper Research Agent** is a multi-agent research assistant that turns "paper exists" into "here's why it matters to you" with zero manual effort. It continuously discovers academic papers from ArXiv and HuggingFace Daily Papers, summarises them with LLMs, and personalises the feed to each user's interests via Mem0 memory and vector-similarity ranking.

It is a **full-stack, AI-orchestrated, production-ready reference system** built on a strict four-layer architecture (see [ADR-001](./adr/0001-four-layer-architecture.md)).

## Who it is for

| Audience | What they get |
|----------|---------------|
| **End users** | A personalised, continuously-updated feed of research papers with AI summaries, difficulty ratings, a 3-D citation graph, and code links |
| **Developers** | A well-documented, four-layer codebase with CI, tests, and decision records to learn from or extend |
| **Operators** | A deployable stack (Docker Compose, Fly.io, Vercel) with caching, rate limiting, observability, and cost guardrails baked in |

## The problem it solves

Researchers and ML engineers are overwhelmed by the volume of new papers. The system removes the manual triage loop:

1. **Discovery** — pulls new papers daily from ArXiv and HuggingFace Daily Papers (see [FLOW.md](./FLOW.md) and [ADR-004](./adr/0004-daily-ingestion-scheduler.md)).
2. **Summarisation** — LLM-generated TL;DR, three key contributions, and a difficulty rating per paper (see [ADR-002](./adr/0002-llm-routing.md), [ADR-008](./adr/0008-summary-cost-cap.md)).
3. **Personalisation** — ranks papers against the user's learned interests (Mem0) and embedding similarity, falling back to keyword overlap when no profile exists.
4. **Presentation** — a streaming, interactive UI: paper feed, detail pages, and a 3-D citation graph (Semantic Scholar, cached — see [ADR-007](./adr/0007-citation-cache.md)).

## Non-goals (explicitly out of scope)

- **Hosted multi-tenancy** — this is a self-deployable reference product; each operator runs their own Supabase/LLM accounts.
- **Paper writing / literature reviews** — we summarise and rank papers; we do not generate papers or full reviews.
- **Desktop / mobile apps** — web-only (Next.js).
- **Closed model lock-in** — every LLM path routes through a provider-agnostic gateway (see [ADR-002](./adr/0002-llm-routing.md)).

## Operating constraints

These constraints recur in every decision in this repo and should be assumed unless an ADR says otherwise:

| Constraint | How the system honours it |
|------------|---------------------------|
| **LLM cost must be bounded** | Token caps per role, tiered model selection, summary fan-out cap ([ADR-008](./adr/0008-summary-cost-cap.md)), summary/citation caching ([ADR-007](./adr/0007-citation-cache.md)) |
| **Third-party rate limits are real** | Centralised retry with backoff ([ADR-005](./adr/0005-retry-strategy.md)), Supabase-backed caches ([ADR-007](./adr/0007-citation-cache.md)) |
| **Secrets never reach the client** | Four-layer boundaries ([ADR-001](./adr/0001-four-layer-architecture.md)); anon key only in the frontend |
| **Works on new and legacy Supabase** | JWT validation supports ES256/JWKS and HS256 fallback ([ADR-003](./adr/0003-jwt-validation.md)) |
| **Multi-instance safe** | Redis-backed rate limiting and run state ([ADR-006](./adr/0006-rate-limiting.md)) |
| **Observability is optional, never blocking** | Langfuse + Sentry are opt-in no-ops without keys ([ADR-009](./adr/0009-observability.md)) |
| **Failure is never silent** | Retriable errors are retried, non-retriable ones surface as structured HTTP errors; citation failures return empty graphs, never fabricated data |

## Repository map

| Path | Purpose |
|------|---------|
| `frontend/` | Next.js 15 app (feed, graph, paper detail, settings, auth) |
| `backend/` | FastAPI app: routers, LangGraph agents, services, middleware |
| `supabase/schema.sql` | Single source of truth for the database schema |
| `.github/workflows/` | CI pipeline and daily ingestion trigger (both manual dispatch only) |
| `docs/` | API, schema, deployment, developer guide, flows, context |
| `docs/adr/` | Architecture Decision Records |
| `.plans/` | Execution plans from improvement reviews (private, git-ignored) |
| `ARCHITECTURE.md` | System architecture overview and design decisions |
| `MEMORY.md` | The memory/personalisation subsystem deep-dive |
| `PLAN.md` | The original master project plan (phases 1–5) |

## Where to start reading

1. **[CONTEXT.md](./CONTEXT.md)** (this file) — the "why".
2. **[ARCHITECTURE.md](../ARCHITECTURE.md)** — the "how it fits together".
3. **[FLOW.md](./FLOW.md)** — the "what happens when" (data flows).
4. **[docs/adr/](./adr/README.md)** — the "why this specific way".
5. **[docs/DEVELOPER_GUIDE.md](./DEVELOPER_GUIDE.md)** — the "how to run and contribute".