"""Project-scoped research endpoints (update.md §§8–9, 15).

Answer and evidence-map routes remain extractive. A separate provisional
synthesis route is feature-gated and returns model-reviewed source relations.
"""
import logging
import re
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from agents.research_types import (
    EvidenceItem,
    EvidenceMapResponse,
    PdfEvidenceItem,
    ResearchCapabilities,
    ResearchPlan,
    ResearchPlanScope,
    ResearchComparisonResponse,
    ResearchSynthesisResponse,
    SynthesisEvidenceItem,
    ResearchAnswer,
    build_comparison,
)
from dependencies import get_current_user
from config import get_settings
from security.authorization import can_access_project
from security.output_validation import validate_citations
from services.retrieval import hybrid_rank, query_entities, query_terms
from services.supabase_client import get_supabase
from services.synthesis import SynthesisOutputError, SynthesisProviderError, synthesize_claims
from services.research_planner import build_research_plan
from security.prompt_injection import scan_untrusted

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/research", tags=["research"])
MAX_DAILY_SYNTHESIS_REQUESTS = 10


@router.get("/capabilities", response_model=ResearchCapabilities)
async def research_capabilities(
    request: Request,
    user: dict[str, Any] = Depends(get_current_user),
) -> ResearchCapabilities:
    """Return enabled research modes without exposing backend configuration."""
    del request
    del user
    return ResearchCapabilities(
        research_synthesis_enabled=get_settings().research_synthesis_enabled
    )


async def _require_project_access(
    project_id: str,
    user: dict[str, Any],
    supabase: Any,
) -> dict[str, Any]:
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
        raise HTTPException(status_code=404, detail="Project not found")

    member_result = await (
        supabase.table("project_members")
        .select("user_id,role")
        .eq("project_id", project_id)
        .execute()
    )
    member_roles = {
        row["user_id"]: row["role"]
        for row in (member_result.data or [])
        if row.get("user_id") and row.get("role")
    }
    if not can_access_project(project.get("owner_id", ""), member_roles, user["user_id"]):
        raise HTTPException(status_code=404, detail="Project not found")
    return project

class ResearchRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=500)
    project_id: str | None = None


class ProjectEvidenceMapRequest(ResearchRequest):
    project_id: str = Field(..., min_length=1, max_length=128)


@router.post("/plan", response_model=ResearchPlan)
async def research_plan(
    body: ResearchRequest,
    request: Request,
    user: dict[str, Any] = Depends(get_current_user),
    supabase: Any = Depends(get_supabase),
) -> ResearchPlan:
    try:
        source_scope: ResearchPlanScope = "public_corpus"
        if body.project_id:
            await _require_project_access(body.project_id, user, supabase)
            source_scope = "project"
        return build_research_plan(
            body.query,
            source_scope=source_scope,
            synthesis_enabled=get_settings().research_synthesis_enabled,
        )
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("research_plan failed")
        raise HTTPException(status_code=500, detail="Research plan unavailable") from exc


def _paper_rows(data: object) -> list[dict[str, Any]]:
    """Narrow the untyped PostgREST response to usable object rows."""
    if not isinstance(data, list):
        return []
    return [
        {key: value for key, value in row.items()}
        for row in data
        if isinstance(row, dict) and all(isinstance(key, str) for key in row)
    ]


async def _papers_for_request(
    body: ResearchRequest,
    user: dict[str, Any],
    supabase: Any,
) -> list[dict[str, Any]]:
    """Load a bounded public corpus or only papers attached to an accessible project."""
    query = supabase.table("papers").select("id,title,abstract")
    if body.project_id:
        await _require_project_access(body.project_id, user, supabase)
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
        return _paper_rows(papers_result.data)

    papers_result = await (
        query.order("published_at", desc=True).range(0, 49).execute()
    )
    return _paper_rows(papers_result.data)


def _extractive_claims(
    query: str,
    ranked_papers: list[dict[str, Any]],
    limit: int = 3,
) -> list[str]:
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


