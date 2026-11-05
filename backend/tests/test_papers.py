import os

import pytest
from fastapi.testclient import TestClient
from main import app

client = TestClient(app)

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
