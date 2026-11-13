"""Typed intermediate outputs for deep research (update.md §9.1)."""
import re
from typing import Any, Literal

from pydantic import BaseModel, Field

ResearchPlanStepId = Literal[
    "retrieve_sources",
    "extract_evidence",
    "compare_sources",
    "identify_gaps",
    "draft_synthesis",
    "review_claims",
    "synthesis_unavailable",
]
ResearchPlanScope = Literal["public_corpus", "project"]


class ResearchPlanStep(BaseModel):
    step_id: ResearchPlanStepId
    title: str
    description: str
    execution_state: Literal["proposed"] = "proposed"


class ResearchPlan(BaseModel):
    query: str
    task_type: Literal["feed", "explain", "compare", "deep_research"] = "feed"
    max_tool_calls: int = Field(default=10, ge=1, le=50)
    max_sources: int = Field(default=10, ge=1, le=50)
    source_scope: ResearchPlanScope = "public_corpus"
    steps: list[ResearchPlanStep] = Field(default_factory=list)
    max_depth: int = Field(default=1, ge=0, le=2)
    max_wall_clock_seconds: int = Field(default=30, ge=1, le=90)
    max_model_calls: int = Field(default=0, ge=0, le=2)
    max_output_tokens: int = Field(default=0, ge=0, le=1800)
    synthesis_available: bool = False
    estimated_cost_usd: None = None
    cost_tracking_available: bool = False
    execution_available: bool = False
    limits_are_preview_only: bool = True


class SourceCandidate(BaseModel):
    paper_id: str
    title: str = ""
    score: float = 0.0


class EvidenceItem(BaseModel):
    """A verbatim abstract sentence with offsets into the exact source text."""

    paper_id: str
    title: str = ""
    sentence: str
    start_offset: int = Field(ge=0)
    end_offset: int = Field(gt=0)


class PdfEvidenceItem(BaseModel):
    """An exact sentence span on a page extracted from a project PDF."""

    document_id: str
    filename: str
    page_number: int = Field(ge=1)
    citation_id: str
    sentence: str
    start_offset: int = Field(ge=0)
    end_offset: int = Field(gt=0)


class EvidenceMapResponse(BaseModel):
    """Bounded, project-scoped evidence; this response contains no synthesis."""

    query: str
    project_id: str
    evidence: list[EvidenceItem] = Field(default_factory=list)
    pdf_evidence: list[PdfEvidenceItem] = Field(default_factory=list)
    source_ids: list[str] = Field(default_factory=list)
    abstained: bool = False
    explanation: str = ""


class ComparisonRow(BaseModel):
    paper_id: str
    problem: str | None = None
    methods: str | None = None
    datasets: str | None = None
    metrics: str | None = None
    limitations: str | None = None
    code_status: str = "unverified"


class ResearchComparisonResponse(BaseModel):
    """Heuristic abstract comparison plus separately cited project PDF spans."""

    rows: list[ComparisonRow] = Field(default_factory=list)
    pdf_evidence: list[PdfEvidenceItem] = Field(default_factory=list)


class SynthesisEvidenceItem(BaseModel):
    """A sentence selected from a public paper abstract with exact offsets."""

    evidence_id: str
    paper_id: str
    title: str = ""
    sentence: str
    start_offset: int = Field(ge=0)
    end_offset: int = Field(gt=0)


class SynthesisClaim(BaseModel):
    """A generated cross-paper claim with model-assessed evidence relations."""

    text: str
    status: Literal["supported", "conflicting", "uncertain"]
    supporting_evidence_ids: list[str] = Field(default_factory=list)
    contradicting_evidence_ids: list[str] = Field(default_factory=list)
    cited_evidence_ids: list[str] = Field(default_factory=list)
    explanation: str = ""


class ResearchSynthesisResponse(BaseModel):
    query: str
    claims: list[SynthesisClaim] = Field(default_factory=list)
    evidence: list[SynthesisEvidenceItem] = Field(default_factory=list)
    abstained: bool = True
    explanation: str = ""


class ResearchCapabilities(BaseModel):
    """Authenticated user-visible research feature switches."""

    research_synthesis_enabled: bool = False
    research_plan_execution_enabled: bool = False


class ResearchPlanStepOutcome(BaseModel):
    step_id: str
    status: Literal["complete", "skipped"]
    count: int | None = None


