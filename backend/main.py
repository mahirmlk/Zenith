import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from jwt.exceptions import InvalidTokenError
from routers import health, auth, papers, search, stream, graph, prefs, pwc, internal, runs, projects, retrieval, research, implementations, watchlists, notifications, account, models
from middleware.rate_limit import limiter, apply_rate_limits
from middleware.timing import TimingMiddleware
from config import get_settings
from logging_config import setup_logging
from services.observability import init_sentry
from services.jwt_validator import decode_supabase_token

setup_logging()
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):  # type: ignore[no-untyped-def]
    # Startup
    init_sentry()
    logger.info("Starting Zenith backend")
    from services.run_store import run_store
    import asyncio

    async def _cleanup_loop() -> None:
        while True:
            await asyncio.sleep(300)  # every 5 minutes
            await run_store.cleanup()  # type: ignore[no-untyped-call]

    cleanup_task = asyncio.create_task(_cleanup_loop())
    from services.job_queue import start_worker, stop_worker

    start_worker()
    yield
    # Shutdown
    cleanup_task.cancel()
    stop_worker()
    logger.info("Shutting down backend")


app = FastAPI(
    title="Zenith",
    description="FastAPI backend for Zenith — AI Research Intelligence & Engineering Workspace",
    version="0.1.0",
    lifespan=lifespan,
)

settings = get_settings()

app.state.limiter = limiter
app.add_middleware(SlowAPIMiddleware)


@app.exception_handler(RateLimitExceeded)
async def rate_limit_exceeded_handler(request: Request, exc: RateLimitExceeded) -> JSONResponse:
    return JSONResponse(
        status_code=429,
        content={"detail": "Rate limit exceeded. Please try again later."},
    )


cors_origins = [o.strip() for o in settings.app_url.split(",") if o.strip()]
if not cors_origins:
    cors_origins = ["http://localhost:3000"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "Idempotency-Key", "Accept", "X-Admin-Key"],
)
app.add_middleware(TimingMiddleware)


@app.middleware("http")
async def security_headers(request: Request, call_next):  # type: ignore[no-untyped-def]
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    if settings.app_env == "production":
        response.headers["Strict-Transport-Security"] = "max-age=63072000; includeSubDomains"
    return response


@app.middleware("http")
async def auth_middleware(request: Request, call_next):  # type: ignore[no-untyped-def]
    token = None
    auth_header = request.headers.get("Authorization")
    if auth_header and auth_header.startswith("Bearer "):
        token = auth_header.replace("Bearer ", "")
    if token:
        try:
            payload = await decode_supabase_token(token)
            request.state.user = {"user_id": payload.get("sub"), "email": payload.get("email")}
        except InvalidTokenError:
            request.state.user = None
    else:
        request.state.user = None
    response = await call_next(request)
    return response


app.include_router(health.router)
app.include_router(health.ready_router)
app.include_router(auth.router)
app.include_router(papers.router)
app.include_router(search.router)
app.include_router(stream.router)
app.include_router(graph.router)
app.include_router(prefs.router)
app.include_router(pwc.router)
app.include_router(internal.router)
app.include_router(runs.router)
app.include_router(projects.router)
app.include_router(retrieval.router)
app.include_router(research.router)
app.include_router(implementations.router)
app.include_router(watchlists.router)
app.include_router(notifications.router)
app.include_router(account.router)
app.include_router(models.router)

apply_rate_limits(app)  # type: ignore[no-untyped-call]


@app.get("/")
async def root() -> dict[str, str]:
    return {"message": "Zenith API"}