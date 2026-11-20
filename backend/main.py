import logging
from contextlib import asynccontextmanager
from urllib.parse import urlsplit
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from jwt.exceptions import InvalidTokenError
from routers import health, auth, papers, search, saved_searches, stream, graph, prefs, paper_code, internal, runs, projects, project_briefs, project_invitations, retrieval, research, implementations, watchlists, notifications, account, models
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
    from services.run_store import get_run_store, run_store
    import asyncio
    from agents.orchestrator import start_checkpointer, stop_checkpointer

    app_settings = get_settings()
    await start_checkpointer(
        app_settings.database_url,
        production=app_settings.app_env == "production",
    )
    # Initialize the canonical store before workers accept jobs. With plan
    # execution enabled, verify_schema also fails startup if migration 0019 is
    # absent or PostgREST has not refreshed its schema cache.
    await get_run_store()

    async def _cleanup_loop() -> None:
        while True:
            await asyncio.sleep(300)  # every 5 minutes
            try:
                from agents.orchestrator import cleanup_expired_checkpoints

                await cleanup_expired_checkpoints()
                await run_store.cleanup()
            except Exception:
                logger.exception("Run/checkpoint cleanup failed; retrying next interval")

    from services.job_queue import start_worker, stop_worker
    from services.daily_scheduler import start_daily_scheduler, stop_daily_scheduler
    from services.account_deletion import start_account_deletion_worker, stop_account_deletion_worker
    from services.notification_email import start_worker as start_notification_email_worker, stop_worker as stop_notification_email_worker

    cleanup_task = asyncio.create_task(_cleanup_loop())
    deletion_worker_started = bool(
        app_settings.supabase_url and app_settings.supabase_service_role_key
    )
    try:
        start_worker()
        start_daily_scheduler()
        if deletion_worker_started:
            start_account_deletion_worker()
        start_notification_email_worker()
        yield
    finally:
        cleanup_task.cancel()
        await asyncio.gather(cleanup_task, return_exceptions=True)
        try:
            await stop_worker()
        finally:
            try:
                await stop_daily_scheduler()
            finally:
                try:
                    await stop_notification_email_worker()
                finally:
                    try:
                        await stop_account_deletion_worker()
                    finally:
                        await stop_checkpointer()
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


def _configured_cors_origins(app_url: str, cors_origins_setting: str) -> list[str]:
    """Use APP_URL only as a backwards-compatible single-origin default."""
    if cors_origins_setting.strip():
        origins = [
            origin.strip().rstrip("/")
            for origin in cors_origins_setting.split(",")
            if origin.strip()
        ]
    else:
        origins = [app_url.strip().rstrip("/")] if app_url.strip() else []
    if not origins:
        return ["http://localhost:3000"]
    validated: list[str] = []
    for origin in origins:
        parsed = urlsplit(origin)
        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.netloc
            or not parsed.hostname
            or "," in origin
            or any(char.isspace() for char in origin)
            or parsed.username is not None
            or parsed.password is not None
            or parsed.path
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError("CORS_ORIGINS must contain exact http(s) origins")
        try:
            parsed.port
        except ValueError as exc:
            raise ValueError("CORS_ORIGINS must contain exact http(s) origins") from exc
        if origin not in validated:
            validated.append(origin)
    return validated


cors_origins = _configured_cors_origins(settings.app_url, settings.cors_origins)

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "PUT", "DELETE", "OPTIONS"],
    allow_headers=[
        "Authorization",
        "Content-Type",
        "Idempotency-Key",
        "Accept",
        "X-Admin-Key",
        "Last-Event-ID",
    ],
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
app.include_router(saved_searches.router)
app.include_router(stream.router)
app.include_router(graph.router)
app.include_router(prefs.router)
app.include_router(paper_code.router)
app.include_router(internal.router)
app.include_router(runs.router)
app.include_router(projects.router)
app.include_router(project_briefs.router)
app.include_router(project_invitations.router)
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
