import os
from importlib import import_module

# LangGraph reads this option when its serializer module is imported. Keep
# persisted checkpoint deserialization restricted to safe types in every env.
os.environ["LANGGRAPH_STRICT_MSGPACK"] = "true"

from datetime import datetime, timezone
from datetime import timedelta
from typing import Any, Awaitable, Callable, Optional, TypedDict, cast
from langgraph.graph import StateGraph, END
from langgraph.constants import START
from models.schemas import AgentStep, PaperSearchResult, Paper
from agents.research_agent import research_agent
from agents.summary_agent import summary_agent
from agents.memory_agent import memory_agent
from services.run_store import run_store
from services.observability import get_langfuse_config

# Module-level callback registry: run_id -> async callback
_callbacks: dict[str, Callable[[AgentStep], Awaitable[None]]] = {}


class OrchestratorState(TypedDict):
    run_id: str
    query: str
    user_id: str
    model: Optional[str]
    raw_papers: list[dict[str, Any]]
    enriched_papers: list[dict[str, Any]]
    ranked_papers: list[dict[str, Any]]
    steps: list[AgentStep]
    failed_agents: list[str]


async def _emit(run_id: str, state: OrchestratorState, step: AgentStep) -> None:
    """Emit a step to both the state list and the live callback."""
    state["steps"].append(step)
    cb = _callbacks.get(run_id)
    if cb:
        await cb(step)


async def _research_node(state: OrchestratorState) -> OrchestratorState:
    run_id = state["run_id"]

    async def cb(step: AgentStep) -> None:
        await _emit(run_id, state, step)

    try:
        await _emit(run_id, state, AgentStep(agent="research", status="started"))
        state["raw_papers"] = await research_agent(state["query"], cb)
    except Exception:
        await _emit(run_id, state, AgentStep(agent="research", status="error", message="Step failed"))
        state["failed_agents"].append("research")
        state["raw_papers"] = []
    return state


async def _summary_node(state: OrchestratorState) -> OrchestratorState:
    run_id = state["run_id"]

    async def cb(step: AgentStep) -> None:
        await _emit(run_id, state, step)

    try:
        state["enriched_papers"] = await summary_agent(
            state["raw_papers"], cb, model_override=state.get("model")
        )
    except Exception:
        await _emit(run_id, state, AgentStep(agent="summary", status="error", message="Step failed"))
        state["failed_agents"].append("summary")
        state["enriched_papers"] = state["raw_papers"]
    return state


async def _memory_node(state: OrchestratorState) -> OrchestratorState:
    run_id = state["run_id"]

    async def cb(step: AgentStep) -> None:
        await _emit(run_id, state, step)

    try:
        state["ranked_papers"] = await memory_agent(
            state["enriched_papers"], state["user_id"], state["query"], cb
        )
    except Exception:
        await _emit(run_id, state, AgentStep(agent="memory", status="error", message="Step failed"))
        state["failed_agents"].append("memory")
        state["ranked_papers"] = state["enriched_papers"]
    return state


_orchestrator_graph: Any = None
_checkpointer: Any = None
_checkpointer_context: Any = None
_durable_checkpointer = False


