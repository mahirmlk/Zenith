# Memory & Personalisation

> How the AI Paper Research Agent learns what you care about and ranks papers accordingly.

---

## Table of Contents

- [Overview](#overview)
- [Mem0 — User Memory Layer](#mem0--user-memory-layer)
- [Supabase pgvector — Paper Vector Store](#supabase-pgvector--paper-vector-store)
- [Memory Agent Pipeline](#memory-agent-pipeline)
- [Write-back Flow](#write-back-flow)
- [Data Flow Diagram](#data-flow-diagram)

---

## Overview

The system uses a **dual memory architecture** to personalise the paper experience:

| Store | What | Technology | Purpose |
|-------|------|------------|---------|
| **Mem0** | User preferences | Third-party hosted service | Natural-language memories about user interests and behaviour |
| **Supabase pgvector** | Paper embeddings | Self-hosted (your Supabase project) | Semantic similarity search across paper abstracts |

Together, these two stores enable the **Memory Agent** (one of the three LangGraph agents) to score and re-rank papers by relevance to each individual user.

---

## Mem0 — User Memory Layer

Mem0 is a managed memory service that stores high-level user preferences as natural-language strings. It is used to build a persistent, evolving profile of each user's research interests.

### What It Stores

Mem0 memories are plain English sentences generated from user actions:

- **Interest signals from saved papers:**
  - `"Saved paper: Attention Is All You Need about transformer architectures..."`
  - `"Interested in diffusion models"`
  - `"Alice is interested in graph neural networks for molecular prediction"`
- **Disinterest signals from dismissed papers:**
  - `"Dismissed paper: A Survey on Cats as Pets about feline behaviour analysis..."`
  - `"Bob dislikes papers without code"`
- **Browsing behaviour** (future: dwell time, repeated visits)

Mem0 automatically **consolidates and deduplicates** these memories over time, merging related statements and removing near-duplicates.

### How Memories Are Created (Write Path)

Memories are written when the user interacts with papers. The write-back is handled by the `POST /api/papers/{paper_id}/save` endpoint in `backend/routers/papers.py`:

1. User saves or dismisses a paper via the frontend.
2. The endpoint upserts the action into the `user_papers` table in Supabase.
3. The endpoint then calls `add_memory()` from `backend/services/mem0_client.py` with a message like:
   ```
   "Saved paper: {title} about {first 120 chars of abstract}..."
   ```
4. If Mem0 write fails, it logs a warning — **the save/dismiss action still succeeds** (graceful degradation).

### How Memories Are Read (Read Path)

When a search is triggered, the Memory Agent calls `get_user_profile()` from `backend/services/mem0_client.py`, which returns all stored memories for the user.

```python
# backend/services/mem0_client.py
from mem0 import MemoryClient

def get_user_profile(user_id: str) -> list[dict]:
    client = MemoryClient(api_key=settings.mem0_api_key)
    return client.get_all(user_id=user_id)
```

Each memory entry has a `"memory"` key containing the natural-language text. These are concatenated and used to compute an interest embedding for relevance scoring.

### When No Profile Exists

If the user has no Mem0 profile (new user, missing `MEM0_API_KEY`), the Memory Agent falls back to **keyword-based scoring** using the search query (see [Memory Agent Pipeline](#memory-agent-pipeline) below).

---

## Supabase pgvector — Paper Vector Store

Paper embeddings are stored in a `papers` table in your Supabase (Postgres) database with the `pgvector` extension enabled.

### Embedding Model

| Property | Value |
|----------|-------|
| Model | OpenAI `text-embedding-3-small` |
| Dimension | 1536 |
| API endpoint | `https://api.openai.com/v1/embeddings` |
| Implementation | `backend/services/embeddings.py` |

Requires `OPENAI_API_KEY` to be set. No other embedding provider is currently supported.

### Chunking

The embedding input is constructed from:

```
{title}
{abstract}
```

The combined text is sent directly to the embedding API without additional chunking. The embedding model handles inputs up to 8191 tokens — well within the typical paper abstract length.

### Cosine Similarity Search — `match_papers()`

A PostgreSQL function defined in `supabase/schema.sql` enables vector similarity search:

```sql
CREATE OR REPLACE FUNCTION match_papers(
  query_embedding VECTOR(1536),
  match_threshold FLOAT,
  match_count INT
)
RETURNS TABLE(
  id TEXT, title TEXT, abstract TEXT, authors JSONB,
  url TEXT, published_at TIMESTAMPTZ,
  summary_tldr TEXT, similarity FLOAT
)
LANGUAGE SQL STABLE
AS $$
  SELECT
    papers.id, papers.title, papers.abstract, papers.authors,
    papers.url, papers.published_at, papers.summary_tldr,
    1 - (papers.embedding <=> query_embedding) AS similarity
  FROM papers
  WHERE 1 - (papers.embedding <=> query_embedding) > match_threshold
  ORDER BY similarity DESC
  LIMIT match_count;
$$;
```

The `<=>` operator computes cosine distance; `1 - distance` gives cosine similarity (range: `[-1, 1]`).

### Indexing

The `papers` table has an **IVFFlat index** for faster approximate nearest-neighbour (ANN) lookup:

```sql
CREATE INDEX IF NOT EXISTS idx_papers_embedding
  ON papers USING ivfflat (embedding vector_cosine_ops);
```

There is also a B-tree index on `published_at DESC` for time-ordered paper feed queries.

### Uses

- **Semantic search:** "Find papers like this one" via `match_papers()`
- **Duplicate detection:** Before inserting a new paper, check if a vector-near match already exists
- **Related papers panel:** The paper detail page surface similar papers

### Embedding Pipeline (Ingestion)

The full ingestion flow is in `backend/scripts/daily_fetch.py`:

```
1. Fetch papers from ArXiv + HuggingFace
2. Deduplicate by paper ID (cross-source + against existing DB)
3. For each new paper:
     text = title + "\n" + abstract
     embedding = embed_texts([text])  → 1536-dim vector
4. Batch upsert into Supabase papers table (100 papers/batch)
5. Run Summary Agent on each paper for TL;DR / difficulty
```

Embeddings are generated once at ingestion and cached in the `papers.embedding` column. They are not regenerated unless the paper's abstract is updated.

---

## Memory Agent Pipeline

The Memory Agent (`backend/agents/memory_agent.py`) runs as the final stage in the LangGraph orchestrator. Its job is to score and re-rank papers by relevance to the current user.

### Step-by-Step Algorithm

#### Step 1: Load User Profile

```
Emit SSE: {agent: "memory", status: "loading_profile"}
```

Call `get_user_profile(user_id)` to retrieve all Mem0 memories. If the call fails (network error, missing API key), the profile is treated as empty and the agent proceeds to fallback scoring.

#### Step 2: Score Papers (Primary — Embedding Similarity)

```
Emit SSE: {agent: "memory", status: "scoring_papers"}
```

**If the user has memories:**

1. Concatenate all memory strings into a single interest text.
2. Call `embed_texts()` to get vectors for:
   - The interest text (vector `I`)
   - Each paper's abstract (vectors `P₁, P₂, ..., Pₙ`)
3. Compute cosine similarity between `I` and each `Pᵢ`:

   ```
   relevance_score = cosine_similarity(I, Pᵢ)
   ```

4. Assign the score directly to the paper's `relevance_score` field.

**If embedding fails** (e.g., network error, missing `OPENAI_API_KEY`), all papers receive a default score of `0.5`.

#### Step 3: Fallback — Keyword Matching

**If the user has NO memories** (new user or Mem0 unavailable):

1. Extract keywords from the search query using a stopword filter (removes common English words like "the", "and", "of").
2. Extract keywords from each paper's `title + abstract`.
3. Compute a keyword overlap score:

   ```
   relevance_score = matches / len(query_keywords)
   ```

   The score is capped at `1.0`.

**If the query also has no extractable keywords**, all papers receive `0.5`.

#### Step 4: Sort by Relevance

```
Emit SSE: {agent: "memory", status: "ranking_complete", count: N}
```

Papers are sorted by `relevance_score` descending and returned to the orchestrator, which streams the final result to the frontend via SSE.

### Scoring Summary

| Condition | Scoring Method | Fallback |
|-----------|---------------|----------|
| User has Mem0 memories | Cosine similarity (interest embedding vs. paper embedding) | Default `0.5` |
| No Mem0 profile | Keyword overlap (query vs. title+abstract) | Default `0.5` |

---

## Write-back Flow

User actions feed back into the memory system to refine future rankings:

```
┌──────────────┐     POST /api/papers/{id}/save     ┌──────────────┐
│   Frontend   │ ──────────────────────────────────► │   FastAPI     │
│  (Save btn)  │                                     │  (papers.py)  │
└──────────────┘                                     └──────┬───────┘
                                                           │
                                                1. Upsert user_papers table
                                                   (Supabase)
                                                           │
                                                2. add_memory(user_id, [...])
                                                   (Mem0)
                                                           │
                                                3. Memory stored:
                                                   "Saved paper: {title}
                                                    about {abstract}..."
```

The write-back is **fire-and-forget** — if the Mem0 write fails, it logs a warning but does not fail the HTTP request. This ensures paper actions are never lost due to Mem0 outages.

---

## Data Flow Diagram

### Search & Scoring Flow

```
User searches "diffusion models for image generation"
       │
       ▼
┌───────────────────────────────────────────────────┐
│ POST /api/search                                   │
│   → orchestrator_graph.ainvoke()                   │
│                                                    │
│   ┌─────────────┐                                  │
│   │ Research    │  ArXiv API + HF Daily Papers     │
│   │ Agent       │  (discover papers)               │
│   └──────┬──────┘                                  │
│          │ papers[]                                │
│   ┌──────▼──────┐                                  │
│   │ Summary     │  LLM: TL;DR, contributions,      │
│   │ Agent       │  difficulty                      │
│   └──────┬──────┘                                  │
│          │ papers[] + summaries                    │
│   ┌──────▼──────┐                                  │
│   │ Memory      │                                  │
│   │ Agent       │──► Mem0.get_all(user_id)         │
│   │             │    ↓                             │
│   │             │──► embed_texts(interests +        │
│   │             │    abstracts) → cosine similarity │
│   │             │    ↓                             │
│   │             │──► sort by relevance_score DESC   │
│   └──────┬──────┘                                  │
│          │ ranked papers[]                         │
│   ┌──────▼──────┐                                  │
│   │ SSE Stream  │──► GET /api/stream/{run_id} ──►  │
│   │             │    Frontend (StreamingResponse)  │
│   └─────────────┘                                  │
└───────────────────────────────────────────────────┘
```

### Memory Write Journey

```
User clicks "Save" on PaperCard
       │
       ▼
POST /api/papers/{id}/save  {dismissed: false}
       │
       ├──► Supabase: UPSERT INTO user_papers (user_id, paper_id, dismissed)
       │
       └──► Mem0: add_memory(user_id, [{
                role: "user",
                content: "Saved paper: Diffusion Models: A Survey about ..."
            }])
                │
                ▼
          Mem0 auto-consolidation & deduplication
                │
                ▼
          Updated profile available for next search
```

---

> **Related docs:** See [docs/SCHEMA.md](./docs/SCHEMA.md) for the `papers` table and `match_papers()` function details. See [ARCHITECTURE.md](./ARCHITECTURE.md) Section 7 for the design decisions behind the memory system.
