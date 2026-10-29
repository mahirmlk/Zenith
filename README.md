# AI Paper Research Agent

> **Project Status:** Phase 1–5 Complete — All features implemented and ready for production

An intelligent agent that discovers, ingests, summarises, and personalises academic papers from ArXiv and HuggingFace Daily Papers. It uses a multi-agent LangGraph orchestration layer to continuously feed you research that matters to you.

**Core value proposition:** Zero effort from "paper exists" to "here's why it matters to you."

---

## Features

### Paper Discovery & Ingestion
- **Multi-source discovery** — Fetches papers from ArXiv (official API) and HuggingFace Daily Papers (community-curated highlights)
- **Automatic deduplication** — Cross-references by paper ID to prevent duplicates across sources
- **Daily cron ingestion** — `daily_fetch.py` script for scheduled paper harvesting with batching and embeddings
- **Dev data seeding** — `seed_dev.py` for quick local development with 5 sample papers

### AI-Powered Summarisation
- **LLM-generated summaries** — Each paper gets a TL;DR, 3 key contributions, and a difficulty rating (introductory/intermediate/expert)
- **Multi-model support** — Route through OpenRouter (primary) with direct provider fallbacks to Anthropic, OpenAI, Google Gemini, and Mistral
- **Cost guardrails** — Token limits per agent role, summary caching in Supabase, tiered model pricing

### Personalisation Engine
- **Mem0 user memory** — Learns user interests from saves, dismissals, and browsing behaviour
- **Relevance scoring** — Ranks papers against user profile using embedding similarity (text-embedding-3-small)
- **Interest-based keyword matching** — Falls back to keyword overlap when no Mem0 profile exists

### Live Streaming
- **SSE-powered agent progress** — Watch the Research Agent, Summary Agent, and Memory Agent work in real time via Server-Sent Events
- **Event-driven UI** — Frontend `StreamingResponse` component renders live status updates
- **Timeout handling** — 30-second inactivity timeout with graceful error messaging

### Interactive UI
- **Paper feed** — Scrollable personalised feed with save, dismiss, and share actions
- **Paper detail** — Full abstract, AI summary, key contributions, difficulty badge, and code links
- **3-D Citation Graph** — Three.js force-directed graph (React Three Fiber) powered by Semantic Scholar API
- **Model selector** — Dropdown to choose from 9 LLM models (Claude, GPT-4o, Gemini, Mistral, Llama, DeepSeek, etc.)
- **Responsive design** — Tailwind CSS, loading skeletons, error boundaries, empty states

### Auth & Security
- **Supabase Auth** — Email/password + OAuth (Google, GitHub)
- **JWT validation** — ES256 JWKS with legacy HS256 fallback, validated on every request
- **Rate limiting** — Redis-backed per-endpoint limits via slowapi (10/min search, 20/min stream, 60/min default)
- **CORS protection** — Whitelisted origins for the frontend domain
- **Admin-gated ingestion** — Internal trigger protected by `X-Admin-Key`

### Papers With Code Integration
- **GitHub repository discovery** — Fetches associated code repositories via Papers With Code API
- **Star counts** — Displays GitHub stars for each repository
- **Built into paper detail** — Code repositories shown on the paper detail page

### Developer Experience
- **Docker Compose** — One-command local dev environment (`docker compose up --build`)
- **GitHub Actions CI (manual)** — Linting (ruff, mypy, eslint), type checking, tests, and Docker builds, run on demand to keep Actions costs down
- **Comprehensive docs** — API reference, architecture overview, developer guide, and deployment guide
- **Structured logging** — Timestamped, level-tagged logs for all services

---

## Quick Start

The easiest way to run the full stack locally is with Docker Compose:

```bash
# 1. Clone the repository
git clone <repo-url>
cd ai-paper-research-agent

# 2. Copy environment variables
cp .env.example .env
# Edit .env and fill in your API keys (at minimum: OPENROUTER_API_KEY, SUPABASE_*)

# 3. Set up Supabase
# - Create a project at supabase.com
# - Run supabase/schema.sql in the SQL Editor
# - Copy credentials to .env

# 4. Start all services
docker compose up --build
```

- **Frontend:** http://localhost:3000
- **Backend API:** http://localhost:8000
- **API Docs (Swagger):** http://localhost:8000/docs
- **Redis:** localhost:6379

See the **[Developer Guide](./docs/DEVELOPER_GUIDE.md)** for detailed setup instructions, prerequisites, and troubleshooting.

---

## Environment Variables

Copy `.env.example` to `.env` and configure the following:

