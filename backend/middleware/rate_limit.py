from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address, default_limits=["60/minute"])


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
        except Exception:
            pass
