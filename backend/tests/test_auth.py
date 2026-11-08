from main import app
from tests.asgi_client import ASGITestClient

client = ASGITestClient(app)


def test_auth_no_token():
    response = client.post("/api/auth/token", json={"token": ""})
    assert response.status_code == 200
    data = response.json()
    assert data["valid"] is False


def test_auth_invalid_token():
    response = client.post("/api/auth/token", json={"token": "bad-token"})
    assert response.status_code == 200
    data = response.json()
    assert data["valid"] is False
