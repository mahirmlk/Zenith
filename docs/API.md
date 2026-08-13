# API Reference

> Base URL: `http://localhost:8000` (development) or your deployed backend URL

---

## Table of Contents

- [Authentication](#authentication)
- [Health](#health)
- [Auth](#auth)
- [Papers](#papers)
- [Search](#search)
- [Stream](#stream)
- [Citation Graph](#citation-graph)
- [Preferences](#preferences)
- [Papers With Code](#papers-with-code)
- [SSE Events](#sse-events-reference)
- [Error Codes](#error-codes)

---

## Authentication

All endpoints except `GET /api/health` require a Supabase JWT token passed in the `Authorization` header.

```
Authorization: Bearer <supabase-access-token>
```

The token is obtained from Supabase Auth after the user signs in via the frontend. The backend middleware validates the token using the Supabase JWKS endpoint (ES256 asymmetric signing) or, for legacy shared-secret projects, `SUPABASE_JWT_SECRET` (HS256).

**Unauthenticated requests** return `401 Unauthorized`.

---

## Health

### `GET /api/health`

Health check endpoint — no authentication required.

**Response (200):**

```json
{
  "status": "ok",
  "service": "ai-paper-agent-backend",
  "checks": {
    "supabase": true,
    "openrouter": true
  }
}
```

- If either check fails, `status` returns `"degraded"`.
- `supabase` check verifies the Supabase client initialises successfully.
- `openrouter` check verifies the `OPENROUTER_API_KEY` is configured.

**Rate Limit:** Exempt (no limit applied).

**Example:**
```bash
curl http://localhost:8000/api/health
```

---

## Auth

### `POST /api/auth/token`

Validate a Supabase JWT token and return the associated user ID.

**Request Body:**
```json
{
  "token": "eyJhbGciOiJIUzI1NiIs..."
}
```

**Response (200) — Valid token:**
```json
{
  "valid": true,
  "user_id": "a1b2c3d4-..."
}
```

**Response (200) — Invalid token:**
```json
{
  "valid": false,
  "user_id": null
}
```

**Errors:**
| Status | Detail |
|--------|--------|
| 500 | `JWT secret not configured` |

**Example:**
```bash
curl -X POST http://localhost:8000/api/auth/token \
  -H "Content-Type: application/json" \
  -d '{"token": "eyJhbGciOiJIUzI1NiIs..."}'
```

---

## Papers

### `GET /api/papers`

List papers from the personalised feed. Uses Supabase to query the `papers` table.

**Auth required:** Yes

**Query Parameters:**
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `q` | string | No | Optional title filter (case-insensitive `ILIKE` search) |

**Response (200):**
```json
[
  {
    "id": "arxiv-2401.001",
    "title": "Attention Is All You Need: A Survey of Transformer Variants",
    "abstract": "We survey the landscape of transformer architectures...",
    "authors": ["Alice Smith", "Bob Jones"],
    "url": "https://arxiv.org/pdf/2401.001.pdf",
    "published_at": "2024-01-15T00:00:00Z",
    "summary_tldr": "A comprehensive survey of transformer architecture variants...",
    "summary_contributions": ["Categorises major transformer variants", "Compares efficiency metrics"],
    "relevance_score": 0.85,
    "difficulty": "intermediate",
    "papers_with_code": null
  }
]
```

Without a query filter, papers are returned ordered by `published_at` descending, limited to 50 results. With a query filter, papers matching the title (ILIKE) are returned, also limited to 50.

**Example:**
```bash
curl http://localhost:8000/api/papers \
  -H "Authorization: Bearer <token>"

# With filter
curl "http://localhost:8000/api/papers?q=diffusion" \
  -H "Authorization: Bearer <token>"
```

---

### `GET /api/papers/{paper_id}`

Get a single paper's full details.

**Auth required:** Yes

**Path Parameters:**
| Parameter | Type | Description |
|-----------|------|-------------|
| `paper_id` | string | Paper identifier (e.g. `arxiv-2401.001`) |

**Response (200):**
```json
{
  "id": "arxiv-2401.001",
  "title": "Attention Is All You Need: A Survey of Transformer Variants",
  "abstract": "We survey the landscape...",
  "authors": ["Alice Smith", "Bob Jones"],
  "url": "https://arxiv.org/pdf/2401.001.pdf",
  "published_at": "2024-01-15T00:00:00Z",
  "summary_tldr": "A comprehensive survey...",
  "summary_contributions": ["Categorises major transformer variants"],
  "relevance_score": 0.85,
  "difficulty": "intermediate",
  "papers_with_code": null
}
```

**Errors:**
| Status | Detail |
|--------|--------|
| 404 | `Paper not found` |
| 500 | Server error |

**Example:**
```bash
curl http://localhost:8000/api/papers/arxiv-2401.001 \
  -H "Authorization: Bearer <token>"
```

---

### `POST /api/papers/{paper_id}/save`

Save or dismiss a paper. This also writes a memory entry to Mem0 for personalised ranking.

**Auth required:** Yes

**Request Body:**
```json
{
  "dismissed": false
}
```
Set `dismissed: true` to mark the paper as dismissed instead of saved.

**Response (200):**
```json
{
  "status": "ok"
}
```

This endpoint upserts into the `user_papers` table. It also records the action in Mem0 as a user memory entry (e.g. "Saved paper: Attention Is All You Need").

**Example:**
```bash
curl -X POST http://localhost:8000/api/papers/arxiv-2401.001/save \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{"dismissed": false}'
```

---

### `DELETE /api/papers/{paper_id}/save`

Remove a previously saved paper from the user's library.

**Auth required:** Yes

**Response (200):**
```json
{
  "status": "ok"
}
```

Deletes the row from `user_papers` table for the given user and paper.

**Example:**
```bash
curl -X DELETE http://localhost:8000/api/papers/arxiv-2401.001/save \
  -H "Authorization: Bearer <token>"
```

---

## Search

### `POST /api/search`

Trigger the multi-agent research pipeline. This creates a new run in the run store and returns a `run_id` that the frontend uses to connect to the SSE stream.

**Auth required:** No (user context is extracted if available)

**Request Body:**
```json
{
  "query": "diffusion models for image generation",
  "model": "anthropic/claude-sonnet-4-5"
}
```

| Field | Type | Required | Constraints | Description |
|-------|------|----------|-------------|-------------|
| `query` | string | Yes | 1–500 characters | Research topic to search for |
| `model` | string | No | — | Override the default LLM model (OpenRouter format: `provider/model-name`) |

**Response (200):**
```json
{
  "run_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890"
}
```

After receiving the `run_id`, the frontend opens an SSE connection to `GET /api/stream/{run_id}` to receive live agent progress and results.

**Rate Limit:** 10 requests per minute.

**Example:**
```bash
curl -X POST http://localhost:8000/api/search \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <token>" \
  -d '{"query": "reinforcement learning from human feedback"}'
```

---

## Stream

### `GET /api/stream/{run_id}`

SSE (Server-Sent Events) endpoint delivering live agent progress and final results. This is consumed by the frontend `StreamingResponse` component via `EventSource`.

**Auth required:** Yes

**Path Parameters:**
| Parameter | Type | Description |
|-----------|------|-------------|
| `run_id` | string | UUID returned from `POST /api/search` |

**Response:** `text/event-stream`

**SSE Event Types:** See [SSE Events Reference](#sse-events-reference) below.

**Rate Limit:** 20 requests per minute.

**Timeout:** The stream times out after 30 seconds of inactivity and sends an error event.

**Errors:**
| Status | Detail |
|--------|--------|
| 404 | `Run not found or expired` |

**Example (JavaScript):**
```javascript
const evtSource = new EventSource(
  `http://localhost:8000/api/stream/${runId}`
);

evtSource.addEventListener('agent_step', (e) => {
  const step = JSON.parse(e.data);
  console.log(`${step.agent}: ${step.status}`);
});

evtSource.addEventListener('result', (e) => {
  const result = JSON.parse(e.data);
  console.log('Papers:', result.papers);
  evtSource.close();
});
```

---

## Citation Graph

### `GET /api/graph/{paper_id}`

Get citation graph data for a paper. Used to render the 3-D citation network in the frontend.

**Auth required:** No (publicly available)

**Path Parameters:**
| Parameter | Type | Description |
|-----------|------|-------------|
| `paper_id` | string | Paper identifier (e.g. arxiv ID) |

**Response (200):**
```json
{
  "nodes": [
    { "id": "arxiv-2401.001", "title": "Target Paper", "x": 0, "y": 0, "z": 0 },
    { "id": "r1", "title": "Related Paper 1", "x": 1.2, "y": -0.8, "z": 2.1 },
    { "id": "r2", "title": "Related Paper 2", "x": -1.5, "y": 1.1, "z": -0.3 },
    { "id": "r3", "title": "Related Paper 3", "x": 2.0, "y": 0.3, "z": -1.8 }
  ],
  "edges": [
    { "source": "r1", "target": "arxiv-2401.001" },
    { "source": "r2", "target": "arxiv-2401.001" },
    { "source": "r3", "target": "arxiv-2401.001" }
  ]
}
```

Data is sourced from the **Semantic Scholar API**. If the S2 API is unavailable, the endpoint falls back to mock data with 3 reference nodes. References are capped at 10 for performance.

**Example:**
```bash
curl http://localhost:8000/api/graph/arxiv-2401.001
```

---

## Preferences

### `GET /api/prefs`

Get the current user's preferences.

**Auth required:** Yes

**Response (200):**
```json
{
  "preferred_model": "anthropic/claude-sonnet-4-5",
  "interests": ["diffusion models", "reinforcement learning"]
}
```

If no preferences are found for the user, a default response is returned with the default model and an empty interests array.

**Example:**
```bash
curl http://localhost:8000/api/prefs \
  -H "Authorization: Bearer <token>"
```

---

### `POST /api/prefs`

Create or update user preferences.

**Auth required:** Yes

**Request Body:**
```json
{
  "preferred_model": "openai/gpt-4o",
  "interests": ["transformer architectures", "rlhf", "multimodal models"]
}
```

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `preferred_model` | string | `"anthropic/claude-sonnet-4-5"` | User's preferred LLM model in OpenRouter format |
| `interests` | string[] | `[]` | List of research interest keywords |

**Response (200):**
```json
{
  "preferred_model": "openai/gpt-4o",
  "interests": ["transformer architectures", "rlhf", "multimodal models"]
}
```

Echoes back the preference data that was stored. Persisted in the `user_prefs` table via upsert.

**Example:**
```bash
curl -X POST http://localhost:8000/api/prefs \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{
    "preferred_model": "openai/gpt-4o",
    "interests": ["diffusion models", "rlhf"]
  }'
```

---

## Papers With Code

### `GET /api/papers/{paper_id}/code`

Fetch associated GitHub repositories for a paper via the Papers With Code API.

**Auth required:** No (publicly available)

**Path Parameters:**
| Parameter | Type | Description |
|-----------|------|-------------|
| `paper_id` | string | Paper identifier (mapped to `arxiv_id` for PWC lookup) |

**Response (200):**
```json
{
  "repos": [
    { "url": "https://github.com/author/paper-name", "stars": 1420 },
    { "url": "https://github.com/other-author/unofficial-impl", "stars": 230 }
  ]
}
```

If no repositories are found or the PWC API is unavailable, returns:

```json
{
  "repos": []
}
```

**Note:** This endpoint maps the `paper_id` parameter to the Papers With Code `arxiv_id` parameter for the lookup. The PWC API is rate-limited; HTTP errors are silently handled and an empty repos array is returned.

**Example:**
```bash
curl http://localhost:8000/api/papers/1706.03762/code \
  -H "Authorization: Bearer <token>"
```

---

## SSE Events Reference

The `GET /api/stream/{run_id}` endpoint emits the following SSE event types:

### `agent_step`

Sent whenever an agent node completes a sub-task.

```json
{
  "agent": "research",
  "status": "fetching_arxiv",
  "count": 12,
  "paper_id": null,
  "message": null
}
```

**Agent field values:** `"research"`, `"summary"`, `"memory"`, `"orchestrator"`

**Common status values:**

| Agent | Status | Meaning |
|-------|--------|---------|
| orchestrator | `started` | Pipeline initiated |
| research | `fetching_arxiv` | Querying ArXiv API |
| research | `arxiv_fetched` | ArXiv results returned |
| research | `fetching_huggingface` | Querying HuggingFace Daily Papers |
| research | `huggingface_fetched` | HF results returned |
| research | `deduplication_complete` | Duplicates removed |
| summary | `summarising` | Summarising a specific paper |
| summary | `complete` | All summaries generated |
| memory | `loading_profile` | Loading Mem0 user profile |
| memory | `scoring_papers` | Computing relevance scores |
| memory | `ranking_complete` | Papers ranked by relevance |
| orchestrator | `complete` | Entire pipeline finished |

### `result`

Sent when the full LangGraph pipeline completes.

```json
{
  "papers": [
    {
      "id": "arxiv-2401.001",
      "title": "Attention Is All You Need...",
      "abstract": "We survey...",
      "authors": ["Alice Smith"],
      "url": "https://arxiv.org/pdf/2401.001.pdf",
      "published_at": "2024-01-15T00:00:00Z",
      "summary_tldr": "A survey of transformer variants...",
      "summary_contributions": ["Contribution 1", "Contribution 2"],
      "relevance_score": 0.92,
      "difficulty": "intermediate",
      "papers_with_code": null
    }
  ],
  "run_id": "a1b2c3d4-..."
}
```

### `error`

Sent on pipeline failure or stream timeout (30s inactivity).

```json
{
  "message": "Failed to process query" 
}
```

---

## Error Codes

| Status | Meaning |
|--------|---------|
| 200 | Success |
| 401 | Unauthorized — missing or invalid JWT token |
| 404 | Resource not found (paper, run, etc.) |
| 429 | Rate limit exceeded |
| 500 | Internal server error |

**Validation errors** (422) are returned for malformed request bodies with FastAPI's standard error format.

### Rate Limits

Limits are enforced by `slowapi`:

| Endpoint | Limit |
|----------|-------|
| `/api/search` | 10 req / minute |
| `/api/stream/*` | 20 req / minute |
| `/api/health` | Exempt (unlimited) |
| All other endpoints | 60 req / minute (default) |
