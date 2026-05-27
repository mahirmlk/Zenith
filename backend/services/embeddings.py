import httpx
from typing import List
from config import get_settings

EMBED_MODEL = "text-embedding-3-small"
EMBED_DIM = 1536
OPENAI_EMBED_URL = "https://api.openai.com/v1/embeddings"


async def embed_texts(texts: List[str]) -> List[List[float]]:
    settings = get_settings()
    if not settings.openai_api_key:
        raise RuntimeError("OPENAI_API_KEY not configured for embeddings")

    async with httpx.AsyncClient() as client:
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


async def embed_text(text: str) -> List[float]:
    results = await embed_texts([text])
    return results[0]
