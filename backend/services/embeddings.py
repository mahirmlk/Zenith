import httpx
import uuid
from typing import List
from config import get_settings
from services.retry import async_retry
from services.openrouter_catalog import EMBEDDING_MODEL, embedding_cost_micros
from services.spend_meter import (
    BillingContext,
    mark_unknown,
    reserve_embedding_attempt,
    settle_embedding_attempt,
)
from services.llm_router import require_llm_enabled

EMBED_MODEL = EMBEDDING_MODEL
EMBED_DIM = 1536
OPENAI_EMBED_URL = "https://api.openai.com/v1/embeddings"

# Shared async client with connection pooling
_http_client: httpx.AsyncClient | None = None


def _get_client() -> httpx.AsyncClient:
    global _http_client
    if _http_client is None or _http_client.is_closed:
        _http_client = httpx.AsyncClient(timeout=30.0, limits=httpx.Limits(max_connections=10))
    return _http_client


async def _embed(texts: List[str], context: BillingContext) -> List[List[float]]:
    require_llm_enabled()
    settings = get_settings()
    if not settings.openai_api_key:
        raise RuntimeError("OPENAI_API_KEY not configured for embeddings")

    byte_lengths = [len(text.encode("utf-8")) for text in texts]
    if any(size > 8_160 for size in byte_lengths):
        raise ValueError("Embedding input exceeds the metered per-input token bound")
    input_bound = sum(byte_lengths) + len(texts) * 32
    if input_bound > 300_000:
        raise ValueError("Embedding request exceeds the metered batch token bound")
    attempt_id = str(uuid.uuid4())
    await reserve_embedding_attempt(
        context=context, attempt_id=attempt_id, max_input_tokens=input_bound
    )
    try:
        client = _get_client()
        r = await client.post(
            OPENAI_EMBED_URL,
            headers={
                "Authorization": f"Bearer {settings.openai_api_key}",
                "Content-Type": "application/json",
            },
            json={"input": texts, "model": EMBED_MODEL, "user": context.subject_id},
        )
        r.raise_for_status()
        data = r.json()
        actual_model = data.get("model")
        usage = data.get("usage", {})
        tokens = usage.get("total_tokens") if isinstance(usage, dict) else None
        if actual_model != EMBED_MODEL or isinstance(tokens, bool) or not isinstance(tokens, int) or tokens < 0:
            raise RuntimeError("Embedding response omitted authoritative model or token usage")
        await settle_embedding_attempt(
            attempt_id=attempt_id,
            tokens=tokens,
            actual_cost_micros=embedding_cost_micros(tokens),
        )
        return [item["embedding"] for item in data["data"]]
    except BaseException as exc:
        await mark_unknown(attempt_id, type(exc).__name__)
        raise


async def embed_texts(
    texts: List[str], *, context: BillingContext | None = None
) -> List[List[float]]:
    """Embed a list of texts, retrying transient OpenAI API errors."""
    billing = context or BillingContext("system", str(uuid.uuid4()), "operator_embedding")
    return await async_retry(
        lambda: _embed(texts, billing), max_retries=3, base_delay=1.0
    )


async def embed_text(text: str, *, context: BillingContext | None = None) -> List[float]:
    results = await embed_texts([text], context=context)
    return results[0]