| Category | Variable | Required | Description |
|----------|----------|----------|-------------|
| **LLM Providers** | `OPENROUTER_API_KEY` | **Yes** | Primary LLM gateway |
| | `ANTHROPIC_API_KEY` | No | Claude direct fallback |
| | `OPENAI_API_KEY` | No | GPT fallback + embeddings |
| | `GOOGLE_API_KEY` | No | Gemini fallback |
| | `MISTRAL_API_KEY` | No | Mistral fallback |
| **Data Sources** | `FIRECRAWL_API_KEY` | No | Full paper crawling |
| | `SEMANTIC_SCHOLAR_API_KEY` | No | Citation graph (higher rate limits) |
| **Memory & Storage** | `MEM0_API_KEY` | No | User memory personalisation |
| | `SUPABASE_URL` | **Yes** | Database & auth |
| | `SUPABASE_ANON_KEY` | **Yes** | Public Supabase key |
| | `SUPABASE_SERVICE_ROLE_KEY` | **Yes** | Admin Supabase key |
| | `SUPABASE_JWT_SECRET` | No* | JWT validation (HS256 fallback; new projects use JWKS) |
| **App** | `APP_URL` | No | Frontend URL (sent to OpenRouter) |
| | `NEXT_PUBLIC_API_URL` | No | Public API URL for frontend |
| | `REDIS_URL` | No | Redis connection string (falls back to in-memory) |
| | `ADMIN_API_KEY` | No | Gate for `POST /api/internal/ingest` |
| | `MAX_SUMMARIES_PER_RUN` | No | Per-run summary fan-out cap (default 20) |
| **Observability** | `LANGFUSE_PUBLIC_KEY` | No | Langfuse tracing (requires secret too) |
| | `LANGFUSE_SECRET_KEY` | No | Langfuse tracing secret |
| | `LANGFUSE_HOST` | No | Langfuse host (default `https://cloud.langfuse.com`) |
| | `SENTRY_DSN` | No | Sentry error tracking |
| | `SENTRY_TRACES_SAMPLE_RATE` | No | Sentry trace sample rate (default 0.1) |
| | `APP_ENV` | No | Environment label for Sentry (default `development`) |

\* `SUPABASE_JWT_SECRET` is only needed for legacy HS256-signed Supabase projects; new projects validate against the public JWKS endpoint.

See `.env.example` for the full template.

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| **Frontend** | Next.js 15, TypeScript, Tailwind CSS, Three.js (React Three Fiber), React Query, Zustand |
| **Backend** | FastAPI, Python 3.12, Uvicorn, SSE (sse-starlette), slowapi |
| **AI Orchestration** | LangGraph 0.2+, LangChain |
| **Memory & Storage** | Supabase (Postgres + pgvector), Mem0, Redis |
| **External APIs** | OpenRouter, Firecrawl, ArXiv, HuggingFace, Semantic Scholar, Papers With Code |
| **DevOps** | Docker, Docker Compose, GitHub Actions |

---

## Architecture

The system follows a four-layer architecture:

```
Next.js Frontend → FastAPI Backend → LangGraph Orchestration → External Services
```

For a detailed breakdown of the architecture, data model, LLM routing strategy, and deployment options, see **[ARCHITECTURE.md](./ARCHITECTURE.md)**.

For the full API reference, see **[docs/API.md](./docs/API.md)**.

---

## Documentation

| Document | Purpose |
|----------|---------|
| [README.md](./README.md) | Project overview and quick start |
| [ARCHITECTURE.md](./ARCHITECTURE.md) | System architecture, data flow, design decisions |
| [docs/CONTEXT.md](./docs/CONTEXT.md) | Project context, goals, and operating constraints |
| [docs/FLOW.md](./docs/FLOW.md) | End-to-end data flows (search, ingestion, graph, auth, memory) |
| [docs/API.md](./docs/API.md) | Complete API reference with examples |
| [docs/SCHEMA.md](./docs/SCHEMA.md) | Database schema and PgSQL functions |
| [docs/DEVELOPER_GUIDE.md](./docs/DEVELOPER_GUIDE.md) | Setup, testing, contributing, troubleshooting |
| [docs/DEPLOYMENT.md](./docs/DEPLOYMENT.md) | Production deployment (Fly.io, Vercel, Docker) |
| [docs/adr/](./docs/adr/README.md) | Architecture Decision Records |
| [MEMORY.md](./MEMORY.md) | Memory/personalisation subsystem deep-dive |
| [PLAN.md](./PLAN.md) | Master project plan (all 5 phases) |

---

## Project Structure

```
.
├── backend/          # FastAPI backend
│   ├── main.py       # App entry point, middleware, router registration
│   ├── routers/      # API endpoints (9 routers incl. internal ingest)
│   ├── agents/       # LangGraph agents (research, summary, memory, orchestrator)
│   ├── services/     # External integrations + shared logic (15 services)
│   ├── middleware/    # Rate limiting, response timing
│   └── models/       # Pydantic schemas
├── frontend/         # Next.js frontend
│   ├── app/          # App Router pages (feed, graph, paper, settings, login)
│   ├── components/   # Reusable UI components
│   ├── lib/          # API client, auth helpers
│   └── store/        # Zustand state management
├── supabase/         # Database migrations & schema
├── docs/             # Documentation (context, flows, API, schema, deployment)
│   └── adr/          # Architecture Decision Records
├── .github/workflows/# CI + daily ingestion triggers (manual dispatch)
├── docker-compose.yml
└── docker-compose.prod.yml
```

---

## License

[MIT](LICENSE)
