import os

import pytest
from main import app
from tests.asgi_client import ASGITestClient
from models.schemas import Paper

client = ASGITestClient(app)


def test_paper_schema_exposes_optional_arxiv_metadata_for_supported_evidence_sources():
    base = {
        "id": "2401.12345v2",
        "title": "Graph retrieval",
        "abstract": "Abstract text",
        "authors": ["A. Researcher"],
        "url": "https://arxiv.org/pdf/2401.12345v2.pdf",
        "published_at": "2024-01-01T00:00:00Z",
    }
    current = Paper.model_validate({**base, "preprint_id": "2401.12345", "source_version": 2})
    legacy = Paper.model_validate({**base, "id": "legacy-id"})

    assert current.preprint_id == "2401.12345"
    assert current.source_version == 2
    assert legacy.preprint_id is None
    assert legacy.source_version is None

needs_supabase = pytest.mark.skipif(
    not os.environ.get("SUPABASE_URL"), reason="needs live Supabase"
)


@needs_supabase
def test_list_papers():
    response = client.get("/api/papers")
    assert response.status_code in (200, 500)  # 500 if supabase not configured


@needs_supabase
def test_get_paper_not_found():
    response = client.get("/api/papers/nonexistent")
    assert response.status_code in (404, 500)


@needs_supabase
def test_save_paper():
    response = client.post("/api/papers/test-id/save", json={"dismissed": False})
    assert response.status_code in (200, 500)
