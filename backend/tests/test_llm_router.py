from __future__ import annotations

import sys
from types import ModuleType, SimpleNamespace
from typing import Any

import pytest

from services import llm_router
from routers.models import list_models


@pytest.mark.parametrize(("model_id", "agent"), [
    ("anthropic/claude-sonnet-5.5", "summary_default"),
    ("openai/gpt-4o-mini", "research"),
    ("google/gemini-3.6-flash", "summary_fast"),
])
def test_metered_model_calls_require_openrouter(
    monkeypatch: pytest.MonkeyPatch,
    model_id: str,
    agent: str,
) -> None:
    monkeypatch.setattr(
        llm_router,
        "get_settings",
        lambda: SimpleNamespace(openrouter_api_key="", llm_enabled=True),
    )
    with pytest.raises(RuntimeError, match="required for metered model calls"):
        llm_router.get_llm(agent=agent, model_override=model_id)


def test_namespaced_model_prefers_openrouter_when_key_is_configured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        llm_router,
        "get_settings",
        lambda: SimpleNamespace(openrouter_api_key="configured", llm_enabled=True),
    )
    expected = object()
    openrouter_calls: list[tuple[str, float, int]] = []

    def openrouter(model: str, temperature: float, max_tokens: int) -> object:
        openrouter_calls.append((model, temperature, max_tokens))
        return expected

    monkeypatch.setattr(llm_router, "get_openrouter_llm", openrouter)
    result = llm_router.get_llm(agent="summary_default")

    assert result is expected
    assert openrouter_calls == [(llm_router.AGENT_MODEL_MAP["summary_default"], 0.3, 4096)]


@pytest.mark.parametrize(
    ("model_id", "agent"),
    [("meta-llama/llama-3.3-70b-instruct", "summary_default")],
)
def test_openrouter_only_families_fail_clearly_without_openrouter(
    monkeypatch: pytest.MonkeyPatch,
    model_id: str,
    agent: str,
) -> None:
    monkeypatch.setattr(
        llm_router,
        "get_settings",
        lambda: SimpleNamespace(openrouter_api_key="", llm_enabled=True),
    )
    with pytest.raises(RuntimeError, match="required for metered model calls"):
        llm_router.get_llm(agent=agent, model_override=model_id)


def test_openrouter_constructor_failure_is_not_hidden_by_direct_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        llm_router,
        "get_settings",
        lambda: SimpleNamespace(openrouter_api_key="configured", llm_enabled=True),
    )
    monkeypatch.setattr(
        llm_router,
        "get_openrouter_llm",
        lambda *_args: (_ for _ in ()).throw(RuntimeError("OpenRouter setup failed")),
    )
    with pytest.raises(RuntimeError, match="OpenRouter setup failed"):
        llm_router.get_llm(agent="summary_default")


def test_defaults_use_models_not_known_to_be_retired_or_shut_down() -> None:
    assert llm_router.AGENT_MODEL_MAP["orchestrator"] == "anthropic/claude-opus-5.5"
    assert llm_router.AGENT_MODEL_MAP["summary_default"] == "anthropic/claude-sonnet-5.5"
    assert llm_router.AGENT_MODEL_MAP["summary_fast"] == "google/gemini-3.6-flash"
    assert "anthropic/claude-opus-4" not in llm_router.MODEL_REGISTRY
    assert "mistralai/mistral-large" not in llm_router.MODEL_REGISTRY
    assert "google/gemini-2.0-flash" not in llm_router.MODEL_REGISTRY