async def start_checkpointer(
    database_url: str = "",
    *,
    production: bool = False,
    saver_context_factory: Callable[[str], Any] | None = None,
) -> None:
    """Open and initialize graph checkpoint storage during app startup.

    Production requires Postgres. MemorySaver is only a local development
    fallback. The Postgres context stays open for the app lifetime and is
    closed by ``stop_checkpointer``.
    """
    global _checkpointer, _checkpointer_context, _durable_checkpointer, _orchestrator_graph
    if _checkpointer is not None:
        if production and not _durable_checkpointer:
            raise RuntimeError("Production LangGraph checkpointing is not durable")
        return
    if not database_url:
        if production:
            raise RuntimeError("DATABASE_URL is required for production LangGraph checkpointing")
        from langgraph.checkpoint.memory import MemorySaver

        _checkpointer = MemorySaver()
        _durable_checkpointer = False
        _orchestrator_graph = None
        return

    if saver_context_factory is None:
        try:
            postgres_checkpoint = import_module("langgraph.checkpoint.postgres.aio")
        except ImportError as exc:
            raise RuntimeError(
                "langgraph-checkpoint-postgres is required when DATABASE_URL is configured"
            ) from exc
        saver_class = getattr(postgres_checkpoint, "AsyncPostgresSaver")
        saver_context_factory = cast(Callable[[str], Any], saver_class.from_conn_string)

    context = saver_context_factory(database_url)
    saver = await context.__aenter__()
    try:
        await saver.setup()
    except BaseException as exc:
        await context.__aexit__(type(exc), exc, exc.__traceback__)
        raise RuntimeError("Could not initialize the LangGraph Postgres checkpoint schema") from exc

    _checkpointer_context = context
    _checkpointer = saver
    _durable_checkpointer = True
    _orchestrator_graph = None


async def stop_checkpointer() -> None:
    """Close the app-scoped Postgres connection and clear the compiled graph."""
    global _checkpointer, _checkpointer_context, _durable_checkpointer, _orchestrator_graph
    context = _checkpointer_context
    _checkpointer_context = None
    _checkpointer = None
    _durable_checkpointer = False
    _orchestrator_graph = None
    if context is not None:
        await context.__aexit__(None, None, None)


def _get_checkpointer() -> Any:
    global _checkpointer, _durable_checkpointer
    from config import get_settings

    if get_settings().app_env == "production" and not _durable_checkpointer:
        raise RuntimeError("Production LangGraph checkpointing was not initialized")
    if _checkpointer is None:
        from langgraph.checkpoint.memory import MemorySaver

        _checkpointer = MemorySaver()
        _durable_checkpointer = False
    return _checkpointer


def has_durable_checkpointer() -> bool:
    return _durable_checkpointer


async def checkpointer_ready() -> bool:
    """Return whether the initialized Postgres saver can reach its database."""
    if not _durable_checkpointer or _checkpointer is None:
        return False
    try:
        await _checkpointer.aget_tuple(
            {"configurable": {"thread_id": "__zenith_readiness_probe__"}}
        )
        return True
    except Exception:
        return False


async def cleanup_expired_checkpoints(batch_size: int = 200) -> int:
    """Delete checkpoints for terminal runs after the run-store retention TTL."""
    if not _durable_checkpointer or _checkpointer is None:
        return 0
    from services.run_store import PostgresRunStore, get_run_store

    store = await get_run_store()
    if not isinstance(store, PostgresRunStore):
        return 0

    cutoff = datetime.now(timezone.utc) - timedelta(seconds=store._ttl)
    deleted = 0
    offset = 0
    while True:
        response = await (
            store._database.table("research_runs")
            .select("id")
            .in_("status", ["complete", "failed", "cancelled"])
            .lt("created_at", cutoff.isoformat())
            .order("created_at")
            .range(offset, offset + batch_size - 1)
            .execute()
        )
        rows = response.data or []
        for row in rows:
            await _checkpointer.adelete_thread(str(row["id"]))
            deleted += 1
        if len(rows) < batch_size:
            break
        offset += len(rows)
    return deleted


async def delete_checkpoints_for_runs(run_ids: list[str]) -> None:
    """Delete checkpoint threads belonging to runs being erased."""
    if not _durable_checkpointer or _checkpointer is None:
        return
    for run_id in run_ids:
        await _checkpointer.adelete_thread(run_id)


