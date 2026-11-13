"""Durable, bounded research-plan execution on the shared run lifecycle.

The Redis run queue, lease, Postgres run/event store, and LangGraph checkpointer
remain the sole execution/recovery path. Provider work is at-least-once across a
crash before a node checkpoint is committed; each node is idempotent/read-only
except for bounded synthesis calls, which may repeat during that window.
"""
from __future__ import annotations

import asyncio
import re
from datetime import datetime, timezone
from typing import Any, Literal, TypedDict, cast

from langgraph.constants import START
from langgraph.graph import END, StateGraph

from agents.research_types import (
    ComparisonRow,
    ResearchPlanExecutionResult,
    ResearchPlanEvidence,
    ResearchPlanSource,
    ResearchPlanStepOutcome,
    SynthesisClaim,
    SynthesisEvidenceItem,
    build_comparison,
)
from config import get_settings
from security.authorization import can_access_project
from security.prompt_injection import scan_untrusted
from services.budget import consume
from services.retrieval import hybrid_rank, query_entities, query_terms
from services.run_store import run_store
from services.supabase_client import get_supabase

MAX_PLAN_SOURCES = 10
MAX_PROJECT_PAPERS_READ = 200
MAX_PROJECT_DOCUMENTS_READ = 10
MAX_PROJECT_PAGES_READ = 500
PLAN_RUN_MODEL_MARKER = "__research_plan_execution__"


class PlanExecutionError(RuntimeError):
    """A plan step could not complete within its persisted contract."""


class PlanExecutionCancelled(PlanExecutionError):
    """The owning research run was cancelled between plan steps."""


class PlanExecutionState(TypedDict):
    run_id: str
    user_id: str
    query: str
    project_id: str | None
    source_scope: Literal["public_corpus", "project"]
    task_type: Literal["feed", "explain", "compare", "deep_research"]
    max_sources: int
    max_tool_calls: int
    max_wall_clock_seconds: int
    max_model_calls: int
    max_output_tokens: int
    synthesis_enabled: bool
    deadline_at: str
    logical_tool_calls: int
    papers: list[dict[str, Any]]
    sources: list[dict[str, Any]]
    evidence: list[dict[str, Any]]
    comparison: list[dict[str, Any]]
    gaps: list[str]
    synthesis: list[dict[str, Any]]
    steps: list[dict[str, Any]]


async def get_plan_execution(run_id: str) -> dict[str, Any] | None:
    """Read immutable execution parameters for a queued run, if it is a plan."""
    supabase = await get_supabase()
    response = await (
        supabase.table("research_plan_executions")
        .select("run_id,user_id,query,project_id,source_scope,task_type,max_sources,max_tool_calls,max_wall_clock_seconds,max_model_calls,max_output_tokens,synthesis_enabled,deadline_at")
        .eq("run_id", run_id)
        .maybe_single()
        .execute()
    )
    return response.data if isinstance(response.data, dict) else None


def is_missing_plan_execution_table(error: Exception) -> bool:
    """Recognize only PostgREST/Postgres missing-table failures for old schemas."""
    message = str(error).casefold()
    return (
        "research_plan_executions" in message
        and ("42p01" in message or "pgrst205" in message or "does not exist" in message or "not found" in message)
    )


async def _require_active_project(project_id: str, user_id: str, supabase: Any) -> None:
    """Reauthorize every project-data read; membership can change mid-run."""
    project_result = await (
        supabase.table("projects")
        .select("owner_id")
        .eq("id", project_id)
        .is_("deleted_at", "null")
        .maybe_single()
        .execute()
    )
    project = project_result.data
    if not isinstance(project, dict):
        raise PlanExecutionError("Project access was revoked")
    member_result = await (
        supabase.table("project_members")
        .select("user_id,role")
        .eq("project_id", project_id)
        .execute()
    )
    member_roles = {
        str(row["user_id"]): str(row["role"])
        for row in (member_result.data or [])
        if isinstance(row, dict) and row.get("user_id") and row.get("role")
    }
    if not can_access_project(str(project.get("owner_id") or ""), member_roles, user_id):
        raise PlanExecutionError("Project access was revoked")


