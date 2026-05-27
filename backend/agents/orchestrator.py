from typing import Callable, Awaitable, Optional, TypedDict
from langgraph.graph import StateGraph, END
from langgraph.constants import START
from models.schemas import AgentStep, PaperSearchResult, Paper
from agents.research_agent import research_agent
from agents.summary_agent import summary_agent
from agents.memory_agent import memory_agent
from services.run_store import run_store


class OrchestratorState(TypedDict):
    run_id: str
    query: str
    user_id: str
    model: Optional[str]
    raw_papers: list[dict]
    enriched_papers: list[dict]
    ranked_papers: list[dict]
    steps: list[AgentStep]


async def _research_node(state: OrchestratorState) -> OrchestratorState:
    async def cb(step: AgentStep):
        state["steps"].append(step)
    try:
        state["raw_papers"] = await research_agent(state["query"], cb)
    except Exception as e:
        state["steps"].append(AgentStep(agent="research", status="error", message=str(e)))
        state["raw_papers"] = []
    return state


async def _summary_node(state: OrchestratorState) -> OrchestratorState:
    async def cb(step: AgentStep):
        state["steps"].append(step)
    try:
        state["enriched_papers"] = await summary_agent(state["raw_papers"], cb, model_override=state.get("model"))
    except Exception as e:
        state["steps"].append(AgentStep(agent="summary", status="error", message=str(e)))
        state["enriched_papers"] = state["raw_papers"]
    return state


async def _memory_node(state: OrchestratorState) -> OrchestratorState:
    async def cb(step: AgentStep):
        state["steps"].append(step)
    try:
        state["ranked_papers"] = await memory_agent(state["enriched_papers"], state["user_id"], state["query"], cb)
    except Exception as e:
        state["steps"].append(AgentStep(agent="memory", status="error", message=str(e)))
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

    # Stream all collected steps
    for step in final_state["steps"]:
        await callback(step)

    papers = []
    for p in final_state.get("ranked_papers", []):
        papers.append(
            Paper(
                id=p.get("id", ""),
                title=p.get("title", ""),
                abstract=p.get("abstract", ""),
                authors=p.get("authors", []),
                url=p.get("url", ""),
                published_at=p.get("published_at", ""),
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
