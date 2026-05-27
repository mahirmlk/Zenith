# AI Paper Research Agent — Project Plan

> Four-layer architecture: Next.js frontend → FastAPI backend → LangGraph orchestration → External services

---

## Table of Contents

1. [Project Overview](#1-project-overview)
2. [Architecture Summary](#2-architecture-summary)
3. [Tech Stack](#3-tech-stack)
4. [Folder Structure](#4-folder-structure)
5. [Layer 1 — Next.js Frontend](#5-layer-1--nextjs-frontend)
6. [Layer 2 — FastAPI Backend](#6-layer-2--fastapi-backend)
7. [Layer 3 — LangGraph Orchestration](#7-layer-3--langgraph-orchestration)
8. [Layer 4 — External Integrations](#8-layer-4--external-integrations)
9. [LLM Provider Strategy](#9-llm-provider-strategy)
10. [Data Sources](#10-data-sources)
11. [Memory & Vector Storage](#11-memory--vector-storage)
12. [Auth Strategy](#12-auth-strategy)
13. [Milestones & Phases](#13-milestones--phases)
14. [Environment Variables](#14-environment-variables)
15. [Open Questions](#15-open-questions)

---

## 1. Project Overview

An AI-powered research assistant that continuously discovers, ingests, summarises, and personalises academic papers from ArXiv and HuggingFace Daily Papers. Users interact via a rich Next.js UI (paper feed + 3-D citation graph). Under the hood, a LangGraph multi-agent system orchestrates three specialised agents, uses Firecrawl to pull full paper text, stores user memory in Mem0/Supabase, and routes LLM calls through OpenRouter (with direct provider fallback).

**Core value proposition:** Zero effort from "paper exists" to "here's why it matters to you."

---

## 2. Architecture Summary

```
┌──────────────────────────────────────────────┐
│          Next.js Frontend                     │
│  Paper feed · Three.js graph · Auth UI        │
└─────────────────┬────────────────────────────┘
                  │ HTTP / SSE
┌─────────────────▼────────────────────────────┐
│          FastAPI Backend                      │
│  API gateway · SSE streaming · Auth (JWT)     │
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
│  Firecrawl │ ArXiv+HF │ OpenRouter │ Mem0+SB  │
└──────────────────────────────────────────────┘
```

---

## 3. Tech Stack

| Layer | Technology |
|---|---|
| Frontend | Next.js 15 (App Router), TypeScript, Tailwind CSS, Three.js / React Three Fiber |
| Backend | Python 3.12, FastAPI, Uvicorn, SSE (Server-Sent Events) |
| Orchestration | LangGraph 0.2+, LangChain core |
| LLM Routing | OpenRouter (primary), Anthropic, OpenAI, Google Gemini, Mistral (direct fallback) |
| Web Crawling | Firecrawl MCP |
| Paper Sources | ArXiv API, HuggingFace Daily Papers API |
| Memory | Mem0 (user memory layer) |
| Vector DB | Supabase pgvector |
| Auth | Supabase Auth (JWT) |
| Containerisation | Docker + Docker Compose |
| CI / CD | GitHub Actions |

---

## 4. Folder Structure

```
ai-paper-agent/
├── frontend/                     # Next.js app
│   ├── app/
│   │   ├── (auth)/               # Login / signup pages
│   │   ├── feed/                 # Paper feed page
│   │   ├── graph/                # Three.js citation graph
│   │   └── paper/[id]/           # Single paper detail
│   ├── components/
│   │   ├── PaperCard.tsx
│   │   ├── CitationGraph.tsx
│   │   ├── StreamingResponse.tsx  # SSE consumer
│   │   └── ModelSelector.tsx      # LLM picker
│   └── lib/
│       ├── api.ts
│       └── auth.ts
│
├── backend/                      # FastAPI app
│   ├── main.py
│   ├── routers/
│   │   ├── papers.py
│   │   ├── stream.py             # SSE endpoints
│   │   └── auth.py
│   ├── agents/                   # LangGraph layer
│   │   ├── orchestrator.py
│   │   ├── research_agent.py
│   │   ├── summary_agent.py
│   │   └── memory_agent.py
│   ├── services/
│   │   ├── llm_router.py         # OpenRouter + direct providers
│   │   ├── firecrawl.py
│   │   ├── arxiv.py
│   │   ├── huggingface.py
│   │   ├── mem0_client.py
│   │   └── supabase_client.py
│   └── models/
│       └── schemas.py
│
├── docker-compose.yml
├── .env.example
└── PLAN.md
```

---

## 5. Layer 1 — Next.js Frontend

### Pages

| Route | Description |
|---|---|
| `/` | Landing / marketing page |
| `/feed` | Personalised paper feed (SSE-powered live updates) |
| `/graph` | 3-D citation network (Three.js / React Three Fiber) |
| `/paper/[id]` | Full paper detail: abstract, AI summary, related papers |
| `/login` · `/signup` | Supabase Auth UI |
| `/settings` | User preferences, interests, model selection |

### Key Components

**PaperCard** — displays title, authors, venue, AI-generated TL;DR, relevance score, save/dismiss actions.

**CitationGraph** — Three.js force-directed graph; nodes = papers, edges = citations. Click a node to navigate to that paper's detail page.

**StreamingResponse** — consumes SSE stream from FastAPI to display agent thinking steps and the final summary in real time.

**ModelSelector** — dropdown allowing users to pick their preferred LLM (Claude Sonnet, GPT-4o, Gemini 1.5 Pro, Mistral Large, etc.) routed via OpenRouter.

### State Management

Use React Context + `useReducer` for lightweight global state (selected model, user prefs). SWR or React Query for data fetching and caching.

---

## 6. Layer 2 — FastAPI Backend

### Endpoints

```
POST   /api/search            # Trigger Research agent for a query
GET    /api/stream/{run_id}   # SSE stream of agent progress + results
GET    /api/papers            # Fetch personalised feed
GET    /api/papers/{id}       # Single paper detail
POST   /api/papers/{id}/save  # Save paper to user library
GET    /api/graph/{id}        # Citation graph data for a paper
POST   /api/auth/token        # Exchange Supabase JWT
GET    /api/health
```

### SSE Streaming

Each agent step emits an SSE event so the frontend can show live progress:

```
event: agent_step
data: {"agent": "research", "status": "fetching_arxiv", "count": 12}

event: agent_step
data: {"agent": "summary", "status": "summarising", "paper_id": "2401.00001"}

event: result
data: {"papers": [...], "run_id": "abc123"}
```

### Auth Middleware

Validate Supabase JWT on all `/api/*` routes (except `/api/health`). Attach `user_id` to request state for downstream personalisation.

---

## 7. Layer 3 — LangGraph Orchestration

### Graph Design

```
START
  └─► Orchestrator
        ├─► Research Agent  ──► Firecrawl ──► ArXiv / HF
        ├─► Summary Agent   ──► LLM (via OpenRouter)
        └─► Memory Agent    ──► Mem0 + Supabase
              └─► Orchestrator (merge & rank)
END
```

### Orchestrator (`orchestrator.py`)

Receives the user query and user context. Builds a task plan: which sources to search, how many papers to fetch, summarisation depth. Dispatches sub-tasks to the three agents using LangGraph's `Send` API for parallel execution. Collects results and produces the final ranked, personalised list.

### Research Agent (`research_agent.py`)

Discovers papers matching the query.

Tools available to this agent:
- `search_arxiv(query, max_results)` — ArXiv API wrapper
- `search_huggingface_daily(date_range)` — HF Daily Papers API
- `crawl_paper(url)` — Firecrawl MCP to extract full text, references, figures

### Summary Agent (`summary_agent.py`)

Receives raw paper content. Produces:
- One-line TL;DR (≤ 25 words)
- 3-bullet key contributions
- Relevance explanation given the user's interest profile
- Difficulty level (introductory / intermediate / expert)

Uses the configured LLM via `llm_router.py`. Adjusts prompt depth based on model capability.

### Memory Agent (`memory_agent.py`)

Reads user's Mem0 profile to understand research interests, previously read papers, and dismissed topics. Scores and re-ranks papers accordingly. Writes back new signals (saves, dismissals, dwell time) to Mem0 after each session.

---

## 8. Layer 4 — External Integrations

### Firecrawl (Full Paper Crawl)

Used by the Research Agent to extract the full text of papers from ArXiv HTML pages and HuggingFace paper cards. Returns clean markdown suitable for the Summary Agent.

```python
# services/firecrawl.py
from firecrawl import FirecrawlApp

app = FirecrawlApp(api_key=settings.FIRECRAWL_API_KEY)

def crawl_paper(url: str) -> str:
    result = app.scrape_url(url, params={"formats": ["markdown"]})
    return result["markdown"]
```

### ArXiv API

Daily cron (or on-demand) fetch of new papers in configured categories (cs.AI, cs.LG, cs.CL, stat.ML, etc.).

```python
# services/arxiv.py
import arxiv

def search_arxiv(query: str, max_results: int = 20) -> list[dict]:
    search = arxiv.Search(query=query, max_results=max_results,
                          sort_by=arxiv.SortCriterion.SubmittedDate)
    return [{"id": r.entry_id, "title": r.title, "abstract": r.summary,
             "url": r.pdf_url, "authors": [a.name for a in r.authors]}
            for r in search.results()]
```

### HuggingFace Daily Papers API

```python
# services/huggingface.py
import httpx

HF_DAILY_URL = "https://huggingface.co/api/daily_papers"

async def fetch_hf_daily(date: str) -> list[dict]:
    async with httpx.AsyncClient() as client:
        r = await client.get(HF_DAILY_URL, params={"date": date})
        r.raise_for_status()
        return r.json()
```

### Mem0 (User Memory)

```python
# services/mem0_client.py
from mem0 import MemoryClient

client = MemoryClient(api_key=settings.MEM0_API_KEY)

def get_user_profile(user_id: str) -> dict:
    return client.get_all(user_id=user_id)

def add_memory(user_id: str, messages: list) -> None:
    client.add(messages, user_id=user_id)
```

### Supabase (Vector DB + Auth)

Papers and their embeddings are stored in a `papers` table with a `pgvector` column. Similarity search is used to surface related papers.

```sql
-- Supabase schema
create table papers (
  id           text primary key,
  title        text,
  abstract     text,
  authors      jsonb,
  url          text,
  published_at timestamptz,
  summary_tldr text,
  embedding    vector(1536),
  created_at   timestamptz default now()
);

create index on papers using ivfflat (embedding vector_cosine_ops);
```

---

## 9. LLM Provider Strategy

All LLM calls are routed through `services/llm_router.py`. OpenRouter is the primary gateway (single API key, unified interface). Direct provider integrations serve as fallback or for specialised tasks.

### OpenRouter (Primary)

OpenRouter provides a single OpenAI-compatible endpoint that proxies to dozens of models. This is the default path for all agents.

```python
# services/llm_router.py
from langchain_openai import ChatOpenAI

def get_llm(model: str = "anthropic/claude-sonnet-4-5",
            temperature: float = 0.3) -> ChatOpenAI:
    return ChatOpenAI(
        base_url="https://openrouter.ai/api/v1",
        api_key=settings.OPENROUTER_API_KEY,
        model=model,
        temperature=temperature,
        default_headers={
            "HTTP-Referer": settings.APP_URL,
            "X-Title": "AI Paper Research Agent",
        },
    )
```

### Supported Models via OpenRouter

| Provider | Model ID (OpenRouter) | Best used for |
|---|---|---|
| **Anthropic** | `anthropic/claude-sonnet-4-5` | Summarisation, long context |
| **Anthropic** | `anthropic/claude-opus-4` | Complex reasoning, orchestration |
| **OpenAI** | `openai/gpt-4o` | General purpose, tool use |
| **OpenAI** | `openai/gpt-4o-mini` | Fast, cheap pre-filtering |
| **Google** | `google/gemini-2.5-pro` | Multimodal (figures/tables) |
| **Google** | `google/gemini-2.0-flash` | High-speed summarisation |
| **Mistral** | `mistralai/mistral-large` | European data-residency option |
| **Mistral** | `mistralai/mistral-7b-instruct` | Lightweight classification |
| **Meta** | `meta-llama/llama-3.3-70b-instruct` | Open-weights, cost-effective |
| **DeepSeek** | `deepseek/deepseek-r1` | Math-heavy / CS paper reasoning |
| **Cohere** | `cohere/command-r-plus` | RAG-optimised summarisation |
| **Qwen** | `qwen/qwen-2.5-72b-instruct` | Multilingual paper support |

### Direct Provider Integrations (Fallback / Specialised)

When OpenRouter is unavailable or a task requires provider-specific features, the router falls back to direct SDK calls.

```python
# Anthropic direct (streaming, extended thinking)
from langchain_anthropic import ChatAnthropic
anthropic_llm = ChatAnthropic(model="claude-sonnet-4-5",
                               api_key=settings.ANTHROPIC_API_KEY)

# OpenAI direct (structured outputs, assistants)
from langchain_openai import ChatOpenAI
openai_llm = ChatOpenAI(model="gpt-4o",
                         api_key=settings.OPENAI_API_KEY)

# Google direct (Gemini multimodal)
from langchain_google_genai import ChatGoogleGenerativeAI
gemini_llm = ChatGoogleGenerativeAI(model="gemini-2.5-pro",
                                     google_api_key=settings.GOOGLE_API_KEY)

# Mistral direct
from langchain_mistralai import ChatMistralAI
mistral_llm = ChatMistralAI(model="mistral-large-latest",
                              api_key=settings.MISTRAL_API_KEY)
```

### Model Selection Logic

```python
# Simplified routing logic
AGENT_MODEL_MAP = {
    "orchestrator":    "anthropic/claude-opus-4",       # best reasoning
    "research":        "openai/gpt-4o-mini",            # fast tool calls
    "summary_default": "anthropic/claude-sonnet-4-5",   # long context + quality
    "summary_fast":    "google/gemini-2.0-flash",       # batch summarisation
    "memory":          "openai/gpt-4o-mini",            # lightweight scoring
}

# Users can override via the ModelSelector UI; stored in their profile.
```

### Cost Guardrails

- Set `max_tokens` per agent role (orchestrator: 4096, summary: 2048, research: 1024).
- Cache embeddings and summaries in Supabase so the same paper is never re-summarised.
- Use the fast/cheap tier models for pre-filtering (e.g. relevance scoring) before sending to expensive models.

---

## 10. Data Sources

| Source | Method | Cadence | Notes |
|---|---|---|---|
| ArXiv | Official API (`arxiv` Python lib) | Daily cron + on-demand | Filter by category; max 200 results per call |
| HuggingFace Daily Papers | REST API | Daily cron | Community-curated highlights |
| Semantic Scholar | S2 REST API | On-demand (citation graph) | Used to build citation edges for Three.js graph |
| Papers With Code | REST API | Weekly sync | Attaches GitHub links and benchmark tables to papers |
| Full paper text | Firecrawl (HTML/PDF scrape) | On-demand when user views a paper | Feeds the Summary Agent |

---

## 11. Memory & Vector Storage

### Mem0

Stores high-level user preferences as natural-language memories ("Alice is interested in diffusion models", "Bob dislikes papers without code"). Automatically consolidates and deduplicates over time.

### Supabase pgvector

Stores paper embeddings (1536-dim, from `text-embedding-3-small` or `text-embedding-ada-002`). Enables:
- Semantic search ("find papers similar to this one")
- Duplicate detection before inserting new papers
- Related-papers panel on the paper detail page

### Embedding Pipeline

```
Raw paper text
    └─► Chunk (abstract + intro, ≤ 512 tokens)
          └─► OpenAI / Cohere embed API
                └─► Supabase upsert (papers.embedding)
```

---

## 12. Auth Strategy

Supabase Auth handles all user management (email/password + OAuth with Google/GitHub). The backend validates the Supabase JWT on each request. `user_id` from the JWT is used as the key in Mem0 and for filtering saved papers.

Flow:
1. User signs in via Next.js Auth UI.
2. Supabase returns a JWT.
3. Frontend attaches the JWT as `Authorization: Bearer <token>` on every API call.
4. FastAPI middleware decodes and validates the token using the Supabase JWT secret.

---

## 13. Milestones & Phases

### Phase 1 — Foundation (Weeks 1–2)
- [ ] Scaffold Next.js frontend and FastAPI backend
- [ ] Supabase project setup (auth, `papers` table, pgvector extension)
- [ ] ArXiv and HuggingFace data fetchers
- [ ] Basic paper feed (no agents yet, raw API data)
- [ ] Docker Compose for local development

### Phase 2 — Agent Core (Weeks 3–4)
- [ ] LangGraph orchestrator graph
- [ ] Research Agent with ArXiv + HF tools
- [ ] Summary Agent with OpenRouter routing (Claude Sonnet as default)
- [ ] SSE streaming from FastAPI to frontend
- [ ] Streaming UI component in Next.js

### Phase 3 — Memory & Personalisation (Week 5)
- [ ] Mem0 integration; user profile reads/writes
- [ ] Memory Agent scoring and re-ranking
- [ ] Firecrawl integration for full paper text
- [ ] Embedding pipeline + pgvector similarity search

### Phase 4 — UI Polish (Week 6)
- [ ] Three.js citation graph (Semantic Scholar edges)
- [ ] ModelSelector UI; per-user model preference stored in Supabase
- [ ] Papers With Code integration (benchmark tables, GitHub links)
- [ ] Save / dismiss / share paper actions

### Phase 5 — Hardening & Launch (Week 7–8)
- [ ] Rate limiting and cost guardrails
- [ ] Error handling and agent retry logic
- [ ] GitHub Actions CI (lint, type-check, pytest)
- [ ] Production deployment (Vercel for frontend, Railway/Fly.io for backend)
- [ ] Load testing SSE endpoint

---

## 14. Environment Variables

```env
# === LLM Providers ===
OPENROUTER_API_KEY=           # Primary — all agent LLM calls
ANTHROPIC_API_KEY=            # Fallback / direct streaming
OPENAI_API_KEY=               # Fallback / embeddings
GOOGLE_API_KEY=               # Gemini fallback
MISTRAL_API_KEY=              # Mistral fallback

# === Data Sources ===
FIRECRAWL_API_KEY=            # Full paper crawl
SEMANTIC_SCHOLAR_API_KEY=     # Citation graph (optional, higher rate limits)

# === Memory & Storage ===
MEM0_API_KEY=                 # User memory
SUPABASE_URL=                 # Supabase project URL
SUPABASE_ANON_KEY=            # Frontend public key
SUPABASE_SERVICE_ROLE_KEY=    # Backend private key
SUPABASE_JWT_SECRET=          # For JWT validation in FastAPI

# === App ===
APP_URL=                      # e.g. https://paperagent.app (sent as HTTP-Referer to OpenRouter)
NEXT_PUBLIC_API_URL=          # FastAPI base URL for the frontend
```

---

## 15. Open Questions

- **Embedding model choice:** Use OpenAI `text-embedding-3-small` (cheap, fast) or route embeddings through OpenRouter too? Consider Cohere `embed-v3` for better multilingual support.
- **Citation graph depth:** How many hops to traverse from a paper? Cap at 2 to avoid explosion (hundreds of papers).
- **PDF vs HTML scraping:** ArXiv now provides HTML for many papers; prefer HTML (Firecrawl is faster and cleaner). Fall back to PDF extraction for older papers.
- **Agent parallelism:** LangGraph's `Send` API enables parallel Research + Summary calls. Decide whether the Memory Agent should block on the final ranking or run concurrently and apply post-hoc.
- **Rate limits:** ArXiv API is capped at ~3 req/s; HF has no official SLA. Add exponential backoff in both fetchers.
- **Model fallback order:** Define the exact fallback chain when OpenRouter returns a 5xx (e.g. OpenRouter → Anthropic direct → OpenAI direct → cached last result).
- **User data privacy:** Mem0 stores user memory on their servers. Evaluate self-hosted Mem0 OSS or equivalent for GDPR compliance if targeting EU users.