def test_every_selectable_model_has_a_verified_spend_bound(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert set(llm_router.MODEL_REGISTRY).issubset(llm_router.MODEL_PRICES)
    with pytest.raises(ValueError, match="Model not in registry"):
        llm_router.validate_model("deepseek/deepseek-r1", "orchestrator")
    monkeypatch.setitem(
        llm_router.MODEL_REGISTRY,
        "unpriced/test-model",
        {"agents": ["summary_default"]},
    )
    with pytest.raises(ValueError, match="no verified spend bound"):
        llm_router.validate_model("unpriced/test-model")


def test_unverified_mistral_alias_is_not_selectable() -> None:
    for model_id in ("mistralai/mistral-large", "google/gemini-2.5-pro"):
        with pytest.raises(ValueError, match="Model not in registry"):
            llm_router.get_llm(
                agent="summary_default",
                model_override=model_id,
            )


def _run_immediate(coro: Any) -> Any:
    try:
        coro.send(None)
    except StopIteration as result:
        return result.value
    raise AssertionError("endpoint unexpectedly performed I/O")


def test_model_catalog_exposes_server_selected_default(monkeypatch: pytest.MonkeyPatch) -> None:
    from services import spend_meter

    monkeypatch.setattr(
        llm_router,
        "get_settings",
        lambda: SimpleNamespace(
            openrouter_api_key="configured", supabase_url="url",
            supabase_service_role_key="service", llm_daily_spend_cap_usd_micros=1_000_000,
            llm_monthly_spend_cap_usd_micros=10_000_000, llm_enabled=True,
        ),
    )
    async def ready() -> bool:
        return True

    monkeypatch.setattr(spend_meter, "meter_ready", ready)
    response = _run_immediate(list_models())

    assert response["available"] is True
    assert response["availability_reason"] is None
    assert response["default_model"] == llm_router.AGENT_MODEL_MAP["summary_default"]
    models = response["models"]
    assert response["default_model"] in {model["id"] for model in models}
    assert all(isinstance(model["agents"], list) for model in models)
    assert {model["id"] for model in models} == set(llm_router.MODEL_REGISTRY).intersection(
        llm_router.MODEL_PRICES
    )
    assert response["available"] is True


def test_model_catalog_is_empty_when_metering_is_unconfigured(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        llm_router,
        "get_settings",
        lambda: SimpleNamespace(
            openrouter_api_key="", supabase_url="url", supabase_service_role_key="service",
            llm_daily_spend_cap_usd_micros=1, llm_monthly_spend_cap_usd_micros=1,
            llm_enabled=True,
        ),
    )
    assert _run_immediate(list_models()) == {
        "available": False,
        "default_model": None,
        "models": [],
        "availability_reason": "metering_unavailable",
    }


@pytest.mark.parametrize(
    ("model_id", "expected_temperature"),
    [("anthropic/claude-sonnet-5.5", None), ("openai/gpt-4o-mini", 0.2)],
)
def test_openrouter_constructor_omits_temperature_only_for_anthropic(
    monkeypatch: pytest.MonkeyPatch,
    model_id: str,
    expected_temperature: float | None,
) -> None:
    captured: dict[str, Any] = {}

    class FakeChatOpenAI:
        def __init__(self, **kwargs: Any) -> None:
            captured.update(kwargs)

    module = ModuleType("langchain_openai")
    module.ChatOpenAI = FakeChatOpenAI  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "langchain_openai", module)
    monkeypatch.setattr(
        llm_router,
        "get_settings",
        lambda: SimpleNamespace(
            openrouter_api_key="secret", app_url="https://zenith.test", llm_enabled=True
        ),
    )

    llm_router.get_openrouter_llm(model_id, temperature=0.2, max_tokens=256)

    assert captured["temperature"] is expected_temperature
    assert captured["max_retries"] == 0
    assert captured["extra_body"]["provider"]["max_price"]["prompt"] > 0
    assert captured["default_headers"]["X-OpenRouter-Metadata"] == "enabled"


def test_global_gate_blocks_model_construction_even_with_provider_configuration(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        llm_router,
        "get_settings",
        lambda: SimpleNamespace(openrouter_api_key="configured", llm_enabled=False),
    )
    with pytest.raises(llm_router.LLMDisabledError, match="LLM_ENABLED is false"):
        llm_router.get_llm(agent="summary_default")
    with pytest.raises(llm_router.LLMDisabledError, match="LLM_ENABLED is false"):
        llm_router.get_openrouter_llm("anthropic/claude-sonnet-5.5")


def test_model_catalog_reports_global_gate_without_checking_meter(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        llm_router,
        "get_settings",
        lambda: SimpleNamespace(
            llm_enabled=False,
            openrouter_api_key="configured",
            supabase_url="url",
            supabase_service_role_key="service",
            llm_daily_spend_cap_usd_micros=1,
            llm_monthly_spend_cap_usd_micros=1,
        ),
    )
    assert _run_immediate(list_models()) == {
        "available": False,
        "default_model": None,
        "models": [],
        "availability_reason": "llm_disabled",
    }
