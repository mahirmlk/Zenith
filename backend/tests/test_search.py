import jwt
from main import app
from tests.asgi_client import ASGITestClient

client = ASGITestClient(app)


def _auth_headers(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", "")
    secret = "test-secret-for-search-long-enough-for-hs256"
    monkeypatch.setenv("SUPABASE_JWT_SECRET", secret)
    token = jwt.encode({"sub": "test-user-1"}, secret, algorithm="HS256")
    return {"Authorization": f"Bearer {token}"}


def _enable_metered_catalog(monkeypatch):
    from services import llm_router, spend_meter

    monkeypatch.setattr(
        llm_router,
        "effective_models",
        lambda: [{"id": "anthropic/claude-sonnet-5.5", "agents": ["summary_default"]}],
    )

    async def ready():
        return True

    monkeypatch.setattr(spend_meter, "meter_ready", ready)


def test_search_requires_auth():
    response = client.post("/api/search", json={"query": "diffusion models"})
    assert response.status_code == 401


def test_search_papers(monkeypatch):
    _enable_metered_catalog(monkeypatch)
    response = client.post(
        "/api/search", json={"query": "diffusion models"}, headers=_auth_headers(monkeypatch)
    )
    assert response.status_code == 200
    data = response.json()
    assert "run_id" in data


def test_search_empty_query(monkeypatch):
    response = client.post(
        "/api/search", json={"query": ""}, headers=_auth_headers(monkeypatch)
    )
    assert response.status_code == 422


def test_search_rejects_run_if_deletion_wins_admission_race(monkeypatch):
    from routers import search as search_router
    from services import budget
    from services.run_store import AccountDeletionInProgressError

    _enable_metered_catalog(monkeypatch)

    refunded = []

    async def consume(_user_id, _limit):
        return True

    async def refund(user_id):
        refunded.append(user_id)

    async def create(*_args, **_kwargs):
        raise AccountDeletionInProgressError("Account deletion is in progress")

    monkeypatch.setattr(budget, "consume", consume)
    monkeypatch.setattr(budget, "refund", refund)
    monkeypatch.setattr(search_router.run_store, "create", create)

    response = client.post(
        "/api/search", json={"query": "diffusion models"}, headers=_auth_headers(monkeypatch)
    )

    assert response.status_code == 423
    assert refunded == ["test-user-1"]
