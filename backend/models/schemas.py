from datetime import datetime
from typing import Literal, Optional
from pydantic import BaseModel, Field


class Paper(BaseModel):
    id: str
    title: str
    abstract: str
    authors: list[str]
    url: str
    published_at: datetime
    summary_tldr: Optional[str] = None
    summary_contributions: Optional[list[str]] = None
    relevance_score: Optional[float] = None
    difficulty: Optional[Literal["introductory", "intermediate", "expert"]] = None
    papers_with_code: Optional[dict] = None


class PaperSearchResult(BaseModel):
    papers: list[Paper]
    run_id: str


class SearchRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=500)
    model: Optional[str] = None


class UserPrefs(BaseModel):
    preferred_model: str = "anthropic/claude-sonnet-4-5"
    interests: list[str] = Field(default_factory=list)


class AgentStep(BaseModel):
    agent: str
    status: str
    count: Optional[int] = None
    paper_id: Optional[str] = None
    message: Optional[str] = None


class StreamEvent(BaseModel):
    event: Literal["agent_step", "result", "error"]
    data: dict


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