async def _invoke_or_resume(
    graph: Any,
    initial_state: OrchestratorState,
    config: dict[str, Any],
) -> Any:
    """Resume an interrupted run from its latest checkpoint when available.

    LangGraph checkpoints at node boundaries. Passing ``None`` resumes pending
    work; a completed checkpoint is returned directly so a worker crash between
    graph completion and run-store finalization does not run the graph twice.
    """
    get_state = getattr(graph, "aget_state", None)
    if not callable(get_state):
        return await graph.ainvoke(initial_state, config=config)

    snapshot = await get_state(config)
    snapshot_config = getattr(snapshot, "config", None) or {}
    configurable = snapshot_config.get("configurable", {})
    checkpoint_id = configurable.get("checkpoint_id")
    if not checkpoint_id:
        return await graph.ainvoke(initial_state, config=config)

    values = getattr(snapshot, "values", None)
    if not isinstance(values, dict):
        raise RuntimeError("Existing LangGraph checkpoint has no valid state")
    for key in ("run_id", "user_id", "query", "model"):
        if values.get(key) != initial_state.get(key):
            raise RuntimeError("LangGraph checkpoint does not match the requested run")

    next_nodes = getattr(snapshot, "next", ())
    if next_nodes:
        return await graph.ainvoke(None, config=config)
    return values


def _get_graph() -> Any:
    global _orchestrator_graph
    if _orchestrator_graph is None:
        builder = StateGraph(OrchestratorState)
        builder.add_node("research", _research_node)
        builder.add_node("summary", _summary_node)
        builder.add_node("memory", _memory_node)
        builder.add_edge(START, "research")
        builder.add_edge("research", "summary")
        builder.add_edge("summary", "memory")
        builder.add_edge("memory", END)
        _orchestrator_graph = builder.compile(checkpointer=_get_checkpointer())
    return _orchestrator_graph


async def run_orchestrator(
    run_id: str,
    query: str,
    callback: Callable[[AgentStep], Awaitable[None]],
    user_id: str = "anonymous",
    model: Optional[str] = None,
) -> PaperSearchResult:
    """Run the full LangGraph agent pipeline."""
    await callback(AgentStep(agent="orchestrator", status="started", message=query))

    # Register callback for real-time streaming
    _callbacks[run_id] = callback

    initial_state: OrchestratorState = {
        "run_id": run_id,
        "query": query,
        "user_id": user_id,
        "model": model,
        "raw_papers": [],
        "enriched_papers": [],
        "ranked_papers": [],
        "steps": [],
        "failed_agents": [],
    }

    try:
        graph_config = {
            **get_langfuse_config(),
            "configurable": {"thread_id": run_id},
        }
        final_state = await _invoke_or_resume(_get_graph(), initial_state, graph_config)
    except Exception:
        await callback(AgentStep(agent="orchestrator", status="error", message="Step failed"))
        raise
    finally:
        _callbacks.pop(run_id, None)

    if final_state is None:
        raise RuntimeError("Research graph returned no state")
    if final_state.get("failed_agents"):
        failed = ", ".join(final_state["failed_agents"])
        await callback(AgentStep(agent="orchestrator", status="error", message="Step failed"))
        raise RuntimeError(f"Research pipeline failed in: {failed}")

    papers: list[Paper] = []
    for p in final_state.get("ranked_papers", []):
        pub_at = p.get("published_at", "")
        if isinstance(pub_at, str) and pub_at:
            try:
                pub_at = datetime.fromisoformat(pub_at.replace("Z", "+00:00"))
            except (ValueError, TypeError):
                pub_at = datetime.now(timezone.utc)
        elif not pub_at:
            pub_at = datetime.now(timezone.utc)

        papers.append(
            Paper(
                id=p.get("id", ""),
                title=p.get("title", ""),
                abstract=p.get("abstract", ""),
                authors=p.get("authors", []),
                url=p.get("url", ""),
                published_at=pub_at,
                summary_tldr=p.get("summary_tldr"),
                summary_contributions=p.get("summary_contributions"),
                relevance_score=p.get("relevance_score"),
                difficulty=p.get("difficulty"),
            )
        )

    result = PaperSearchResult(papers=papers, run_id=run_id)
    await callback(AgentStep(agent="orchestrator", status="complete", count=len(papers)))
    await run_store.update(run_id, status="complete", results=[paper.model_dump() for paper in papers])
    return result