async def _check_run_and_deadline(state: PlanExecutionState) -> None:
    current = await run_store.get(state["run_id"])
    if current is None or current.status == "cancelled":
        raise PlanExecutionCancelled("Research plan was cancelled")
    deadline = datetime.fromisoformat(state["deadline_at"].replace("Z", "+00:00"))
    if datetime.now(timezone.utc) >= deadline:
        raise TimeoutError("Research plan exceeded its wall-clock limit")


def _consume_logical_tool(state: PlanExecutionState) -> None:
    next_count = state["logical_tool_calls"] + 1
    if next_count > state["max_tool_calls"]:
        raise PlanExecutionError("Research plan exceeded its tool-call limit")
    state["logical_tool_calls"] = next_count


async def _emit_step(
    state: PlanExecutionState,
    step_id: str,
    status: str,
    *,
    count: int | None = None,
    message: str | None = None,
) -> None:
    await run_store.add_event(
        state["run_id"],
        "agent_step",
        {
            "agent": f"plan:{step_id}",
            "status": status,
            "count": count,
            "message": message,
        },
    )


async def _retrieve_sources(state: PlanExecutionState) -> PlanExecutionState:
    await _check_run_and_deadline(state)
    await _emit_step(state, "retrieve_sources", "started")
    _consume_logical_tool(state)
    supabase = await get_supabase()
    if state["project_id"]:
        project_id = state["project_id"]
        await _require_active_project(project_id, state["user_id"], supabase)
        source_rows = await (
            supabase.table("project_sources")
            .select("paper_id")
            .eq("project_id", project_id)
            .range(0, MAX_PROJECT_PAPERS_READ - 1)
            .execute()
        )
        paper_ids = list(dict.fromkeys(
            str(row["paper_id"])
            for row in (source_rows.data or [])
            if isinstance(row, dict) and row.get("paper_id")
        ))[:MAX_PROJECT_PAPERS_READ]
        if paper_ids:
            await _require_active_project(project_id, state["user_id"], supabase)
            result = await (
                supabase.table("papers")
                .select("id,title,abstract")
                .in_("id", paper_ids)
                .execute()
            )
            papers = [row for row in (result.data or []) if isinstance(row, dict)]
        else:
            papers = []
    else:
        result = await (
            supabase.table("papers")
            .select("id,title,abstract")
            .order("published_at", desc=True)
            .range(0, 49)
            .execute()
        )
        papers = [row for row in (result.data or []) if isinstance(row, dict)]

    state["papers"] = hybrid_rank(state["query"], papers)[: state["max_sources"]]
    state["sources"] = [
        {"paper_id": str(paper.get("id") or ""), "title": str(paper.get("title") or "")}
        for paper in state["papers"]
        if paper.get("id")
    ]
    outcome = ResearchPlanStepOutcome(
        step_id="retrieve_sources", status="complete", count=len(state["sources"])
    )
    state["steps"].append(outcome.model_dump())
    await _emit_step(state, "retrieve_sources", "complete", count=len(state["sources"]))
    return state


def _abstract_evidence(state: PlanExecutionState) -> list[ResearchPlanEvidence]:
    query_tokens = query_terms(state["query"])
    if not query_tokens:
        return []
    query_entities_set = query_entities(state["query"])
    sentence_pattern = re.compile(r"\S.*?(?:[.!?](?=\s|$)|$)", re.DOTALL)
    selected: list[ResearchPlanEvidence] = []
    for paper in state["papers"][: state["max_sources"]]:
        paper_id = str(paper.get("id") or "")
        title = str(paper.get("title") or "")
        abstract = paper.get("abstract")
        if not paper_id or not isinstance(abstract, str):
            continue
        if query_entities_set and not query_entities_set.intersection(
            query_terms(f"{title} {abstract}")
        ):
            continue
        for match in sentence_pattern.finditer(abstract):
            sentence = match.group(0)
            if scan_untrusted(sentence):
                continue
            terms = query_terms(sentence)
            if not terms.intersection(query_tokens):
                continue
            start, end = match.span()
            if abstract[start:end] != sentence:
                continue
            selected.append(
                ResearchPlanEvidence(
                    citation_id=f"{paper_id}:{start}:{end}",
                    paper_id=paper_id,
                    title=title,
                    sentence=sentence,
                    start_offset=start,
                    end_offset=end,
                )
            )
            if len(selected) >= 5:
                return selected
    return selected


