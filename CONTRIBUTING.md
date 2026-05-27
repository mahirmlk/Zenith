# Contributing Guide

> Everything you need to contribute code, tests, documentation, or bug reports to the AI Paper Research Agent.

---

## Table of Contents

- [Welcome](#welcome)
- [Code of Conduct](#code-of-conduct)
- [Getting Started](#getting-started)
- [Project Structure](#project-structure)
- [Development Workflow](#development-workflow)
- [Coding Standards](#coding-standards)
- [Testing Guidelines](#testing-guidelines)
- [Commit Convention](#commit-convention)
- [Pull Request Process](#pull-request-process)
- [Issue Guidelines](#issue-guidelines)

---

## Welcome

Thank you for your interest in contributing! The AI Paper Research Agent is a multi-layered system spanning a Next.js frontend, a FastAPI backend, LangGraph agent orchestration, and several external integrations. Whether you are fixing a typo, adding a test, building a new agent tool, or improving the citation graph — your contribution is valued.

Before you start, please read this guide and the [Code of Conduct](#code-of-conduct).

---

## Code of Conduct

We follow the [Contributor Covenant Code of Conduct](https://www.contributor-covenant.org/version/2/1/code_of_conduct/). In summary:

- Be respectful and inclusive.
- Assume good intent.
- Provide constructive feedback.
- Report unacceptable behaviour to the maintainers.

---

## Getting Started

### Prerequisites

| Tool | Minimum Version | Purpose |
|------|----------------|---------|
| Python | 3.12+ | Backend runtime |
| Node.js | 20 LTS | Frontend runtime |
| Docker | 24+ | Docker Compose local dev stack |
| Supabase Account | Free tier | Auth, database, pgvector |
| OpenRouter API Key | — | Primary LLM gateway |
| Git | 2.40+ | Version control |

Optional API keys (features degrade gracefully without them): `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `GOOGLE_API_KEY`, `MISTRAL_API_KEY`, `FIRECRAWL_API_KEY`, `SEMANTIC_SCHOLAR_API_KEY`, `MEM0_API_KEY`.

### 1. Fork and Clone

```bash
# Fork the repository on GitHub, then:
git clone https://github.com/<your-username>/ai-paper-research-agent.git
cd ai-paper-research-agent

# Add the upstream remote
git remote add upstream https://github.com/<org>/ai-paper-research-agent.git
```

### 2. Install Dependencies

**Backend:**
```bash
cd backend
pip install -e ".[dev]"
```

This installs the backend with all dev dependencies: `pytest`, `pytest-asyncio`, `httpx`, `ruff`, `mypy`.

**Frontend:**
```bash
cd frontend
npm install
```

### 3. Set Up Environment

```bash
# Copy the environment template
cp .env.example .env

# Edit .env with your API keys
# At minimum, fill in:
#   OPENROUTER_API_KEY, SUPABASE_URL, SUPABASE_ANON_KEY
#   SUPABASE_SERVICE_ROLE_KEY, SUPABASE_JWT_SECRET
```

### 4. Set Up Supabase

1. Create a free project at [supabase.com](https://supabase.com).
2. Enable the `vector` extension in the SQL Editor:
   ```sql
   CREATE EXTENSION IF NOT EXISTS vector;
   ```
3. Run the schema migration: copy the contents of `supabase/schema.sql` into the SQL Editor and execute.
4. Copy your project's URL, anon key, service role key, and JWT secret into `.env`.

### 5. Run Locally

```bash
# Start all services with Docker Compose
docker compose up --build
```

- **Frontend:** [http://localhost:3000](http://localhost:3000)
- **Backend:** [http://localhost:8000](http://localhost:8000)
- **API Docs (Swagger):** [http://localhost:8000/docs](http://localhost:8000/docs)
- **Redis:** `localhost:6379`

For individual service startup without Docker, see [docs/DEVELOPER_GUIDE.md](./docs/DEVELOPER_GUIDE.md).

---

## Project Structure

The project follows a strict **four-layer architecture**:

| Layer | Directory | Layer Boundary |
|-------|-----------|---------------|
| **1 — Frontend** | `frontend/` | Never accesses DB or LLM APIs directly |
| **2 — Backend** | `backend/` | Never imports from `frontend/` |
| **3 — Agents** | `backend/agents/` | Calls services only; never accesses request/response objects |
| **4 — Services** | `backend/services/` | Never calls agents or routers |

```
ai-paper-research-agent/
├── frontend/                # Next.js 15 (App Router), TypeScript, Tailwind
│   ├── app/                 # Pages: feed, graph, paper/[id], settings, (auth)
│   ├── components/          # PaperCard, StreamingResponse, CitationGraph, etc.
│   ├── lib/                 # API client (api.ts), auth helpers (auth.ts)
│   ├── store/               # Zustand store (useAppStore.ts)
│   └── types/               # TypeScript type definitions
├── backend/                 # FastAPI (Python 3.12)
│   ├── main.py              # App entry, middleware, router registration
│   ├── config.py            # Pydantic settings (env var loading)
│   ├── dependencies.py      # Auth dependency injection
│   ├── routers/             # 8 API routers (health, auth, papers, search, stream, graph, prefs, pwc)
│   ├── agents/              # LangGraph agents (orchestrator, research, summary, memory)
│   ├── services/            # 12 external service integrations
│   ├── middleware/           # Rate limiting (slowapi), response timing
│   └── models/              # Pydantic schemas (schemas.py)
├── supabase/
│   └── schema.sql           # Database migration (tables + match_papers function)
├── docs/                    # API, developer guide, deployment guide, schema
├── .github/workflows/       # CI (lint, type-check, test, Docker build)
├── docker-compose.yml       # Local dev stack
└── docker-compose.prod.yml  # Production Docker stack
```

### Layer Violations — Do Not Cross Boundaries

- **Frontend** must never call Supabase directly for paper data (use the API).
- **Backend routers** must never contain business logic — delegate to agents and services.
- **Agents** must never read from `request` objects or write to `response` objects.
- **Services** must never import from `agents/` or `routers/`.

---

## Development Workflow

### 1. Create a Feature Branch

```bash
git checkout main
git pull upstream main
git checkout -b feat/your-feature-name
```

Use branch prefixes: `feat/`, `fix/`, `docs/`, `chore/`, `refactor/`, `test/`.

### 2. Make Your Changes

Follow the [Coding Standards](#coding-standards). Write tests for new functionality. Keep PRs focused — one logical change per PR.

### 3. Run Tests

**Backend:**
```bash
cd backend
pytest
```

**Frontend:**
```bash
cd frontend
npx vitest run
```

All tests must pass before opening a PR.

### 4. Run Linters & Type Checkers

**Backend:**
```bash
cd backend
ruff check .        # Python linter
mypy .              # Static type checker (strict mode)
```

**Frontend:**
```bash
cd frontend
npm run lint        # ESLint
npx tsc --noEmit    # TypeScript type-check
```

All linters and type checks must pass before opening a PR. The CI workflow (`ci.yml`) enforces this automatically.

### 5. Commit

Follow the [Commit Convention](#commit-convention). Write clear, descriptive messages.

### 6. Open a Pull Request

Push your branch and open a PR against `main` on the upstream repository. Fill in the PR template and request a review.

---

## Coding Standards

### Python (Backend & Agents)

- **Type hints everywhere.** Every function signature must have parameter types and a return type. The project uses `mypy` in strict mode (`backend/pyproject.toml`).
- **Pydantic v2 models** for all request/response schemas. Use `BaseModel` from `pydantic`.
- **Async where I/O is involved.** All database queries, HTTP calls, and LLM invocations must be `async def`. Use `httpx.AsyncClient`, `supabase-py`'s async client, and LangChain's async invoke methods.
- **Error handling:** Return structured errors via `fastapi.HTTPException`. Services should raise domain-specific exceptions; routers should catch and convert them.
- **Configuration:** All config values come from `backend/config.py` (Pydantic `BaseSettings`). Never hardcode URLs, keys, or model names.
- **Logging:** Use the standard `logging` module with module-level loggers (`logger = logging.getLogger(__name__)`). The project uses structured logging (`backend/logging_config.py`).
- **Retry logic:** Use `backend/services/retry.py` (`async_retry` with exponential backoff) for all external API calls.
- **Line length:** 100 characters (`ruff` line-length setting).

### TypeScript / React (Frontend)

- **`'use client'` directive** at the top of any file that uses React hooks (`useState`, `useEffect`, `useQuery`, etc.) or browser APIs. Server components (App Router default) do not include this.
- **Tailwind CSS** for all styling. No inline styles or CSS modules unless Tailwind cannot express the style.
- **React Query (TanStack Query)** for all server state — data fetching, caching, background refetching. Configured via `QueryProvider` wrapping the app.
- **Zustand** for lightweight client-side state (selected model, UI preferences). Keep store actions minimal and focused.
- **TypeScript types** are defined in `frontend/types/index.ts`. Export interfaces matching the backend Pydantic schemas. Use strict TypeScript (`tsc --noEmit` must pass).
- **Components:** One component per file, named export preferred. Use functional components with hooks.
- **Accessibility:** Add `aria-label` on interactive elements, ensure keyboard navigation works, use semantic HTML elements.
- **Error boundaries:** Wrap sections that may fail (e.g., citation graph) in `ErrorBoundary` components.

### Architecture Boundaries

- No direct database access from the frontend — use the API.
- No business logic in routers — delegate to agents and services.
- No request/response objects in agents — they work with plain data.
- No agent imports in services — services have no knowledge of the agent layer.

---

## Testing Guidelines

### Every Feature Needs at Least One Test

Before a feature is considered complete, add a test that covers its core behaviour. This is enforced during PR review.

### Backend Tests

- **Framework:** `pytest` + `pytest-asyncio`
- **Location:** `backend/tests/`
- **Pattern:** Arrange objects and mocks, act by calling the function, assert expectations.
- **Mock external services:** Use `unittest.mock` or `pytest-mock` for ArXiv, HuggingFace, Mem0, Supabase, and LLM calls. Do not make real API calls in unit tests.
- **Test routers separately:** Use FastAPI's `TestClient` with dependency overrides to mock auth and database calls.

Example test structure:
```python
# backend/tests/test_memory_agent.py
import pytest
from agents.memory_agent import memory_agent

@pytest.mark.asyncio
async def test_ranks_papers_by_keyword_match():
    papers = [
        {"id": "1", "title": "Diffusion Models", "abstract": "We present a survey..."},
        {"id": "2", "title": "Cat Behaviour", "abstract": "Feline psychology..."},
    ]
    async def mock_callback(step):
        pass

    result = await memory_agent(papers, user_id="u1", query="diffusion", callback=mock_callback)
    assert result[0]["id"] == "1"  # Higher relevance to "diffusion"
```

### Frontend Tests

- **Framework:** `vitest` + `@testing-library/react`
- **Location:** Co-located with components or in `frontend/__tests__/`
- **Pattern:** Render the component, query the DOM, simulate user interaction, assert the rendered output.
- **Mock API calls:** Use `vi.mock()` to stub `api.ts` functions so no real network requests are made.

Example test structure:
```tsx
// frontend/__tests__/PaperCard.test.tsx
import { render, screen } from "@testing-library/react";
import { PaperCard } from "@/components/PaperCard";

test("renders paper title and TL;DR", () => {
  render(<PaperCard paper={{ id: "1", title: "Test Paper", summary_tldr: "A test TL;DR" }} />);
  expect(screen.getByText("Test Paper")).toBeInTheDocument();
  expect(screen.getByText("A test TL;DR")).toBeInTheDocument();
});
```

### Running Tests

```bash
# Backend (all tests)
cd backend && pytest

# Backend (single file)
cd backend && pytest tests/test_papers.py

# Frontend (all tests)
cd frontend && npx vitest run

# Frontend (single file)
cd frontend && npx vitest run __tests__/PaperCard.test.tsx
```

---

## Commit Convention

We use [Conventional Commits](https://www.conventionalcommits.org/). Every commit message must follow this format:

```
<type>: <short description>

[optional body]

[optional footer(s)]
```

### Types

| Type | When to Use |
|------|------------|
| `feat` | A new feature (e.g., `feat: add Semantic Scholar citation graph integration`) |
| `fix` | A bug fix (e.g., `fix: handle null abstract in memory agent scoring`) |
| `docs` | Documentation changes only (e.g., `docs: add deployment guide for Fly.io`) |
| `chore` | Maintenance, dependency bumps, tooling (e.g., `chore: upgrade ruff to 0.9.0`) |
| `refactor` | Code changes that neither fix a bug nor add a feature (e.g., `refactor: extract retry logic to shared module`) |
| `test` | Adding or updating tests (e.g., `test: add integration tests for search pipeline`) |
| `style` | Formatting, whitespace, lint-fix changes (e.g., `style: run ruff format`) |
| `ci` | CI/CD configuration changes (e.g., `ci: add Docker build job to CI pipeline`) |

### Examples

```
feat: add Papers With Code integration to paper detail page
fix: prevent duplicate memories from rapid save/dismiss
docs: document Mem0 write-back flow in MEMORY.md
refactor: move embeddings logic to separate service
test: add unit tests for keyword extraction in memory agent
```

### Scope (Optional)

You may include a scope in parentheses for clarity:

```
feat(agents): add fallback model chain to llm_router
fix(stream): handle client disconnect during SSE stream
```

---

## Pull Request Process

### Before Opening a PR

- [ ] All tests pass (`pytest` and `npx vitest run`)
- [ ] All linters pass (`ruff check .`, `mypy .`, `npm run lint`, `npx tsc --noEmit`)
- [ ] The branch is up to date with `main` (rebase, do not merge)
- [ ] New code follows the [Coding Standards](#coding-standards)
- [ ] New features include at least one test
- [ ] New environment variables are added to `.env.example`
- [ ] Documentation is updated if the change affects user-facing behaviour

### PR Review Checklist

Reviewers will verify:

1. **Architecture:** Does the change respect the four-layer boundaries? No layer violations.
2. **Correctness:** Does the logic handle edge cases (null values, network failures, empty results)?
3. **Performance:** Are expensive operations (LLM calls, embedding generation) cached or batched?
4. **Security:** Are new endpoints rate-limited? Are secrets kept out of client-side code?
5. **Tests:** Does the PR include adequate test coverage for the change?
6. **Style:** Does the code follow [Coding Standards](#coding-standards)?

### How to Request a Review

1. Open the PR on GitHub.
2. Fill in the PR template (if available).
3. Assign at least one reviewer (or tag `@maintainers`).
4. Respond to review feedback — make changes, push new commits, and request re-review.

Tip: Keep PRs small and focused. A PR that touches 5 files is much easier to review than one that touches 50.

---

## Issue Guidelines

### Bug Report Template

When filing a bug, include:

```markdown
**Description:** Clear and concise description of the bug.

**Steps to Reproduce:**
1. Go to '...'
2. Click on '...'
3. See error

**Expected Behaviour:** What should have happened.

**Actual Behaviour:** What actually happened. Include error messages, stack traces, or screenshots.

**Environment:**
- OS: [e.g. macOS 14, Windows 11]
- Browser: [e.g. Chrome 120]
- Backend version: [e.g. 0.1.0]
- Node version: [e.g. 20.11]
- Python version: [e.g. 3.12.1]
- Docker: [yes/no]
```

### Feature Request Template

```markdown
**Problem:** What problem does this feature solve?

**Proposed Solution:** Describe the feature you would like to see.

**Alternatives Considered:** Any alternatives you have thought about.

**Impact:** Which layers would be affected (frontend, backend, agents, services)?
```

---

> **Questions?** Check [docs/DEVELOPER_GUIDE.md](./docs/DEVELOPER_GUIDE.md) for detailed setup and troubleshooting. For architecture questions, see [ARCHITECTURE.md](./ARCHITECTURE.md).
