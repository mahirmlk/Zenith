import pytest
from fastapi.testclient import TestClient
from main import app

client = TestClient(app)


def test_search_papers():
    response = client.post("/api/search", json={"query": "diffusion models"})
    assert response.status_code == 200
    data = response.json()
    assert "run_id" in data


def test_search_empty_query():
    response = client.post("/api/search", json={"query": ""})
    assert response.status_code == 422
