import json
import logging
from typing import Optional
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta, timezone
import asyncio
import secrets

logger = logging.getLogger(__name__)
TERMINAL_STATUSES = {"complete", "failed", "cancelled"}


@dataclass
class RunState:
    run_id: str
    query: str
    model: Optional[str] = None
    status: str = "pending"
    results: list[dict] = field(default_factory=list)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    # Phase P0-C (update.md §5.2/§7): ownership, idempotency, start-once, events.
    user_id: Optional[str] = None
    idempotency_key: Optional[str] = None
    started: bool = False
    events: list[dict] = field(default_factory=list)


class RunStore:
    def __init__(self, ttl_seconds: int = 3600):
        self._store: dict[str, RunState] = {}
        self._ttl = timedelta(seconds=ttl_seconds)
        self._lock = asyncio.Lock()
        self._active_runs: set[str] = set()

    async def create(
        self,
        run_id: str,
        query: str,
        model: Optional[str] = None,
        user_id: Optional[str] = None,
        idempotency_key: Optional[str] = None,
    ) -> RunState:
        async with self._lock:
            if idempotency_key:
                for existing in self._store.values():
                    if (
                        existing.idempotency_key == idempotency_key
                        and existing.user_id == user_id
                        and not self._expired(existing)
                    ):
                        return existing
            state = RunState(
                run_id=run_id,
                query=query,
                model=model,
                user_id=user_id,
                idempotency_key=idempotency_key,
            )
            self._store[run_id] = state
            return state

    def _expired(self, state: RunState) -> bool:
        return datetime.now(timezone.utc) - state.created_at > self._ttl

    async def get(self, run_id: str) -> Optional[RunState]:
        async with self._lock:
            state = self._store.get(run_id)
            if state and self._expired(state):
                del self._store[run_id]
                return None
            return state

    async def update(self, run_id: str, status: Optional[str] = None, results: Optional[list] = None):
        async with self._lock:
            state = self._store.get(run_id)
            if not state:
                return
            # A cancellation is terminal. Late orchestration completions must
            # never turn a cancelled run back into a successful result.
            if state.status in TERMINAL_STATUSES and status != state.status:
                return
            if status:
                state.status = status
            if results is not None:
                state.results = results
            if state.status in TERMINAL_STATUSES:
                self._active_runs.discard(run_id)

    async def try_start(self, run_id: str) -> bool:
        """Atomically mark a run started. True only for the first caller."""
        async with self._lock:
            state = self._store.get(run_id)
            if not state or state.status in TERMINAL_STATUSES or run_id in self._active_runs:
                return False
            self._active_runs.add(run_id)
            state.started = True
            state.status = "running"
            return True

    async def heartbeat(self, run_id: str) -> bool:
        async with self._lock:
            state = self._store.get(run_id)
            return bool(state and state.status == "running" and run_id in self._active_runs)

    async def release(self, run_id: str) -> None:
        async with self._lock:
            self._active_runs.discard(run_id)

    async def add_event(self, run_id: str, event: str, data: dict) -> None:
        async with self._lock:
            state = self._store.get(run_id)
            if not state:
                return
            state.events.append(
                {"sequence": len(state.events) + 1, "event": event, "data": data}
            )

    async def get_events(self, run_id: str) -> list[dict]:
        async with self._lock:
            state = self._store.get(run_id)
            return list(state.events) if state else []

    async def cleanup(self):
        async with self._lock:
            now = datetime.now(timezone.utc)
            expired = [k for k, v in self._store.items() if now - v.created_at > self._ttl]
            for k in expired:
                del self._store[k]