def _pdf_evidence(
    query: str,
    documents: list[dict[str, Any]],
    pages: list[dict[str, Any]],
) -> list[ResearchPlanEvidence]:
    query_tokens = query_terms(query)
    if not query_tokens:
        return []
    documents_by_id = {
        str(document.get("id")): document for document in documents if document.get("id")
    }
    sentence_pattern = re.compile(r"\S.*?(?:[.!?](?=\s|$)|$)", re.DOTALL)
    candidates: list[tuple[int, ResearchPlanEvidence]] = []
    for page in pages:
        doc_id = str(page.get("document_id") or "")
        document = documents_by_id.get(doc_id)
        page_number = page.get("page_number")
        text = page.get("text")
        if not document or not isinstance(page_number, int) or not isinstance(text, str):
            continue
        if query_entities(query) and not query_entities(query).intersection(query_terms(text)):
            continue
        for match in sentence_pattern.finditer(text):
            sentence = match.group(0)
            if scan_untrusted(sentence):
                continue
            overlap = query_tokens.intersection(query_terms(sentence))
            if not overlap:
                continue
            start, end = match.span()
            if text[start:end] != sentence:
                continue
            candidates.append((
                len(overlap),
                ResearchPlanEvidence(
                    citation_id=f"{doc_id}:page:{page_number}",
                    document_id=doc_id,
                    page_number=page_number,
                    sentence=sentence,
                    start_offset=start,
                    end_offset=end,
                ),
            ))
    candidates.sort(key=lambda item: item[0], reverse=True)
    return [item for _, item in candidates[:5]]


async def _extract_evidence(state: PlanExecutionState) -> PlanExecutionState:
    await _check_run_and_deadline(state)
    await _emit_step(state, "extract_evidence", "started")
    _consume_logical_tool(state)
    evidence = _abstract_evidence(state)
    if state["project_id"]:
        supabase = await get_supabase()
        project_id = state["project_id"]
        await _require_active_project(project_id, state["user_id"], supabase)
        documents_result = await (
            supabase.table("project_documents")
            .select("id,filename,page_count")
            .eq("project_id", project_id)
            .order("created_at", desc=True)
            .range(0, MAX_PROJECT_DOCUMENTS_READ - 1)
            .execute()
        )
        documents = [row for row in (documents_result.data or []) if isinstance(row, dict)]
        doc_ids = [str(document["id"]) for document in documents if document.get("id")]
        if doc_ids:
            await _require_active_project(project_id, state["user_id"], supabase)
            pages_result = await (
                supabase.table("project_document_pages")
                .select("document_id,page_number,text")
                .in_("document_id", doc_ids)
                .range(0, MAX_PROJECT_PAGES_READ - 1)
                .execute()
            )
            pages = [row for row in (pages_result.data or []) if isinstance(row, dict)]
            evidence.extend(_pdf_evidence(state["query"], documents, pages))
    state["evidence"] = [item.model_dump() for item in evidence[:10]]
    outcome = ResearchPlanStepOutcome(
        step_id="extract_evidence", status="complete", count=len(state["evidence"])
    )
    state["steps"].append(outcome.model_dump())
    await _emit_step(state, "extract_evidence", "complete", count=len(state["evidence"]))
    return state


async def _compare_sources(state: PlanExecutionState) -> PlanExecutionState:
    await _check_run_and_deadline(state)
    await _emit_step(state, "compare_sources", "started")
    _consume_logical_tool(state)
    state["comparison"] = [
        row.model_dump() for row in build_comparison(state["papers"][: state["max_sources"]])
    ]
    state["steps"].append(
        ResearchPlanStepOutcome(
            step_id="compare_sources", status="complete", count=len(state["comparison"])
        ).model_dump()
    )
    await _emit_step(state, "compare_sources", "complete", count=len(state["comparison"]))
    return state


async def _identify_gaps(state: PlanExecutionState) -> PlanExecutionState:
    await _check_run_and_deadline(state)
    await _emit_step(state, "identify_gaps", "started")
    _consume_logical_tool(state)
    evidenced_terms: set[str] = set()
    for item in state["evidence"]:
        evidenced_terms.update(query_terms(str(item.get("sentence") or "")))
    state["gaps"] = sorted(query_terms(state["query"]) - evidenced_terms)[:8]
    state["steps"].append(
        ResearchPlanStepOutcome(
            step_id="identify_gaps", status="complete", count=len(state["gaps"])
        ).model_dump()
    )
    await _emit_step(state, "identify_gaps", "complete", count=len(state["gaps"]))
    return state


