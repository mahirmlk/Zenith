from fastapi.testclient import TestClient
from main import app

client = TestClient(app)


def test_health():
    response = client.get("/api/health")
    assert response.status_code == 200
    data = response.json()
    assert data["service"] == "ai-paper-agent-backend"
    assert "status" in data
    assert "checks" in data
