# Plan 005: Fix ruff and mypy baseline — establish clean verification gate

> **Executor instructions**: Follow this plan step by step. Run every
> verification command and confirm the expected result before moving to the
> next step. If anything in the "STOP conditions" section occurs, stop and
> report — do not improvise. When done, update the status row for this plan
> in `plans/README.md` — unless a reviewer dispatched you and told you they
> maintain the index.
>
> **Drift check (run first)**: `git diff --stat d21a134..HEAD -- backend/`
> If any in-scope file changed since this plan was written, compare the
> "Current state" excerpts against the live code before proceeding; on a
> mismatch, treat it as a STOP condition.

## Status

- **Priority**: P1
- **Effort**: M
- **Risk**: MED
- **Depends on**: none
- **Category**: dx
- **Planned at**: commit `d21a134`, 2026-06-12

## Why this matters

The backend has 13 ruff errors (all fixable unused imports) and 206 mypy errors (missing stubs, missing annotations, generic dict/list without type args). Strict mode (`strict = true` in `pyproject.toml`) is effectively useless — real type regressions are hidden in noise. Fixing the ruff errors is a quick win; for mypy, the goal is to get to a green baseline so that new code can be caught.

## Current state

**ruff** (13 errors, all auto-fixable):
```
backend/dependencies.py:1 — unused import `fastapi.Request`
backend/logging_config.py:3 — unused import `typing.Any`
backend/routers/auth.py:1 — unused import `fastapi.Depends`
backend/routers/search.py:20 — assigned but unused variable `user_id`
backend/scripts/seed_dev.py:9 — unused imports `datetime`, `timezone`
backend/tests/test_papers.py:1 — unused import `pytest`
backend/tests/test_retry.py:2 — unused import `asyncio`
backend/tests/test_run_store.py:3 — unused imports `datetime`, `timedelta`, `timezone`
backend/tests/test_run_store.py:4 — unused import `RunState`
backend/tests/test_search.py:1 — unused import `pytest`
```

**mypy** (206 errors) — major categories:
1. Missing type stubs: `slowapi`, `python-jose`, `supabase`, `mem0ai`, `firecrawl`, `langchain_mistralai`, `arxiv`
2. Missing return type annotations on functions
3. Generic `dict` / `list` without type arguments
4. `Returning Any from function declared to return X`
5. `Call to untyped function` errors
6. Actual type errors in `llm_router.py` (unexpected keyword args, argument types)

## Commands you will need

| Purpose | Command | Expected on success |
|---------|---------|---------------------|
| Auto-fix ruff | `cd backend && ruff check . --fix` | exit 0, 13 auto-fixes applied |
| Check ruff | `cd backend && ruff check .` | exit 0, no errors |
| Check mypy (after stubs) | `cd backend && mypy .` | exit 0 (or significantly reduced errors) |
| Backend tests | `cd backend && pytest` | all pass |

## Scope

**In scope**:
- `backend/pyproject.toml` — add stub packages, configure mypy ignore rules
- All Python files in `backend/` — auto-fix ruff, add type annotations where needed
- `backend/services/llm_router.py` — fix actual type errors

**Out of scope**:
- Rewriting the entire codebase for perfect type coverage
- Changes to frontend code
- Adding new features

## Git workflow

- Branch: `advisor/005-fix-ruff-mypy-baseline`
- Commit message: `fix(dx): clean ruff errors, install mypy stubs, reduce mypy errors to 0`
- Do NOT push or open a PR unless the operator instructed it.

## Steps

### Step 1: Auto-fix ruff errors

```bash
cd backend && ruff check . --fix
```

This will remove all 13 unused imports automatically.

**Verify**: `cd backend && ruff check .` exits 0

### Step 2: Add stub packages to dev dependencies

In `backend/pyproject.toml`, add to the `[project.optional-dependencies] dev` list:

```toml
dev = [
    "pytest>=8.3.0",
    "pytest-asyncio>=0.24.0",
    "httpx>=0.28.0",
    "ruff>=0.8.0",
    "mypy>=1.13.0",
    "types-python-jose>=3.3.0",
    "types-redis>=5.0.0",
]
```

**Verify**: `grep -n "types-python-jose\|types-redis" backend/pyproject.toml` — both should appear

### Step 3: Configure mypy to ignore missing stubs for packages without stubs

In `backend/pyproject.toml`, add ignore rules:

```toml
[tool.mypy]
python_version = "3.12"
strict = true
warn_return_any = true
warn_unused_configs = true

[[tool.mypy.overrides]]
module = [
    "slowapi.*",
    "slowapi.util.*",
    "supabase.*",
    "mem0.*",
    "firecrawl.*",
    "langchain_mistralai.*",
    "arxiv.*",
    "sse_starlette.*",
]
ignore_missing_imports = true
```

**Verify**: `grep -A5 "ignore_missing_imports" backend/pyproject.toml` — should show the module list

### Step 4: Fix actual type errors in `llm_router.py`

The mypy output shows real type errors in `backend/services/llm_router.py`:
- `Unexpected keyword argument "max_tokens" for "ChatOpenAI"` — Pydantic model fields may differ between LangChain versions
- `Argument "api_key" has incompatible type "str"; expected "SecretStr"` — PyJWT/Pydantic SecretStr issue

For these, add `# type: ignore[call-arg]` and `# type: ignore[arg-type]` comments on the affected lines, since these are known LangChain API patterns that work at runtime but confuse mypy.

**Verify**: `cd backend && mypy services/llm_router.py` — errors are suppressed

### Step 5: Add return type annotations to remaining untyped functions

The biggest source of mypy errors is missing `-> None` or other return type annotations on functions. For the most critical files, add annotations:

- `backend/main.py` — add `-> None` to `lifespan`, `rate_limit_exceeded_handler`, `auth_middleware`, `root`
- `backend/routers/` — add `-> None` or proper return types to all endpoint functions
- `backend/middleware/` — add types to `apply_rate_limits` and `TimingMiddleware`

For functions that are hard to type (e.g., LangGraph node functions that return `OrchestratorState`), add explicit return type annotations.

**Verify**: `cd backend && mypy .` — error count drops significantly (ideally to 0, but realistic target is < 10)

### Step 6: Run the full verification suite

```bash
cd backend && ruff check . && mypy . && pytest
```

**Verify**: all pass

## Test plan

- No new tests required — this is a DX/tooling fix.
- All existing tests must continue to pass.
- `ruff check .` and `mypy .` must exit 0 (or near-0 for mypy).

## Done criteria

- [ ] `cd backend && ruff check .` exits 0
- [ ] `cd backend && mypy .` exits 0 (or < 5 remaining errors with justification)
- [ ] `cd backend && pytest` passes
- [ ] `types-python-jose` and `types-redis` are in `pyproject.toml` dev deps
- [ ] `[[tool.mypy.overrides]]` section exists with `ignore_missing_imports = true`
- [ ] No files outside the in-scope list are modified
- [ ] `plans/README.md` status row updated

## STOP conditions

- If `ruff check . --fix` removes imports that are actually needed (e.g., imported for side effects)
- If adding type annotations breaks runtime behavior (unlikely but possible with complex generics)
- If mypy still reports > 20 errors after all fixes

## Maintenance notes

- New code should pass `ruff check . && mypy .` before merge.
- If `strict = true` is too noisy, consider changing to `strict = false` and enabling individual strict flags gradually.
- When new third-party packages are added, check if they have type stubs and add to the ignore list if not.
