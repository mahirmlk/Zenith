from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address, default_limits=["60/minute"])


def apply_rate_limits(app):
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
                route.endpoint = limiter.exempt(route.endpoint)
        except Exception:
            # Skip routes that don't have a request parameter (slowapi requirement)
            pass
