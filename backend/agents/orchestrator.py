from datetime import datetime, timezone
from typing import Callable, Awaitable, Optional, TypedDict
from langgraph.graph import StateGraph, END
from langgraph.constants import START
from models.schemas import AgentStep, PaperSearchResult, Paper
from agents.research_agent import research_agent
from agents.summary_agent import summary_agent
from agents.memory_agent import memory_agent
from services.run_store import run_store

# Module-level callback registry: run_id -> async callback
_callbacks: dict[str, Callable[[AgentStep], Awaitable[None]]] = {}


class OrchestratorState(TypedDict):
    run_id: str
    query: str
    user_id: str
    model: Optional[str]
    raw_papers: list[dict]
    enriched_papers: list[dict]
    ranked_papers: list[dict]
    steps: list[AgentStep]


async def _emit(run_id: str, state: OrchestratorState, step: AgentStep):
    """Emit a step to both the state list and the live callback."""
    state["steps"].append(step)
    cb = _callbacks.get(run_id)
    if cb:
        await cb(step)


async def _research_node(state: OrchestratorState) -> OrchestratorState:
    run_id = state["run_id"]

    async def cb(step: AgentStep):
        await _emit(run_id, state, step)

    try:
        await _emit(run_id, state, AgentStep(agent="research", status="started"))
        state["raw_papers"] = await research_agent(state["query"], cb)
    except Exception as e:
        await _emit(run_id, state, AgentStep(agent="research", status="error", message=str(e)))
        state["raw_papers"] = []
    return state


async def _summary_node(state: OrchestratorState) -> OrchestratorState:
    run_id = state["run_id"]

    async def cb(step: AgentStep):
        await _emit(run_id, state, step)

    try:
        state["enriched_papers"] = await summary_agent(
            state["raw_papers"], cb, model_override=state.get("model")
        )
    except Exception as e:
        await _emit(run_id, state, AgentStep(agent="summary", status="error", message=str(e)))
        state["enriched_papers"] = state["raw_papers"]
    return state


async def _memory_node(state: OrchestratorState) -> OrchestratorState:
    run_id = state["run_id"]

    async def cb(step: AgentStep):
        await _emit(run_id, state, step)

    try:
        state["ranked_papers"] = await memory_agent(
            state["enriched_papers"], state["user_id"], state["query"], cb
        )
    except Exception as e:
        await _emit(run_id, state, AgentStep(agent="memory", status="error", message=str(e)))
        state["ranked_papers"] = state["enriched_papers"]
    return state


_orchestrator_graph = None


def _get_graph():
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
        _orchestrator_graph = builder.compile()
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
    }

    try:
        final_state = await _get_graph().ainvoke(initial_state)
    except Exception as e:
        await callback(AgentStep(agent="orchestrator", status="error", message=str(e)))
        final_state = initial_state
    finally:
        _callbacks.pop(run_id, None)

    if final_state is None:
        final_state = initial_state

    papers = []
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
    await run_store.update(run_id, status="complete", results=[paper.model_dump() for paper in papers])
    await callback(AgentStep(agent="orchestrator", status="complete", count=len(papers)))
    return result
