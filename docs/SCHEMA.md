# Database Schema Reference

> This is a legacy schema reference for Supabase (Postgres) tables and Pydantic representations. It is not a complete current-schema specification.

> **Current source of truth:** the ordered files in [`supabase/migrations/`](../supabase/migrations/) (currently 0001–0034) define the supported database schema. Read [`MIGRATIONS_RUNBOOK.md`](./MIGRATIONS_RUNBOOK.md) and apply the migration sequence to staging before production. `supabase/schema.sql` is an incomplete legacy baseline; do not use it to initialize or upgrade a production database.

---

## Table of Contents

- [Overview](#overview)
- [Entity Relationship Diagram](#entity-relationship-diagram)
- [Tables](#tables)
  - [papers](#papers)
  - [user_papers](#user_papers)
  - [user_prefs](#user_prefs)
  - [citations](#citations)
  - [crawled_content](#crawled_content)
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

Zenith uses **Supabase** (managed Postgres) with the **pgvector** extension enabled. This document's opening table descriptions are a legacy overview and omit objects added by later migrations. The supported schema is the cumulative result of migrations `0001`–`0034`.

- **Database:** PostgreSQL (via Supabase)
- **Vector extension:** `pgvector` — for 1536-dimensional paper embeddings
- **Auth:** Supabase Auth — `auth.users` table managed by Supabase (not defined in our schema)
- **Migration:** Apply the ordered files under `supabase/migrations/` using `docs/MIGRATIONS_RUNBOOK.md`; do not initialize production from `supabase/schema.sql`

The `papers` table schema is defined in SQL; the Pydantic models in `backend/models/schemas.py` extend it with computed and runtime-only fields (e.g., `relevance_score`, `difficulty`).

## Project annotations (migration 0031)

`project_annotations` stores user-authored notes anchored to source text. Each
row references either one attached `project_sources` row for a paper abstract,
or one `project_documents` row and page number for extracted PDF text. Composite
foreign keys include `project_id`, so a source in another project cannot be
used as an anchor. PDF anchors also reference an existing page row. Direct
authenticated table writes are revoked so quote validation must pass through
the API. The quote uses zero-based, half-open Unicode character
offsets and stores a server-generated SHA-256 fingerprint. Source, offsets,
quote, fingerprint, and creator are immutable; only `content` can be edited.
Authenticated project members can read annotations, while project owners and
editors can write. Rows cascade when their project or attached source/document
is deleted. The original PDF bytes are discarded after extraction, so an
annotation refers to retained extracted page text only. Migration
[`0031_project_annotations.sql`](../supabase/migrations/0031_project_annotations.sql)
is the authoritative table definition; this legacy schema reference is not a
complete installation snapshot.

## Saved searches (migration 0032)

`saved_searches` stores a normalized search name, query, optional model, and
optional project scope. Personal rows are visible only to their creator.
Project rows are visible to project members; owners/editors can create them,
and current project members may run them. The creator, owner, or editor may
update/delete a project row while still a member. Project scope and creator are immutable after creation.
The table stores configuration only; each explicit run starts a new search
through standard metered admission rather than replaying saved results.
Watchlists are separate recurring subscriptions. Migration
[`0032_saved_searches.sql`](../supabase/migrations/0032_saved_searches.sql)
is authoritative; this legacy schema reference is incomplete.

## Versioned project briefs (migration 0033)

`project_briefs` stores project-scoped brief metadata and the latest version
number. `project_brief_versions` stores immutable, manually authored revisions
and structured snapshots of citations to attached paper abstracts or extracted
PDF pages. Each snapshot includes stable source IDs, a zero-based half-open
Unicode locator, exact quote, and source/quote fingerprints. Members can read;
owners/editors append through service-only atomic RPCs that recheck the actor's
role, lock the brief, verify every source quote against current project text,
and reject stale expected version numbers. Direct authenticated table writes
are revoked. Account export includes brief metadata for accessible projects
and all versions in owned projects plus caller-authored versions in shared
projects. Account deletion removes the caller's authored records and reconciles
the shared brief head. Migration
[`0033_versioned_project_briefs.sql`](../supabase/migrations/0033_versioned_project_briefs.sql)
is authoritative.

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
        text summary_status "default unknown"
        text summary_fallback_reason
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

    citations {
        text paper_id PK_FK
        text root_title
        text cited_id PK
        text cited_title
        timestamptz fetched_at
    }

    crawled_content {
        text paper_id PK_FK
        text url
        text parser_version
        text content
        timestamptz fetched_at
    }

    auth_users ||--o{ user_papers : "saves"
    auth_users ||--|| user_prefs : "has"
    papers ||--o{ user_papers : "saved in"
    papers ||--o{ citations : "references"
    papers ||--o| crawled_content : "crawled"
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
| `doi` | `TEXT` | Yes | — | DOI returned by the source; Crossref update checks require a valid DOI |
| `publication_update_type` | `TEXT` | Yes | — | Supported Crossref update type, when present in deposited metadata |
| `publication_update_doi` | `TEXT` | Yes | — | DOI of the Crossmark update/retraction notice |
| `publication_update_label` | `TEXT` | Yes | — | Provider label for the notice |
| `publication_update_date` | `DATE` | Yes | — | Provider-reported notice date |
| `publication_update_source` | `TEXT` | Yes | — | `crossref` when a supported relation is stored |
| `publication_update_deposit_source` | `TEXT` | Yes | — | Crossref relation depositor/source: `publisher` or `retraction-watch`; null when absent or unknown |
| `publication_update_checked_at` | `TIMESTAMPTZ` | Yes | — | Last successful Crossref metadata lookup, including empty metadata |
| `summary_tldr` | `TEXT` | Yes | — | AI-generated one-line TL;DR (populated by Summary Agent) |
| `summary_status` | `TEXT` | No | `unknown` | `generated` only after provider settlement and output validation; `abstract_preview` for visible abstract-derived fallback text; `unknown` for legacy rows |
| `summary_fallback_reason` | `TEXT` | Yes | `NULL` | One of `per_run_cap`, `spend_limit`, `billing_unavailable`, `provider_unavailable`, or `invalid_output`; required when status is `abstract_preview` |
| `embedding` | `VECTOR(1536)` | Yes | — | OpenAI `text-embedding-3-small` vector of title + abstract |
| `created_at` | `TIMESTAMPTZ` | — | `NOW()` | Row creation timestamp |

**Additional columns added by `ALTER TABLE` at runtime:**

| Column | Type | Default | Description |
|--------|------|---------|-------------|
| `summary_contributions` | `JSONB` | `NULL` | AI-generated 3-bullet key contributions list (populated by Summary Agent) |
| `summary_status` | `TEXT` | `'unknown'` | Provenance for the stored `summary_tldr`; migration 0024 adds a check constraint |
| `summary_fallback_reason` | `TEXT` | `NULL` | Bounded reason code for an abstract-preview fallback; migration 0024 constrains allowed values and status pairing |
| publication update fields | `TEXT`, `DATE`, `TIMESTAMPTZ` | `NULL` | Migration 0025 stores DOI-backed Crossref update provenance; empty metadata remains unknown |

### `paper_status_watches` (migration 0025)

Explicit per-user opt-in to Crossref update alerts. The composite primary key
`(user_id, paper_id)` makes repeated opt-in idempotent. RLS permits each user
to select, insert, and delete only their own preference; the backend scheduler
uses its service-role client and still derives recipients from these scoped
rows. `last_attempt_at` applies retry backoff and is not a provider-success
cursor. Notifications use a per-user stable notice key so distinct later
notices remain deliverable.

**> Note:** The legacy `papers_with_code` response field remains for wire compatibility but is not populated by the current GitHub repository search path. Repository candidates are returned by the paper-code and implementation-plan endpoints.

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
  preferred_model  TEXT DEFAULT 'anthropic/claude-sonnet-5.5',
  interests        TEXT[] DEFAULT '{}',
  updated_at       TIMESTAMPTZ DEFAULT NOW()
);
```

**Column Details:**

| Column | Type | Nullable | Default | Description |
|--------|------|----------|---------|-------------|
| `user_id` | `UUID` | No (PK, FK) | — | References `auth.users(id)`. Cascade delete — removing a user removes their prefs. |
| `preferred_model` | `TEXT` | — | `'anthropic/claude-sonnet-5.5'` | The user's chosen LLM model (OpenRouter model ID). Set via ModelSelector UI. |
| `interests` | `TEXT[]` | — | `'{}'` | Array of research interest strings. E.g., `{"diffusion models", "graph neural networks"}`. |
| `updated_at` | `TIMESTAMPTZ` | — | `NOW()` | Last update timestamp |

**Relationship:** One-to-one with `auth.users` via the primary key foreign key.

---

### `citations`

Caches citation-graph edges fetched from Semantic Scholar, keyed by the root paper. This is the backing table for `GET /api/graph/{paper_id}` — without it the endpoint would hit the rate-limited S2 API (~100 req/5 min unshared) on every graph load.

```sql
CREATE TABLE IF NOT EXISTS citations (
  paper_id    TEXT REFERENCES papers(id) ON DELETE CASCADE,
  root_title  TEXT,
  cited_id    TEXT,
  cited_title TEXT,
  fetched_at  TIMESTAMPTZ DEFAULT NOW(),
  PRIMARY KEY (paper_id, cited_id)
);
```

**Column Details:**

| Column | Type | Nullable | Default | Description |
|--------|------|----------|---------|-------------|
| `paper_id` | `TEXT` | No (PK, FK) | — | The root paper the graph was expanded from. References `papers(id)`. |
| `root_title` | `TEXT` | Yes | — | Title of the root paper (denormalised so the graph can render without a join). |
| `cited_id` | `TEXT` | No (PK) | — | Cited neighbour paper ID (Semantic Scholar `paperId`). |
| `cited_title` | `TEXT` | Yes | — | Title of the cited neighbour. |
| `fetched_at` | `TIMESTAMPTZ` | — | `NOW()` | When the edge was fetched. Used for cache freshness (7-day TTL). |

**Indexes:**

```sql
CREATE INDEX IF NOT EXISTS idx_citations_paper_id ON citations (paper_id, fetched_at DESC);
```

The router reads `citations` first and only calls S2 on a cache miss or when the cache is stale, then upserts the fresh edges.

---

### `crawled_content`

Retains legacy derived full-text content by paper ID. The current application does not access this table. If a controlled fetcher is enabled later, cache reuse must require the exact source URL and parser version; hosted crawling remains disabled because redirect destinations and worker egress cannot currently be constrained.

```sql
CREATE TABLE IF NOT EXISTS crawled_content (
  paper_id   TEXT PRIMARY KEY REFERENCES papers(id) ON DELETE CASCADE,
  url        TEXT,
  parser_version TEXT,
  content    TEXT,
  fetched_at TIMESTAMPTZ DEFAULT NOW()
);
```

**Column Details:**

| Column | Type | Nullable | Default | Description |
|--------|------|----------|---------|-------------|
| `paper_id` | `TEXT` | No (PK, FK) | — | Paper ID the content belongs to. |
| `url` | `TEXT` | Yes | — | The URL that was crawled. |
| `parser_version` | `TEXT` | Yes | — | Version recorded by prior extraction implementations; not read by the disabled crawler. |
| `content` | `TEXT` | Yes | — | Legacy derived markdown. New hosted crawls are disabled. |
| `fetched_at` | `TIMESTAMPTZ` | — | `NOW()` | When the crawl was stored. |

The disabled crawler does not read or write this legacy table. The table remains for existing deployments and is deleted with its paper row.

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
    doi: Optional[str] = None
    publication_update_type: Optional[Literal["retraction", "partial_retraction", "withdrawal", "removal", "expression_of_concern"]] = None
    publication_update_doi: Optional[str] = None
    publication_update_label: Optional[str] = None
    publication_update_date: Optional[date] = None
    publication_update_source: Optional[Literal["crossref"]] = None
    publication_update_deposit_source: Optional[Literal["publisher", "retraction-watch"]] = None
    publication_update_checked_at: Optional[datetime] = None
    summary_tldr: Optional[str] = None               # matches papers.summary_tldr
    summary_contributions: Optional[list[str]] = None  # runtime field (ALTER TABLE)
    summary_status: Literal["generated", "abstract_preview", "unknown"] = "unknown"
    summary_fallback_reason: Optional[Literal["per_run_cap", "spend_limit", "billing_unavailable", "provider_unavailable", "invalid_output"]] = None
    relevance_score: Optional[float] = None          # COMPUTED — not in DB
    difficulty: Optional[Literal["introductory", "intermediate", "expert"]] = None  # runtime field
    papers_with_code: Optional[dict] = None          # legacy response compatibility field
```

| Field | Source | Notes |
|-------|--------|-------|
| `id` through `summary_tldr` | `papers` table | Direct column mapping |
| `authors` | `papers.authors` (JSONB) | Deserialised from JSON array to Python `list[str]` |
| `summary_contributions` | Runtime upsert | Added by `ALTER TABLE` in schema.sql; populated by Summary Agent |
| `summary_status` | `papers` table / summary runtime | `generated` requires metered settlement and validated output; legacy rows remain `unknown` |
| `summary_fallback_reason` | `papers` table / summary runtime | Set only for `abstract_preview` fallback results |
| `relevance_score` | **Computed** | Assigned by Memory Agent at query time. Not stored in the database. |
| `difficulty` | Runtime upsert | Populated by Summary Agent during paper ingestion or on-demand summarisation |
| `papers_with_code` | Legacy response field | Not currently populated; repository candidates come from the paper-code lookup endpoint |

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
    preferred_model: str = "anthropic/claude-sonnet-5.5"
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
> - [supabase/schema.sql](../supabase/schema.sql) — Incomplete legacy schema baseline; not the production migration source
