from mem0 import MemoryClient
from config import get_settings

_client: MemoryClient | None = None


def get_mem0_client() -> MemoryClient:
    global _client
    if _client is None:
        settings = get_settings()
        if not settings.mem0_api_key:
            raise RuntimeError("MEM0_API_KEY not configured")
        _client = MemoryClient(api_key=settings.mem0_api_key)
    return _client


def get_user_profile(user_id: str) -> list[dict]:
    client = get_mem0_client()
    return client.get_all(user_id=user_id)


def add_memory(user_id: str, messages: list[dict]) -> None:
    client = get_mem0_client()
    client.add(messages, user_id=user_id)
