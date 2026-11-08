from __future__ import annotations

from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from langchain_core.language_models.chat_models import BaseChatModel
from config import get_settings

AGENT_MODEL_MAP = {
    "orchestrator": "anthropic/claude-opus-4",
    "research": "openai/gpt-4o-mini",
    "summary_default": "anthropic/claude-sonnet-4-5",
    "summary_fast": "google/gemini-2.0-flash",
    "memory": "openai/gpt-4o-mini",
}

# Capability registry (update.md §2/§14): the only model IDs a user may
# request, with the agents each is allowed for. Unknown IDs are rejected
# instead of being passed through to a provider (cost/retirement control).
MODEL_REGISTRY: dict[str, dict[str, list[str]]] = {
    "anthropic/claude-opus-4": {"agents": ["orchestrator", "summary_default"]},
    "anthropic/claude-sonnet-4-5": {"agents": ["summary_default", "orchestrator"]},
    "openai/gpt-4o": {"agents": ["summary_default", "orchestrator"]},
    "openai/gpt-4o-mini": {"agents": ["research", "memory", "summary_fast"]},
    "google/gemini-2.5-pro": {"agents": ["summary_default"]},
    "google/gemini-2.0-flash": {"agents": ["summary_fast", "research"]},
    "mistralai/mistral-large": {"agents": ["summary_default"]},
    "meta-llama/llama-3.3-70b-instruct": {"agents": ["summary_default", "summary_fast"]},
    "deepseek/deepseek-r1": {"agents": ["orchestrator"]},
}


def validate_model(model: str | None, agent: str = "summary_default") -> str | None:
    """Return model if allowed for agent, else raise ValueError."""
    if model is None:
        return None
    entry = MODEL_REGISTRY.get(model)
    if entry is None:
        raise ValueError(f"Model not in registry: {model}")
    if agent not in entry["agents"]:
        raise ValueError(f"Model {model} not allowed for agent {agent}")
    return model


def get_openrouter_llm(model: str, temperature: float = 0.3) -> BaseChatModel:
    from langchain_openai import ChatOpenAI

    settings = get_settings()
    if not settings.openrouter_api_key:
        raise RuntimeError("OPENROUTER_API_KEY not configured")
    return ChatOpenAI(  # type: ignore[call-arg]
        base_url="https://openrouter.ai/api/v1",
        api_key=settings.openrouter_api_key,  # type: ignore[arg-type]
        model=model,
        temperature=temperature,
        max_tokens=4096,
        default_headers={
            "HTTP-Referer": settings.app_url,
            "X-Title": "Zenith",
        },
    )


def get_anthropic_llm(model: str = "claude-sonnet-4-5", temperature: float = 0.3) -> BaseChatModel:
    from langchain_anthropic import ChatAnthropic

    settings = get_settings()
    if not settings.anthropic_api_key:
        raise RuntimeError("ANTHROPIC_API_KEY not configured")
    return ChatAnthropic(  # type: ignore[call-arg]
        model=model,
        api_key=settings.anthropic_api_key,  # type: ignore[arg-type]
        temperature=temperature,
        max_tokens=4096,
    )


def get_openai_llm(model: str = "gpt-4o", temperature: float = 0.3) -> BaseChatModel:
    from langchain_openai import ChatOpenAI

    settings = get_settings()
    if not settings.openai_api_key:
        raise RuntimeError("OPENAI_API_KEY not configured")
    return ChatOpenAI(  # type: ignore[call-arg]
        model=model,
        api_key=settings.openai_api_key,  # type: ignore[arg-type]
        temperature=temperature,
        max_tokens=4096,
    )


def get_gemini_llm(model: str = "gemini-2.0-flash", temperature: float = 0.3) -> BaseChatModel:
    from langchain_google_genai import ChatGoogleGenerativeAI

    settings = get_settings()
    if not settings.google_api_key:
        raise RuntimeError("GOOGLE_API_KEY not configured")
    return ChatGoogleGenerativeAI(
        model=model,
        google_api_key=settings.google_api_key,
        temperature=temperature,
        max_output_tokens=4096,
    )


def get_mistral_llm(model: str = "mistral-large-latest", temperature: float = 0.3) -> BaseChatModel:
    from langchain_mistralai import ChatMistralAI
    from pydantic import SecretStr

    settings = get_settings()
    if not settings.mistral_api_key:
        raise RuntimeError("MISTRAL_API_KEY not configured")
    return ChatMistralAI(
        model_name=model,
        api_key=SecretStr(settings.mistral_api_key),
        temperature=temperature,
        max_tokens=4096,
    )


def get_llm(
    agent: str = "summary_default",
    model_override: Optional[str] = None,
    temperature: float = 0.3,
) -> BaseChatModel:
    if model_override is not None:
        validate_model(model_override, agent)
    model = model_override or AGENT_MODEL_MAP.get(agent, AGENT_MODEL_MAP["summary_default"])

    # Try OpenRouter first for any model string that looks like an OpenRouter ID
    if "/" in model:
        try:
            return get_openrouter_llm(model, temperature)
        except RuntimeError:
            pass

    # Fallback to direct providers based on model prefix
    if model.startswith("claude"):
        return get_anthropic_llm(model, temperature)
    if model.startswith("gpt"):
        return get_openai_llm(model, temperature)
    if model.startswith("gemini"):
        return get_gemini_llm(model, temperature)
    if model.startswith("mistral"):
        return get_mistral_llm(model, temperature)

    # Final fallback: OpenAI direct with the given model name
    return get_openai_llm(model, temperature)  # type: ignore[no-any-return,unused-ignore]
