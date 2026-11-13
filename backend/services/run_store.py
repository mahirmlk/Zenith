import json
import logging
from typing import Any, Optional, Protocol
from collections.abc import Callable
from typing import cast
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta, timezone
import asyncio
import secrets
import hashlib

logger = logging.getLogger(__name__)
TERMINAL_STATUSES = {"complete", "failed", "cancelled"}


class AccountDeletionInProgressError(RuntimeError):
    """Raised when the database admission barrier rejects a new run."""


@dataclass
class RunState:
    run_id: str
    query: str
    model: Optional[str] = None
    status: str = "pending"
    results: list[dict[str, Any]] = field(default_factory=list)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    # Phase P0-C (update.md §5.2/§7): ownership, idempotency, start-once, events.
    user_id: Optional[str] = None
    idempotency_key: Optional[str] = None
    started: bool = False
    events: list[dict[str, Any]] = field(default_factory=list)


class RunStoreProtocol(Protocol):
    """Typed async contract shared by development and production stores."""

    async def create(
        self,
        run_id: str,
        query: str,
        model: Optional[str] = None,
        user_id: Optional[str] = None,
        idempotency_key: Optional[str] = None,
    ) -> RunState: ...

    async def get(self, run_id: str) -> Optional[RunState]: ...

    async def find_idempotent(self, user_id: str, idempotency_key: str) -> Optional[RunState]: ...

    async def update(
        self,
        run_id: str,
        status: Optional[str] = None,
        results: Optional[list[dict[str, Any]]] = None,
    ) -> None: ...

    async def try_start(self, run_id: str) -> bool: ...

    async def heartbeat(self, run_id: str) -> bool: ...

    async def release(self, run_id: str) -> None: ...

    async def add_event(self, run_id: str, event: str, data: dict[str, Any]) -> None: ...

    async def get_events(self, run_id: str) -> list[dict[str, Any]]: ...

    async def has_active_run(self, run_id: str) -> bool: ...

    async def delete_run(self, run_id: str) -> None: ...

    async def cleanup(self) -> None: ...


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
                        if existing.query != query or existing.model != model:
                            raise ValueError("Idempotency key was already used for a different request")
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

    async def find_idempotent(self, user_id: str, idempotency_key: str) -> Optional[RunState]:
        async with self._lock:
            for state in self._store.values():
                if (
                    state.user_id == user_id
                    and state.idempotency_key == idempotency_key
                    and not self._expired(state)
                ):
                    return state
        return None

    async def get(self, run_id: str) -> Optional[RunState]:
        async with self._lock:
            state = self._store.get(run_id)
            if state and self._expired(state):
                del self._store[run_id]
                return None
            return state

    async def update(
        self,
        run_id: str,
        status: Optional[str] = None,
        results: Optional[list[dict[str, Any]]] = None,
    ) -> None:
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

    async def add_event(self, run_id: str, event: str, data: dict[str, Any]) -> None:
        async with self._lock:
            state = self._store.get(run_id)
            if not state:
                return
            state.events.append(
                {"sequence": len(state.events) + 1, "event": event, "data": data}
            )

    async def get_events(self, run_id: str) -> list[dict[str, Any]]:
        async with self._lock:
            state = self._store.get(run_id)
            return list(state.events) if state else []

    async def has_active_run(self, run_id: str) -> bool:
        async with self._lock:
            return run_id in self._active_runs

    async def delete_run(self, run_id: str) -> None:
        async with self._lock:
            self._active_runs.discard(run_id)
            self._store.pop(run_id, None)

    async def cleanup(self) -> None:
        async with self._lock:
            now = datetime.now(timezone.utc)
            expired = [k for k, v in self._store.items() if now - v.created_at > self._ttl]
            for k in expired:
                del self._store[k]


