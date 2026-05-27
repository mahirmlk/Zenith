# Database Schema Reference

> The data model for the AI Paper Research Agent — Supabase (Postgres) tables, functions, and Pydantic representations.

---

## Table of Contents

- [Overview](#overview)
- [Entity Relationship Diagram](#entity-relationship-diagram)
- [Tables](#tables)
  - [papers](#papers)
  - [user_papers](#user_papers)
  - [user_prefs](#user_prefs)
- [Functions](#functions)
  - [match_papers](#match_papers)
- [Pydantic Models](#pydantic-models)
  - [Paper](#paper)
  - [Search & Stream](#search--stream)
  - [User Preferences](#user-preferences)
  - [Citation Graph](#citation-graph)
- [Embedding Pipeline](#embedding-pipeline)

---

## Overview

The AI Paper Research Agent uses **Supabase** (managed Postgres) with the **pgvector** extension enabled. The schema is defined in `supabase/schema.sql` and consists of three tables plus one stored function.

- **Database:** PostgreSQL (via Supabase)
- **Vector extension:** `pgvector` — for 1536-dimensional paper embeddings
- **Auth:** Supabase Auth — `auth.users` table managed by Supabase (not defined in our schema)
- **Migration:** Run `supabase/schema.sql` once in the Supabase SQL Editor to initialise the schema

The `papers` table schema is defined in SQL; the Pydantic models in `backend/models/schemas.py` extend it with computed and runtime-only fields (e.g., `relevance_score`, `difficulty`).

---

## Entity Relationship Diagram

```mermaid
erDiagram
    auth_users {
        uuid id PK
        text email
    }

    papers {
        text id PK
        text title
        text abstract
        jsonb authors
        text url
        timestamptz published_at
        text summary_tldr
        vector embedding "(1536-dim)"
        timestamptz created_at
        jsonb summary_contributions "ALTER TABLE added"
    }

    user_papers {
        uuid user_id PK_FK
        text paper_id PK_FK
        timestamptz saved_at
        boolean dismissed
    }

    user_prefs {
        uuid user_id PK_FK
        text preferred_model
        text interests
        timestamptz updated_at
    }

    auth_users ||--o{ user_papers : "saves"
    auth_users ||--|| user_prefs : "has"
    papers ||--o{ user_papers : "saved in"
```

ASCII version:

```
┌──────────────┐       ┌──────────────────────┐       ┌──────────────┐
│  auth.users  │       │     user_papers       │       │    papers    │
│  (Supabase)  │       ├──────────────────────┤       ├──────────────┤
├──────────────┤       │ user_id    UUID  PK FK│──────►│ id    TEXT PK│
│ id    UUID PK│◄──────│ paper_id   TEXT  PK FK│       │ title   TEXT │
│ email  TEXT  │       │ saved_at   TIMESTAMPTZ│       │ abstract TEXT│
└──────────────┘       │ dismissed  BOOLEAN    │       │ ...          │
        │              └──────────────────────┘       └──────────────┘
        │
        │              ┌──────────────────────┐
        └──────────────│     user_prefs       │
                       ├──────────────────────┤
                       │ user_id   UUID PK FK │
                       │ preferred_model TEXT │
                       │ interests  TEXT[]    │
                       │ updated_at TIMESTAMPTZ│
                       └──────────────────────┘
```

---

## Tables

### `papers`

Stores all ingested papers with their metadata and vector embedding.

```sql
CREATE TABLE IF NOT EXISTS papers (
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
```

**Column Details:**

| Column | Type | Nullable | Default | Description |
|--------|------|----------|---------|-------------|
| `id` | `TEXT` | No (PK) | — | Unique paper identifier (ArXiv ID, HF paper ID). E.g., `"2301.00001v1"` |
| `title` | `TEXT` | No | — | Paper title |
| `abstract` | `TEXT` | Yes | — | Full abstract text |
| `authors` | `JSONB` | — | `'[]'` | Array of author name strings. E.g., `["Jane Doe", "John Smith"]` |
| `url` | `TEXT` | Yes | — | Link to the paper (ArXiv abstract page or PDF URL) |
| `published_at` | `TIMESTAMPTZ` | Yes | — | Publication or submission date |
| `summary_tldr` | `TEXT` | Yes | — | AI-generated one-line TL;DR (populated by Summary Agent) |
| `embedding` | `VECTOR(1536)` | Yes | — | OpenAI `text-embedding-3-small` vector of title + abstract |
| `created_at` | `TIMESTAMPTZ` | — | `NOW()` | Row creation timestamp |

**Additional columns added by `ALTER TABLE` at runtime:**

| Column | Type | Default | Description |
|--------|------|---------|-------------|
| `summary_contributions` | `JSONB` | `NULL` | AI-generated 3-bullet key contributions list (populated by Summary Agent) |

**> Note:** The columns `difficulty` and `papers_with_code` are used at runtime by the Summary Agent and Papers With Code service, but are added dynamically via upsert — they are not declared in the schema DDL. If running the schema on a fresh database, these columns will be created on first upsert.

**Indexes:**

```sql
-- Vector similarity search (approximate nearest neighbour)
CREATE INDEX IF NOT EXISTS idx_papers_embedding
  ON papers USING ivfflat (embedding vector_cosine_ops);

-- Time-sorted paper feed
CREATE INDEX IF NOT EXISTS idx_papers_published_at
  ON papers (published_at DESC);
```

| Index | Type | Column(s) | Purpose |
|-------|------|-----------|---------|
| `idx_papers_embedding` | IVFFlat | `embedding` (cosine ops) | Fast ANN for `match_papers()` semantic search |
| `idx_papers_published_at` | B-tree | `published_at DESC` | Efficient time-ordered paper listing |

---

### `user_papers`

Tracks which papers each user has saved or dismissed.

```sql
CREATE TABLE IF NOT EXISTS user_papers (
  user_id    UUID REFERENCES auth.users(id) ON DELETE CASCADE,
  paper_id   TEXT REFERENCES papers(id) ON DELETE CASCADE,
  saved_at   TIMESTAMPTZ DEFAULT NOW(),
  dismissed  BOOLEAN DEFAULT FALSE,
  PRIMARY KEY (user_id, paper_id)
);
```

**Column Details:**

| Column | Type | Nullable | Default | Description |
|--------|------|----------|---------|-------------|
| `user_id` | `UUID` | No (PK, FK) | — | References `auth.users(id)`. Cascade delete — removing a user removes their saved papers. |
| `paper_id` | `TEXT` | No (PK, FK) | — | References `papers(id)`. Cascade delete — removing a paper removes all saves/dismissals. |
| `saved_at` | `TIMESTAMPTZ` | — | `NOW()` | When the user saved or dismissed this paper |
| `dismissed` | `BOOLEAN` | — | `FALSE` | `TRUE` if dismissed, `FALSE` if saved (default). Used to filter feed. |

**Primary Key:** Composite `(user_id, paper_id)` — a user can only have one save/dismiss record per paper (upsert-overwrite semantics in the API).

**Relationships:**
- `user_id → auth.users(id)` — each record belongs to one user
- `paper_id → papers(id)` — each record references one paper

---

### `user_prefs`

Stores per-user application preferences.

```sql
CREATE TABLE IF NOT EXISTS user_prefs (
  user_id          UUID PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
  preferred_model  TEXT DEFAULT 'anthropic/claude-sonnet-4-5',
  interests        TEXT[] DEFAULT '{}',
  updated_at       TIMESTAMPTZ DEFAULT NOW()
);
```

**Column Details:**

| Column | Type | Nullable | Default | Description |
|--------|------|----------|---------|-------------|
| `user_id` | `UUID` | No (PK, FK) | — | References `auth.users(id)`. Cascade delete — removing a user removes their prefs. |
| `preferred_model` | `TEXT` | — | `'anthropic/claude-sonnet-4-5'` | The user's chosen LLM model (OpenRouter model ID). Set via ModelSelector UI. |
| `interests` | `TEXT[]` | — | `'{}'` | Array of research interest strings. E.g., `{"diffusion models", "graph neural networks"}`. |
| `updated_at` | `TIMESTAMPTZ` | — | `NOW()` | Last update timestamp |

**Relationship:** One-to-one with `auth.users` via the primary key foreign key.

---

## Functions

### `match_papers`

PostgreSQL function for cosine similarity vector search over the `papers` table.

```sql
CREATE OR REPLACE FUNCTION match_papers(
  query_embedding VECTOR(1536),
  match_threshold FLOAT,
  match_count INT
)
RETURNS TABLE(
  id TEXT,
  title TEXT,
  abstract TEXT,
  authors JSONB,
  url TEXT,
  published_at TIMESTAMPTZ,
  summary_tldr TEXT,
  similarity FLOAT
)
LANGUAGE SQL STABLE
AS $$
  SELECT
    papers.id,
    papers.title,
    papers.abstract,
    papers.authors,
    papers.url,
    papers.published_at,
    papers.summary_tldr,
    1 - (papers.embedding <=> query_embedding) AS similarity
  FROM papers
  WHERE 1 - (papers.embedding <=> query_embedding) > match_threshold
  ORDER BY similarity DESC
  LIMIT match_count;
$$;
```

**Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `query_embedding` | `VECTOR(1536)` | The 1536-dim embedding vector to search against (e.g., user interest embedding) |
| `match_threshold` | `FLOAT` | Minimum cosine similarity threshold (0.0–1.0). Papers below this are excluded. |
| `match_count` | `INT` | Maximum number of results to return. |

**Returns:** Table of matching paper rows, each with a `similarity` column (cosine similarity, 0.0–1.0).

**How it works:**
- `papers.embedding <=> query_embedding` computes **cosine distance** using pgvector's `<=>` operator (range `[0, 2]` where 0 = identical).
- `1 - distance` converts to **cosine similarity** (range `[-1, 1]` where 1 = identical).
- Results are filtered by `match_threshold`, sorted by similarity descending, and limited to `match_count`.

**Usage example:**
```sql
SELECT * FROM match_papers(
  query_embedding := '[0.012, -0.034, ...]'::VECTOR(1536),
  match_threshold := 0.7,
  match_count := 10
);
```

---

## Pydantic Models

The FastAPI backend uses Pydantic v2 models defined in `backend/models/schemas.py` for request/response serialisation and validation. These extend the database schema with computed and runtime-only fields.

### `Paper`

```python
class Paper(BaseModel):
    id: str                                          # matches papers.id
    title: str                                       # matches papers.title
    abstract: str                                    # matches papers.abstract
    authors: list[str]                               # Python list from JSONB
    url: str                                         # matches papers.url
    published_at: datetime                           # matches papers.published_at
    summary_tldr: Optional[str] = None               # matches papers.summary_tldr
    summary_contributions: Optional[list[str]] = None  # runtime field (ALTER TABLE)
    relevance_score: Optional[float] = None          # COMPUTED — not in DB
    difficulty: Optional[Literal["introductory", "intermediate", "expert"]] = None  # runtime field
    papers_with_code: Optional[dict] = None          # runtime field (Papers With Code)
```

| Field | Source | Notes |
|-------|--------|-------|
| `id` through `summary_tldr` | `papers` table | Direct column mapping |
| `authors` | `papers.authors` (JSONB) | Deserialised from JSON array to Python `list[str]` |
| `summary_contributions` | Runtime upsert | Added by `ALTER TABLE` in schema.sql; populated by Summary Agent |
| `relevance_score` | **Computed** | Assigned by Memory Agent at query time. Not stored in the database. |
| `difficulty` | Runtime upsert | Populated by Summary Agent during paper ingestion or on-demand summarisation |
| `papers_with_code` | Runtime upsert | Populated by Papers With Code service; contains `{"repos": [{"url": "...", "stars": 123}]}` |

### `PaperSearchResult`

```python
class PaperSearchResult(BaseModel):
    papers: list[Paper]
    run_id: str
```

Returned by `POST /api/search` and streamed via SSE. `run_id` is a unique identifier for the agent run, used to subscribe to the SSE stream at `GET /api/stream/{run_id}`.

### `SearchRequest`

```python
class SearchRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=500)  # 1-500 characters
    model: Optional[str] = None                              # Optional model override (OpenRouter ID)
```

Validates the search query length. `model` allows users to override the default summarisation LLM.

### `UserPrefs`

```python
class UserPrefs(BaseModel):
    preferred_model: str = "anthropic/claude-sonnet-4-5"
    interests: list[str] = Field(default_factory=list)
```

Maps to the `user_prefs` table. Used by `GET /api/prefs` and `POST /api/prefs`.

### `AgentStep`

```python
class AgentStep(BaseModel):
    agent: str                            # "research", "summary", "memory", "orchestrator"
    status: str                           # "fetching_arxiv", "summarising", "scoring_papers", etc.
    count: Optional[int] = None           # Paper count or batch index
    paper_id: Optional[str] = None        # Current paper being processed
    message: Optional[str] = None         # Human-readable status
```

Emitted as SSE events during agent pipeline execution. The frontend `StreamingResponse` component renders these as live progress indicators.

### `StreamEvent`

```python
class StreamEvent(BaseModel):
    event: Literal["agent_step", "result", "error"]
    data: dict
```

The top-level SSE event wrapper. Three event types:
- `agent_step` — progress from an agent (data is `AgentStep`)
- `result` — final ranked results (data is `PaperSearchResult`)
- `error` — pipeline failure or timeout

### `SavePaperRequest`

```python
class SavePaperRequest(BaseModel):
    dismissed: bool = False   # TRUE = dismiss, FALSE = save
```

### Citation Graph Models

```python
class GraphNode(BaseModel):
    id: str        # Paper ID
    title: str     # Paper title (for labels)
    x: float       # 3D position
    y: float
    z: float

class GraphEdge(BaseModel):
    source: str    # Citing paper ID
    target: str    # Cited paper ID

class CitationGraph(BaseModel):
    nodes: list[GraphNode]
    edges: list[GraphEdge]
```

Returned by `GET /api/graph/{paper_id}` for the Three.js citation graph visualisation. Source data comes from the Semantic Scholar API (`backend/services/semantic_scholar.py`).

---

## Embedding Pipeline

Paper text is converted to vector embeddings for semantic search by `backend/services/embeddings.py`.

### Model

| Property | Value |
|----------|-------|
| Model | OpenAI `text-embedding-3-small` |
| Dimension | 1536 |
| API | `POST https://api.openai.com/v1/embeddings` |
| Auth | `Authorization: Bearer $OPENAI_API_KEY` |
| Implementation | `embed_texts(texts: list[str]) → list[list[float]]` |

### Ingestion Flow

The pipeline is triggered by `backend/scripts/daily_fetch.py` (daily cron) or on-demand during search:

```
1. Paper text is constructed:  title + "\n" + abstract
                                 │
2. embed_texts([text])           ◄── OpenAI text-embedding-3-small API
                                 │
3. Returns 1536-dim float list   ◄── e.g., [0.0123, -0.0456, ...]
                                 │
4. Upserted into papers table    ◄── papers.embedding column
```

### Search Flow

When a user searches, the Memory Agent uses embeddings for relevance scoring (see [MEMORY.md](../MEMORY.md)):

```
1. User interest text → embed_texts([interest_text]) → interest_vector
2. Each paper abstract → embed_texts([abstracts]) → paper_vectors
3. Cosine similarity between interest_vector and each paper_vector
4. Sort by relevance_score DESC
```

The `match_papers()` PostgreSQL function enables direct database-side similarity search for "related papers" lookups without pulling all embeddings into Python.

---

> **Related docs:**
> - [ARCHITECTURE.md](../ARCHITECTURE.md) Section 5 — Data model in the architecture overview
> - [MEMORY.md](../MEMORY.md) — Memory system (Mem0 + pgvector) that uses this schema
> - [docs/API.md](./API.md) — API endpoints that expose these models
> - [supabase/schema.sql](../supabase/schema.sql) — The canonical DDL source file