def _extractive_evidence_items(
    query: str,
    ranked_papers: list[dict[str, Any]],
    limit: int = 5,
) -> list[EvidenceItem]:
    """Select at most `limit` exact abstract sentences with verifiable offsets."""
    terms = query_terms(query)
    if not terms or limit <= 0:
        return []

    entities = query_entities(query)
    candidates: list[tuple[int, float, EvidenceItem]] = []
    sentence_pattern = re.compile(r"\S.*?(?:[.!?](?=\s|$)|$)", re.DOTALL)

    for paper in ranked_papers[:10]:
        paper_id = str(paper.get("id") or "")
        title = paper.get("title") or ""
        abstract = paper.get("abstract") or ""
        if not paper_id or not isinstance(title, str) or not isinstance(abstract, str):
            continue

        document_terms = query_terms(f"{title} {abstract}")
        if entities and not entities.intersection(document_terms):
            continue

        raw_score = paper.get("score")
        try:
            score = float(raw_score or 0)
        except (TypeError, ValueError):
            score = 0.0

        for match in sentence_pattern.finditer(abstract):
            sentence = match.group(0)
            if scan_untrusted(sentence):
                continue
            overlap = len(terms.intersection(query_terms(sentence)))
            if not overlap or overlap / len(terms) < 0.34:
                continue

            start, end = match.span()
            # Keep the span tied to the exact persisted abstract string.
            if abstract[start:end] != sentence:
                continue
            candidates.append(
                (
                    overlap,
                    score,
                    EvidenceItem(
                        paper_id=paper_id,
                        title=title,
                        sentence=sentence,
                        start_offset=start,
                        end_offset=end,
                    ),
                )
            )

    candidates.sort(key=lambda item: (item[0], item[1]), reverse=True)
    evidence: list[EvidenceItem] = []
    seen: set[tuple[str, int, int]] = set()
    for _, _, item in candidates:
        key = (item.paper_id, item.start_offset, item.end_offset)
        if key in seen:
            continue
        seen.add(key)
        evidence.append(item)
        if len(evidence) >= limit:
            break
    return evidence


def _extractive_pdf_evidence(
    query: str,
    documents: list[dict[str, Any]],
    pages: list[dict[str, Any]],
    limit: int = 5,
) -> list[PdfEvidenceItem]:
    """Select exact matching PDF page sentences and retain page-local offsets."""
    terms = query_terms(query)
    if not terms or limit <= 0:
        return []
    document_by_id = {
        str(document.get("id")): document
        for document in documents
        if document.get("id")
    }
    entities = query_entities(query)
    candidates: list[tuple[int, PdfEvidenceItem]] = []
    sentence_pattern = re.compile(r"\S.*?(?:[.!?](?=\s|$)|$)", re.DOTALL)
    for page in pages:
        document_id = str(page.get("document_id") or "")
        document = document_by_id.get(document_id)
        text = page.get("text")
        page_number = page.get("page_number")
        if (
            not document
            or not isinstance(text, str)
            or not isinstance(page_number, int)
            or page_number < 1
        ):
            continue
        if entities and not entities.intersection(query_terms(text)):
            continue
        for match in sentence_pattern.finditer(text):
            sentence = match.group(0)
            if scan_untrusted(sentence):
                continue
            overlap = len(terms.intersection(query_terms(sentence)))
            if not overlap or overlap / len(terms) < 0.34:
                continue
            start, end = match.span()
            if text[start:end] != sentence:
                continue
            candidates.append((
                overlap,
                PdfEvidenceItem(
                    document_id=document_id,
                    filename=str(document.get("filename") or "document.pdf"),
                    page_number=page_number,
                    citation_id=f"{document_id}:page:{page_number}",
                    sentence=sentence,
                    start_offset=start,
                    end_offset=end,
                ),
            ))

    candidates.sort(key=lambda item: item[0], reverse=True)
    selected: list[PdfEvidenceItem] = []
    seen: set[tuple[str, int, int, int]] = set()
    for _, item in candidates:
        key = (item.document_id, item.page_number, item.start_offset, item.end_offset)
        if key in seen:
            continue
        seen.add(key)
        selected.append(item)
        if len(selected) >= limit:
            break
    return selected