async def _synthesize(state: PlanExecutionState) -> PlanExecutionState:
    await _check_run_and_deadline(state)
    if not _synthesis_within_budget(state):
        state["steps"].append(
            ResearchPlanStepOutcome(step_id="synthesis_unavailable", status="skipped").model_dump()
        )
        await _emit_step(state, "synthesis_unavailable", "skipped", message="Synthesis is disabled")
        return state

    await _emit_step(state, "draft_synthesis", "started")
    if not await consume(state["user_id"], 10, namespace="synthesis"):
        raise PlanExecutionError("Daily synthesis request limit reached")
    from services.synthesis import synthesize_claims

    evidence = [
        SynthesisEvidenceItem(
            evidence_id=f"{item.paper_id}:{item.start_offset}:{item.end_offset}",
            paper_id=str(item.paper_id),
            title=str(item.title or ""),
            sentence=item.sentence,
            start_offset=item.start_offset,
            end_offset=item.end_offset,
        )
        for item in _abstract_evidence(state)
        if item.paper_id
    ][:6]
    await _emit_step(state, "draft_synthesis", "complete", count=len(evidence))
    await _emit_step(state, "review_claims", "started")
    claims = await synthesize_claims(state["query"], evidence)
    state["synthesis"] = [claim.model_dump() for claim in claims]
    state["steps"].append(
        ResearchPlanStepOutcome(
            step_id="draft_synthesis", status="complete", count=len(evidence)
        ).model_dump()
    )
    state["steps"].append(
        ResearchPlanStepOutcome(
            step_id="review_claims", status="complete", count=len(state["synthesis"])
        ).model_dump()
    )
    await _emit_step(state, "review_claims", "complete", count=len(state["synthesis"]))
    return state


def _synthesis_within_budget(state: PlanExecutionState) -> bool:
    """The synthesis service uses two calls capped at 900 tokens each."""
    return bool(
        state["synthesis_enabled"]
        and state["max_model_calls"] >= 2
        and state["max_output_tokens"] >= 1800
    )


def _graph() -> Any:
    builder = StateGraph(PlanExecutionState)
    builder.add_node("retrieve_sources", _retrieve_sources)
    builder.add_node("extract_evidence", _extract_evidence)
    builder.add_node("compare_sources", _compare_sources)
    builder.add_node("identify_gaps", _identify_gaps)
    builder.add_node("synthesize", _synthesize)
    builder.add_edge(START, "retrieve_sources")
    builder.add_edge("retrieve_sources", "extract_evidence")

    def after_extract(state: PlanExecutionState) -> str:
        return "compare_sources" if state["task_type"] == "compare" else (
            "identify_gaps" if state["task_type"] == "deep_research" else END
        )

    def after_gaps(state: PlanExecutionState) -> str:
        return "synthesize" if state["task_type"] == "deep_research" else END

    builder.add_conditional_edges(
        "extract_evidence", after_extract,
        {"compare_sources": "compare_sources", "identify_gaps": "identify_gaps", END: END},
    )
    builder.add_edge("compare_sources", "identify_gaps")
    builder.add_conditional_edges("identify_gaps", after_gaps, {"synthesize": "synthesize", END: END})
    builder.add_edge("synthesize", END)
    from agents.orchestrator import _get_checkpointer

    return builder.compile(checkpointer=_get_checkpointer())


_compiled_graph: Any | None = None


def _get_graph() -> Any:
    global _compiled_graph
    if _compiled_graph is None:
        _compiled_graph = _graph()
    return _compiled_graph


async def _invoke_or_resume(
    graph: Any,
    initial_state: PlanExecutionState,
    config: dict[str, Any],
) -> PlanExecutionState:
    get_state = getattr(graph, "aget_state", None)
    if not callable(get_state):
        return cast(PlanExecutionState, await graph.ainvoke(initial_state, config=config))
    snapshot = await get_state(config)
    configurable = (getattr(snapshot, "config", None) or {}).get("configurable", {})
    if not configurable.get("checkpoint_id"):
        return cast(PlanExecutionState, await graph.ainvoke(initial_state, config=config))
    values = getattr(snapshot, "values", None)
    if not isinstance(values, dict):
        raise PlanExecutionError("Existing plan checkpoint has no valid state")
    for key in (
        "run_id",
        "user_id",
        "query",
        "project_id",
        "source_scope",
        "task_type",
        "max_sources",
        "max_tool_calls",
        "max_wall_clock_seconds",
        "max_model_calls",
        "max_output_tokens",
        "synthesis_enabled",
        "deadline_at",
    ):
        if values.get(key) != cast(dict[str, Any], initial_state).get(key):
            raise PlanExecutionError("Checkpoint does not match the requested plan")
    if getattr(snapshot, "next", ()):
        return cast(PlanExecutionState, await graph.ainvoke(None, config=config))
    return cast(PlanExecutionState, values)


