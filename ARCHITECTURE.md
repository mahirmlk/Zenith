# AI Paper Research Agent — Architecture

> Four-layer architecture: Next.js frontend → FastAPI backend → LangGraph orchestration → External services

---

## 1. System Context

The AI Paper Research Agent continuously discovers, ingests, summarises, and personalises academic papers from ArXiv and HuggingFace Daily Papers. Users interact via a rich Next.js UI featuring a paper feed and a 3-D citation graph. A LangGraph multi-agent system orchestrates three specialised agents, uses Firecrawl to pull full paper text, stores user memory in Mem0/Supabase, and routes LLM calls through OpenRouter.

**Core value proposition:** Zero effort from "paper exists" to "here's why it matters to you."

---

## 2. High-Level Architecture

```
┌──────────────────────────────────────────────┐
│          Next.js Frontend                     │
│  Paper feed · Three.js graph · Auth UI        │
└─────────────────┬────────────────────────────┘
                  │ HTTP / SSE
┌─────────────────▼────────────────────────────┐
│          FastAPI Backend                      │
│  API gateway · SSE streaming · Auth (JWT)     │
│  Rate limiting · Response timing              │
└─────────────────┬────────────────────────────┘
                  │
┌─────────────────▼────────────────────────────┐
│        LangGraph Orchestration Layer          │
│  ┌────────────┐  ┌────────────┐  ┌─────────┐ │
│  │ Research   │  │ Summary    │  │ Memory  │ │
│  │ Agent      │  │ Agent      │  │ Agent   │ │
│  │ (discover) │  │ (simplify) │  │(person.)│ │
│  └─────┬──────┘  └─────┬──────┘  └────┬────┘ │
└────────┼───────────────┼──────────────┼──────┘
         │               │              │
┌────────▼───────────────▼──────────────▼──────┐
│             External Services                 │
│  Firecrawl │ ArXiv+HF │ OpenRouter │ S2+PWC   │
│  Mem0+Supabase │ Redis (run state)            │
└──────────────────────────────────────────────┘
```

---

## 3. Layer Details

### Layer 1 — Next.js Frontend

| Concern | Decision |
|---------|----------|
| Framework | Next.js 15 (App Router) |
| Language | TypeScript |
| Styling | Tailwind CSS |
| 3D Graphics | Three.js / React Three Fiber |
| State | React Query (server) + Zustand (client) |
| Auth UI | Supabase Auth (email/password + OAuth) |

**Pages:**
- `/` — Landing / marketing page
- `/feed` — Personalised paper feed with search, SSE progress, model selector, save/dismiss
- `/graph` — 3-D citation network (force-directed graph)
- `/paper/[id]` — Paper detail with AI summary, contributions, difficulty, code repos
- `/login` · `/signup` — Supabase Auth UI
- `/settings` — User preferences (model selection, research interests)

**Key Components:**
- `PaperCard` — Title, authors, AI TL;DR, relevance score, save/dismiss/share actions
- `CitationGraph` — Force-directed Three.js graph; nodes=papers, edges=citations; click to navigate
- `StreamingResponse` — SSE consumer for live agent progress (research → summary → memory)
- `ModelSelector` — Dropdown for 9 LLM models (Claude, GPT-4o, Gemini, Mistral, Llama, DeepSeek, etc.)
- `SkeletonCard` — Loading placeholder with shimmer animation
- `Navbar` / `Footer` — Shared layout components
- `EmptyState` — Empty state placeholder for no-results states
- `ErrorBoundary` — React error boundary for graceful failure handling
- `QueryProvider` — TanStack Query provider wrapping the app

**Supported LLM Models (ModelSelector):**
- `anthropic/claude-opus-4`
- `anthropic/claude-sonnet-4-5`
- `openai/gpt-4o`
- `openai/gpt-4o-mini`
- `google/gemini-2.5-pro`
- `google/gemini-2.0-flash`
- `mistralai/mistral-large`
- `meta-llama/llama-3.3-70b-instruct`
- `deepseek/deepseek-r1`

---

### Layer 2 — FastAPI Backend

