import logging
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from jose import jwt, JWTError
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from routers import health, auth, papers, search, stream, graph, prefs, pwc
from middleware.rate_limit import limiter, apply_rate_limits
from middleware.timing import TimingMiddleware
from config import get_settings
from logging_config import setup_logging

setup_logging()
logger = logging.getLogger(__name__)

app = FastAPI(
    title="AI Paper Research Agent",
    description="FastAPI backend for the AI Paper Research Agent",
    version="0.1.0",
)

app.state.limiter = limiter
app.add_middleware(SlowAPIMiddleware)


@app.exception_handler(RateLimitExceeded)
async def rate_limit_exceeded_handler(request: Request, exc: RateLimitExceeded):
    return JSONResponse(
        status_code=429,
        content={"detail": "Rate limit exceeded. Please try again later."},
    )


app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(TimingMiddleware)


@app.middleware("http")
async def auth_middleware(request: Request, call_next):
    settings = get_settings()
    token = None
    auth_header = request.headers.get("Authorization")
    if auth_header and auth_header.startswith("Bearer "):
        token = auth_header.replace("Bearer ", "")
    if token and settings.supabase_jwt_secret:
        try:
            payload = jwt.decode(
                token,
                settings.supabase_jwt_secret,
                algorithms=["HS256"],
                options={"verify_aud": False},
            )
            request.state.user = {"user_id": payload.get("sub"), "email": payload.get("email")}
        except JWTError:
            request.state.user = None
    else:
        request.state.user = None
    response = await call_next(request)
    return response


app.include_router(health.router)
app.include_router(auth.router)
app.include_router(papers.router)
app.include_router(search.router)
app.include_router(stream.router)
app.include_router(graph.router)
app.include_router(prefs.router)
app.include_router(pwc.router)

apply_rate_limits(app)


@app.on_event("startup")
async def startup():
    logger.info("Starting AI Paper Research Agent backend")


@app.on_event("shutdown")
async def shutdown():
    logger.info("Shutting down backend")


@app.get("/")
async def root():
    return {"message": "AI Paper Research Agent API"}
