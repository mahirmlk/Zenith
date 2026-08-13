# ADR-001: Four-Layer Architecture

**Status:** Accepted

## Context

The original codebase mixed responsibilities: routers reached into databases directly, agents duplicated external-call logic, and the frontend talked to Supabase directly. This made the system hard to test, hard to change, and risky to scale (client-side secrets, duplicated credentials, un-cacheable calls).

We needed clear boundaries so that:
- The frontend never holds service-role credentials or business logic.
- API behaviour (auth, rate limits) lives in one place.
- Agent orchestration can be tested with mock LLM responses.
- External integrations are swap-in/swap-out.

## Decision

Adopt a strict four-layer architecture enforced in `CONTRIBUTING.md` and `docs/DEVELOPER_GUIDE.md`:

1. **Layer 1 — Frontend** (`frontend/`): UI only. Never accesses the database or LLM APIs directly; communicates exclusively over HTTP/SSE with the backend.
2. **Layer 2 — Backend** (`backend/routers/`): REST API gateway. Validates JWT, applies rate limits, and delegates to agents. Routers contain no business logic.
3. **Layer 3 — Agents** (`backend/agents/`): LangGraph orchestration. Never imports from routers, never touches request/response objects, calls services for all I/O.
4. **Layer 4 — Services** (`backend/services/`): External API wrappers and shared logic. Never imports from agents or routers.

The backend is structured accordingly:

```
backend/
├── routers/     # Layer 2 — HTTP endpoints
├── agents/      # Layer 3 — LangGraph orchestration
├── services/    # Layer 4 — external integrations
├── middleware/  # rate limiting, response timing
├── models/      # Pydantic schemas (shared contracts)
└── main.py      # app entry, router registration
```

## Consequences

- **Positive:** Clear test seams at every layer; frontend uses only anon keys; secrets stay server-side; endpoints can be rate-limited and auth-protected uniformly.
- **Positive:** Services are independently swappable (e.g., swapping the citation source only touches `services/`).
- **Negative:** Cross-layer features require touching multiple directories and agreeing on a Pydantic/TypeScript contract first.
- **Follow-up:** RLS policies on Supabase tables are intentionally left for deployers (`docs/DEPLOYMENT.md`) so the layer boundaries in code match a defence-in-depth posture in the database.