| Concern | Decision |
|---------|----------|
| Framework | FastAPI |
| Runtime | Python 3.12, Uvicorn |
| Streaming | Server-Sent Events (sse-starlette) |
| Auth | Supabase JWT validation (ES256 JWKS, HS256 legacy fallback) |
| Rate Limiting | slowapi, Redis-backed (per-endpoint limits) |
| CORS | `allow_origins=["http://localhost:3000"]` |
| Logging | Structured logging with timestamps and module names |
| Observability | Langfuse tracing (LangGraph) + Sentry error tracking |

**Registered Routers (8 total):**
```
GET    /api/health                         # Health check (health.router)
POST   /api/auth/token                     # Validate Supabase JWT (auth.router)
GET    /api/papers                         # List papers with optional ?q= filter (papers.router)
GET    /api/papers/{paper_id}              # Single paper detail (papers.router)
POST   /api/papers/{paper_id}/save         # Save/dismiss paper + Mem0 memory (papers.router)
DELETE /api/papers/{paper_id}/save         # Unsave paper (papers.router)
POST   /api/search                         # Trigger research pipeline (search.router)
GET    /api/stream/{run_id}                # SSE stream of agent progress (stream.router)
GET    /api/graph/{paper_id}               # Citation graph data (S2, cached in Supabase) (graph.router)
GET    /api/prefs                          # Get user preferences (prefs.router)
POST   /api/prefs                          # Update user preferences (prefs.router)
GET    /api/papers/{paper_id}/code         # Papers With Code repos (pwc.router)
POST   /api/internal/ingest                # Trigger daily ingestion (internal.router, admin key)
```

**Rate Limits** (enforced by slowapi, backed by Redis when `REDIS_URL` is set so limits are global across instances):
| Endpoint | Limit |
|----------|-------|
| `/api/search` | 10 req / minute |
| `/api/stream/*` | 20 req / minute |
| `/api/health` | Exempt (unlimited) |
| All other endpoints | 60 req / minute (default) |

**Middleware Stack:**
1. `CORSMiddleware` — Allows frontend origin
2. `SlowAPIMiddleware` — Rate limiting via slowapi (Redis-backed when `REDIS_URL` set)
3. `TimingMiddleware` — Adds `X-Response-Time` header
4. Auth middleware — Decodes and validates Supabase JWT (ES256 via JWKS, HS256 legacy fallback), attaches `request.state.user`
5. Rate limit exception handler — Returns 429 JSON response

**SSE Events:**
- `agent_step` — Live progress from each agent (research, summary, memory, orchestrator)
- `result` — Final ranked paper list with `PaperSearchResult` schema
- `error` — Pipeline failure or 30-second inactivity timeout

---

### Layer 3 — LangGraph Orchestration

**Graph Topology:**
```
START
  └─► Research Agent ──► ArXiv API + HuggingFace Daily Papers
         │                    (deduplication by paper ID)
         ▼
      Summary Agent   ──► LLM (via OpenRouter, with retry + exponential backoff)
         │                    (generates TL;DR, contributions, difficulty)
         ▼
      Memory Agent    ──► Mem0 profile + embedding similarity ranking
         │                    (keyword fallback if no Mem0 profile)
         ▼
        END
```

The graph is compiled with `langgraph.graph.StateGraph` and uses a typed `OrchestratorState` TypedDict.

**Agents:**

- **Orchestrator** (`agents/orchestrator.py`) — Initialises the state graph, invokes agents sequentially, streams all collected steps, and returns `PaperSearchResult`. Updates the run store on completion.

- **Research Agent** (`agents/research_agent.py`) — Discovers papers via ArXiv API (`arxiv` Python lib) and HuggingFace Daily Papers API (`httpx`). Deduplicates by paper ID. Uses async retry with exponential backoff for all API calls. Emits SSE steps for `fetching_arxiv`, `arxiv_fetched`, `fetching_huggingface`, `huggingface_fetched`, and `deduplication_complete`.

- **Summary Agent** (`agents/summary_agent.py`) — Generates AI summaries using the configured LLM. Reads its system prompt from `agents/prompts/summary_prompt.txt`. Wraps paper content in `<paper_content>` delimiters and instructs the model to treat it as untrusted data (prompt-injection guard). Handles JSON extraction from LLM responses (supports direct JSON, markdown fences, and partial JSON). Uses `async_retry` for LLM calls (transient API/rate-limit errors). Caps per-request LLM fan-out to `MAX_SUMMARIES_PER_RUN` (default 20); overflow papers get an abstract-preview fallback with no LLM call. Graceful degradation: returns truncated abstract as fallback on failure.

