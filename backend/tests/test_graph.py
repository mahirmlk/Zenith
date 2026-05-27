from fastapi.testclient import TestClient
from main import app

client = TestClient(app)


def test_graph():
    response = client.get("/api/graph/demo")
    assert response.status_code == 200
    data = response.json()
    assert "nodes" in data
    assert "edges" in data
