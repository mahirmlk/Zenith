"""Paper-to-code endpoints (update.md §11, §15): plan + export only."""
import logging
import re
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import PlainTextResponse

from agents.implementation_planner import make_plan
from agents.implementation_planner import ImplementationPlan
from dependencies import get_current_user
from services.papers_with_code import fetch_paper_repos
from services.sandbox_runner import run_in_sandbox
from services.supabase_client import get_supabase

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/implementations", tags=["implementations"])


@router.get("/{paper_id}/plan")
async def implementation_plan(
    paper_id: str,
    request: Request,
    user: dict[str, Any] = Depends(get_current_user),
    supabase: Any = Depends(get_supabase),
) -> ImplementationPlan:
    try:
        resp = await supabase.table("papers").select("*").eq("id", paper_id).single().execute()
        if not resp.data:
            raise HTTPException(status_code=404, detail="Paper not found")
        repo_result = await fetch_paper_repos(paper_id)
        repos = repo_result.get("repos", [])
        lookup_status: Literal["available", "no_results", "unavailable"] = (
            "unavailable"
            if repo_result.get("source_error")
            else "available"
            if repos
            else "no_results"
        )
        return make_plan(
            resp.data,
            repos if isinstance(repos, list) else [],
            repository_lookup_status=lookup_status,
        )
    except HTTPException:
        raise
    except Exception:
        logger.exception("implementation_plan failed")
        raise HTTPException(status_code=500, detail="Internal error")


def _markdown_text(value: object) -> str:
    """Flatten untrusted paper/repository text and escape Markdown syntax."""
    text = str(value).replace("\r", " ").replace("\n", " ")
    return re.sub(r"([\\`*_{}\[\]()#+.!|>])", r"\\\1", text)


@router.get("/{paper_id}/export")
async def implementation_export(
    paper_id: str,
    request: Request,
    user: dict[str, Any] = Depends(get_current_user),
    supabase: Any = Depends(get_supabase),
) -> PlainTextResponse:
    """Export the plan as Markdown (no code execution)."""
    plan = await implementation_plan(paper_id, request, user, supabase)
    lines = [
        f"# Implementation brief: {_markdown_text(plan.title or plan.paper_id)}",
        "",
        "**Status:** plan generated; execution not attempted.",
        "",
        "## Architecture / method",
        _markdown_text(plan.architecture),
        "",
        "## Evidence extracted from the abstract",
        *(
            [
                f"- **{_markdown_text(fact.category)}:** {_markdown_text(fact.text)} "
                f"(paper `{_markdown_text(fact.evidence.paper_id)}`, abstract characters "
                f"{fact.evidence.start}–{fact.evidence.end})"
                for fact in plan.facts
            ]
            or ["- No supported implementation facts were identified in the abstract."]
        ),
        "",
        "## Dependencies, datasets, metrics, and procedures",
        *[f"- **Dependencies:** {_markdown_text(value)}" for value in plan.dependencies],
        *[f"- **Datasets:** {_markdown_text(value)}" for value in plan.datasets],
        *[f"- **Metrics:** {_markdown_text(value)}" for value in plan.metrics],
        *[f"- **Training:** {_markdown_text(value)}" for value in plan.training_steps],
        *[f"- **Evaluation:** {_markdown_text(value)}" for value in plan.evaluation_steps],
        *[f"- **Compute:** {_markdown_text(value)}" for value in plan.compute_requirements],
        "",
        "## Candidate repositories",
        *(
            [
                f"- `{_markdown_text(repo['url'])}` — unverified association; "
                f"{repo['stars']} reported stars; source: {_markdown_text(repo['source'])}."
                for repo in plan.candidate_repos
            ]
            or [f"- Lookup status: {_markdown_text(plan.repository_lookup_status)}; no candidate is verified."]
        ),
        "",
        "## Suggested project structure",
        *[f"- `{_markdown_text(path)}`" for path in plan.suggested_structure],
        "",
        "## Implementation checklist",
        *[f"- [ ] {_markdown_text(item)}" for item in plan.checklist],
        "",
        "## Compatibility notes",
        *[f"- {_markdown_text(item)}" for item in plan.compatibility_notes],
        "",
        "## Model / data card (partial)",
        f"- Model or method: {_markdown_text(plan.model_data_card.model_or_method or 'Not identified')}",
        f"- Dataset license: {_markdown_text(plan.model_data_card.dataset_license or 'Not verified')}",
        f"- Intended use: {_markdown_text(plan.model_data_card.intended_use or 'Not assessed')}",
        "",
        "## Reproducibility gaps",
        *[f"- {_markdown_text(gap)}" for gap in plan.reproducibility_gaps],
        "",
        "No code was generated, cloned, executed, or tested by this brief.",
    ]
    return PlainTextResponse("\n".join(lines), media_type="text/markdown")


@router.post("/{paper_id}/run")
async def implementation_run(
    paper_id: str,
    request: Request,
    user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, str]:
    """Always refuses until a reviewed sandbox exists (update.md §11)."""
    return run_in_sandbox(paper_id=paper_id)