- **Memory Agent** (`agents/memory_agent.py`) — Loads user profile from Mem0, computes relevance scores using embedding similarity (cosine similarity on `text-embedding-3-small` vectors). Falls back to keyword overlap matching when no Mem0 profile exists. Returns papers sorted by relevance score descending.

---

### Layer 4 — External Integrations

| Service | Role | Integration | Auth | Retry |
|---------|------|-------------|------|-------|
| **ArXiv API** | Paper discovery | `arxiv` Python lib (sync, run in executor) | No | Yes (3 retries, exp backoff) |
| **HuggingFace Daily Papers** | Curated highlights | REST API (`httpx`) | No | Yes (3 retries) |
| **OpenRouter** | Primary LLM gateway | OpenAI-compatible endpoint (`langchain-openai`) | API key | Yes (transient errors at call site) |
| **Anthropic (direct)** | Claude fallback | `langchain-anthropic` | API key | Yes (transient errors at call site) |
| **OpenAI (direct)** | GPT fallback + embeddings | `langchain-openai` + direct `httpx` for embeddings | API key | Yes (transient errors at call site) |
| **Google Gemini (direct)** | Gemini fallback | `langchain-google-genai` | API key | Yes (transient errors at call site) |
| **Mistral (direct)** | Mistral fallback | `langchain-mistralai` | API key | Yes (transient errors at call site) |
| **Firecrawl** | Full paper crawl | `firecrawl-py` SDK | API key | No (cached in Supabase, keyed by paper ID) |
| **Mem0** | User memory | `mem0` Python client | API key | No |
| **Supabase** | Auth + vector DB + relational data | `supabase-py` async client | Service role key | No |
| **Semantic Scholar** | Citation graph | S2 REST API (`httpx`) | Optional API key | Yes (3 retries), edges cached in Supabase |
| **Papers With Code** | GitHub repos for papers | PWC REST API (`httpx`) | No | No (silent degradation) |
| **Redis** | Agent run state + global rate limiting | `redis.asyncio` (optional) | No (optional `REDIS_URL`) | No |

Retry is kept separate from the provider fallback chain: `async_retry` handles
same-provider transient failures (connect/read timeouts, 5xx, rate limits on
any of the LLM/embedding SDKs), while `llm_router` handles provider swapping.
`services/retry.py` matches transient errors by exception class (builtin +
`httpx` errors, plus vendor SDK names such as `APIConnectionError`,
`RateLimitError`, `InternalServerError`).

---

## 4. Data Flow

### Paper Ingestion Flow
```
1. Daily scheduler triggers the pipeline:
   - Fly.io scheduled machine running `python -m scripts.daily_fetch`
     (see backend/fly.toml), or
   - GitHub Actions cron job (.github/workflows/daily_fetch.yml) calling
     POST /api/internal/ingest with the X-Admin-Key header.
2. Research fetches ArXiv + HF APIs (with async retry)
3. New papers are deduplicated by paper ID (cross-source)
4. Summary Agent generates TL;DR, key contributions, and difficulty via LLM
   (capped at MAX_SUMMARIES_PER_RUN per run)
5. Embedding pipeline chunks abstract and stores vector in Supabase (text-embedding-3-small, 1536-dim)
6. Memory Agent scores papers against user profile (embedding similarity or keyword fallback)
7. Orchestrator merges and ranks; results stream to frontend via SSE
```

### User Interaction Flow
```
1. User visits /feed
2. Frontend requests GET /api/papers (JWT attached via Authorization header)
3. Backend fetches ranked papers from Supabase user_papers + Mem0 profile
4. User enters a search query and clicks "Search"
5. Frontend POSTs to /api/search, receives run_id
6. Frontend opens EventSource to GET /api/stream/{run_id}
7. Orchestrator runs Research → Summary → Memory pipeline
8. Live steps stream to frontend; StreamingResponse component renders progress
9. Final result renders as PaperCards in the feed
```

