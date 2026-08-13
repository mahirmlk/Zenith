import httpx
from typing import List
from config import get_settings
from services.retry import async_retry

EMBED_MODEL = "text-embedding-3-small"
EMBED_DIM = 1536
OPENAI_EMBED_URL = "https://api.openai.com/v1/embeddings"

# Shared async client with connection pooling
_http_client: httpx.AsyncClient | None = None


def _get_client() -> httpx.AsyncClient:
    global _http_client
    if _http_client is None or _http_client.is_closed:
        _http_client = httpx.AsyncClient(timeout=30.0, limits=httpx.Limits(max_connections=10))
    return _http_client


async def _embed(texts: List[str]) -> List[List[float]]:
    settings = get_settings()
    if not settings.openai_api_key:
        raise RuntimeError("OPENAI_API_KEY not configured for embeddings")

    client = _get_client()
    r = await client.post(
        OPENAI_EMBED_URL,
        headers={
            "Authorization": f"Bearer {settings.openai_api_key}",
            "Content-Type": "application/json",
        },
        json={"input": texts, "model": EMBED_MODEL},
    )
    r.raise_for_status()
    data = r.json()
    return [item["embedding"] for item in data["data"]]


async def embed_texts(texts: List[str]) -> List[List[float]]:
    """Embed a list of texts, retrying transient OpenAI API errors."""
    return await async_retry(lambda: _embed(texts), max_retries=3, base_delay=1.0)


async def embed_text(text: str) -> List[float]:
    results = await embed_texts([text])
    return results[0]
