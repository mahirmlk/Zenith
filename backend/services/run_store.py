import json
import logging
from typing import Optional
from dataclasses import dataclass, field
from datetime import datetime, timedelta
import asyncio

logger = logging.getLogger(__name__)


@dataclass
class RunState:
    run_id: str
    query: str
    model: Optional[str] = None
    status: str = "pending"
    results: list = field(default_factory=list)
    created_at: datetime = field(default_factory=datetime.utcnow)


class RunStore:
    def __init__(self, ttl_seconds: int = 3600):
        self._store: dict[str, RunState] = {}
        self._ttl = timedelta(seconds=ttl_seconds)
        self._lock = asyncio.Lock()

    async def create(self, run_id: str, query: str, model: Optional[str] = None) -> RunState:
        async with self._lock:
            state = RunState(run_id=run_id, query=query, model=model)
            self._store[run_id] = state
            return state

    async def get(self, run_id: str) -> Optional[RunState]:
        async with self._lock:
            state = self._store.get(run_id)
            if state and datetime.utcnow() - state.created_at > self._ttl:
                del self._store[run_id]
                return None
            return state

    async def update(self, run_id: str, status: Optional[str] = None, results: Optional[list] = None):
        async with self._lock:
            state = self._store.get(run_id)
            if not state:
                return
            if status:
                state.status = status
            if results is not None:
                state.results = results

    async def cleanup(self):
        async with self._lock:
            now = datetime.utcnow()
            expired = [k for k, v in self._store.items() if now - v.created_at > self._ttl]
            for k in expired:
                del self._store[k]


class RedisRunStore:
    def __init__(self, redis_url: str = "redis://localhost:6379", ttl_seconds: int = 3600):
        self._redis_url = redis_url
        self._ttl = ttl_seconds
        self._redis = None

    async def _ensure_connected(self):
        if self._redis is None:
            import redis.asyncio as redis_mod
            self._redis = redis_mod.from_url(self._redis_url, decode_responses=True)

    async def create(self, run_id: str, query: str, model: Optional[str] = None) -> RunState:
        await self._ensure_connected()
        state = RunState(run_id=run_id, query=query, model=model)
        await self._redis.set(run_id, json.dumps(state.__dict__, default=str), ex=self._ttl)
        return state

    async def get(self, run_id: str) -> Optional[RunState]:
        await self._ensure_connected()
        data = await self._redis.get(run_id)
        if data is None:
            return None
        return RunState(**json.loads(data))

    async def update(self, run_id: str, status: Optional[str] = None, results: Optional[list] = None):
        await self._ensure_connected()
        state = await self.get(run_id)
        if state is None:
            return
        if status:
            state.status = status
        if results is not None:
            state.results = results
        await self._redis.set(run_id, json.dumps(state.__dict__, default=str), ex=self._ttl)

    async def cleanup(self):
        pass


async def _create_run_store():
    from config import get_settings
    settings = get_settings()
    if settings.redis_url:
        try:
            store = RedisRunStore(redis_url=settings.redis_url)
            await store._ensure_connected()
            await store._redis.ping()
            logger.info("Using RedisRunStore")
            return store
        except Exception as exc:
            logger.warning("Redis unavailable, falling back to in-memory store: %s", exc)
    return RunStore()


# Initialise lazily to avoid blocking import
def _get_run_store():
    if not hasattr(_get_run_store, "_instance"):
        _get_run_store._instance = None
    return _get_run_store._instance


# Module-level singleton resolved on first use
_run_store_future = None


async def get_run_store():
    global _run_store_future
    if _run_store_future is None:
        _run_store_future = _create_run_store()
    return await _run_store_future


# Export a simple wrapper that proxies to the async singleton
class _RunStoreProxy:
    async def _store(self):
        return await get_run_store()

    async def create(self, run_id: str, query: str, model: Optional[str] = None) -> RunState:
        store = await self._store()
        return await store.create(run_id, query, model)

    async def get(self, run_id: str) -> Optional[RunState]:
        store = await self._store()
        return await store.get(run_id)

    async def update(self, run_id: str, status: Optional[str] = None, results: Optional[list] = None):
        store = await self._store()
        await store.update(run_id, status, results)

    async def cleanup(self):
        store = await self._store()
        await store.cleanup()


run_store = _RunStoreProxy()
