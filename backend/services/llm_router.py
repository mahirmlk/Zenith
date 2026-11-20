from __future__ import annotations

from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from langchain_core.language_models.chat_models import BaseChatModel
from config import get_settings
from services.openrouter_catalog import MODEL_PRICES


class LLMDisabledError(RuntimeError):
    """Raised when model-backed features are intentionally gated off."""


def llm_is_enabled(settings: object | None = None) -> bool:
    """Return the single global model-feature switch, failing closed by default."""
    current = settings if settings is not None else get_settings()
    return bool(getattr(current, "llm_enabled", False))


def require_llm_enabled() -> None:
    """Enforce the global gate at every backend provider-call boundary."""
    if not llm_is_enabled():
        raise LLMDisabledError("LLM_ENABLED is false; model-backed features are disabled")

AGENT_MODEL_MAP = {
    # Lifecycle audit 2026-11-13: Anthropic retired Claude Opus 4 on 2026-06-15,
    # and Google shut down Gemini 2.0 Flash on 2026-06-01. These defaults use
    # currently active Anthropic 5.5 and Gemini 3.6 model IDs.
    "orchestrator": "anthropic/claude-opus-5.5",
    "research": "openai/gpt-4o-mini",
    "summary_default": "anthropic/claude-sonnet-5.5",
    "summary_fast": "google/gemini-3.6-flash",
    "memory": "openai/gpt-4o-mini",
}

# Capability registry (update.md §2/§14): the only model IDs a user may
# request, with the agents each is allowed for. Unknown IDs are rejected
# instead of being passed through to a provider (cost/retirement control).
MODEL_REGISTRY: dict[str, dict[str, list[str]]] = {
    "anthropic/claude-opus-5.5": {"agents": ["orchestrator", "summary_default"]},
    "anthropic/claude-sonnet-5.5": {"agents": ["summary_default", "orchestrator"]},
    "openai/gpt-4o": {"agents": ["summary_default", "orchestrator"]},
    "openai/gpt-4o-mini": {"agents": ["research", "memory", "summary_fast"]},
    "google/gemini-3.6-flash": {"agents": ["summary_fast", "research"]},
    "meta-llama/llama-3.3-70b-instruct": {"agents": ["summary_default", "summary_fast"]},
}

def validate_model(model: str | None, agent: str = "summary_default") -> str | None:
    """Return model if allowed for agent, else raise ValueError."""
    if model is None:
        return None
    entry = MODEL_REGISTRY.get(model)
    if entry is None:
        raise ValueError(f"Model not in registry: {model}")
    if model not in MODEL_PRICES:
        raise ValueError(f"Model has no verified spend bound: {model}")
    if agent not in entry["agents"]:
        raise ValueError(f"Model {model} not allowed for agent {agent}")
    return model


def effective_models() -> list[dict[str, object]]:
    """Return only registry entries that can pass the spend admission gate."""
    settings = get_settings()
    from services.openrouter_catalog import MODEL_PRICES

    if (
        not llm_is_enabled(settings)
        or not settings.openrouter_api_key
        or not settings.supabase_url
        or not settings.supabase_service_role_key
        or settings.llm_daily_spend_cap_usd_micros <= 0
        or settings.llm_monthly_spend_cap_usd_micros <= 0
    ):
        return []
    return [
        {"id": model_id, "agents": entry["agents"]}
        for model_id, entry in MODEL_REGISTRY.items()
        if model_id in MODEL_PRICES
    ]


def get_openrouter_llm(
    model: str, temperature: float = 0.3, max_tokens: int = 4096
) -> BaseChatModel:
    require_llm_enabled()
    from langchain_openai import ChatOpenAI

    settings = get_settings()
    if not settings.openrouter_api_key:
        raise RuntimeError("OPENROUTER_API_KEY not configured")
    return ChatOpenAI(  # type: ignore[call-arg]
        base_url="https://openrouter.ai/api/v1",
        api_key=settings.openrouter_api_key,  # type: ignore[arg-type]
        model=model,
        # Anthropic removed temperature from its API. OpenRouter omits `None`
        # from the downstream request body, which also keeps this path valid.
        temperature=None if model.startswith("anthropic/") else temperature,
        max_tokens=max_tokens,
        # One SDK request per meter attempt; application retry loops explicitly
        # reserve a distinct attempt before retrying.
        max_retries=0,
        extra_body={
            "provider": {
                "max_price": {
                    "prompt": MODEL_PRICES[model].max_price_prompt_usd_per_million,
                    "completion": MODEL_PRICES[model].max_price_completion_usd_per_million,
                }
            },
        },
        default_headers={
            "HTTP-Referer": settings.app_url,
            "X-Title": "Zenith",
            "X-OpenRouter-Metadata": "enabled",
        },
    )


def get_llm(
    agent: str = "summary_default",
    model_override: Optional[str] = None,
    temperature: float = 0.3,
    max_tokens: int = 4096,
) -> BaseChatModel:
    if not 1 <= max_tokens <= 4096:
        raise ValueError("max_tokens must be between 1 and 4096")
    if model_override is not None:
        validate_model(model_override, agent)
    require_llm_enabled()
    model = model_override or AGENT_MODEL_MAP.get(agent, AGENT_MODEL_MAP["summary_default"])

    if not get_settings().openrouter_api_key:
        raise RuntimeError("OPENROUTER_API_KEY is required for metered model calls")
    if "/" not in model:
        raise RuntimeError(f"Model is not an OpenRouter model ID: {model}")
    if model not in MODEL_PRICES:
        raise RuntimeError(f"No verified spend bound is available for model: {model}")
    return get_openrouter_llm(model, temperature, max_tokens)