class RedisRunStore:
    """Redis-backed run state and leases. Postgres canonical storage is not
    wired yet; production still requires the separately tracked DB work."""

    def __init__(self, redis_url: str = "redis://localhost:6379", ttl_seconds: int = 3600):
        self._redis_url = redis_url
        self._ttl = ttl_seconds
        self._redis = None
        self._fallback = RunStore(ttl_seconds=ttl_seconds)
        self._lease_seconds = 90
        self._lease_tokens: dict[str, str] = {}

    async def _ensure_connected(self):
        if self._redis is None:
            import redis.asyncio as redis_mod

            self._redis = redis_mod.from_url(self._redis_url, decode_responses=True)

    def _serialize(self, state: RunState) -> str:
        d = asdict(state)
        d["created_at"] = state.created_at.isoformat()
        return json.dumps(d, default=str)

    def _deserialize(self, data: str) -> RunState:
        d = json.loads(data)
        if isinstance(d.get("created_at"), str):
            try:
                d["created_at"] = datetime.fromisoformat(d["created_at"])
            except ValueError:
                d["created_at"] = datetime.now(timezone.utc)
        d.setdefault("user_id", None)
        d.setdefault("idempotency_key", None)
        d.setdefault("started", False)
        d.setdefault("events", [])
        return RunState(**d)

    async def create(
        self,
        run_id: str,
        query: str,
        model: Optional[str] = None,
        user_id: Optional[str] = None,
        idempotency_key: Optional[str] = None,
    ) -> RunState:
        await self._ensure_connected()
        state = RunState(
            run_id=run_id, query=query, model=model,
            user_id=user_id, idempotency_key=idempotency_key,
        )
        await self._redis.set(run_id, self._serialize(state), ex=self._ttl)
        return state

    async def get(self, run_id: str) -> Optional[RunState]:
        await self._ensure_connected()
        data = await self._redis.get(run_id)
        if data is None:
            return None
        return self._deserialize(data)

    async def update(self, run_id: str, status: Optional[str] = None, results: Optional[list] = None):
        await self._ensure_connected()
        from redis.exceptions import WatchError

        for _ in range(5):
            async with self._redis.pipeline(transaction=True) as pipe:
                try:
                    await pipe.watch(run_id)
                    data = await pipe.get(run_id)
                    if data is None:
                        return
                    state = self._deserialize(data)
                    if state.status in TERMINAL_STATUSES and status != state.status:
                        return
                    if status:
                        state.status = status
                    if results is not None:
                        state.results = results
                    pipe.multi()
                    pipe.set(run_id, self._serialize(state), ex=self._ttl)
                    await pipe.execute()
                    return
                except WatchError:
                    continue
        raise RuntimeError(f"Could not update run {run_id}: concurrent updates did not settle")

    async def try_start(self, run_id: str) -> bool:
        await self._ensure_connected()
        from redis.exceptions import WatchError

        lease_key = self._lease_key(run_id)
        for _ in range(5):
            token = secrets.token_urlsafe(24)
            async with self._redis.pipeline(transaction=True) as pipe:
                try:
                    await pipe.watch(run_id)
                    data = await pipe.get(run_id)
                    if data is None:
                        return False
                    state = self._deserialize(data)
                    if state.status in TERMINAL_STATUSES:
                        return False
                    acquired = await self._redis.set(
                        lease_key, token, nx=True, ex=self._lease_seconds
                    )
                    if not acquired:
                        return False
                    state.started = True
                    state.status = "running"
                    pipe.multi()
                    pipe.set(run_id, self._serialize(state), ex=self._ttl)
                    await pipe.execute()
                    self._lease_tokens[run_id] = token
                    return True
                except WatchError:
                    await self._redis.eval(
                        "if redis.call('get', KEYS[1]) == ARGV[1] then "
                        "return redis.call('del', KEYS[1]) else return 0 end",
                        1,
                        lease_key,
                        token,
                    )
        return False

    @staticmethod
    def _lease_key(run_id: str) -> str:
        return f"zenith:runs:lease:{run_id}"

    async def heartbeat(self, run_id: str) -> bool:
        await self._ensure_connected()
        token = self._lease_tokens.get(run_id)
        if not token:
            return False
        result = await self._redis.eval(
            "if redis.call('get', KEYS[1]) == ARGV[1] then "
            "return redis.call('expire', KEYS[1], ARGV[2]) else return 0 end",
            1,
            self._lease_key(run_id),
            token,
            self._lease_seconds,
        )
        return bool(result)

    async def release(self, run_id: str) -> None:
        await self._ensure_connected()
        token = self._lease_tokens.pop(run_id, None)
        if not token:
            return
        await self._redis.eval(
            "if redis.call('get', KEYS[1]) == ARGV[1] then "
            "return redis.call('del', KEYS[1]) else return 0 end",
            1,
            self._lease_key(run_id),
            token,
        )

    async def add_event(self, run_id: str, event: str, data: dict) -> None:
        await self._ensure_connected()
        from redis.exceptions import WatchError

        for _ in range(5):
            async with self._redis.pipeline(transaction=True) as pipe:
                try:
                    await pipe.watch(run_id)
                    raw = await pipe.get(run_id)
                    if raw is None:
                        return
                    state = self._deserialize(raw)
                    state.events.append(
                        {"sequence": len(state.events) + 1, "event": event, "data": data}
                    )
                    pipe.multi()
                    pipe.set(run_id, self._serialize(state), ex=self._ttl)
                    await pipe.execute()
                    return
                except WatchError:
                    continue
        raise RuntimeError(f"Could not append run event for {run_id}: concurrent updates did not settle")

    async def get_events(self, run_id: str) -> list[dict]:
        state = await self.get(run_id)
        return list(state.events) if state else []

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
            # update.md §7: never silently degrade in production.
            if getattr(settings, "app_env", "development") == "production":
                logger.error("Redis unavailable in production: %s", exc)
                raise
            logger.warning("Redis unavailable, falling back to in-memory store: %s", exc)
    return RunStore()


_instance = None


async def get_run_store():
    global _instance
    if _instance is None:
        _instance = await _create_run_store()
    return _instance


class _RunStoreProxy:
    async def _store(self):
        return await get_run_store()

    async def create(self, run_id, query, model=None, user_id=None, idempotency_key=None):
        store = await self._store()
        return await store.create(run_id, query, model, user_id=user_id, idempotency_key=idempotency_key)

    async def get(self, run_id):
        store = await self._store()
        return await store.get(run_id)

    async def update(self, run_id, status=None, results=None):
        store = await self._store()
        await store.update(run_id, status, results)

    async def try_start(self, run_id):
        store = await self._store()
        return await store.try_start(run_id)

    async def add_event(self, run_id, event, data):
        store = await self._store()
        await store.add_event(run_id, event, data)

    async def get_events(self, run_id):
        store = await self._store()
        return await store.get_events(run_id)

    async def cleanup(self):
        store = await self._store()
        await store.cleanup()


run_store = _RunStoreProxy()