class ResearchPlanSource(BaseModel):
    paper_id: str
    title: str = ""


class ResearchPlanEvidence(BaseModel):
    citation_id: str
    paper_id: str | None = None
    document_id: str | None = None
    page_number: int | None = None
    title: str | None = None
    sentence: str
    start_offset: int = Field(ge=0)
    end_offset: int = Field(gt=0)


class ResearchPlanExecutionResult(BaseModel):
    kind: Literal["research_plan_execution"] = "research_plan_execution"
    run_id: str
    task_type: Literal["feed", "explain", "compare", "deep_research"]
    source_scope: ResearchPlanScope
    steps: list[ResearchPlanStepOutcome] = Field(default_factory=list)
    sources: list[ResearchPlanSource] = Field(default_factory=list)
    evidence: list[ResearchPlanEvidence] = Field(default_factory=list)
    gaps: list[str] = Field(default_factory=list)
    comparison: list["ComparisonRow"] = Field(default_factory=list)
    synthesis: list["SynthesisClaim"] = Field(default_factory=list)
    cost_tracking_available: Literal[False] = False
    estimated_cost_usd: None = None


class ResearchAnswer(BaseModel):
    summary: str
    claims: list[str] = Field(default_factory=list)
    citation_ids: list[str] = Field(default_factory=list)
    pdf_evidence: list[PdfEvidenceItem] = Field(default_factory=list)
    abstained: bool = False
    confidence_explanation: str = ""


def classify_task(query: str) -> ResearchPlan:
    """Deterministic routing (update.md §9.1): planner only for complex tasks."""
    q = re.sub(r"\s+", " ", (query or "").strip().casefold())
    task: Literal["feed", "explain", "compare", "deep_research"]
    if re.search(r"\b(?:compare|comparison|comparative|versus|vs\.?|differences? between)\b", q):
        task = "compare"
    elif re.search(r"\b(?:explain|what is|what are|how does|how do|summari[sz]e)\b", q):
        task = "explain"
    elif re.search(r"\b(?:deep research|survey|literature review|state of the art|sota)\b", q):
        task = "deep_research"
    else:
        task = "feed"
    return ResearchPlan(query=query, task_type=task)


def build_comparison(papers: list[dict[str, Any]]) -> list[ComparisonRow]:
    """Extract exact abstract sentences for comparison dimensions.

    This is a conservative heuristic, not a scientific interpretation. Missing
    dimensions stay null, and generated summaries are deliberately excluded.
    """
    dimension_signals = {
        "problem": re.compile(r"\b(problem|challenge|task|we study|we investigate|we address|aim of this work)\b", re.IGNORECASE),
        "methods": re.compile(r"\b(method|approach|algorithm|model|framework|we propose|we present|we introduce|we develop|we use)\b", re.IGNORECASE),
        "datasets": re.compile(r"\b(dataset|data set|benchmark|corpus|corpora)\b", re.IGNORECASE),
        "metrics": re.compile(r"\b(accuracy|precision|recall|f1|f1-score|bleu|rouge|auc|perplexity|mean squared error|mse|metric|metrics)\b", re.IGNORECASE),
        "limitations": re.compile(r"\b(limitation|however|future work|remain(s|ed)? a challenge|cannot|fails? to|failed to|limited by)\b", re.IGNORECASE),
    }

    def extract_dimension(abstract: object, pattern: re.Pattern[str]) -> str | None:
        if not isinstance(abstract, str):
            return None
        for sentence in re.split(r"(?<=[.!?])\s+", abstract.strip()):
            sentence = sentence.strip()
            if sentence and pattern.search(sentence):
                return sentence
        return None

    rows = []
    for p in papers:
        abstract = p.get("abstract")
        rows.append(
            ComparisonRow(
                paper_id=p.get("id", ""),
                problem=extract_dimension(abstract, dimension_signals["problem"]),
                methods=extract_dimension(abstract, dimension_signals["methods"]),
                datasets=extract_dimension(abstract, dimension_signals["datasets"]),
                metrics=extract_dimension(abstract, dimension_signals["metrics"]),
                limitations=extract_dimension(abstract, dimension_signals["limitations"]),
                code_status="unverified",
            )
        )
    return rows
