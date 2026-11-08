"""Deep-research routing/comparison tests (update.md §9). Offline."""
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from agents.research_types import build_comparison, classify_task
from routers.research import ResearchRequest, research_answer, research_compare


class FakeSupabase:
    def __init__(self, *, project=None, members=None, sources=None, papers=None):
        self.project = project
        self.members = members or []
        self.sources = sources or []
        self.papers = papers or []

    def table(self, name):
        return FakeQuery(self, name)


class FakeQuery:
    def __init__(self, db, table):
        self.db = db
        self.name = table
        self.filters = {}
        self.paper_ids = None

    def select(self, *_args):
        return self

    def eq(self, key, value):
        self.filters[key] = value
        return self

    def in_(self, key, values):
        assert key == "id"
        self.paper_ids = set(values)
        return self

    def maybe_single(self):
        return self

    def range(self, *_args):
        return self

    def order(self, *_args, **_kwargs):
        return self

    async def execute(self):
        if self.name == "projects":
            data = self.db.project
        elif self.name == "project_members":
            data = [row for row in self.db.members if row.get("project_id") == self.filters.get("project_id")]
        elif self.name == "project_sources":
            data = [row for row in self.db.sources if row.get("project_id") == self.filters.get("project_id")]
        elif self.name == "papers":
            data = self.db.papers
            if self.paper_ids is not None:
                data = [paper for paper in data if paper.get("id") in self.paper_ids]
        else:
            raise AssertionError(f"Unexpected table {self.name}")
        return SimpleNamespace(data=data)


def test_classify_compare():
    assert classify_task("compare diffusion vs GANs").task_type == "compare"


def test_classify_explain():
    assert classify_task("explain transformers").task_type == "explain"


def test_classify_deep():
    assert classify_task("deep survey of LLM agents").task_type == "deep_research"


def test_classify_feed_default():
    assert classify_task("new papers on diffusion").task_type == "feed"


def test_build_comparison_marks_code_unverified():
    rows = build_comparison([{"id": "p1", "title": "T", "abstract": "A"}])
    assert rows[0].paper_id == "p1"
    assert rows[0].code_status == "unverified"


@pytest.mark.asyncio
async def test_research_answer_returns_verbatim_cited_project_evidence_for_member():
    supabase = FakeSupabase(
        project={"owner_id": "owner"},
        members=[{"project_id": "proj", "user_id": "member", "role": "viewer"}],
        sources=[{"project_id": "proj", "paper_id": "project-paper"}],
        papers=[
            {"id": "project-paper", "title": "Diffusion", "abstract": "Diffusion models generate images through iterative denoising."},
            {"id": "outside-paper", "title": "Diffusion", "abstract": "Diffusion models outside the project are private."},
        ],
    )

    result = await research_answer(
        ResearchRequest(query="diffusion models", project_id="proj"),
        object(),
        {"user_id": "member"},
        supabase,
    )

    assert result.abstained is False
    assert result.claims == [
        "Diffusion models generate images through iterative denoising. [project-paper]"
    ]
    assert result.citation_ids == ["project-paper"]
    assert "outside-paper" not in " ".join(result.claims)


@pytest.mark.asyncio
async def test_research_answer_abstains_without_matching_abstract_evidence():
    supabase = FakeSupabase(papers=[{
        "id": "p1", "title": "Weather", "abstract": "We study ocean temperatures and circulation.",
    }])

    result = await research_answer(
        ResearchRequest(query="quantum cryptography"),
        object(),
        {"user_id": "reader"},
        supabase,
    )

    assert result.abstained is True
    assert result.claims == []
    assert result.citation_ids == []


@pytest.mark.asyncio
async def test_project_research_hides_projects_from_nonmembers():
    supabase = FakeSupabase(project={"owner_id": "owner"})

    with pytest.raises(HTTPException) as exc_info:
        await research_compare(
            ResearchRequest(query="diffusion", project_id="proj"),
            object(),
            {"user_id": "outsider"},
            supabase,
        )

    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_project_comparison_uses_only_attached_papers():
    supabase = FakeSupabase(
        project={"owner_id": "owner"},
        members=[],
        sources=[{"project_id": "proj", "paper_id": "p1"}],
        papers=[
            {"id": "p1", "title": "Project Diffusion", "abstract": "Diffusion method for project images."},
            {"id": "p2", "title": "Global Diffusion", "abstract": "Global paper about diffusion."},
        ],
    )

    result = await research_compare(
        ResearchRequest(query="diffusion", project_id="proj"),
        object(),
        {"user_id": "owner"},
        supabase,
    )

    assert [row["paper_id"] for row in result["rows"]] == ["p1"]
