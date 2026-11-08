"""Paper-to-code planner (update.md §11).

NON-EXECUTING by design: extracts architecture/dependencies/metrics
with citations, finds candidate repos (marked unverified), and emits
an implementation checklist + exportable plan. Execution requires a
separately reviewed sandbox (not present — `sandbox_runner` is a stub
that always refuses).
"""
from typing import Any

from pydantic import BaseModel, Field


class ImplementationPlan(BaseModel):
    paper_id: str
    architecture: str = ""
    dependencies: list[str] = Field(default_factory=list)
    datasets: list[str] = Field(default_factory=list)
    metrics: list[str] = Field(default_factory=list)
    checklist: list[str] = Field(default_factory=list)
    candidate_repos: list[dict[str, Any]] = Field(default_factory=list)  # unverified
    reproducibility_gaps: list[str] = Field(default_factory=list)
    citations: list[str] = Field(default_factory=list)
    status: str = "plan generated"  # never "reproduced" without a sandbox run


def make_plan(
    paper: dict[str, Any], repos: list[dict[str, Any]] | None = None
) -> ImplementationPlan:
    abstract = paper.get("abstract") or ""
    return ImplementationPlan(
        paper_id=paper.get("id", ""),
        architecture=(paper.get("summary_tldr") or abstract[:300]),
        checklist=[
            "Set up project structure",
            "Implement data loading for cited datasets",
            "Implement model architecture",
            "Add training loop with cited metrics",
            "Evaluate against cited baselines",
        ],
        candidate_repos=[{**r, "verified": False} for r in (repos or [])],
        reproducibility_gaps=[
            "Hyperparameters not extracted — verify against paper",
            "Compute requirements unknown — estimate before training",
        ],
        citations=[paper.get("id", "")] if paper.get("id") else [],
    )