### Agent Pipeline Flow (with retry)
```
POST /api/search
  ├─► Creates RunState in RunStore (Redis or in-memory)
  ├─► Returns run_id to frontend
  │
GET /api/stream/{run_id}
  ├─► Validates run_id in RunStore
  ├─► Opens SSE connection
  ├─► Launches orchestrator_graph.ainvoke()
  │     ├─► research_node → ArXiv (retry 3x) + HF (retry 3x) → deduplicate
  │     ├─► summary_node  → LLM (retry 3x per paper, async_retry with exp backoff)
  │     └─► memory_node   → Mem0 profile → embedding similarity → rank
  ├─► Streams all steps via callback
  ├─► Emits result event with PaperSearchResult
  └─► Updates RunStore status to "complete"
```

---

## 5. Data Model

### Supabase Schema

```sql
-- Papers table with vector search
CREATE TABLE papers (
  id           TEXT PRIMARY KEY,
  title        TEXT NOT NULL,
  abstract     TEXT,
  authors      JSONB DEFAULT '[]',
  url          TEXT,
  published_at TIMESTAMPTZ,
  summary_tldr TEXT,
  embedding    VECTOR(1536),
  created_at   TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX ON papers USING ivfflat (embedding vector_cosine_ops);
CREATE INDEX ON papers (published_at DESC);

-- User saved papers
CREATE TABLE user_papers (
  user_id    UUID REFERENCES auth.users(id) ON DELETE CASCADE,
  paper_id   TEXT REFERENCES papers(id) ON DELETE CASCADE,
  saved_at   TIMESTAMPTZ DEFAULT NOW(),
  dismissed  BOOLEAN DEFAULT FALSE,
  PRIMARY KEY (user_id, paper_id)
);

-- User preferences (LLM model, research interests)
CREATE TABLE user_prefs (
  user_id          UUID PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
  preferred_model  TEXT DEFAULT 'anthropic/claude-sonnet-4-5',
  interests        TEXT[] DEFAULT '{}',
  updated_at       TIMESTAMPTZ DEFAULT NOW()
);

-- Vector similarity search function
CREATE FUNCTION match_papers(
  query_embedding VECTOR(1536),
  match_threshold FLOAT,
  match_count INT
) RETURNS TABLE(...) LANGUAGE SQL STABLE;

-- Citation graph edges, cached from Semantic Scholar (backing table for
-- GET /api/graph/{paper_id}; avoids hammering the rate-limited S2 API)
CREATE TABLE citations (
  paper_id    TEXT REFERENCES papers(id) ON DELETE CASCADE,
  root_title  TEXT,
  cited_id    TEXT,
  cited_title TEXT,
  fetched_at  TIMESTAMPTZ DEFAULT NOW(),
  PRIMARY KEY (paper_id, cited_id)
);

-- Firecrawl full-text crawl cache, keyed by paper ID
CREATE TABLE crawled_content (
  paper_id   TEXT PRIMARY KEY REFERENCES papers(id) ON DELETE CASCADE,
  url        TEXT,
  content    TEXT,
  fetched_at TIMESTAMPTZ DEFAULT NOW()
);

-- Compound index for the personalised feed query
CREATE INDEX idx_user_papers_feed ON user_papers (user_id, dismissed, saved_at DESC);
```

### Mem0 Memory Model

Mem0 stores user preferences as natural-language memories:
- "Alice is interested in diffusion models"
- "Bob dislikes papers without code"
- "Saved paper: Attention Is All You Need — a survey of transformer variants"

Memories are auto-consolidated and deduplicated by Mem0 over time.

---

## 6. LLM Routing Strategy

All LLM calls flow through `services/llm_router.py`.

**Primary path:** OpenRouter (single API key, unified OpenAI-compatible interface). Identified by the presence of `/` in the model name (e.g. `anthropic/claude-sonnet-4-5`).

**Fallback chain:** When OpenRouter is unavailable (API key missing or runtime error):
1. `claude-*` models → Anthropic direct SDK
2. `gpt-*` models → OpenAI direct SDK
3. `gemini-*` models → Google Gemini direct SDK
4. `mistral-*` models → Mistral direct SDK
5. Everything else → OpenAI direct (as final fallback)