class RedisRunStore:
    """Redis-backed run state and leases for local/development deployments.

    Production uses :class:`PostgresRunStore` for canonical metadata and
    events while Redis remains the queue and worker-lease service.
    """

    def __init__(self, redis_url: str = "redis://localhost:6379", ttl_seconds: int = 3600):
        self._redis_url = redis_url
        self._ttl = ttl_seconds
        self._redis: Any = None
        self._fallback = RunStore(ttl_seconds=ttl_seconds)
        self._lease_seconds = 90
        self._lease_tokens: dict[str, str] = {}

    async def _ensure_connected(self) -> None:
        if self._redis is None:
            import redis.asyncio as redis_mod

            redis_from_url = cast(Callable[..., Any], redis_mod.from_url)
            self._redis = redis_from_url(self._redis_url, decode_responses=True)

    def _serialize(self, state: RunState) -> str:
        d = asdict(state)
        d["created_at"] = state.created_at.isoformat()
        return json.dumps(d, default=str)

    @staticmethod
    def _idempotency_index_key(user_id: Optional[str], idempotency_key: str) -> str:
        digest = hashlib.sha256(
            f"{user_id or ''}\0{idempotency_key}".encode("utf-8")
        ).hexdigest()
        return f"zenith:runs:idempotency:{digest}"

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
        if not idempotency_key:
            await self._redis.set(run_id, self._serialize(state), ex=self._ttl)
            return state

        index_key = self._idempotency_index_key(user_id, idempotency_key)
        create_or_replay = """
        local existing = redis.call('GET', KEYS[1])
        if existing and redis.call('EXISTS', existing) == 1 then
            return existing
        end
        redis.call('SET', KEYS[2], ARGV[1], 'EX', ARGV[2])
        redis.call('SET', KEYS[1], KEYS[2], 'EX', ARGV[2])
        return KEYS[2]
        """
        actual_run_id = await self._redis.eval(
            create_or_replay,
            2,
            index_key,
            run_id,
            self._serialize(state),
            self._ttl,
        )
        stored_state = await self.get(actual_run_id)
        if stored_state is None:
            raise RuntimeError("Run idempotency record points to missing state")
        if stored_state.query != query or stored_state.model != model:
            raise ValueError("Idempotency key was already used for a different request")
        return stored_state

    async def get(self, run_id: str) -> Optional[RunState]:
        await self._ensure_connected()
        data = await self._redis.get(run_id)
        if data is None:
            return None
        return self._deserialize(data)

    async def find_idempotent(self, user_id: str, idempotency_key: str) -> Optional[RunState]:
        await self._ensure_connected()
        run_id = await self._redis.get(self._idempotency_index_key(user_id, idempotency_key))
        return await self.get(run_id) if run_id else None

    async def update(
        self,
        run_id: str,
        status: Optional[str] = None,
        results: Optional[list[dict[str, Any]]] = None,
    ) -> None:
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

    async def add_event(self, run_id: str, event: str, data: dict[str, Any]) -> None:
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

    async def get_events(self, run_id: str) -> list[dict[str, Any]]:
        state = await self.get(run_id)
        return list(state.events) if state else []

    async def has_active_run(self, run_id: str) -> bool:
        await self._ensure_connected()
        return bool(await self._redis.exists(self._lease_key(run_id)))

    async def delete_run(self, run_id: str) -> None:
        """Remove Redis state, lease, and any user-scoped idempotency index."""
        await self._ensure_connected()
        state = await self.get(run_id)
        keys = [run_id, self._lease_key(run_id)]
        if state and state.user_id and state.idempotency_key:
            keys.append(self._idempotency_index_key(state.user_id, state.idempotency_key))
        await self._redis.delete(*keys)
        self._lease_tokens.pop(run_id, None)

    async def cleanup(self) -> None:
        pass


