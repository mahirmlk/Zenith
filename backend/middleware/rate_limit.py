from slowapi import Limiter
from slowapi.util import get_remote_address
from config import get_settings

# Use Redis as the shared rate-limit store so limits are global across
# multiple backend instances. Falls back to in-memory if Redis is
# unreachable (or not configured).
_settings = get_settings()
_storage_uri = _settings.redis_url or "memory://"

limiter = Limiter(
    key_func=get_remote_address,
    default_limits=["60/minute"],
    storage_uri=_storage_uri,
    key_prefix="rate_limit",
    in_memory_fallback_enabled=True,
)


def apply_rate_limits(app):  # type: ignore[no-untyped-def]
    """Apply per-endpoint rate limits using slowapi decorators."""
    from fastapi.routing import APIRoute

    for route in app.routes:
        if not isinstance(route, APIRoute):
            continue

        try:
            if route.path == "/api/search":
                route.endpoint = limiter.limit("10/minute")(route.endpoint)
            elif route.path.startswith("/api/stream/"):
                route.endpoint = limiter.limit("20/minute")(route.endpoint)
            elif route.path == "/api/health":
                route.endpoint = limiter.exempt(route.endpoint)  # type: ignore[no-untyped-call]
            elif route.path == "/api/auth/token":
                route.endpoint = limiter.limit("5/minute")(route.endpoint)
            elif (route.path.startswith("/api/papers")
                    and route.methods
                    and ("POST" in route.methods or "DELETE" in route.methods)):
                route.endpoint = limiter.limit("30/minute")(route.endpoint)
            elif (route.path.startswith("/api/prefs")
                    and route.methods
                    and "POST" in route.methods):
                route.endpoint = limiter.limit("10/minute")(route.endpoint)
            elif route.path.startswith("/api/research") or route.path.startswith("/api/retrieval"):
                route.endpoint = limiter.limit("10/minute")(route.endpoint)
            elif route.path.startswith("/api/internal"):
                route.endpoint = limiter.limit("5/minute")(route.endpoint)
            elif route.path.startswith("/api/account"):
                route.endpoint = limiter.limit("10/minute")(route.endpoint)
            elif route.path.startswith("/api/implementations"):
                route.endpoint = limiter.limit("10/minute")(route.endpoint)
        except Exception:
            pass