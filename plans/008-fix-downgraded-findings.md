# Plan 008: Fix downgraded findings (input validation, datetime import, graph mock data, error boundary)

> **Executor instructions**: Follow this plan step by step. Run every
> verification command and confirm the expected result before moving to the
> next step. If anything in the "STOP conditions" section occurs, stop and
> report — do not improvise. When done, update the status row for this plan
> in `plans/README.md` — unless a reviewer dispatched you and told you they
> maintain the index.
>
> **Drift check (run first)**: `git diff --stat d21a134..HEAD -- backend/routers/graph.py backend/agents/orchestrator.py backend/routers/papers.py frontend/components/ErrorBoundary.tsx`
> If any in-scope file changed, compare the "Current state" excerpts against the
> live code before proceeding; on a mismatch, treat it as a STOP condition.

## Status

- **Priority**: P2
- **Effort**: S
- **Risk**: LOW
- **Depends on**: none
- **Category**: bug
- **Planned at**: commit `d21a134`, 2026-06-12

## Why this matters

This plan bundles four small fixes that were downgraded from the main findings table but are still worth doing:

1. **SEC-05: Input validation on `paper_id`** — the graph endpoint passes `paper_id` directly to the Semantic Scholar URL without format validation, enabling potential path traversal or injection.
2. **PERF-07: `datetime` import inside a loop** — `orchestrator.py` imports `datetime` inside the paper result loop on every iteration. Trivial to fix.
3. **COR-05: Graph endpoint returns mock data on failure** — when Semantic Scholar is unavailable, the endpoint returns fabricated citation data instead of an error, eroding user trust.
4. **COR-10: ErrorBoundary renders raw error messages** — the error boundary component shows internal error text to users, which leaks details and looks unprofessional.

## Current state

### 1. `backend/routers/graph.py:20-23`
```python
@router.get("/{paper_id}", response_model=CitationGraph)
async def get_graph(paper_id: str):
    try:
        data = await get_paper_citations(paper_id)
```
No validation on `paper_id` format.

### 2. `backend/agents/orchestrator.py:134-144`
```python
for p in final_state.get("ranked_papers", []):
    pub_at = p.get("published_at", "")
    if isinstance(pub_at, str) and pub_at:
        try:
            from datetime import datetime, timezone  # <-- inside loop
            pub_at = datetime.fromisoformat(pub_at.replace("Z", "+00:00"))
```
The `from datetime import datetime, timezone` is inside the loop body.

### 3. `backend/routers/graph.py:22-34`
```python
    try:
        data = await get_paper_citations(paper_id)
    except Exception:
        # Fallback to mock data if S2 is unavailable
        data = {
            "paperId": paper_id,
            "title": "Target Paper",
            "references": [
                {"paperId": "r1", "title": "Related Paper 1"},
                {"paperId": "r2", "title": "Related Paper 2"},
                {"paperId": "r3", "title": "Related Paper 3"},
            ],
        }
```

### 4. `frontend/components/ErrorBoundary.tsx:45-48`
```tsx
{this.state.error && (
  <pre className="mb-6 max-w-md overflow-auto rounded-md bg-gray-50 p-3 text-left text-xs text-red-700">
    {this.state.error.message}
  </pre>
)}
```

## Commands you will need

| Purpose | Command | Expected on success |
|---------|---------|---------------------|
| Backend lint | `cd backend && ruff check routers/graph.py agents/orchestrator.py` | exit 0 |
| Backend tests | `cd backend && pytest tests/test_graph.py -v` | all pass |
| Frontend build | `cd frontend && npm run build` | exit 0 |

## Scope

**In scope**:
- `backend/routers/graph.py` — add input validation, replace mock data with error response
- `backend/agents/orchestrator.py` — move datetime import to top of file
- `frontend/components/ErrorBoundary.tsx` — replace raw error message with generic message

**Out of scope**:
- Changes to the Semantic Scholar service itself
- Changes to other routers
- Frontend error logging service integration

## Git workflow

- Branch: `advisor/008-fix-downgraded-findings`
- Commit message: `fix(backend): input validation, move datetime import, remove mock graph data, sanitize error boundary`
- Do NOT push or open a PR unless the operator instructed it.

## Steps

### Step 1: Add input validation on `paper_id` in graph router

