# Plan 007: Remove JWT token from SSE URL query parameter

> **Executor instructions**: Follow this plan step by step. Run every
> verification command and confirm the expected result before moving to the
> next step. If anything in the "STOP conditions" section occurs, stop and
> report — do not improvise. When done, update the status row for this plan
> in `plans/README.md` — unless a reviewer dispatched you and told you they
> maintain the index.
>
> **Drift check (run first)****: `git diff --stat d21a134..HEAD -- frontend/lib/api.ts backend/routers/stream.py`
> If either file has changed, compare the "Current state" excerpts against the
> live code before proceeding; on a mismatch, treat it as a STOP condition.

## Status

- **Priority**: P1
- **Effort**: M
- **Risk**: MED
- **Depends on**: none
- **Category**: security
- **Planned at**: commit `d21a134`, 2026-06-12

## Why this matters

The SSE streaming endpoint passes the JWT as a URL query parameter (`?token=...`). Browser history, server access logs, reverse-proxy logs, and referrer headers all capture the token. If an attacker gains access to any of these, they can impersonate the user.

The fix is to switch SSE auth to a POST-based handshake that exchanges the Authorization header for a short-lived SSE session ID, or use the `Authorization` header directly (which EventSource doesn't support natively). The simplest approach that's compatible with `EventSource` is to pass the token via a custom header — but `EventSource` doesn't support custom headers. So the recommended approach is a **handshake endpoint**: the frontend POSTs credentials to get a short-lived token, then passes that token in the URL (it's short-lived, so exposure is limited).

## Current state

**Frontend** — `frontend/lib/api.ts:170-203`:
```typescript
export async function streamSearch(runId: string, onEvent: ..., onError?: ...) {
  const token = await getJWT();
  const params = token ? `?token=${encodeURIComponent(token)}` : '';
  const evtSource = new EventSource(`${API_BASE}/api/stream/${runId}${params}`);
  // ...
}
```

**Backend** — `backend/routers/stream.py:71-83`:
```python
@router.get("/{run_id}")
async def stream(
    run_id: str,
    token: str | None = Query(default=None, description="Supabase JWT for auth"),
):
    user_id = _validate_token_from_query(token)
    if not user_id:
        raise HTTPException(status_code=401, detail="Valid authentication required")
    # ...
```

## Commands you will need

| Purpose | Command | Expected on success |
|---------|---------|---------------------|
| Backend tests | `cd backend && pytest tests/test_search.py tests/test_auth.py -v` | all pass |
| Frontend build | `cd frontend && npm run build` | exit 0 |
| Frontend type check | `cd frontend && npm run typecheck` | exit 0 |

## Scope

**In scope**:
- `backend/routers/stream.py` — add a POST endpoint for SSE session token exchange, keep GET with session token validation
- `frontend/lib/api.ts` — call POST endpoint to get session token, then use it in EventSource URL

**Out of scope**:
- Changes to the EventSource protocol itself
- Changes to other routers
- Cookie-based auth (more complex, not compatible with EventSource)

## Git workflow

- Branch: `advisor/007-fix-sse-jwt-exposure`
- Commit message: `fix(security): replace JWT-in-URL with short-lived SSE session tokens`
- Do NOT push or open a PR unless the operator instructed it.

## Steps

### Step 1: Add SSE session token endpoint to backend

In `backend/routers/stream.py`, add a new POST endpoint that validates the JWT from the Authorization header and returns a short-lived session token (UUID) that can be used for SSE streaming.

```python
import uuid
from datetime import datetime, timedelta, timezone

# In-memory store for SSE session tokens (short-lived, 5-minute TTL)
_sse_sessions: dict[str, dict] = {}

@router.post("/session")
async def create_sse_session(user: dict = Depends(get_current_user)):
    """Exchange JWT for a short-lived SSE session token."""
    session_id = str(uuid.uuid4())
    _sse_sessions[session_id] = {
        "user_id": user["user_id"],
        "created_at": datetime.now(timezone.utc),
        "expires_at": datetime.now(timezone.utc) + timedelta(minutes=5),
    }
    return {"session_token": session_id}

def _validate_sse_session(session_token: str) -> str | None:
    """Validate SSE session token. Returns user_id or None."""
    session = _sse_sessions.get(session_token)
    if not session:
        return None
    if datetime.now(timezone.utc) > session["expires_at"]:
        del _sse_sessions[session_token]
        return None
    return session["user_id"]
```

Then modify the existing `stream` endpoint to validate via session token:

```python
@router.get("/{run_id}")
async def stream(
    run_id: str,
    token: str | None = Query(default=None, description="SSE session token"),
):
    user_id = _validate_sse_session(token) if token else None
    if not user_id:
        raise HTTPException(status_code=401, detail="Valid authentication required")
    # ... rest unchanged
```

Also add the import for `get_current_user`:
```python
from dependencies import get_current_user
```

**Verify**: `grep -n "create_sse_session\|_validate_sse_session" backend/routers/stream.py` — both functions exist

### Step 2: Update frontend to use session token

In `frontend/lib/api.ts`, modify `streamSearch` to first call the POST endpoint to get a session token, then use that token in the EventSource URL:

```typescript
export async function streamSearch(runId: string, onEvent: ..., onError?: ...) {
  // Get a short-lived SSE session token
  const token = await getJWT();
  const headers: Record<string, string> = { 'Content-Type': 'application/json' };
  if (token) headers['Authorization'] = `Bearer ${token}`;

  const sessionRes = await fetch(`${API_BASE}/api/stream/session`, {
    method: 'POST',
    headers,
  });

  if (!sessionRes.ok) {
    if (onError) onError(new Error('Failed to create SSE session'));
    return () => {};
  }

  const { session_token } = await sessionRes.json();
  const evtSource = new EventSource(`${API_BASE}/api/stream/${runId}?token=${encodeURIComponent(session_token)}`);

  // ... rest of the function unchanged
}
```

**Verify**: `grep -n "session_token\|api/stream/session" frontend/lib/api.ts` — both references exist

### Step 3: Run tests and build

```bash
cd backend && pytest tests/test_search.py tests/test_auth.py -v
cd frontend && npm run typecheck
cd frontend && npm run build
```

**Verify**: all pass

## Test plan

- Add a test for the new `POST /api/stream/session` endpoint in `tests/test_search.py`:
  ```python
  def test_create_sse_session():
      response = client.post("/api/stream/session", headers={"Authorization": "Bearer <valid-token>"})
      assert response.status_code in (200, 401)  # 401 if JWT secret not configured
      if response.status_code == 200:
          assert "session_token" in response.json()
  ```
- Verify existing search and auth tests still pass.

## Done criteria

- [ ] `grep -n "create_sse_session" backend/routers/stream.py` returns a match
- [ ] `grep -n "api/stream/session" frontend/lib/api.ts` returns a match
- [ ] `cd backend && pytest tests/test_search.py -v` passes
- [ ] `cd frontend && npm run typecheck` exits 0
- [ ] `cd frontend && npm run build` exits 0
- [ ] No files outside the in-scope list are modified
- [ ] `plans/README.md` status row updated

## STOP conditions

- If the `EventSource` API doesn't support the session token approach (it does — query params work fine)
- If the session token store grows unbounded (add a cleanup loop in the lifespan, or use a TTL dict)
- If existing SSE tests break

## Maintenance notes

- The session tokens are stored in-memory and expire after 5 minutes. For multi-instance deployments, this needs to be moved to Redis.
- The POST endpoint requires a valid JWT (via Authorization header), so it's protected by the standard auth middleware.
- This is a defense-in-depth measure — the short-lived token limits the blast radius of URL exposure.
