from typing import Optional
from langchain_core.language_models.chat_models import BaseChatModel
from config import get_settings

AGENT_MODEL_MAP = {
    "orchestrator": "anthropic/claude-opus-4",
    "research": "openai/gpt-4o-mini",
    "summary_default": "anthropic/claude-sonnet-4-5",
    "summary_fast": "google/gemini-2.0-flash",
    "memory": "openai/gpt-4o-mini",
}


def get_openrouter_llm(model: str, temperature: float = 0.3) -> BaseChatModel:
    from langchain_openai import ChatOpenAI

    settings = get_settings()
    if not settings.openrouter_api_key:
        raise RuntimeError("OPENROUTER_API_KEY not configured")
    return ChatOpenAI(
        base_url="https://openrouter.ai/api/v1",
        api_key=settings.openrouter_api_key,
        model=model,
        temperature=temperature,
        max_tokens=4096,
        default_headers={
            "HTTP-Referer": settings.app_url,
            "X-Title": "AI Paper Research Agent",
        },
    )


def get_anthropic_llm(model: str = "claude-sonnet-4-5", temperature: float = 0.3) -> BaseChatModel:
    from langchain_anthropic import ChatAnthropic

    settings = get_settings()
    if not settings.anthropic_api_key:
        raise RuntimeError("ANTHROPIC_API_KEY not configured")
    return ChatAnthropic(
        model=model,
        api_key=settings.anthropic_api_key,
        temperature=temperature,
        max_tokens=4096,
    )


def get_openai_llm(model: str = "gpt-4o", temperature: float = 0.3) -> BaseChatModel:
    from langchain_openai import ChatOpenAI

    settings = get_settings()
    if not settings.openai_api_key:
        raise RuntimeError("OPENAI_API_KEY not configured")
    return ChatOpenAI(
        model=model,
        api_key=settings.openai_api_key,
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

    settings = get_settings()
    if not settings.mistral_api_key:
        raise RuntimeError("MISTRAL_API_KEY not configured")
    return ChatMistralAI(
        model=model,
        api_key=settings.mistral_api_key,
        temperature=temperature,
        max_tokens=4096,
    )


def get_llm(
    agent: str = "summary_default",
    model_override: Optional[str] = None,
    temperature: float = 0.3,
) -> BaseChatModel:
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
    return get_openai_llm(model, temperature)