In `backend/routers/graph.py`, add a validation function and use it:

```python
import re

_PAPER_ID_RE = re.compile(r"^[a-zA-Z0-9\-._:/]+$")

def _validate_paper_id(paper_id: str) -> str:
    """Validate paper_id format to prevent path traversal."""
    if not paper_id or len(paper_id) > 200:
        raise HTTPException(status_code=422, detail="Invalid paper ID format")
    if not _PAPER_ID_RE.match(paper_id):
        raise HTTPException(status_code=422, detail="Invalid paper ID format")
    return paper_id
```

Then in the endpoint, validate before using:
```python
@router.get("/{paper_id}", response_model=CitationGraph)
async def get_graph(paper_id: str):
    paper_id = _validate_paper_id(paper_id)
    try:
        data = await get_paper_citations(paper_id)
    except Exception:
        # Return empty graph instead of mock data
        return CitationGraph(nodes=[], edges=[])
```

**Verify**: `grep -n "_validate_paper_id" backend/routers/graph.py` — function exists

### Step 2: Move datetime import to top of file in orchestrator

In `backend/agents/orchestrator.py`, move the import from inside the loop (lines 138, 143) to the top of the file:

Add at the top (after existing imports):
```python
from datetime import datetime, timezone
```

Then remove the two inline imports inside the for loop (lines 138 and 143).

**Verify**: `grep -n "from datetime" backend/agents/orchestrator.py` — should show only one match at the top

### Step 3: Replace graph mock data with empty response

In `backend/routers/graph.py`, change the except block from returning mock data to returning an empty graph:

```python
    except Exception:
        # Return empty graph instead of fabricated data
        return CitationGraph(nodes=[], edges=[])
```

**Verify**: `grep -n "mock data\|Target Paper\|Related Paper" backend/routers/graph.py` — should return no matches

### Step 4: Sanitize ErrorBoundary

In `frontend/components/ErrorBoundary.tsx`, replace the `<pre>` block with a generic message:

Replace:
```tsx
{this.state.error && (
  <pre className="mb-6 max-w-md overflow-auto rounded-md bg-gray-50 p-3 text-left text-xs text-red-700">
    {this.state.error.message}
  </pre>
)}
```

With:
```tsx
<p className="mb-6 max-w-md text-sm text-gray-500">
  If this keeps happening, please contact support.
</p>
```

**Verify**: `grep -n "error.message" frontend/components/ErrorBoundary.tsx` — should return no matches

### Step 5: Run verification

```bash
cd backend && ruff check routers/graph.py agents/orchestrator.py
cd backend && pytest tests/test_graph.py -v
cd frontend && npm run build
```

**Verify**: all pass

## Test plan

- Existing `test_graph.py` tests should still pass.
- Optionally add a test for invalid paper_id:
  ```python
  def test_graph_invalid_paper_id():
      response = client.get("/api/graph/../../../etc/passwd")
      assert response.status_code == 422
  ```

## Done criteria

- [ ] `grep -n "_validate_paper_id" backend/routers/graph.py` returns a match
- [ ] `grep -n "from datetime" backend/agents/orchestrator.py` shows exactly one match at the top
- [ ] `grep -n "Target Paper" backend/routers/graph.py` returns no matches
- [ ] `grep -n "error.message" frontend/components/ErrorBoundary.tsx` returns no matches
- [ ] `cd backend && ruff check routers/graph.py agents/orchestrator.py` exits 0
- [ ] `cd backend && pytest tests/test_graph.py -v` passes
- [ ] `cd frontend && npm run build` exits 0
- [ ] No files outside the in-scope list are modified
- [ ] `plans/README.md` status row updated

## STOP conditions

- If the input validation regex rejects valid paper IDs (e.g., IDs with special characters like `:` or `/`)
- If removing mock data breaks the frontend (the frontend should handle empty graphs gracefully)
- If the error boundary change causes a regression in error visibility

## Maintenance notes

- The paper ID regex `^[a-zA-Z0-9\-._:/]+$` covers ArXiv IDs, DOIs, and Semantic Scholar IDs. If new ID formats are added, the regex must be updated.
- Empty graph responses are better than fabricated data — the frontend already handles empty states.
- Consider adding an error logging service (e.g., Sentry) to capture real errors client-side.
