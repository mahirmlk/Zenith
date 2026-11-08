"""Project-scoped research endpoints (update.md §§8–9, 15).

Answers are intentionally extractive until a real synthesis pipeline and
evaluation gate are available: every returned claim is a sentence copied
from a retrieved abstract and carries that paper's ID citation.
"""
import logging
import re

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from agents.research_types import ResearchAnswer, build_comparison, classify_task
from dependencies import get_current_user
from security.authorization import can_access_project
from security.output_validation import validate_citations
from services.retrieval import hybrid_rank, query_entities, query_terms
from services.supabase_client import get_supabase
from security.prompt_injection import scan_untrusted

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/research", tags=["research"])

class ResearchRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=500)
    project_id: str | None = None


@router.post("/plan")
async def research_plan(body: ResearchRequest, request: Request, user: dict = Depends(get_current_user)):
    return classify_task(body.query)


async def _papers_for_request(body: ResearchRequest, user: dict, supabase) -> list[dict]:
    """Load a bounded public corpus or only papers attached to an accessible project."""
    query = supabase.table("papers").select("*")
    if body.project_id:
        project_result = await (
            supabase.table("projects")
            .select("owner_id")
            .eq("id", body.project_id)
            .maybe_single()
            .execute()
        )
        project = project_result.data
        if not project:
            raise HTTPException(status_code=404, detail="Project not found")

        member_result = await (
            supabase.table("project_members")
            .select("user_id,role")
            .eq("project_id", body.project_id)
            .execute()
        )
        member_roles = {
            row["user_id"]: row["role"]
            for row in (member_result.data or [])
            if row.get("user_id") and row.get("role")
        }
        if not can_access_project(project.get("owner_id", ""), member_roles, user["user_id"]):
            # Do not disclose whether another user's project exists.
            raise HTTPException(status_code=404, detail="Project not found")

        source_result = await (
            supabase.table("project_sources")
            .select("paper_id")
            .eq("project_id", body.project_id)
            .range(0, 199)
            .execute()
        )
        paper_ids = list(dict.fromkeys(
            row["paper_id"] for row in (source_result.data or []) if row.get("paper_id")
        ))
        if not paper_ids:
            return []
        papers_result = await query.in_("id", paper_ids).execute()
        return papers_result.data or []

    papers_result = await (
        query.order("published_at", desc=True).range(0, 49).execute()
    )
    return papers_result.data or []


def _extractive_claims(query: str, ranked_papers: list[dict], limit: int = 3) -> list[str]:
    """Pick exact abstract sentences with at least one substantive query term."""
    terms = query_terms(query)
    if not terms:
        return []

    candidates: list[tuple[int, float, str, str]] = []
    entities = query_entities(query)
    for paper in ranked_papers:
        paper_id = str(paper.get("id") or "")
        abstract = paper.get("abstract") or ""
        if not paper_id or not isinstance(abstract, str):
            continue
        document_terms = query_terms(f"{paper.get('title') or ''} {abstract}")
        if entities and not entities.intersection(document_terms):
            continue
        for sentence in re.split(r"(?<=[.!?])\s+", abstract.strip()):
            sentence = sentence.strip()
            if not sentence:
                continue
            if scan_untrusted(sentence):
                continue
            overlap = len(terms.intersection(query_terms(sentence)))
            coverage = overlap / len(terms)
            if overlap and coverage >= 0.34:
                candidates.append((overlap, float(paper.get("score") or 0), paper_id, sentence))

    candidates.sort(key=lambda item: (item[0], item[1]), reverse=True)
    claims: list[str] = []
    seen: set[tuple[str, str]] = set()
    for _, _, paper_id, sentence in candidates:
        key = (paper_id, sentence)
        if key in seen:
            continue
        seen.add(key)
        claims.append(f"{sentence} [{paper_id}]")
        if len(claims) >= limit:
            break
    return claims


@router.post("/compare")
async def research_compare(
    body: ResearchRequest,
    request: Request,
    user: dict = Depends(get_current_user),
    supabase=Depends(get_supabase),
):
    try:
        papers = await _papers_for_request(body, user, supabase)
        ranked = hybrid_rank(body.query, papers)[:10]
        return {"rows": [row.model_dump() for row in build_comparison(ranked)]}
    except HTTPException:
        raise
    except Exception:
        logger.exception("research_compare failed")
        raise HTTPException(status_code=500, detail="Internal error")


@router.post("/answer", response_model=ResearchAnswer)
async def research_answer(
    body: ResearchRequest,
    request: Request,
    user: dict = Depends(get_current_user),
    supabase=Depends(get_supabase),
) -> ResearchAnswer:
    """Return only extractive, cited evidence; abstain when support is absent."""
    try:
        papers = await _papers_for_request(body, user, supabase)
        ranked = hybrid_rank(body.query, papers)[:5]
        claims = _extractive_claims(body.query, ranked)
        retrieved_ids = {str(paper["id"]) for paper in ranked if paper.get("id")}
        fabricated = validate_citations(" ".join(claims), retrieved_ids)
        if fabricated:
            logger.error("Extractive answer citation validation failed: %s", fabricated)
            claims = []

        if not claims:
            return ResearchAnswer(
                summary="No abstract evidence matched this question. Try a more specific query or add relevant papers to the project.",
                abstained=True,
                confidence_explanation="Abstained: no retrieved abstract sentence shared a substantive query term.",
            )

        citations = list(dict.fromkeys(
            match.group(1) for claim in claims
            if (match := re.search(r"\[([A-Za-z0-9_\-:.]+)\]$", claim))
        ))
        return ResearchAnswer(
            summary="Extractive evidence from retrieved paper abstracts; this is not a synthesized conclusion.",
            claims=claims,
            citation_ids=citations,
            abstained=False,
            confidence_explanation="Claims are verbatim abstract sentences selected by keyword overlap; support has not been independently verified.",
        )
    except HTTPException:
        raise
    except Exception:
        logger.exception("research_answer failed")
        raise HTTPException(status_code=500, detail="Internal error")
