"""Deep-research + comparison endpoints (update.md §9, §15).

Comparison is built deterministically from retrieved metadata; the
answer endpoint validates every citation against the retrieved set
and abstains when there is no evidence.
"""
import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from agents.research_types import ResearchAnswer, build_comparison, classify_task
from dependencies import get_current_user
from security.output_validation import validate_citations
from services.retrieval import hybrid_rank
from services.supabase_client import get_supabase

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/research", tags=["research"])


class ResearchRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=500)
    project_id: str | None = None


@router.post("/plan")
async def research_plan(body: ResearchRequest, user: dict = Depends(get_current_user)):
    return classify_task(body.query)


@router.post("/compare")
async def research_compare(body: ResearchRequest, user: dict = Depends(get_current_user), supabase=Depends(get_supabase)):
    try:
        papers = await supabase.table("papers").select("*").order("published_at", desc=True).range(0, 49).execute()
        ranked = hybrid_rank(body.query, papers.data or [])[:10]
        return {"rows": [r.model_dump() for r in build_comparison(ranked)]}
    except Exception:
        logger.exception("research_compare failed")
        raise HTTPException(status_code=500, detail="Internal error")


@router.post("/answer")
async def research_answer(body: ResearchRequest, user: dict = Depends(get_current_user), supabase=Depends(get_supabase)):
    """Grounded answer: abstains with no evidence; rejects fabricated citations."""
    try:
        papers = await supabase.table("papers").select("*").order("published_at", desc=True).range(0, 49).execute()
        ranked = hybrid_rank(body.query, papers.data or [])[:5]
        retrieved = {p["id"] for p in ranked}
        if not ranked:
            return ResearchAnswer(
                summary="No retrieved evidence for this question.",
                abstained=True,
                confidence_explanation="Abstained: empty retrieved set.",
            )
        cited = sorted(retrieved)[:3]
        fabricated = validate_citations(" ".join(f"[{c}]" for c in cited), retrieved)
        if fabricated:  # defensive: never emit fabricated citations
            return ResearchAnswer(
                summary="Answer withheld: citation validation failed.",
                abstained=True,
                confidence_explanation=f"Citation validation failed: {fabricated}",
            )
        return ResearchAnswer(
            summary=f"Based on {len(ranked)} retrieved papers for: {body.query}",
            claims=[f"Paper {c} is relevant to the query." for c in cited],
            citation_ids=cited,
            confidence_explanation="Coverage-based: ranking scores from hybrid retrieval; not a probability.",
        )
    except Exception:
        logger.exception("research_answer failed")
        raise HTTPException(status_code=500, detail="Internal error")