async def _project_pdf_evidence(
    query: str,
    project_id: str,
    supabase: Any,
    limit: int = 5,
) -> list[PdfEvidenceItem]:
    """Load bounded extracted pages for an already-authorized project request."""
    documents_result = await (
        supabase.table("project_documents")
        .select("id,filename,page_count")
        .eq("project_id", project_id)
        .order("created_at", desc=True)
        .range(0, 9)
        .execute()
    )
    documents = [
        row for row in (documents_result.data or [])
        if isinstance(row, dict) and row.get("id")
    ]
    document_ids = [str(row["id"]) for row in documents]
    if not document_ids:
        return []

    pages_result = await (
        supabase.table("project_document_pages")
        .select("document_id,page_number,text")
        .in_("document_id", document_ids)
        .range(0, 499)
        .execute()
    )
    pages = [row for row in (pages_result.data or []) if isinstance(row, dict)]
    return _extractive_pdf_evidence(query, documents, pages, limit=limit)


@router.post("/evidence-map", response_model=EvidenceMapResponse)
async def research_evidence_map(
    body: ProjectEvidenceMapRequest,
    request: Request,
    user: dict[str, Any] = Depends(get_current_user),
    supabase: Any = Depends(get_supabase),
) -> EvidenceMapResponse:
    """Return bounded verbatim evidence from papers attached to an accessible project."""
    try:
        papers = await _papers_for_request(body, user, supabase)
        ranked = hybrid_rank(body.query, papers)[:10]
        abstract_evidence = _extractive_evidence_items(body.query, ranked, limit=5)
        documents_result = await (
            supabase.table("project_documents")
            .select("id,filename,page_count")
            .eq("project_id", body.project_id)
            .order("created_at", desc=True)
            .range(0, 9)
            .execute()
        )
        documents = [
            row for row in (documents_result.data or [])
            if isinstance(row, dict) and row.get("id")
        ]
        document_ids = [str(row["id"]) for row in documents]
        pages: list[dict[str, Any]] = []
        if document_ids:
            pages_result = await (
                supabase.table("project_document_pages")
                .select("document_id,page_number,text")
                .in_("document_id", document_ids)
                .range(0, 499)
                .execute()
            )
            pages = [row for row in (pages_result.data or []) if isinstance(row, dict)]

        pdf_candidates = _extractive_pdf_evidence(body.query, documents, pages, limit=5)
        if pdf_candidates and abstract_evidence:
            # Keep both source types visible while respecting the shared five-span cap.
            abstract_count = min(2, len(abstract_evidence))
            pdf_count = min(5 - abstract_count, len(pdf_candidates))
            abstract_count = min(5 - pdf_count, len(abstract_evidence))
        else:
            pdf_count = min(5, len(pdf_candidates))
            abstract_count = min(5 - pdf_count, len(abstract_evidence))
        pdf_evidence = pdf_candidates[:pdf_count]
        evidence = abstract_evidence[:abstract_count]

        pdf_source_ids = list(dict.fromkeys(item.document_id for item in pdf_evidence))
        evidence_paper_ids = list(dict.fromkeys(
            item.paper_id for item in evidence
        ))
        ranked_paper_ids = list(dict.fromkeys(
            str(paper["id"]) for paper in ranked if paper.get("id")
        ))
        paper_source_ids = list(dict.fromkeys(evidence_paper_ids + ranked_paper_ids))
        source_ids = (pdf_source_ids + paper_source_ids)[:10]
        # Verify both source membership and exact source span before returning it.
        paper_by_id = {str(paper["id"]): paper for paper in ranked if paper.get("id")}
        verified: list[EvidenceItem] = []
        for item in evidence:
            paper = paper_by_id.get(item.paper_id)
            abstract = paper.get("abstract") if paper else None
            if (
                isinstance(abstract, str)
                and 0 <= item.start_offset < item.end_offset <= len(abstract)
                and abstract[item.start_offset:item.end_offset] == item.sentence
            ):
                verified.append(item)

        verified_pdf: list[PdfEvidenceItem] = []
        page_by_key = {
            (str(page.get("document_id") or ""), page.get("page_number")): page
            for page in pages
        }
        for pdf_item in pdf_evidence:
            page = page_by_key.get((pdf_item.document_id, pdf_item.page_number))
            text = page.get("text") if page else None
            if (
                isinstance(text, str)
                and 0 <= pdf_item.start_offset < pdf_item.end_offset <= len(text)
                and text[pdf_item.start_offset:pdf_item.end_offset] == pdf_item.sentence
                and pdf_item.document_id in pdf_source_ids
            ):
                verified_pdf.append(pdf_item)

        return EvidenceMapResponse(
            query=body.query,
            project_id=body.project_id,
            evidence=verified,
            pdf_evidence=verified_pdf,
            source_ids=source_ids,
            abstained=not verified and not verified_pdf,
            explanation=(
                "Evidence consists of exact sentences from attached paper abstracts and/or extracted PDF pages; "
                "no cross-source synthesis was generated."
                if verified or verified_pdf
                else "No matching, non-instruction-like abstract or PDF page evidence was found in this project."
            ),
        )
    except HTTPException:
        raise
    except Exception:
        logger.exception("research_evidence_map failed")
        raise HTTPException(status_code=500, detail="Internal error")


