# Project Context

> Who this project is for, what problem it solves, and the operating constraints that shape every decision in this repo.

---

## What this project is

**Zenith** is a research workspace for discovering and understanding academic papers. It ingests ArXiv and Hugging Face Daily Papers, supports paper projects, ranks and summarizes papers, and provides extractive research evidence with source references. Provider behavior and live ingestion still require staging verification.

It is a **full-stack reference application under active development**, built around the four-layer architecture in [ADR-001](./adr/0001-four-layer-architecture.md). Local backend, frontend, and deterministic evaluation gates pass. Current-head remote CI and Docker image builds are unverified; the product is **not production-ready** until staging migrations/RLS, distributed recovery, provider behavior, backup restore, monitoring, and deployment are verified. See the live [shipment status](./STATUS.md).

## Who it is for

| Audience | What they get |
|----------|---------------|
| **End users** | A paper feed, project libraries, summaries, citation graph, extractive answers, evidence map, provisional cross-paper synthesis, and non-executing implementation briefs |
| **Developers** | A four-layer codebase with API documentation, tests, CI, and decision records |
| **Operators** | Docker/Fly/Vercel configuration and readiness checks; live deployment and operational recovery still require staging validation |

## The problem it solves

Researchers and ML engineers are overwhelmed by the volume of new papers. Zenith aims to reduce the manual triage loop:

1. **Discovery** — pulls new papers daily from ArXiv and HuggingFace Daily Papers (see [FLOW.md](./FLOW.md) and [ADR-004](./adr/0004-daily-ingestion-scheduler.md)).
2. **Summarisation** — LLM-generated TL;DR, three key contributions, and a difficulty rating per paper (see [ADR-002](./adr/0002-llm-routing.md), [ADR-008](./adr/0008-summary-cost-cap.md)).
3. **Personalisation** — ranks papers against user interests and available embeddings, with deterministic retrieval fallbacks.
4. **Research and implementation** — returns extractive evidence from attached project papers, provisional claim synthesis over public abstracts, and source-grounded implementation briefs. Model-reviewed synthesis is not independently verified and does not reproduce code.
5. **Presentation** — a web UI for the feed, paper details, project workspace, streaming research runs, and citation graph.

## Non-goals (explicitly out of scope)

- **Organization-wide collaboration** — project membership and email invitation flows are implemented locally; delivery and acceptance remain unverified in staging, and account discovery/complete collaboration workflows remain incomplete.
- **Independently verified scientific synthesis or reproduction** — bounded abstract-level synthesis is available with provisional model-reviewed evidence labels; implementation briefs are not experimental reproductions.
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
| **Multi-instance design** | Redis-backed coordination and Postgres-backed run/checkpoint persistence; multi-instance recovery remains to be verified against shared staging services ([ADR-006](./adr/0006-rate-limiting.md)) |
| **Observability is optional, never blocking** | Langfuse + Sentry are opt-in no-ops without keys ([ADR-009](./adr/0009-observability.md)) |
| **Failures are surfaced where handled** | API errors are structured and extractive research abstains when matching evidence is absent; provider fallbacks and outage behavior still need staging validation |

## Repository map

| Path | Purpose |
|------|---------|
| `frontend/` | Next.js 15 app (feed, graph, paper detail, settings, auth) |
| `backend/` | FastAPI app: routers, LangGraph agents, services, middleware |
| `supabase/migrations/` | Ordered schema history; apply to staging and verify before production |
| `supabase/schema.sql` | Schema reference snapshot; not a substitute for versioned migrations |
| `.github/workflows/` | Pull-request/push CI gates and scheduled/manual workflows |
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
