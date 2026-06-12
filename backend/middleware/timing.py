import time
from starlette.middleware.base import BaseHTTPMiddleware


class TimingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):  # type: ignore[no-untyped-def]
        start = time.time()
        response = await call_next(request)
        duration = time.time() - start
        response.headers["X-Response-Time"] = f"{duration:.3f}s"
        return response