class PostgresRunStore(RedisRunStore):
    """Canonical run/event storage in Postgres with Redis worker leases.

    Redis keeps its existing job queue and lease role. Run metadata, results,
    and ordered events are read from and committed to Supabase Postgres so a
    backend restart cannot erase the API's run history.
    """

    def __init__(self, database: Any, redis_url: str, ttl_seconds: int = 3600):
        super().__init__(redis_url=redis_url, ttl_seconds=ttl_seconds)
        self._database = database

    async def verify_schema(self) -> None:
        """Fail fast when the canonical run migration is absent."""
        await (
            self._database.table("research_runs")
            .select("id,user_id,query,model,results,status,created_at,updated_at,started,idempotency_key")
            .limit(0)
            .execute()
        )
        # These no-op RPCs also verify that PostgREST has refreshed its schema
        # cache and that service_role can invoke the security-definer writers.
        await self._database.rpc(
            "update_research_run_atomic",
            {
                "p_run_id": None,
                "p_status": None,
                "p_results": None,
                "p_started": False,
            },
        ).execute()
        await self._database.rpc(
            "append_run_event_atomic",
            {"p_run_id": None, "p_kind": "readiness_probe", "p_payload": {}},
        ).execute()
        await (
            self._database.table("run_events")
            .select("run_id,sequence,kind,safe_payload,created_at")
            .limit(0)
            .execute()
        )
        from config import get_settings

        if get_settings().research_plan_execution_enabled:
            await (
                self._database.table("research_plan_executions")
                .select("run_id,user_id,query,deadline_at")
                .limit(0)
                .execute()
            )

    @staticmethod
    def _idempotency_digest(user_id: Optional[str], idempotency_key: Optional[str]) -> Optional[str]:
        if not idempotency_key:
            return None
        return hashlib.sha256(
            f"{user_id or ''}\0{idempotency_key}".encode("utf-8")
        ).hexdigest()

    @staticmethod
    def _row(response: Any) -> Optional[dict[str, Any]]:
        data = getattr(response, "data", None)
        if isinstance(data, list):
            return data[0] if data else None
        return data if isinstance(data, dict) else None

    @staticmethod
    def _state_from_row(row: dict[str, Any]) -> RunState:
        created_at = row.get("created_at")
        if isinstance(created_at, str):
            try:
                created_at = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
            except ValueError:
                created_at = datetime.now(timezone.utc)
        if not isinstance(created_at, datetime):
            created_at = datetime.now(timezone.utc)
        results = row.get("results") or []
        if isinstance(results, str):
            try:
                results = json.loads(results)
            except json.JSONDecodeError:
                results = []
        return RunState(
            run_id=str(row["id"]),
            query=row.get("query") or "",
            model=row.get("model"),
            status=row.get("status") or "pending",
            results=results if isinstance(results, list) else [],
            created_at=created_at,
            user_id=str(row["user_id"]) if row.get("user_id") is not None else None,
            idempotency_key=row.get("idempotency_key"),
            started=bool(row.get("started", False)),
            events=[],
        )

    async def create(
        self,
        run_id: str,
        query: str,
        model: Optional[str] = None,
        user_id: Optional[str] = None,
        idempotency_key: Optional[str] = None,
    ) -> RunState:
        digest = self._idempotency_digest(user_id, idempotency_key)
        try:
            response = await self._database.rpc(
                "create_research_run_atomic",
                {
                    "p_run_id": run_id,
                    "p_user_id": user_id,
                    "p_query": query,
                    "p_model": model,
                    "p_idempotency_key": digest,
                    "p_ttl_seconds": self._ttl,
                },
            ).execute()
        except Exception as exc:
            if "account_deletion_in_progress" in str(exc):
                raise AccountDeletionInProgressError(
                    "Account deletion is in progress"
                ) from exc
            raise
        row = self._row(response)
        if row is None:
            raise RuntimeError("Postgres did not return the created research run")
        state = self._state_from_row(row)
        if state.query != query or state.model != model:
            raise ValueError("Idempotency key was already used for a different request")
        # Preserve the caller's opaque key in the immediate response. Only
        # the digest is persisted and returned by later lookups.
        state.idempotency_key = idempotency_key
        return state

    async def get(self, run_id: str) -> Optional[RunState]:
        response = await (
            self._database.table("research_runs")
            .select("*")
            .eq("id", run_id)
            .maybe_single()
            .execute()
        )
        row = self._row(response)
        if row is None:
            return None
        state = self._state_from_row(row)
        return None if datetime.now(timezone.utc) - state.created_at > timedelta(seconds=self._ttl) else state

    async def find_idempotent(self, user_id: str, idempotency_key: str) -> Optional[RunState]:
        digest = self._idempotency_digest(user_id, idempotency_key)
        response = await (
            self._database.table("research_runs")
            .select("*")
            .eq("user_id", user_id)
            .eq("idempotency_key", digest)
            .maybe_single()
            .execute()
        )
        row = self._row(response)
        if row is None:
            return None
        state = self._state_from_row(row)
        if datetime.now(timezone.utc) - state.created_at > timedelta(seconds=self._ttl):
            return None
        state.idempotency_key = idempotency_key
        return state

    async def update(
        self,
        run_id: str,
        status: Optional[str] = None,
        results: Optional[list[dict[str, Any]]] = None,
    ) -> None:
        response = await self._database.rpc(
            "update_research_run_atomic",
            {
                "p_run_id": run_id,
                "p_status": status,
                "p_results": results,
                "p_started": status == "running",
            },
        ).execute()
        if response.data is False:
            logger.debug("Run %s missing or already terminal; update ignored", run_id)

    async def try_start(self, run_id: str) -> bool:
        """Claim the Redis lease, then persist running state atomically."""
        state = await self.get(run_id)
        if state is None or state.status in TERMINAL_STATUSES:
            return False
        await self._ensure_connected()
        lease_key = self._lease_key(run_id)
        token = secrets.token_urlsafe(24)
        acquired = await self._redis.set(
            lease_key, token, nx=True, ex=self._lease_seconds
        )
        if not acquired:
            return False
        self._lease_tokens[run_id] = token
        try:
            response = await self._database.rpc(
                "update_research_run_atomic",
                {
                    "p_run_id": run_id,
                    "p_status": "running",
                    "p_results": None,
                    "p_started": True,
                },
            ).execute()
            if not response.data:
                await self.release(run_id)
                return False
            return True
        except Exception:
            await self.release(run_id)
            raise

    async def add_event(self, run_id: str, event: str, data: dict[str, Any]) -> None:
        await self._database.rpc(
            "append_run_event_atomic",
            {"p_run_id": run_id, "p_kind": event, "p_payload": data},
        ).execute()

    async def get_events(self, run_id: str) -> list[dict[str, Any]]:
        response = await (
            self._database.table("run_events")
            .select("sequence,kind,safe_payload")
            .eq("run_id", run_id)
            .order("sequence")
            .execute()
        )
        return [
            {
                "sequence": row["sequence"],
                "event": row["kind"],
                "data": row.get("safe_payload") or {},
            }
            for row in (response.data or [])
        ]

    async def delete_run(self, run_id: str) -> None:
        """Delete canonical run data; attached execution metadata cascades."""
        await super().delete_run(run_id)
        await self._database.table("research_runs").delete().eq("id", run_id).execute()

    async def cleanup(self) -> None:
        cutoff = datetime.now(timezone.utc) - timedelta(seconds=self._ttl)
        await (
            self._database.table("research_runs")
            .delete()
            .in_("status", ["complete", "failed", "cancelled"])
            .lt("created_at", cutoff.isoformat())
            .execute()
        )


