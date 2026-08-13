# Architecture Decision Records

This directory records the significant architectural decisions for the AI Paper Research Agent. Each ADR captures the **context**, the **decision**, and its **consequences**, so future contributors understand *why* the system is shaped the way it is.

Status values: **Accepted** | **Superseded by ADR-XXX** | **Rejected**

## Index

| ADR | Decision | Status |
|-----|----------|--------|
| [001](./0001-four-layer-architecture.md) | Four-layer architecture (Next.js → FastAPI → LangGraph → External) | Accepted |
| [002](./0002-llm-routing.md) | OpenRouter-primary LLM routing with direct provider fallbacks | Accepted |
| [003](./0003-jwt-validation.md) | Supabase JWT validation: ES256 JWKS with HS256 legacy fallback | Accepted |
| [004](./0004-daily-ingestion-scheduler.md) | Daily ingestion triggered via internal authenticated endpoint | Accepted |
| [005](./0005-retry-strategy.md) | Centralised async retry with exponential backoff for all external calls | Accepted |
| [006](./0006-rate-limiting.md) | Redis-backed rate limiting via slowapi | Accepted |
| [007](./0007-citation-cache.md) | Supabase-backed citation and crawl cache (Semantic Scholar / Firecrawl) | Accepted |
| [008](./0008-summary-cost-cap.md) | Summary fan-out capped per run to bound LLM cost | Accepted |
| [009](./0009-observability.md) | Optional Langfuse tracing and Sentry error tracking | Accepted |

## Template

Each ADR follows this shape:

- **Status** — lifecycle state
- **Context** — the forces, constraints, or problems that motivated the decision
- **Decision** — what was chosen and where it lives in the code
- **Consequences** — trade-offs, follow-ups, and what to revisit later

## Convention

- New ADRs are numbered sequentially and linked from this index.
- Superseded ADRs are marked in the index and point to the ADR that replaced them.
- Small, reversible choices do not need an ADR; ADRs are for decisions that are costly to reverse or that others will likely revisit.
