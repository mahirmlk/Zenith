from datetime import date, datetime
from typing import Any, Literal, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class Paper(BaseModel):
    id: str
    preprint_id: Optional[str] = Field(default=None, max_length=64)
    source_version: Optional[int] = Field(default=None, ge=1)
    title: str
    abstract: str
    authors: list[str]
    url: str
    published_at: datetime
    doi: Optional[str] = None
    publication_update_type: Optional[
        Literal["retraction", "partial_retraction", "withdrawal", "removal", "expression_of_concern"]
    ] = None
    publication_update_doi: Optional[str] = None
    publication_update_label: Optional[str] = None
    publication_update_date: Optional[date] = None
    publication_update_source: Optional[Literal["crossref"]] = None
    publication_update_deposit_source: Optional[Literal["publisher", "retraction-watch"]] = None
    publication_update_checked_at: Optional[datetime] = None
    summary_tldr: Optional[str] = None
    summary_contributions: Optional[list[str]] = None
    summary_status: Literal["generated", "abstract_preview", "unknown"] = "unknown"
    summary_fallback_reason: Optional[
        Literal[
            "per_run_cap",
            "spend_limit",
            "billing_unavailable",
            "provider_unavailable",
            "invalid_output",
        ]
    ] = None
    relevance_score: Optional[float] = None
    difficulty: Optional[Literal["introductory", "intermediate", "expert"]] = None
    papers_with_code: Optional[dict[str, Any]] = None


class PaperSearchResult(BaseModel):
    papers: list[Paper]
    run_id: str


class PublicPaperEvidenceItem(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    page_number: int = Field(..., ge=1, le=500)
    citation_id: str = Field(..., min_length=1, max_length=160)
    sentence: str = Field(..., min_length=1, max_length=500)
    start_offset: int = Field(..., ge=0, le=100_000)
    end_offset: int = Field(..., ge=1, le=100_000)

    @model_validator(mode="after")
    def validate_exact_offsets(self) -> "PublicPaperEvidenceItem":
        if self.end_offset <= self.start_offset:
            raise ValueError("Evidence end offset must follow its start offset")
        if self.end_offset - self.start_offset != len(self.sentence):
            raise ValueError("Evidence offsets must match the exact sentence length")
        return self


class PublicPaperEvidenceResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    paper_id: str = Field(..., min_length=1, max_length=200)
    preprint_id: str = Field(..., min_length=1, max_length=64)
    version: int = Field(..., ge=1)
    title: str = Field(..., min_length=1, max_length=300)
    source_url: str = Field(..., pattern=r"^https://arxiv\.org/abs/[^\s?#]+$")
    license_url: str = Field(
        ...,
        pattern=r"^https://creativecommons\.org/(?:licenses/by/4\.0|publicdomain/zero/1\.0)/$",
    )
    license_name: Literal[
        "Creative Commons Attribution 4.0 International",
        "Creative Commons Zero 1.0 Universal",
    ]
    attribution: str = Field(..., min_length=1, max_length=700)
    evidence: list[PublicPaperEvidenceItem] = Field(..., max_length=5)


class SearchRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=500)
    model: Optional[str] = None


class SavedSearchCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(..., min_length=1, max_length=120)
    query: str = Field(..., min_length=1, max_length=500)
    model: str | None = Field(default=None, max_length=100)
    project_id: UUID | None = None

    @field_validator("name", "query")
    @classmethod
    def _trim_search_text(cls, value: str) -> str:
        if value.strip() != value or not value.strip():
            raise ValueError("must contain non-whitespace text without surrounding whitespace")
        return value


class SavedSearchUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=120)
    query: str | None = Field(default=None, min_length=1, max_length=500)
    model: str | None = Field(default=None, max_length=100)

    @field_validator("name", "query")
    @classmethod
    def _trim_optional_search_text(cls, value: str | None) -> str | None:
        if value is not None and (value.strip() != value or not value.strip()):
            raise ValueError("must contain non-whitespace text without surrounding whitespace")
        return value

    @model_validator(mode="after")
    def _require_update(self) -> "SavedSearchUpdate":
        if not self.model_fields_set:
            raise ValueError("at least one field must be provided")
        return self


class SavedSearchResponse(BaseModel):
    id: UUID
    name: str
    query: str
    model: str | None = None
    project_id: UUID | None = None
    created_by: UUID
    created_at: datetime | None = None
    updated_at: datetime | None = None


class SavedSearchRunResponse(BaseModel):
    run_id: str


class ProjectAnnotationCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_type: Literal["paper_abstract", "pdf_page"]
    paper_source_id: UUID | None = None
    document_id: UUID | None = None
    page_number: int | None = Field(default=None, ge=1, le=500)
    start_offset: int = Field(..., ge=0)
    end_offset: int = Field(..., gt=0)
    quote: str = Field(..., min_length=1, max_length=4000)
    content: str = Field(..., min_length=1, max_length=5000)

    @model_validator(mode="after")
    def _validate_anchor(self) -> "ProjectAnnotationCreate":
        if self.end_offset <= self.start_offset:
            raise ValueError("end_offset must be greater than start_offset")
        if self.end_offset - self.start_offset != len(self.quote):
            raise ValueError("quote length must match its character offsets")
        if self.source_type == "paper_abstract":
            if self.paper_source_id is None or self.document_id is not None or self.page_number is not None:
                raise ValueError("paper_abstract annotations require only paper_source_id")
        elif (
            self.paper_source_id is not None
            or self.document_id is None
            or self.page_number is None
        ):
            raise ValueError("pdf_page annotations require document_id and page_number only")
        if self.content.strip() != self.content or not self.content.strip():
            raise ValueError("content must contain non-whitespace text without surrounding whitespace")
        return self


class ProjectAnnotationUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    content: str = Field(..., min_length=1, max_length=5000)

    @field_validator("content")
    @classmethod
    def _validate_content(cls, value: str) -> str:
        if value.strip() != value or not value.strip():
            raise ValueError("content must contain non-whitespace text without surrounding whitespace")
        return value


class ProjectAnnotationResponse(BaseModel):
    id: UUID
    project_id: UUID
    source_type: Literal["paper_abstract", "pdf_page"]
    paper_source_id: UUID | None = None
    document_id: UUID | None = None
    page_number: int | None = None
    start_offset: int
    end_offset: int
    quote: str
    quote_sha256: str
    content: str
    created_by: UUID
    created_at: datetime | None = None
    updated_at: datetime | None = None
    source_label: str | None = None
    is_stale: bool = False


class ProjectBriefSourceLocator(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_type: Literal["paper_abstract", "pdf_page"]
    paper_source_id: UUID | None = None
    document_id: UUID | None = None
    page_number: int | None = Field(default=None, ge=1, le=500)
    start_offset: int = Field(..., ge=0)
    end_offset: int = Field(..., gt=0)
    quote: str = Field(..., min_length=1, max_length=4000)

    @model_validator(mode="after")
    def _validate_locator_shape(self) -> "ProjectBriefSourceLocator":
        if self.end_offset <= self.start_offset or self.end_offset - self.start_offset != len(self.quote):
            raise ValueError("quote length must match its half-open character offsets")
        if self.source_type == "paper_abstract":
            if self.paper_source_id is None or self.document_id is not None or self.page_number is not None:
                raise ValueError("paper_abstract locators require only paper_source_id")
        elif self.paper_source_id is not None or self.document_id is None or self.page_number is None:
            raise ValueError("pdf_page locators require document_id and page_number only")
        return self


class ProjectBriefCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(..., min_length=1, max_length=160)
    content: str = Field(..., min_length=1, max_length=50000)
    source_snapshot: list[ProjectBriefSourceLocator] = Field(default_factory=list, max_length=50)

    @field_validator("title", "content")
    @classmethod
    def _require_trimmed_text(cls, value: str) -> str:
        if not value.strip() or value != value.strip():
            raise ValueError("text must contain non-whitespace content without surrounding whitespace")
        return value


class ProjectBriefVersionCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_current_version: int = Field(..., ge=1)
    content: str = Field(..., min_length=1, max_length=50000)
    source_snapshot: list[ProjectBriefSourceLocator] = Field(default_factory=list, max_length=50)

    @field_validator("content")
    @classmethod
    def _require_trimmed_content(cls, value: str) -> str:
        if not value.strip() or value != value.strip():
            raise ValueError("content must contain non-whitespace text without surrounding whitespace")
        return value


class ProjectBriefResponse(BaseModel):
    id: UUID
    project_id: UUID
    title: str
    created_by: UUID
    current_version: int
    created_at: datetime | None = None
    updated_at: datetime | None = None


class ProjectBriefVersionResponse(BaseModel):
    id: UUID
    brief_id: UUID
    version: int
    content: str
    source_snapshot: list[dict[str, Any]]
    created_by: UUID
    created_at: datetime | None = None
    content_sha256: str
    origin: Literal["user_authored"] = "user_authored"


class ProjectBriefCreateResponse(BaseModel):
    brief: ProjectBriefResponse
    version: ProjectBriefVersionResponse


class UserPrefs(BaseModel):
    preferred_model: str = Field(default="anthropic/claude-sonnet-5.5", max_length=100)
    interests: list[str] = Field(default_factory=list, max_length=50)

    @field_validator("interests")
    @classmethod
    def _cap_interest_len(cls, v: list[str]) -> list[str]:
        if any(len(s) > 200 for s in v):
            raise ValueError("Each interest must be <= 200 chars")
        return v


class AgentStep(BaseModel):
    agent: str
    status: str
    count: Optional[int] = None
    paper_id: Optional[str] = None
    message: Optional[str] = None


class StreamEvent(BaseModel):
    event: Literal["agent_step", "result", "error"]
    data: dict[str, Any]


class SavePaperRequest(BaseModel):
    dismissed: bool = False


class GraphNode(BaseModel):
    id: str
    title: str
    x: float
    y: float
    z: float


class GraphEdge(BaseModel):
    source: str
    target: str


class CitationGraph(BaseModel):
    nodes: list[GraphNode]
    edges: list[GraphEdge]


class ErrorResponse(BaseModel):
    detail: str
    error_code: Optional[str] = None