**Agent model map:**
| Agent | Default Model | Reason |
|-------|--------------|--------|
| Orchestrator | `anthropic/claude-opus-4` | Best reasoning |
| Research | `openai/gpt-4o-mini` | Fast tool calls |
| Summary (default) | `anthropic/claude-sonnet-4-5` | Long context + quality |
| Summary (fast) | `google/gemini-2.0-flash` | Batch summarisation |
| Memory | `openai/gpt-4o-mini` | Lightweight scoring |

**Cost guardrails:**
- `max_tokens=4096` on all LLM calls (or `max_output_tokens` for Gemini)
- Cache embeddings and summaries in Supabase to avoid re-processing
- Use fast/cheap models for pre-filtering (relevance scoring) before expensive models
- `MAX_SUMMARIES_PER_RUN` (default 20) caps per-request LLM fan-out; a search
  returning 30-50 papers only gets the top-N summarised by the LLM, the rest
  receive an abstract-preview fallback with no LLM call

**User override:** The `ModelSelector` component on the frontend lets users choose their preferred model. This is sent as `model` in `POST /api/search` and passed through the orchestrator to the summary agent.

---

## 7. Memory & Personalisation

### Mem0 (User Memory)

Stores high-level user preferences as natural-language memories. The Memory Agent reads the user's Mem0 profile and uses it to score and re-rank papers. New signals (saves, dismissals) are written back to Mem0 after each user action.

### Supabase pgvector

Stores paper embeddings (1536-dim from `text-embedding-3-small`). Enables:
- Semantic search via `match_papers()` PostgreSQL function
- Duplicate detection before inserting new papers
- Related-papers panel on the paper detail page

### Embedding Pipeline

```
Raw paper text (title + abstract)
    └─► OpenAI text-embedding-3-small API (httpx)
          └─► Supabase upsert (papers.embedding column)
```

### Memory Agent Scoring

1. **Embedding-based (primary):** When Mem0 has user memories, the agent embeds the user's interest text and each paper abstract. Relevance is computed as cosine similarity between the interest vector and each paper vector.
2. **Keyword-based (fallback):** When no Mem0 profile exists, the agent extracts keywords from the search query and matches against paper title/abstract keywords. Score = matches / query keyword count.
3. **Default (last resort):** If neither method works, all papers get a score of 0.5.

---

## 8. Run State Management

Agent run states are managed by `services/run_store.py`, which provides two implementations:

### In-Memory Store (`RunStore`)
- Used when `REDIS_URL` is not set
- Python dict with asyncio locks for thread safety
- Entries expire after 3600 seconds (1 hour TTL)
- States are lost on backend restart

### Redis Store (`RedisRunStore`)
- Used when `REDIS_URL` is configured
- Persists run state in Redis with automatic key expiry
- **Required for multi-instance deployments** (otherwise SSE streams may fail)
- Falls back to in-memory store silently if Redis is unreachable

The `run_store` module exports a `RunStore` instance and a `RedisRunStore` instance. At startup, the backend tries Redis first, falling back to in-memory with a warning log.

---

## 9. Retry Mechanism

The `services/retry.py` module provides `async_retry(func, max_retries=3, base_delay=1.0)`, an async retry wrapper with exponential backoff.

**Used by:**
- `services/arxiv.py` — ArXiv API calls (3 retries)
- `services/huggingface.py` — HuggingFace Daily Papers API (3 retries)
- `services/semantic_scholar.py` — Semantic Scholar API (3 retries)
- `agents/summary_agent.py` — LLM calls per paper (3 retries, on any OpenRouter or direct-provider SDK)
- `services/embeddings.py` — OpenAI embedding calls (3 retries)
- `services/ingestion.py` — Supabase upserts during daily fetch (3 retries)

**Backoff schedule:** 1s → 2s → 4s (base_delay * 2^attempt)

