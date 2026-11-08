"""Typed intermediate outputs for deep research (update.md §9.1)."""
from typing import Any, Literal

from pydantic import BaseModel, Field


class ResearchPlan(BaseModel):
    query: str
    task_type: Literal["feed", "explain", "compare", "deep_research"] = "feed"
    max_tool_calls: int = Field(default=10, ge=1, le=50)
    max_sources: int = Field(default=10, ge=1, le=50)


class SourceCandidate(BaseModel):
    paper_id: str
    title: str = ""
    score: float = 0.0


class ComparisonRow(BaseModel):
    paper_id: str
    problem: str = ""
    methods: str = ""
    datasets: str = ""
    metrics: str = ""
    limitations: str = ""
    code_status: str = "unverified"


class ResearchAnswer(BaseModel):
    summary: str
    claims: list[str] = Field(default_factory=list)
    citation_ids: list[str] = Field(default_factory=list)
    abstained: bool = False
    confidence_explanation: str = ""


def classify_task(query: str) -> ResearchPlan:
    """Deterministic routing (update.md §9.1): planner only for complex tasks."""
    q = (query or "").lower()
    task: Literal["feed", "explain", "compare", "deep_research"]
    if any(w in q for w in ("compare", "comparison", "vs", "versus", "difference between")):
        task = "compare"
    elif any(w in q for w in ("explain", "what is", "how does", "summarize", "summarise")):
        task = "explain"
    elif any(w in q for w in ("deep", "survey", "literature", "state of the art", "sota")):
        task = "deep_research"
    else:
        task = "feed"
    return ResearchPlan(query=query, task_type=task)


def build_comparison(papers: list[dict[str, Any]]) -> list[ComparisonRow]:
    """Structured cross-paper table rows (deterministic extraction from metadata)."""
    rows = []
    for p in papers:
        rows.append(
            ComparisonRow(
                paper_id=p.get("id", ""),
                problem=(p.get("abstract") or "")[:200],
                methods=p.get("summary_tldr") or "",
                datasets="",
                metrics="",
                limitations="",
                code_status="unverified",
            )
        )
    return rows
