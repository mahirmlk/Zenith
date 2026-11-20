from types import SimpleNamespace

import pytest

from services import embeddings, llm_router, mem0_client
from services.spend_meter import BillingContext


def test_mem0_model_calls_fail_closed_when_global_gate_is_off(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = SimpleNamespace(llm_enabled=False, mem0_api_key="configured", mem0_provider_spend_limit_confirmed=True)
    monkeypatch.setattr(llm_router, "get_settings", lambda: settings)
    monkeypatch.setattr(mem0_client, "get_settings", lambda: settings)
    monkeypatch.setattr(mem0_client, "_get_client", lambda: pytest.fail("Mem0 must not be called"))

    assert mem0_client.is_configured() is False
    with pytest.raises(llm_router.LLMDisabledError, match="LLM_ENABLED is false"):
        mem0_client._get_user_profile_sync("user-1")
    with pytest.raises(llm_router.LLMDisabledError, match="LLM_ENABLED is false"):
        mem0_client._add_memory_sync("user-1", [{"role": "user", "content": "test"}])


@pytest.mark.asyncio
async def test_embedding_provider_call_fails_before_reservation_when_gate_is_off(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        llm_router,
        "get_settings",
        lambda: SimpleNamespace(llm_enabled=False),
    )
    monkeypatch.setattr(embeddings, "reserve_embedding_attempt", lambda **_kwargs: pytest.fail("Must not reserve"))

    with pytest.raises(llm_router.LLMDisabledError, match="LLM_ENABLED is false"):
        await embeddings._embed(["test"], BillingContext("user-1", None, "test"))