async def _plan_parameters(run_id: str) -> dict[str, Any] | None:
    return await get_plan_execution(run_id)


async def run_plan_execution(run_id: str, user_id: str, query: str) -> None:
    """Execute a plan graph, persist progress, then stream its typed result."""
    params = await _plan_parameters(run_id)
    if params is None:
        raise PlanExecutionError("Research plan execution metadata is missing")
    if params.get("user_id") != user_id or params.get("query") != query:
        raise PlanExecutionError("Research plan execution metadata mismatch")
    max_sources = min(MAX_PLAN_SOURCES, max(1, int(params.get("max_sources") or 10)))
    max_wall_clock_seconds = min(90, max(1, int(params.get("max_wall_clock_seconds") or 30)))
    deadline_value = params.get("deadline_at")
    if not isinstance(deadline_value, str):
        raise PlanExecutionError("Research plan deadline is missing")
    state: PlanExecutionState = {
        "run_id": run_id,
        "user_id": user_id,
        "query": query,
        "project_id": str(params["project_id"]) if params.get("project_id") else None,
        "source_scope": "project" if params.get("project_id") else "public_corpus",
        "task_type": params["task_type"],
        "max_sources": max_sources,
        "max_tool_calls": min(6, max(1, int(params.get("max_tool_calls") or 6))),
        "max_wall_clock_seconds": max_wall_clock_seconds,
        "max_model_calls": min(2, max(0, int(params.get("max_model_calls") or 0))),
        "max_output_tokens": min(1800, max(0, int(params.get("max_output_tokens") or 0))),
        "synthesis_enabled": bool(params.get("synthesis_enabled")) and get_settings().research_synthesis_enabled,
        "deadline_at": deadline_value,
        "logical_tool_calls": 0,
        "papers": [],
        "sources": [],
        "evidence": [],
        "comparison": [],
        "gaps": [],
        "synthesis": [],
        "steps": [],
    }
    await _check_run_and_deadline(state)
    graph = _get_graph()
    from services.observability import get_langfuse_config

    config = {
        **get_langfuse_config(),
        "configurable": {"thread_id": run_id},
    }
    remaining = max(0.1, (
        datetime.fromisoformat(deadline_value.replace("Z", "+00:00"))
        - datetime.now(timezone.utc)
    ).total_seconds())
    try:
        final = await asyncio.wait_for(
            _invoke_or_resume(graph, state, config),
            timeout=min(max_wall_clock_seconds, remaining),
        )
    except PlanExecutionCancelled:
        raise
    except asyncio.TimeoutError as exc:
        await run_store.add_event(run_id, "error", {"error_code": "plan_timeout", "message": "Research plan exceeded its time limit"})
        await run_store.update(run_id, status="failed")
        raise PlanExecutionError("Research plan exceeded its time limit") from exc
    if not isinstance(final, dict):
        raise PlanExecutionError("Research plan returned no result")

    # A cancellation can race with the final node; never publish a late result.
    await _check_run_and_deadline(state)

    results = ResearchPlanExecutionResult(
        run_id=run_id,
        task_type=final["task_type"],
        source_scope=final["source_scope"],
        steps=[ResearchPlanStepOutcome.model_validate(step) for step in final["steps"]],
        sources=[ResearchPlanSource.model_validate(source) for source in final["sources"]],
        evidence=[ResearchPlanEvidence.model_validate(item) for item in final["evidence"]],
        gaps=list(final["gaps"]),
        comparison=[ComparisonRow.model_validate(row) for row in final["comparison"]],
        synthesis=[SynthesisClaim.model_validate(claim) for claim in final["synthesis"]],
    )
    await run_store.update(run_id, status="complete", results=[results.model_dump()])
    current = await run_store.get(run_id)
    if current is not None and current.status == "complete":
        await run_store.add_event(run_id, "result", results.model_dump())