**Transient errors:** `async_retry` retries builtin `ConnectionError`/`TimeoutError`,
any `httpx.HTTPError` (connect/read timeouts, 5xx), and vendor LLM SDK errors
matched by class name (`APIConnectionError`, `RateLimitError`,
`InternalServerError`, `ServiceUnavailable`, `Unavailable`, etc.). Non-transient
errors (validation, JSON parse) are re-raised immediately. Retry is orthogonal
to the provider fallback chain in `llm_router.py` — retry handles the same
provider's transient failure, fallback handles provider unavailability.

---

## 10. Auth & Security

**Supabase Auth:**
- Email/password + OAuth (Google, GitHub)
- JWT returned to frontend after sign-in
- Frontend attaches `Authorization: Bearer <token>` on every API call
- FastAPI middleware validates the JWT in `services/jwt_validator.py`:
  - Since October 2025 new Supabase projects sign JWTs **asymmetrically (ES256)**
    with the public key published on `{SUPABASE_URL}/auth/v1/.well-known/jwks.json`.
    The validator fetches and caches the JWKS (1-hour TTL), selects the key by the
    token's `kid` header, and verifies with ES256.
  - Legacy projects that still sign with the shared secret are verified with
    HS256 against `SUPABASE_JWT_SECRET` (fallback only for HS256-tagged tokens).
- `user_id` from JWT used as Mem0 key and for filtering saved papers

**Rate Limiting:**
- `POST /api/search`: 10 req/min
- `GET /api/stream/*`: 20 req/min
- `GET /api/health`: exempt
- Default: 60 req/min for all other endpoints
- slowapi's limiter is backed by Redis (`storage_uri` = `REDIS_URL`) so limits
  are **global** across multiple backend instances; it falls back to in-memory
  when Redis is unavailable or unconfigured

**CORS:**
- Allowed origins: `http://localhost:3000` (configurable per deployment)
- Credentials enabled
- All methods and headers allowed

---

## 11. Folder Structure

```
ai-paper-research-agent/
├── frontend/                        # Next.js 15 application
│   ├── app/                         # App Router pages
│   │   ├── (auth)/                  # Login / signup pages
│   │   ├── feed/                    # Paper feed page (+ loading.tsx)
│   │   ├── graph/                   # 3-D citation graph (+ layout.tsx)
│   │   ├── paper/[id]/             # Single paper detail (+ loading.tsx)
│   │   ├── settings/               # User preferences (+ loading.tsx)
│   │   ├── api/                     # API routes (if any)
│   │   ├── page.tsx                 # Landing page
│   │   ├── layout.tsx               # Root layout
│   │   └── globals.css              # Global styles
│   ├── components/
│   │   ├── PaperCard.tsx
│   │   ├── CitationGraph.tsx (or in graph/page.tsx)
│   │   ├── StreamingResponse.tsx    # SSE consumer component
│   │   ├── ModelSelector.tsx        # LLM model picker
│   │   ├── SkeletonCard.tsx
│   │   ├── Navbar.tsx
│   │   ├── Footer.tsx
│   │   ├── EmptyState.tsx
│   │   ├── ErrorBoundary.tsx
│   │   └── QueryProvider.tsx
│   ├── lib/
│   │   ├── api.ts                   # API client (fetch wrappers)
│   │   ├── auth.ts                  # Supabase auth helpers
│   │   ├── hooks.ts                 # Custom React hooks
│   │   └── supabase.ts              # Supabase client singleton
│   ├── store/
│   │   └── useAppStore.ts           # Zustand store (model, prefs, loading)
│   ├── types/
│   │   └── index.ts                 # TypeScript interfaces
│   ├── package.json
│   └── Dockerfile
│
├── backend/                         # FastAPI application
│   ├── main.py                      # App entry, middleware, routers
│   ├── config.py                    # Pydantic settings (env vars)
│   ├── dependencies.py              # Auth dependency injection
│   ├── logging_config.py            # Structured logging setup
│   ├── routers/                     # 9 API routers
│   │   ├── __init__.py
│   │   ├── health.py
│   │   ├── auth.py
│   │   ├── papers.py
│   │   ├── search.py
│   │   ├── stream.py
│   │   ├── graph.py
│   │   ├── prefs.py
│   │   ├── pwc.py
│   │   └── internal.py              # POST /api/internal/ingest (admin key)
│   ├── agents/                      # LangGraph agent layer
│   │   ├── __init__.py
│   │   ├── orchestrator.py          # StateGraph: research → summary → memory
│   │   ├── research_agent.py
│   │   ├── summary_agent.py
│   │   ├── memory_agent.py
│   │   └── prompts/
│   │       └── summary_prompt.txt
│   ├── services/                    # 17 external service integrations
│   │   ├── __init__.py
│   │   ├── arxiv.py
│   │   ├── huggingface.py
│   │   ├── firecrawl.py             # crawl_paper + crawl_paper_cached (Supabase cache)
│   │   ├── papers_with_code.py
│   │   ├── semantic_scholar.py
│   │   ├── citation_cache.py        # Supabase-backed citation edge cache
│   │   ├── jwt_validator.py         # ES256 JWKS + HS256 legacy JWT validation
│   │   ├── mem0_client.py
│   │   ├── supabase_client.py
│   │   ├── llm_router.py
│   │   ├── embeddings.py
│   │   ├── ingestion.py             # run_daily_fetch() pipeline
│   │   ├── observability.py         # Langfuse + Sentry initialisation
│   │   ├── run_store.py             # Redis + in-memory run state
│   │   └── retry.py                 # Async retry with exp backoff
│   ├── middleware/
│   │   ├── __init__.py
│   │   ├── rate_limit.py
│   │   └── timing.py
│   ├── models/
│   │   ├── __init__.py
│   │   └── schemas.py
│   ├── scripts/
│   │   ├── __init__.py
│   │   ├── seed_dev.py
│   │   └── daily_fetch.py
│   ├── pyproject.toml
│   └── Dockerfile
│
├── supabase/
│   └── schema.sql                   # Database migration
│
├── docs/                            # Documentation
│   ├── API.md                       # Full API reference
│   ├── DEVELOPER_GUIDE.md           # Developer onboarding
│   └── DEPLOYMENT.md                # Production deployment guide
│
├── .github/workflows/
│   ├── ci.yml                       # GitHub Actions CI
│   └── daily_fetch.yml              # Scheduled daily ingestion (cron)
│
├── docker-compose.yml               # Local dev stack
├── docker-compose.prod.yml          # Production Docker stack
├── .env.example                     # Environment variable template
├── PLAN.md                          # Master project plan
├── ARCHITECTURE.md                  # This file
└── README.md                        # Project overview
```

