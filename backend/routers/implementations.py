"""Paper-to-code endpoints (update.md §11, §15): plan + export only."""
import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import PlainTextResponse

from agents.implementation_planner import make_plan
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
) -> Any:
    try:
        resp = await supabase.table("papers").select("*").eq("id", paper_id).single().execute()
        if not resp.data:
            raise HTTPException(status_code=404, detail="Paper not found")
        repos = await fetch_paper_repos(paper_id)
        return make_plan(resp.data, repos.get("repos", []))
    except HTTPException:
        raise
    except Exception:
        logger.exception("implementation_plan failed")
        raise HTTPException(status_code=500, detail="Internal error")


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
        f"# Implementation plan: {paper_id}",
        "",
        plan.architecture,
        "",
        "## Checklist",
        *[f"- [ ] {item}" for item in plan.checklist],
        "",
        "## Reproducibility gaps",
        *[f"- {g}" for g in plan.reproducibility_gaps],
        "",
        f"Status: {plan.status} (repos unverified: {len(plan.candidate_repos)})",
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
