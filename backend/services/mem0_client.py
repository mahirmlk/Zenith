import asyncio
from functools import lru_cache
from mem0 import MemoryClient
from config import get_settings


@lru_cache
def _get_client_cached() -> MemoryClient:
    settings = get_settings()
    if not settings.mem0_api_key:
        raise RuntimeError("MEM0_API_KEY not configured")
    return MemoryClient(api_key=settings.mem0_api_key)


def _get_client() -> MemoryClient:
    return _get_client_cached()


def _get_user_profile_sync(user_id: str) -> list[dict]:
    return _get_client().get_all(user_id=user_id)


def _add_memory_sync(user_id: str, messages: list[dict]) -> None:
    _get_client().add(messages, user_id=user_id)


async def get_user_profile(user_id: str) -> list[dict]:
    return await asyncio.to_thread(_get_user_profile_sync, user_id)


async def add_memory(user_id: str, messages: list[dict]) -> None:
    await asyncio.to_thread(_add_memory_sync, user_id, messages)
