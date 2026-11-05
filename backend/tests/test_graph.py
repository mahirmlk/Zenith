import jwt
from fastapi.testclient import TestClient

from main import app

client = TestClient(app)


def _headers(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", "")
    monkeypatch.setenv("SUPABASE_JWT_SECRET", "test-secret-graph")
    token = jwt.encode({"sub": "u1"}, "test-secret-graph", algorithm="HS256")
    return {"Authorization": f"Bearer {token}"}


def test_graph_requires_auth():
    assert client.get("/api/graph/demo").status_code == 401


def test_graph(monkeypatch):
    response = client.get("/api/graph/demo", headers=_headers(monkeypatch))
    assert response.status_code == 200
    data = response.json()
    assert "nodes" in data
    assert "edges" in data


def test_graph_rejects_traversal(monkeypatch):
    # Encoded slash either fails validation (422) or route match (404) —
    # both mean the traversal never reaches Semantic Scholar.
    assert client.get("/api/graph/..%2Fsecret", headers=_headers(monkeypatch)).status_code in (404, 422)
    assert client.get("/api/graph/foo/bar", headers=_headers(monkeypatch)).status_code in (404, 422)
