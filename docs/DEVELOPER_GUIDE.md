# Developer Guide

> Everything you need to set up, run, and contribute to the AI Paper Research Agent.

---

## Table of Contents

- [Prerequisites](#prerequisites)
- [Quick Setup](#quick-setup)
- [Environment Variables](#environment-variables)
- [Running Locally](#running-locally)
  - [Option A: Docker Compose (Recommended)](#option-a-docker-compose-recommended)
  - [Option B: Run Services Individually](#option-b-run-services-individually)
- [Project Structure Walkthrough](#project-structure-walkthrough)
- [Database Setup](#database-setup)
- [Seeding Dev Data](#seeding-dev-data)
- [Running Tests](#running-tests)
- [Linting & Type Checking](#linting--type-checking)
- [Making Your First Change](#making-your-first-change)
- [Common Issues & Troubleshooting](#common-issues--troubleshooting)

---

## Prerequisites

| Tool | Minimum Version | Required? |
|------|----------------|-----------|
| Python | 3.12+ | Yes — for backend |
| Node.js | 20 LTS | Yes — for frontend |
| Docker | 24+ | Yes — for Docker Compose setup |
| Supabase Account | Free tier works | Yes — for auth, database, pgvector |
| OpenRouter API Key | — | Yes — primary LLM gateway |
| Git | 2.40+ | Yes — for version control |

**Optional API keys** (features degrade gracefully without them):
- `ANTHROPIC_API_KEY` — direct Claude fallback
- `OPENAI_API_KEY` — GPT fallback + embeddings
- `GOOGLE_API_KEY` — Gemini fallback
- `MISTRAL_API_KEY` — Mistral fallback
- `FIRECRAWL_API_KEY` — full paper text extraction
- `SEMANTIC_SCHOLAR_API_KEY` — citation graph (higher rate limits)
- `MEM0_API_KEY` — user memory personalisation

---

## Quick Setup

### 1. Clone the Repository

```bash
git clone <repo-url>
cd ai-paper-research-agent
```

### 2. Create Your .env File

```bash
cp .env.example .env
```

Then edit `.env` and fill in at minimum:

```
OPENROUTER_API_KEY=sk-or-v1-...
SUPABASE_URL=https://yourproject.supabase.co
SUPABASE_ANON_KEY=eyJ...
SUPABASE_SERVICE_ROLE_KEY=eyJ...
SUPABASE_JWT_SECRET=your-jwt-secret-from-supabase-dashboard
```

### 3. Set Up Supabase

1. Create a [Supabase](https://supabase.com) project (free tier works).
2. Go to the SQL Editor and run the migration from `supabase/schema.sql`. This creates:
   - `papers` table with pgvector embedding support
   - `user_papers` table for saved/dismissed papers
   - `user_prefs` table for user preferences
   - `match_papers()` function for vector similarity search
3. Get your `SUPABASE_JWT_SECRET` from **Project Settings > API > JWT Secret**.
4. Enable Google/GitHub OAuth in **Authentication > Providers** if desired.

### 4. Start the Stack

```bash
docker compose up --build
```

This starts three services:
- **frontend** — Next.js on `http://localhost:3000`
- **backend** — FastAPI on `http://localhost:8000`
- **redis** — Redis 7 on `localhost:6379`

### 5. Verify

- Open http://localhost:3000 — you should see the landing page
- Open http://localhost:8000/docs — the interactive Swagger docs should load
- Run `curl http://localhost:8000/api/health` — should return `{"status":"ok"}`

---

## Environment Variables

All environment variables are defined in `.env.example`. Here is what each does:

### LLM Providers

| Variable | Required | Purpose |
|----------|----------|---------|
| `OPENROUTER_API_KEY` | **Yes** | Primary LLM gateway for all agents |
| `ANTHROPIC_API_KEY` | No | Fallback for Claude models |
| `OPENAI_API_KEY` | No | Fallback for GPT models + embeddings |
| `GOOGLE_API_KEY` | No | Fallback for Gemini models |
| `MISTRAL_API_KEY` | No | Fallback for Mistral models |

### Data Sources

| Variable | Required | Purpose |
|----------|----------|---------|
| `FIRECRAWL_API_KEY` | No | Full paper text extraction |
| `SEMANTIC_SCHOLAR_API_KEY` | No | Citation graph data (higher rate limits) |

### Memory & Storage

| Variable | Required | Purpose |
|----------|----------|---------|
| `MEM0_API_KEY` | No | User memory personalisation |
| `SUPABASE_URL` | **Yes** | Postgres database + auth URL |
| `SUPABASE_ANON_KEY` | **Yes** | Public Supabase key (used by frontend) |
| `SUPABASE_SERVICE_ROLE_KEY` | **Yes** | Admin key (used by backend, bypasses RLS) |
| `SUPABASE_JWT_SECRET` | No* | Legacy HS256 JWT validation; new projects use JWKS |

### App

| Variable | Default | Purpose |
|----------|---------|---------|
| `APP_URL` | `http://localhost:3000` | Sent as HTTP-Referer to OpenRouter |
| `NEXT_PUBLIC_API_URL` | `http://localhost:8000` | Backend URL for frontend API calls |
| `REDIS_URL` | (empty) | Redis connection URL; falls back to in-memory store if not set |
| `ADMIN_API_KEY` | (empty) | Gate for `POST /api/internal/ingest` (scheduled ingestion) |
| `MAX_SUMMARIES_PER_RUN` | `20` | Per-run summary fan-out cap |

### Observability (all optional)

| Variable | Default | Purpose |
|----------|---------|---------|
| `LANGFUSE_PUBLIC_KEY` | (empty) | Langfuse tracing public key |
| `LANGFUSE_SECRET_KEY` | (empty) | Langfuse tracing secret key |
| `LANGFUSE_HOST` | `https://cloud.langfuse.com` | Langfuse host |
| `SENTRY_DSN` | (empty) | Sentry error-tracking DSN |
| `SENTRY_TRACES_SAMPLE_RATE` | `0.1` | Sentry trace sample rate |
| `APP_ENV` | `development` | Environment label for Sentry |

\* Only needed for legacy HS256-signed Supabase projects. New projects validate asymmetric (ES256) JWTs against the project's public JWKS endpoint.

The backend automatically detects the **frontend** variables prefixed with `NEXT_PUBLIC_` from the docker-compose environment blocks. `REDIS_URL` is used in production; in Docker Compose, the Redis service is automatically available at `redis://redis:6379`.

---

## Running Locally

### Option A: Docker Compose (Recommended)

The `docker-compose.yml` file orchestrates all three services:

```bash
docker compose up --build
```

Services:
| Service | URL | Description |
|---------|-----|-------------|
| Frontend | http://localhost:3000 | Next.js dev server with HMR |
| Backend | http://localhost:8000 | FastAPI with auto-reload (`--reload`) |
| Redis | localhost:6379 | Used by `RedisRunStore` for agent state |

The backend container uses **volume mounting** so changes to `backend/` source code are reflected immediately. The frontend uses the **dev mode** from the Dockerfile.

**Stopping:**
```bash
docker compose down
```

### Option B: Run Services Individually

If you prefer running without Docker:

#### Backend

```bash
cd backend
python -m venv .venv
source .venv/bin/activate  # or .venv\Scripts\activate on Windows
pip install -e ".[dev]"

# Start Redis separately (Docker or native)
docker run -d -p 6379:6379 redis:7-alpine

# Start the API
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

#### Frontend

```bash
cd frontend
npm install
npm run dev
```

#### Redis (if not using Docker)

```bash
docker run -d -p 6379:6379 --name paper-agent-redis redis:7-alpine
```

---

## Project Structure Walkthrough

```
ai-paper-research-agent/
├── frontend/                         # Next.js 15 application
│   ├── app/                          # App Router pages
│   │   ├── (auth)/login/             # Login/signup pages (Supabase Auth UI)
│   │   ├── feed/                     # Paper feed with search + SSE
│   │   ├── graph/                    # 3-D citation network
│   │   ├── paper/[id]/               # Single paper detail page
│   │   ├── settings/                 # User preferences
│   │   ├── page.tsx                  # Landing page
│   │   └── layout.tsx                # Root layout (providers, navbar)
│   ├── components/
│   │   ├── PaperCard.tsx             # Paper card with save/dismiss/share
│   │   ├── StreamingResponse.tsx     # SSE consumer for live agent progress
│   │   ├── ModelSelector.tsx         # LLM model picker dropdown
│   │   ├── SkeletonCard.tsx          # Loading placeholder
│   │   ├── Navbar.tsx                # Navigation bar
│   │   ├── Footer.tsx                # Page footer
│   │   ├── EmptyState.tsx            # Empty state placeholder
│   │   ├── ErrorBoundary.tsx         # React error boundary
│   │   └── QueryProvider.tsx         # TanStack Query provider
│   ├── lib/
│   │   ├── api.ts                    # API client (fetch wrappers)
│   │   ├── auth.ts                   # Supabase auth helpers
│   │   └── supabase.ts               # Supabase client singleton
│   ├── store/
│   │   └── useAppStore.ts            # Zustand store (model, prefs, loading)
│   ├── types/
│   │   └── index.ts                  # Shared TypeScript types
│   ├── package.json
│   └── Dockerfile
│
├── backend/                          # FastAPI application
│   ├── main.py                       # App entry point, middleware, router registration
│   ├── config.py                     # Pydantic settings (env var loading)
│   ├── dependencies.py               # FastAPI dependency injection (auth)
│   ├── logging_config.py             # Structured logging setup
│   ├── routers/                      # API endpoint handlers
│   │   ├── health.py                 # GET /api/health
│   │   ├── auth.py                   # POST /api/auth/token
│   │   ├── papers.py                 # CRUD for papers
│   │   ├── search.py                 # POST /api/search
│   │   ├── stream.py                 # GET /api/stream/{run_id} (SSE)
│   │   ├── graph.py                  # GET /api/graph/{paper_id}
│   │   ├── prefs.py                  # GET/POST /api/prefs
│   │   ├── pwc.py                    # GET /api/papers/{paper_id}/code
│   │   └── internal.py               # POST /api/internal/ingest (admin-key)
│   ├── agents/                       # LangGraph multi-agent layer
│   │   ├── orchestrator.py           # StateGraph: research → summary → memory
│   │   ├── research_agent.py         # ArXiv + HuggingFace data fetching
│   │   ├── summary_agent.py          # LLM-powered paper summarisation (capped)
│   │   ├── memory_agent.py           # User memory scoring + ranking
│   │   └── prompts/
│   │       └── summary_prompt.txt    # System prompt template for summary agent
│   ├── services/                     # External integrations + shared logic
│   │   ├── llm_router.py             # OpenRouter primary, direct provider fallbacks
│   │   ├── arxiv.py                  # ArXiv API wrapper
│   │   ├── huggingface.py            # HuggingFace Daily Papers API
│   │   ├── firecrawl.py              # Firecrawl full-text extraction (cached)
│   │   ├── papers_with_code.py       # Papers With Code API (GitHub repos)
│   │   ├── semantic_scholar.py       # Semantic Scholar citation data
│   │   ├── mem0_client.py            # Mem0 user memory client
│   │   ├── supabase_client.py        # Supabase async client singleton
│   │   ├── embeddings.py             # OpenAI text-embedding-3-small (retried)
│   │   ├── run_store.py              # In-memory + Redis-backed agent run state
│   │   ├── retry.py                  # Async retry with exponential backoff
│   │   ├── jwt_validator.py          # Supabase JWT: ES256 JWKS + HS256 fallback
│   │   ├── ingestion.py              # Daily ingestion pipeline (run_daily_fetch)
│   │   ├── citation_cache.py         # Supabase-backed citation cache (7-day TTL)
│   │   └── observability.py          # Langfuse tracing + Sentry init
│   ├── middleware/
│   │   ├── rate_limit.py             # Per-endpoint rate limiting (slowapi)
│   │   └── timing.py                 # X-Response-Time header middleware
│   ├── models/
│   │   └── schemas.py                # Pydantic models for all data shapes
│   ├── scripts/
│   │   ├── seed_dev.py               # Dev DB seeder (sample papers)
│   │   └── daily_fetch.py            # Cron script for daily paper ingestion
│   └── Dockerfile
│
├── supabase/
│   └── schema.sql                    # Database migration (tables, indexes, functions)
│
├── .github/workflows/
│   ├── ci.yml                        # GitHub Actions CI pipeline (manual dispatch)
│   └── daily_fetch.yml               # Daily ingestion trigger (manual dispatch)
│
├── docker-compose.yml                # Local development stack
├── docker-compose.prod.yml           # Production Docker deployment
├── .env.example                      # Environment variable template
├── PLAN.md                           # Master project plan
├── ARCHITECTURE.md                   # Architecture documentation
├── MEMORY.md                         # Memory subsystem deep-dive
├── README.md                         # Project overview
└── docs/
    ├── API.md                        # Full API reference
    ├── CONTEXT.md                    # Project context & constraints
    ├── DEVELOPER_GUIDE.md            # This file
    ├── DEPLOYMENT.md                 # Deployment guide
    ├── FLOW.md                       # End-to-end data flows
    ├── SCHEMA.md                     # Database schema reference
    └── adr/                          # Architecture Decision Records
```

### Layer Boundaries

The project enforces a strict four-layer architecture:

1. **Layer 1 — Frontend** (`frontend/`): Never accesses the database directly. Communicates only via HTTP/SSE to the backend.
2. **Layer 2 — Backend** (`backend/routers/`): REST API gateway. Validates JWT, applies rate limits, delegates to agents.
3. **Layer 3 — Agents** (`backend/agents/`): LangGraph orchestration. Never imports from routers. Uses services for all external calls.
4. **Layer 4 — Services** (`backend/services/`): External API wrappers. Never imports from agents or routers.

---

## Database Setup

### Apply the Migration

The Supabase schema is defined in `supabase/schema.sql`. Run it in the Supabase SQL Editor:

1. Open your Supabase project dashboard
2. Go to **SQL Editor**
3. Paste the contents of `supabase/schema.sql`
4. Click **Run**

This creates the following tables:

| Table | Purpose |
|-------|---------|
| `papers` | Paper metadata with pgvector embedding column (1536-dim) |
| `user_papers` | Junction table for saved/dismissed papers |
| `user_prefs` | Per-user LLM model preference and research interests |
| `citations` | Cached Semantic Scholar citation edges (feed + graph) |
| `crawled_content` | Cached Firecrawl full-text extractions |

It also creates:
- `match_papers()` — PostgreSQL function for vector similarity search
- `idx_papers_embedding` — IVFFlat index on the embedding column
- `idx_papers_published_at` — B-tree index for chronological sorting
- `idx_user_papers_feed` — compound index for feed queries

---

## Seeding Dev Data

For local development, you can populate the database with sample papers:

```bash
cd backend
python -m backend.scripts.seed_dev
```

This inserts 5 sample papers (covering transformer surveys, diffusion models, RLHF, scaling laws, multimodal models) with embeddings generated via OpenAI's `text-embedding-3-small`. The script is idempotent — running it multiple times will not duplicate papers.

---

## Running Tests

### Backend (pytest)

```bash
cd backend
pip install -e ".[dev]"  # if not already installed
pytest
```

### Frontend (vitest)

```bash
cd frontend
npm test
```

### CI Pipeline

The CI pipeline is defined in `.github/workflows/ci.yml` and runs on pushes, pull requests, and manual dispatch:
- **Backend job:** `ruff check`, `mypy`, `pytest`
- **Frontend job:** `npm run lint` (ESLint), `npm run typecheck` (tsc), `npm run build`
- **Docker job:** `docker compose build`

---

## Linting & Type Checking

### Backend

```bash
cd backend

# Lint (Ruff)
ruff check .

# Type check (mypy, strict mode)
mypy .

# Auto-fix lint issues
ruff check . --fix
```

Configuration: `pyproject.toml` sections `[tool.ruff]` and `[tool.mypy]`.

### Frontend

```bash
cd frontend

# Lint (ESLint with next/core-web-vitals)
npm run lint

# Type check
npm run typecheck

# Auto-fix lint issues
npm run lint -- --fix
```

---

## Making Your First Change

Here is a complete example workflow for adding a new feature:

### Step 1: Plan

Read `PLAN.md` and `ARCHITECTURE.md` to understand where your change fits in the four-layer architecture.

### Step 2: Create a Branch

```bash
git checkout -b feature/my-new-feature
```

### Step 3: Make Changes

For example, adding a new API endpoint:

1. **Define the schema** in `backend/models/schemas.py` (Pydantic models)
2. **Add the router** in `backend/routers/` (FastAPI endpoint)
3. **Register the router** in `backend/main.py` with `app.include_router()`
4. **Add the frontend API client** in `frontend/lib/api.ts` (fetch wrapper)
5. **Add the TypeScript type** in `frontend/types/index.ts`
6. **Build the UI component** in `frontend/components/`

### Step 4: Verify Locally

```bash
# Start the dev stack
docker compose up --build

# Run backend checks
cd backend && ruff check . && mypy . && pytest

# Run frontend checks
cd frontend && npm run lint && npm run typecheck && npm test
```

### Step 5: Commit

```bash
git add .
git commit -m "[backend] add endpoint for feature X"
git commit -m "[frontend] add UI for feature X"
```

Follow the convention: `[layer] brief description`.

### Step 6: Push and Open PR

```bash
git push origin feature/my-new-feature
# Create PR on GitHub
```

The CI pipeline will run automatically and report pass/fail.

---

## Common Issues & Troubleshooting

### "OPENROUTER_API_KEY not configured"

Set `OPENROUTER_API_KEY` in your `.env` file. This is required. Get a key from [openrouter.ai/keys](https://openrouter.ai/keys).

### "JWT secret not configured"

Set `SUPABASE_JWT_SECRET` in your `.env` file for legacy HS256-signed projects. Find it in your Supabase dashboard under **Project Settings > API > JWT Secret**. New Supabase projects sign tokens asymmetrically (ES256) and validate against the project's JWKS endpoint, so `SUPABASE_JWT_SECRET` is not required there — but `SUPABASE_URL` must be set.

### "Supabase connection failed"

Check that `SUPABASE_URL` and `SUPABASE_SERVICE_ROLE_KEY` are correct. Verify your Supabase project is active (not paused on the free tier).

### "Redis unavailable, falling back to in-memory store"

This is logged when Redis is not reachable. The backend will use an in-memory `RunStore` instead. Run states will be lost when the backend restarts. To fix, ensure the Redis container is running:

```bash
docker compose up redis
```

Or set `REDIS_URL` to your Redis instance if running services individually.

### Port conflicts

If ports 3000 or 8000 are already in use:

```bash
# Find what's using the port (Windows)
netstat -ano | findstr :3000

# Or change ports in docker-compose.yml
# frontend -> "3001:3000"
# backend -> "8001:8000"
```

### Import errors after pulling

If you see `ModuleNotFoundError` after pulling changes:

```bash
# Backend
cd backend
pip install -e ".[dev]"

# Frontend
cd frontend
npm install
```

### Docker build fails on Windows

Ensure:
- Docker Desktop is running in Linux containers mode (not Windows containers)
- Line endings are LF (not CRLF) in shell scripts and Dockerfiles
- The `.env` file is properly formatted (no trailing spaces, no quotes around values)

### Pre-commit hook failures

If you have pre-commit hooks set up and they fail, run the checks manually to see detailed output:

```bash
cd backend
ruff check .
mypy .
pytest

cd ../frontend
npm run lint
npm run typecheck
```

### Streaming not working

For SSE to work in Docker, ensure the backend's `--reload` flag is not interfering. The dev Dockerfile uses `uvicorn main:app --reload` which should be fine. If streams disconnect immediately, check that your reverse proxy (if any) is not buffering the response.

### Papers not showing in feed

1. Run the seed script: `python -m backend.scripts.seed_dev`
2. Check `http://localhost:8000/api/health` — the `supabase` check should be `true`
3. Verify the JWT token is valid by calling `POST /api/auth/token`
4. Check browser console for CORS errors (allowed origins are `http://localhost:3000`)