@router.post("/compare", response_model=ResearchComparisonResponse)
async def research_compare(
    body: ResearchRequest,
    request: Request,
    user: dict[str, Any] = Depends(get_current_user),
    supabase: Any = Depends(get_supabase),
) -> ResearchComparisonResponse:
    try:
        papers = await _papers_for_request(body, user, supabase)
        ranked = hybrid_rank(body.query, papers)[:10]
        pdf_evidence = (
            await _project_pdf_evidence(body.query, body.project_id, supabase, limit=5)
            if body.project_id
            else []
        )
        return ResearchComparisonResponse(
            rows=build_comparison(ranked),
            pdf_evidence=pdf_evidence,
        )
    except HTTPException:
        raise
    except Exception:
        logger.exception("research_compare failed")
        raise HTTPException(status_code=500, detail="Internal error")


@router.post("/answer", response_model=ResearchAnswer)
async def research_answer(
    body: ResearchRequest,
    request: Request,
    user: dict[str, Any] = Depends(get_current_user),
    supabase: Any = Depends(get_supabase),
) -> ResearchAnswer:
    """Return only extractive, cited evidence; abstain when support is absent."""
    try:
        papers = await _papers_for_request(body, user, supabase)
        ranked = hybrid_rank(body.query, papers)[:5]
        abstract_claims = _extractive_claims(body.query, ranked)
        retrieved_ids = {str(paper["id"]) for paper in ranked if paper.get("id")}
        fabricated = validate_citations(" ".join(abstract_claims), retrieved_ids)
        if fabricated:
            logger.error("Extractive answer citation validation failed: %s", fabricated)
            abstract_claims = []

        pdf_candidates = (
            await _project_pdf_evidence(body.query, body.project_id, supabase, limit=5)
            if body.project_id
            else []
        )
        if abstract_claims and pdf_candidates:
            abstract_count = min(2, len(abstract_claims))
            pdf_count = min(5 - abstract_count, len(pdf_candidates))
            abstract_count = min(5 - pdf_count, len(abstract_claims))
        else:
            pdf_count = min(5, len(pdf_candidates))
            abstract_count = min(5 - pdf_count, len(abstract_claims))
        selected_abstract_claims = abstract_claims[:abstract_count]
        selected_pdf = pdf_candidates[:pdf_count]
        # The selector checks exact page-local offsets before constructing each item.
        # Five abstract ranks plus at most five PDF source IDs stay within ten sources.
        verified_pdf = selected_pdf

        pdf_claims = [f"{item.sentence} [{item.citation_id}]" for item in verified_pdf]
        claims = selected_abstract_claims + pdf_claims

        if not claims:
            return ResearchAnswer(
                summary=(
                    "No abstract or project PDF evidence matched this question. Try a more specific query or add relevant sources."
                    if body.project_id
                    else "No abstract evidence matched this question. Try a more specific query or add relevant papers to the project."
                ),
                abstained=True,
                confidence_explanation=(
                    "Abstained: no retrieved abstract or project PDF sentence shared a substantive query term."
                    if body.project_id
                    else "Abstained: no retrieved abstract sentence shared a substantive query term."
                ),
            )

        citations = list(dict.fromkeys(
            match.group(1) for claim in claims
            if (match := re.search(r"\[([A-Za-z0-9_\-:.]+)\]$", claim))
        ))
        return ResearchAnswer(
            summary=(
                "Extractive evidence from retrieved paper abstracts and project PDF pages; this is not a synthesized conclusion."
                if verified_pdf
                else "Extractive evidence from retrieved paper abstracts; this is not a synthesized conclusion."
            ),
            claims=claims,
            citation_ids=citations,
            pdf_evidence=verified_pdf,
            abstained=False,
            confidence_explanation=(
                "Claims are verbatim abstract sentences or project PDF page spans selected by keyword overlap; support has not been independently verified."
                if verified_pdf
                else "Claims are verbatim abstract sentences selected by keyword overlap; support has not been independently verified."
            ),
        )
    except HTTPException:
        raise
    except Exception:
        logger.exception("research_answer failed")
        raise HTTPException(status_code=500, detail="Internal error")


