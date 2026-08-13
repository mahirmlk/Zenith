# ADR-006: Redis-Backed Rate Limiting

**Status:** Accepted

## Context

The original rate limiting used `slowapi` with an in-memory limiter. In-memory limits are per-process, so they are useless behind a load balancer (each replica enforces its own quota) and reset on restart. A single Fly machine could be scaled to multiple instances without meaningful abuse protection.

## Decision

Keep `slowapi` as the enforcement mechanism but back it with Redis when `REDIS_URL` is configured (`backend/middleware/rate_limit.py`):

- `storage_uri = redis_url or "memory://"` — production uses Redis, local dev gracefully falls back to memory.
- `key_prefix = "rate_limit"` namespaces keys so multiple apps sharing a Redis instance don't collide.
- `in_memory_fallback_enabled = True` keeps the app functional if Redis is briefly unreachable.

Per-endpoint limits are unchanged:

| Endpoint | Limit |
|----------|-------|
| `POST /api/search` | 10 req / minute |
| `GET /api/stream/*` | 20 req / minute |
| `GET /api/health` | exempt |
| All others | 60 req / minute |

## Consequences

- **Positive:** Consistent quotas across multiple backend replicas behind one Redis.
- **Positive:** Works identically in local dev (no Redis required) and production (Redis recommended).
- **Negative:** Redis becomes part of the rate-limiting critical path; mitigated by the in-memory fallback and by `docs/DEPLOYMENT.md` guidance to run an authenticated Redis instance.
- **Negative:** Slowapi's `in_memory_fallback` parameter was removed in 0.1.9; the correct flag is `in_memory_fallback_enabled`. Keep the dependency pinned to a compatible version.