---

## 12. Deployment

| Component | Primary Platform | Alternative |
|-----------|-----------------|-------------|
| Frontend | Vercel | Docker, any Node.js host |
| Backend | Fly.io | Railway, Docker on cloud VM |
| Database | Supabase (managed Postgres) | Self-hosted Postgres |
| Redis | Fly Upstash / local Redis | In-memory (single instance only) |
| Daily ingestion scheduler | Fly scheduled machine | GitHub Actions cron → `/api/internal/ingest` |
| CI/CD | GitHub Actions | — |

Docker Compose files are available for both local development (`docker-compose.yml`) and single-server production deployment (`docker-compose.prod.yml`).

See **[docs/DEPLOYMENT.md](./docs/DEPLOYMENT.md)** for step-by-step deployment instructions.

---

## 13. Environment Variables

See `.env.example` for the full list. Key categories:
- **LLM Providers:** `OPENROUTER_API_KEY` (required), `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `GOOGLE_API_KEY`, `MISTRAL_API_KEY`
- **Data Sources:** `FIRECRAWL_API_KEY`, `SEMANTIC_SCHOLAR_API_KEY`
- **Memory & Storage:** `MEM0_API_KEY`, `SUPABASE_URL`, `SUPABASE_ANON_KEY`, `SUPABASE_SERVICE_ROLE_KEY`, `SUPABASE_JWT_SECRET` (HS256 legacy fallback only)
- **Scheduler:** `ADMIN_API_KEY` (authenticates `/api/internal/ingest`)
- **Cost guardrails:** `MAX_SUMMARIES_PER_RUN`
- **Observability:** `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY`, `LANGFUSE_HOST`, `SENTRY_DSN`, `SENTRY_TRACES_SAMPLE_RATE`, `APP_ENV`
- **App:** `APP_URL`, `NEXT_PUBLIC_API_URL`, `REDIS_URL` (run state + global rate limiting)