@router.post("/synthesize", response_model=ResearchSynthesisResponse)
async def research_synthesize(
    body: ResearchRequest,
    request: Request,
    user: dict[str, Any] = Depends(get_current_user),
    supabase: Any = Depends(get_supabase),
) -> ResearchSynthesisResponse:
    """Return bounded, model-reviewed claims over public paper abstract spans.

    Project authorization happens in `_papers_for_request` before retrieval.
    Private project PDF text is deliberately excluded from provider input.
    """
    try:
        if not get_settings().research_synthesis_enabled:
            raise HTTPException(status_code=404, detail="Not found")
        papers = await _papers_for_request(body, user, supabase)
        ranked = hybrid_rank(body.query, papers)[:10]
        evidence: list[SynthesisEvidenceItem] = []
        for paper in ranked:
            candidate = _extractive_evidence_items(body.query, [paper], limit=1)
            if not candidate:
                continue
            item = candidate[0]
            abstract = paper.get("abstract")
            if (
                not isinstance(abstract, str)
                or item.start_offset < 0
                or item.end_offset > len(abstract)
                or abstract[item.start_offset:item.end_offset] != item.sentence
            ):
                continue
            evidence.append(
                SynthesisEvidenceItem(
                    evidence_id=f"E{len(evidence) + 1}",
                    paper_id=item.paper_id,
                    title=item.title,
                    sentence=item.sentence,
                    start_offset=item.start_offset,
                    end_offset=item.end_offset,
                )
            )
            if len(evidence) >= 6:
                break

        if len({item.paper_id for item in evidence}) < 2:
            return ResearchSynthesisResponse(
                query=body.query,
                evidence=evidence,
                abstained=True,
                explanation="Cross-paper synthesis needs matching evidence from at least two papers.",
            )

        from services import budget

        try:
            within_budget = await budget.consume(
                user["user_id"], MAX_DAILY_SYNTHESIS_REQUESTS, namespace="synthesis"
            )
        except budget.BudgetUnavailableError as exc:
            raise HTTPException(status_code=503, detail="Research synthesis temporarily unavailable") from exc
        if not within_budget:
            raise HTTPException(status_code=429, detail="Daily synthesis limit reached")

        claims = await synthesize_claims(body.query, evidence)
        return ResearchSynthesisResponse(
            query=body.query,
            claims=claims,
            evidence=evidence,
            abstained=not claims,
            explanation=(
                "Claims were generated from public abstract sentences and separately model-reviewed for support and conflict. This is not independent scientific verification."
                if claims
                else "No cross-paper claim passed the bounded evidence and review steps."
            ),
        )
    except HTTPException:
        raise
    except SynthesisProviderError as exc:
        logger.warning("research_synthesis provider unavailable")
        raise HTTPException(status_code=503, detail="Research synthesis temporarily unavailable") from exc
    except SynthesisOutputError as exc:
        logger.warning("research_synthesis response failed validation")
        raise HTTPException(status_code=502, detail="Research synthesis could not be validated") from exc
    except Exception:
        logger.exception("research_synthesis failed")
        raise HTTPException(status_code=500, detail="Internal error")
