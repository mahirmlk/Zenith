# Plan 002: Fix memory agent blocking the async event loop

> **Executor instructions**: Follow this plan step by step. Run every
> verification command and confirm the expected result before moving to the
> next step. If anything in the "STOP conditions" section occurs, stop and
> report — do not improvise. When done, update the status row for this plan
> in `plans/README.md` — unless a reviewer dispatched you and told you they
> maintain the index.
>
> **Drift check (run first)**: `git diff --stat d21a134..HEAD -- backend/agents/memory_agent.py`
> If the file has changed, compare the "Current state" excerpts against the
> live code before proceeding; on a mismatch, treat it as a STOP condition.

## Status

- **Priority**: P1
- **Effort**: S
- **Risk**: LOW
- **Depends on**: none
- **Category**: bug
- **Planned at**: commit `d21a134`, 2026-06-12

## Why this matters

The memory agent calls `supabase.rpc("match_papers", ...).execute()` inside `_try_match_papers_sql()`. `get_supabase()` returns a synchronous `supabase.Client`; `execute()` is a blocking I/O call. This blocks the entire asyncio event loop, stalling all concurrent requests and SSE streams while waiting for a Postgres/pgvector query.

## Current state

File: `backend/agents/memory_agent.py:29-54`

```python
async def _try_match_papers_sql(interest_text: str, papers: list[dict]) -> bool:
    """Try to use the match_papers SQL function for scoring. Returns True if successful."""
    try:
        from services.supabase_client import get_supabase
        from services.embeddings import embed_text

        interest_vec = await embed_text(interest_text)
        supabase = get_supabase()

        result = supabase.rpc(
            "match_papers",
            {
                "query_embedding": interest_vec,
                "match_threshold": 0.3,
                "match_count": len(papers),
            },
        ).execute()
```

The issue is on line 38-45: `supabase.rpc(...).execute()` is a synchronous call on a synchronous client, run inside an async function without `await` or `asyncio.to_thread`.

## Commands you will need

| Purpose | Command | Expected on success |
|---------|---------|---------------------|
| Backend lint | `cd backend && ruff check agents/memory_agent.py` | exit 0 |
| Backend type check | `cd backend && mypy agents/memory_agent.py` | exit 0 (or pre-existing errors only) |
| Backend tests | `cd backend && pytest tests/test_agents.py -v` | all pass |

## Scope

**In scope**:
- `backend/agents/memory_agent.py` — wrap synchronous Supabase call in `asyncio.to_thread`

**Out of scope**:
- Switching to Supabase's async client (`create_async_client`) — that's a larger refactor.
- Any changes to `services/supabase_client.py`.

## Git workflow

- Branch: `advisor/002-fix-memory-agent-async`
- Commit message: `fix(agents): wrap sync Supabase call in asyncio.to_thread`
- Do NOT push or open a PR unless the operator instructed it.

## Steps

### Step 1: Wrap the blocking call in `asyncio.to_thread`

In `backend/agents/memory_agent.py`, replace the blocking `supabase.rpc(...).execute()` call with a wrapper.

Change:
```python
        result = supabase.rpc(
            "match_papers",
            {
                "query_embedding": interest_vec,
                "match_threshold": 0.3,
                "match_count": len(papers),
            },
        ).execute()
```

To:
```python
        def _blocking_rpc():
            return supabase.rpc(
                "match_papers",
                {
                    "query_embedding": interest_vec,
                    "match_threshold": 0.3,
                    "match_count": len(papers),
                },
            ).execute()

        result = await asyncio.to_thread(_blocking_rpc)
```

Also add `import asyncio` at the top of the file if not already present.

**Verify**: `grep -n "asyncio.to_thread" backend/agents/memory_agent.py` — should show the new call

### Step 2: Run lint and type check

```bash
cd backend && ruff check agents/memory_agent.py
cd backend && mypy agents/memory_agent.py
```

**Verify**: exit 0 (or only pre-existing errors)

### Step 3: Run tests

```bash
cd backend && pytest tests/test_agents.py -v
```

**Verify**: all tests pass

## Test plan

- No new tests required — this is a correctness fix with no behavioral change.
- Verify existing agent tests still pass.
- Optionally add a test that mocks `supabase.rpc` and asserts the call doesn't block the event loop (advanced — skip if time-constrained).

## Done criteria

- [ ] `grep -n "asyncio.to_thread" backend/agents/memory_agent.py` returns a match
- [ ] `grep -n "supabase.rpc" backend/agents/memory_agent.py` still exists (the RPC call is still there, just wrapped)
- [ ] `cd backend && ruff check agents/memory_agent.py` exits 0
- [ ] `cd backend && pytest tests/test_agents.py -v` passes
- [ ] No files outside the in-scope list are modified
- [ ] `plans/README.md` status row updated

## STOP conditions

Stop and report back if:

- `asyncio.to_thread` is not available (requires Python 3.9+; this project uses 3.12, so this shouldn't happen)
- The test suite fails after the change
- You discover `get_supabase()` returns an async client (in which case, the whole premise is wrong)

## Maintenance notes

- If the project later switches to Supabase's official async client (`create_async_client`), this `to_thread` wrapper can be removed.
- The `asyncio.to_thread` call moves the blocking I/O to a thread pool, which is the standard Python pattern for wrapping sync code in async contexts.
