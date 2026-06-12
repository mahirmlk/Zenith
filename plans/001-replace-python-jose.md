# Plan 001: Replace unmaintained `python-jose` with PyJWT

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
- **Effort**: S
- **Risk**: LOW
- **Depends on**: none
- **Category**: security
- **Planned at**: commit `d21a134`, 2026-06-12

## Why this matters

`python-jose` is unmaintained and has known CVEs (CVE-2024-33663, CVE-2024-33664). JWT verification is the single gate for all authenticated endpoints — a vulnerability here compromises the entire auth layer. Swapping to PyJWT is a drop-in replacement for the HS256 decode calls used in this codebase.

## Current state

Four files import from `jose`:

- `backend/main.py:6` — `from jose import jwt, JWTError`
- `backend/dependencies.py:3` — `from jose import jwt, JWTError`
- `backend/routers/auth.py:3` — `from jose import jwt, JWTError`
- `backend/routers/stream.py:4` — `from jose import jwt, JWTError`

All four use `jwt.decode(token, secret, algorithms=["HS256"], options={"verify_aud": False})` and catch `JWTError`.

The backend `pyproject.toml` currently lists `"python-jose[cryptography]>=3.3.0"` in dependencies.

The frontend is not affected — JWT handling is all server-side.

## Commands you will need

| Purpose | Command | Expected on success |
|---------|---------|---------------------|
| Install PyJWT | `pip install PyJWT[crypto]>=2.8.0` | exit 0 |
| Uninstall python-jose | `pip uninstall python-jose -y` | exit 0 |
| Backend lint | `cd backend && ruff check main.py dependencies.py routers/auth.py routers/stream.py` | exit 0, no errors |
| Backend type check | `cd backend && mypy main.py dependencies.py routers/auth.py routers/stream.py` | exit 0 (may show pre-existing errors in other modules) |

## Scope

**In scope** (the only files you should modify):
- `backend/pyproject.toml` — swap dependency
- `backend/main.py` — change import
- `backend/dependencies.py` — change import
- `backend/routers/auth.py` — change import
- `backend/routers/stream.py` — change import

**Out of scope**:
- Any changes to the JWT decode call signature — the PyJWT `decode` call is compatible with the current usage.
- Any frontend changes.

## Git workflow

- Branch: `advisor/001-replace-jose`
- Commit per logical unit: dependency swap, then import updates
- Message style: `fix(security): replace python-jose with PyJWT`
- Do NOT push or open a PR unless the operator instructed it.

## Steps

### Step 1: Swap the dependency in `pyproject.toml`

In `backend/pyproject.toml`, in the `dependencies` list, replace:
```
"python-jose[cryptography]>=3.3.0",
```
with:
```
"PyJWT[crypto]>=2.8.0",
```

**Verify**: `grep -n "jose\|PyJWT" backend/pyproject.toml` — should show only `PyJWT[crypto]>=2.8.0`

### Step 2: Update imports in all four files

For each of `backend/main.py`, `backend/dependencies.py`, `backend/routers/auth.py`, `backend/routers/stream.py`:

Change:
```python
from jose import jwt, JWTError
```
to:
```python
import jwt as pyjwt  # PyJWT
from jwt import decode as jwt_decode, DecodeError as JWTError
```

Wait — that's too verbose. Simpler approach: PyJWT's import is `import jwt` but that conflicts with common variable names. Use this pattern:

```python
from jwt import decode as jwt_decode
from jwt.exceptions import DecodeError as JWTError
```

Then update each `jwt.decode(...)` call to `jwt_decode(...)`.

Actually, the simplest drop-in is: `PyJWT` exposes `jwt.decode()` just like `python-jose`. The only difference is that PyJWT requires `algorithms` as a positional or keyword argument (which is already the case), and the `options` dict uses different keys for audience verification. Let me check:

python-jose uses: `options={"verify_aud": False}`
PyJWT uses: `options={"verify_aud": False}` — same key! PyJWT also supports `audience=None` to skip audience verification.

So the actual change per file is:

```python
# OLD
from jose import jwt, JWTError

# NEW
import jwt as jose_jwt
from jwt.exceptions import DecodeError as JWTError
```

Then replace `jwt.decode(...)` with `jose_jwt.decode(...)`. This preserves all existing code patterns.

Actually even simpler — since the import is `from jose import jwt`, we can just do:

```python
import jwt
from jwt.exceptions import DecodeError as JWTError
```

And then `jwt.decode(...)` works unchanged. The only issue is if there are other `jwt` variables in scope — but there aren't in any of these files.

**For each of the 4 files, make the import change and update `jwt.decode` calls if needed.**

Actually, let me re-read the current usage more carefully:

In `main.py:81`: `payload = jwt.decode(token, settings.supabase_jwt_secret, algorithms=["HS256"], options={"verify_aud": False})`
In `dependencies.py:15`: same pattern
In `routers/auth.py`: same pattern
In `routers/stream.py:21`: same pattern

PyJWT's `decode` signature is: `jwt.decode(token, key, algorithms=[...], options={...})` — identical.

So the only change needed is the import line. The `jwt.decode(...)` calls work unchanged.

**Verify**: `grep -rn "from jose" backend/` — should return no matches

### Step 3: Install and run lint

```bash
cd backend && pip install -e ".[dev]"
cd backend && ruff check main.py dependencies.py routers/auth.py routers/stream.py
```

**Verify**: exit 0, no jose-related errors

### Step 4: Update the Makefile or docs if they reference python-jose

Check `Makefile`, `README.md`, `docs/DEVELOPER_GUIDE.md` for any mention of `python-jose`. If found, update to reference `PyJWT`.

**Verify**: `grep -rn "python-jose\|jose" Makefile README.md docs/` — should return no matches (or only mentions of the new package)

## Test plan

- No new tests needed — this is a drop-in dependency swap with identical behavior.
- Verify existing auth tests still pass: `cd backend && pytest tests/test_auth.py -v`
- Verify existing search tests still pass: `cd backend && pytest tests/test_search.py -v`

## Done criteria

Machine-checkable. ALL must hold:

- [ ] `grep -rn "from jose" backend/` returns no matches
- [ ] `grep -n "python-jose" backend/pyproject.toml` returns no matches
- [ ] `grep -n "PyJWT" backend/pyproject.toml` returns a match
- [ ] `cd backend && ruff check main.py dependencies.py routers/auth.py routers/stream.py` exits 0
- [ ] `cd backend && pytest tests/test_auth.py -v` passes
- [ ] No files outside the in-scope list are modified (`git status`)
- [ ] `plans/README.md` status row updated

## STOP conditions

Stop and report back (do not improvise) if:

- PyJWT's `decode` function signature does not match the current usage (e.g., `options` dict keys differ)
- Any existing test fails after the swap
- You discover the assumption "PyJWT is a drop-in replacement" is false

## Maintenance notes

- Future reviewers should check that the `algorithms` argument is always passed (PyJWT requires it; python-jose defaulted to allowing all).
- If the project later adds token encoding (not just decoding), note that PyJWT's `jwt.encode()` has a slightly different signature than python-jose's.
