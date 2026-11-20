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
        self.range_args = None

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

    def range(self, *args):
        self.range_args = args
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
        elif self.table_name == "project_documents":
            data = [
                row for row in self.database.documents
                if row.get("project_id") == self.filters.get("project_id")
            ]
        elif self.table_name == "project_document_pages":
            data = [
                row for row in self.database.pages
                if row.get("document_id") in (self.ids or set())
            ]
        elif self.table_name == "papers":
            data = self.database.papers
            if self.ids is not None:
                data = [paper for paper in data if paper.get("id") in self.ids]
        else:
            raise AssertionError(self.table_name)
        if self.range_args is not None:
            first, last = self.range_args
            data = data[first : last + 1]
        self.database.query_details.append(
            (self.table_name, self.filters.copy(), self.ids, self.range_args)
        )
        return type("Response", (), {"data": data})()


class _FakeDatabase:
    def __init__(self, project=None, members=None, sources=None, papers=None, documents=None, pages=None):
        self.project = project
        self.members = members or []
        self.sources = sources or []
        self.papers = papers or []
        self.documents = documents or []
        self.pages = pages or []
        self.queries = []
        self.query_details = []

    def table(self, name):
        self.queries.append(name)
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
    assert response["results"][0]["source_type"] == "paper"
    assert "project_documents" in db.queries


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
    assert "project_documents" not in db.queries


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
    assert "project_documents" not in db.queries


@pytest.mark.asyncio
async def test_project_search_includes_exact_pdf_page_for_documents_only_project():
    document_id = "document-1"
    page_text = "\nDiffusion methods improved retrieval quality on the benchmark.\n"
    db = _FakeDatabase(
        project={"owner_id": "owner"},
        members=[{"project_id": "p", "user_id": "member", "role": "viewer"}],
        documents=[{"id": document_id, "project_id": "p", "filename": "methods.pdf"}],
        pages=[{"document_id": document_id, "page_number": 4, "text": page_text}],
    )

    response = await hybrid_search(
        HybridSearchRequest(query="diffusion methods", project_id="p"),
        object(),
        {"user_id": "member"},
        db,
    )

    assert len(response["results"]) == 1
    result = response["results"][0]
    assert result["source_type"] == "pdf_page"
    assert result["citation_id"] == f"{document_id}:page:4"
    assert page_text[result["start_offset"] : result["end_offset"]] == result["snippet"]
    assert result["snippet"] == "Diffusion methods improved retrieval quality on the benchmark."
    assert result["start_offset"] == page_text.index(result["snippet"])


@pytest.mark.asyncio
async def test_project_search_caps_pdf_reads_and_respects_result_limit():
    documents = [
        {"id": f"document-{index:02}", "project_id": "p", "filename": f"{index}.pdf"}
        for index in range(11)
    ]
    pages = [
        {"document_id": document["id"], "page_number": page, "text": "Diffusion systems."}
        for document in documents
        for page in range(1, 502)
    ]
    db = _FakeDatabase(
        project={"owner_id": "owner"},
        documents=documents,
        pages=pages,
    )

    response = await hybrid_search(
        HybridSearchRequest(query="diffusion", project_id="p", limit=3),
        object(),
        {"user_id": "owner"},
        db,
    )

    assert len(response["results"]) <= 3
    document_query = next(item for item in db.query_details if item[0] == "project_documents")
    page_query = next(item for item in db.query_details if item[0] == "project_document_pages")
    assert document_query[3] == (0, 9)
    assert page_query[3] == (0, 499)
    assert len(page_query[2] or set()) == 10
    assert len([row for row in pages if row["document_id"] in (page_query[2] or set())][:500]) == 500


@pytest.mark.asyncio
async def test_project_search_mixes_papers_and_pdf_pages_with_deterministic_citations():
    document_id = "document-1"
    page_text = "Diffusion methods improve retrieval quality."
    db = _FakeDatabase(
        project={"owner_id": "owner"},
        members=[{"project_id": "p", "user_id": "member", "role": "editor"}],
        sources=[{"project_id": "p", "paper_id": "paper-1"}],
        papers=[{
            "id": "paper-1",
            "title": "Diffusion methods",
            "abstract": "Diffusion methods improve retrieval quality.",
        }],
        documents=[{"id": document_id, "project_id": "p", "filename": "methods.pdf"}],
        pages=[{"document_id": document_id, "page_number": 2, "text": page_text}],
    )
    body = HybridSearchRequest(query="diffusion methods", project_id="p")

    first = await hybrid_search(body, object(), {"user_id": "member"}, db)
    second = await hybrid_search(body, object(), {"user_id": "member"}, db)

    assert {row["source_type"] for row in first["results"]} == {"paper", "pdf_page"}
    assert [row["id"] for row in first["results"]] == [row["id"] for row in second["results"]]
    pdf_result = next(row for row in first["results"] if row["source_type"] == "pdf_page")
    assert pdf_result["citation_id"] == f"{document_id}:page:2"
    assert page_text[pdf_result["start_offset"] : pdf_result["end_offset"]] == pdf_result["snippet"]


@pytest.mark.asyncio
async def test_public_search_never_reads_project_pdf_tables():
    db = _FakeDatabase(papers=DOCS)

    response = await hybrid_search(
        HybridSearchRequest(query="diffusion"),
        object(),
        {"user_id": "reader"},
        db,
    )

    assert response["results"]
    assert {row["source_type"] for row in response["results"]} == {"paper"}
    assert "project_documents" not in db.queries
    assert "project_document_pages" not in db.queries
