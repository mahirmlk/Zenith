"""Security regression tests (update.md §5.5, §10.2). No live services needed."""
import pytest
import jwt
from jwt.exceptions import InvalidTokenError

from services import jwt_validator
from services.llm_router import validate_model
from services.run_store import RunStore
from services.ssrf import validate_public_url


@pytest.mark.asyncio
async def test_alg_none_rejected(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_JWT_SECRET", "test-secret-long-enough-for-hs256-signing")
    # alg=none token crafted manually
    token = jwt.encode({"sub": "u1"}, key="", algorithm="none")
    with pytest.raises(InvalidTokenError):
        await jwt_validator.decode_supabase_token(token)


@pytest.mark.asyncio
async def test_wrong_audience_rejected(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", "")
    monkeypatch.setenv("SUPABASE_JWT_SECRET", "legacy-secret-long-enough-for-hs256-signing")
    token = jwt.encode(
        {"sub": "u1", "aud": "some-other-app"},
        "legacy-secret-long-enough-for-hs256-signing",
        algorithm="HS256",
    )
    with pytest.raises(InvalidTokenError):
        await jwt_validator.decode_supabase_token(token)


@pytest.mark.asyncio
async def test_wrong_issuer_rejected(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_JWT_SECRET", "legacy-secret-long-enough-for-hs256-signing")
    token = jwt.encode(
        {"sub": "u1", "iss": "https://evil.supabase.co/auth/v1"},
        "legacy-secret-long-enough-for-hs256-signing",
        algorithm="HS256",
    )
    with pytest.raises(InvalidTokenError):
        await jwt_validator.decode_supabase_token(token)


@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1/admin",
        "http://10.0.0.1/secret",
        "http://169.254.169.254/latest/meta-data",
        "http://[::1]/",
        "file:///etc/passwd",
        "ftp://example.com/x",
        "http://localhost:8000/api",
    ],
)
def test_ssrf_blocked(url):
    with pytest.raises(ValueError):
        validate_public_url(url, resolve=False)


def test_ssrf_public_ip_allowed():
    assert validate_public_url("https://8.8.8.8/paper", resolve=False)


def test_model_registry_rejects_unknown():
    with pytest.raises(ValueError):
        validate_model("evil/expensive-model", "summary_default")


def test_model_registry_rejects_wrong_agent():
    with pytest.raises(ValueError):
        validate_model("deepseek/deepseek-r1", "memory")


def test_model_registry_allows_known():
    assert validate_model("openai/gpt-4o-mini", "research") == "openai/gpt-4o-mini"


@pytest.mark.asyncio
async def test_run_store_idempotency_and_start_once():
    store = RunStore(ttl_seconds=60)
    first = await store.create("r1", "q", user_id="u1", idempotency_key="k1")
    second = await store.create("r2", "q", user_id="u1", idempotency_key="k1")
    assert first.run_id == second.run_id == "r1"
    assert await store.try_start("r1") is True
    assert await store.try_start("r1") is False  # reconnect must not restart
    await store.add_event("r1", "agent_step", {"agent": "research"})
    events = await store.get_events("r1")
    assert events[0]["sequence"] == 1 and events[0]["event"] == "agent_step"
