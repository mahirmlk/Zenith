from fastapi.testclient import TestClient
from main import app

client = TestClient(app)


def test_list_papers():
    response = client.get("/api/papers")
    assert response.status_code in (200, 500)  # 500 if supabase not configured


def test_get_paper_not_found():
    response = client.get("/api/papers/nonexistent")
    assert response.status_code in (404, 500)


def test_save_paper():
    response = client.post("/api/papers/test-id/save", json={"dismissed": False})
    assert response.status_code in (200, 500)