async def _create_run_store() -> RunStoreProtocol:
    from config import get_settings

    settings = get_settings()
    if settings.app_env == "production":
        if not settings.redis_url:
            raise RuntimeError("REDIS_URL is required for production run leases and queueing")
        from services.supabase_client import get_supabase

        database = await get_supabase()
        postgres_store = PostgresRunStore(database, redis_url=settings.redis_url)
        await postgres_store._ensure_connected()
        await postgres_store._redis.ping()
        await postgres_store.verify_schema()
        logger.info("Using PostgresRunStore with Redis leases")
        return postgres_store

    if settings.redis_url:
        try:
            redis_store = RedisRunStore(redis_url=settings.redis_url)
            await redis_store._ensure_connected()
            await redis_store._redis.ping()
            logger.info("Using RedisRunStore")
            return redis_store
        except Exception as exc:
            # update.md §7: never silently degrade in production.
            if getattr(settings, "app_env", "development") == "production":
                logger.error("Redis unavailable in production: %s", exc)
                raise
            logger.warning("Redis unavailable, falling back to in-memory store: %s", exc)
    return RunStore()


_instance = None
_instance_lock: Optional[asyncio.Lock] = None


async def get_run_store() -> RunStoreProtocol:
    global _instance, _instance_lock
    if _instance is None:
        if _instance_lock is None:
            _instance_lock = asyncio.Lock()
        async with _instance_lock:
            if _instance is None:
                _instance = await _create_run_store()
    return _instance


class _RunStoreProxy:
    async def _store(self) -> RunStoreProtocol:
        return await get_run_store()

    async def create(
        self,
        run_id: str,
        query: str,
        model: Optional[str] = None,
        user_id: Optional[str] = None,
        idempotency_key: Optional[str] = None,
    ) -> RunState:
        store = await self._store()
        return await store.create(run_id, query, model, user_id=user_id, idempotency_key=idempotency_key)

    async def get(self, run_id: str) -> Optional[RunState]:
        store = await self._store()
        return await store.get(run_id)

    async def find_idempotent(self, user_id: str, idempotency_key: str) -> Optional[RunState]:
        store = await self._store()
        return await store.find_idempotent(user_id, idempotency_key)

    async def update(
        self,
        run_id: str,
        status: Optional[str] = None,
        results: Optional[list[dict[str, Any]]] = None,
    ) -> None:
        store = await self._store()
        await store.update(run_id, status, results)

    async def try_start(self, run_id: str) -> bool:
        store = await self._store()
        return await store.try_start(run_id)

    async def heartbeat(self, run_id: str) -> bool:
        store = await self._store()
        return await store.heartbeat(run_id)

    async def release(self, run_id: str) -> None:
        store = await self._store()
        await store.release(run_id)

    async def add_event(self, run_id: str, event: str, data: dict[str, Any]) -> None:
        store = await self._store()
        await store.add_event(run_id, event, data)

    async def get_events(self, run_id: str) -> list[dict[str, Any]]:
        store = await self._store()
        return await store.get_events(run_id)

    async def delete_run(self, run_id: str) -> None:
        store = await self._store()
        await store.delete_run(run_id)

    async def cleanup(self) -> None:
        store = await self._store()
        await store.cleanup()


run_store = _RunStoreProxy()
