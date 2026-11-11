"""Hybrid retrieval + evidence tests (update.md §8). Offline/deterministic."""
from services.evidence_store import Claim, EvidenceItem, validate_evidence
from services.retrieval import bm25_scores, hybrid_fuse, hybrid_rank
from fastapi import HTTPException
import pytest
from routers.retrieval import HybridSearchRequest, hybrid_search

DOCS = [
    {"id": "a", "title": "Diffusion models for images", "abstract": "We study diffusion sampling."},
    {"id": "b", "title": "Graph neural networks", "abstract": "Message passing on graphs."},
    {"id": "c", "title": "Diffusion sampling theory", "abstract": "Diffusion theory and proofs."},
]


def test_bm25_relevant_doc_wins():
    scores = bm25_scores("diffusion sampling", DOCS)
    assert scores[0] > scores[1]
    assert scores[0] > 0


def test_bm25_empty_query():
    assert bm25_scores("", DOCS) == [0.0, 0.0, 0.0]


def test_hybrid_rank_orders_and_scores():
    ranked = hybrid_rank("diffusion", DOCS)
    assert ranked[0]["id"] in ("a", "c")
    assert ranked[0]["score"] >= ranked[-1]["score"]
    fused = hybrid_fuse([0.0, 1.0], [1.0, 0.0])
    assert fused == [0.5, 0.5]


def test_evidence_validation():
    good = [Claim(claim_text="x", evidence=[EvidenceItem(paper_id="a")])]
    assert validate_evidence(good, {"a"}) == []
    bad = [Claim(claim_text="y", evidence=[EvidenceItem(paper_id="fake")])]
    assert validate_evidence(bad, {"a"}) != []


class _FakeQuery:
    def __init__(self, database, table):
        self.database = database
        self.table_name = table
        self.filters = {}
        self.ids = None
        self.require_null = set()

    def select(self, *_args):
        return self

    def eq(self, key, value):
        self.filters[key] = value
        return self

    def in_(self, _key, values):
        self.ids = set(values)
        return self

    def is_(self, key, value):
        assert value == "null"
        self.require_null.add(key)
        return self

    def maybe_single(self):
        return self

    def range(self, *_args):
        return self

    def order(self, *_args, **_kwargs):
        return self

    async def execute(self):
        if self.table_name == "projects":
            data = self.database.project
            if data and any(data.get(key) is not None for key in self.require_null):
                data = None
        elif self.table_name == "project_members":
            data = [
                row for row in self.database.members
                if row.get("project_id") == self.filters.get("project_id")
            ]
        elif self.table_name == "project_sources":
            data = [
                row for row in self.database.sources
                if row.get("project_id") == self.filters.get("project_id")
            ]
        elif self.table_name == "papers":
            data = self.database.papers
            if self.ids is not None:
                data = [paper for paper in data if paper.get("id") in self.ids]
        else:
            raise AssertionError(self.table_name)
        return type("Response", (), {"data": data})()


class _FakeDatabase:
    def __init__(self, project=None, members=None, sources=None, papers=None):
        self.project = project
        self.members = members or []
        self.sources = sources or []
        self.papers = papers or []

    def table(self, name):
        return _FakeQuery(self, name)


@pytest.mark.asyncio
async def test_project_retrieval_allows_member_and_limits_to_project_sources():
    db = _FakeDatabase(
        project={"owner_id": "owner"},
        members=[{"project_id": "p", "user_id": "member", "role": "viewer"}],
        sources=[{"project_id": "p", "paper_id": "a"}],
        papers=[*DOCS, {"id": "outside", "title": "Diffusion outside", "abstract": "Diffusion."}],
    )

    response = await hybrid_search(
        HybridSearchRequest(query="diffusion", project_id="p"),
        object(),
        {"user_id": "member"},
        db,
    )

    assert [paper["id"] for paper in response["results"]] == ["a"]


@pytest.mark.asyncio
async def test_project_retrieval_hides_project_from_nonmember():
    db = _FakeDatabase(project={"owner_id": "owner"})

    with pytest.raises(HTTPException) as error:
        await hybrid_search(
            HybridSearchRequest(query="diffusion", project_id="p"),
            object(),
            {"user_id": "outsider"},
            db,
        )

    assert error.value.status_code == 404


@pytest.mark.asyncio
async def test_project_retrieval_hides_soft_deleted_project_from_owner():
    db = _FakeDatabase(project={"owner_id": "owner", "deleted_at": "2026-11-01T00:00:00Z"})

    with pytest.raises(HTTPException) as error:
        await hybrid_search(
            HybridSearchRequest(query="diffusion", project_id="p"),
            object(),
            {"user_id": "owner"},
            db,
        )

    assert error.value.status_code == 404
