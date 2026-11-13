"""Typed intermediate outputs for deep research (update.md §9.1)."""
import re
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


class ResearchAnswer(BaseModel):
    summary: str
    claims: list[str] = Field(default_factory=list)
    citation_ids: list[str] = Field(default_factory=list)
    pdf_evidence: list[PdfEvidenceItem] = Field(default_factory=list)
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
