from __future__ import annotations

import asyncio
from functools import lru_cache
from typing import TYPE_CHECKING, Any, cast

if TYPE_CHECKING:
    from mem0 import MemoryClient
from config import get_settings


@lru_cache
def _get_client_cached() -> MemoryClient:
    from mem0 import MemoryClient

    settings = get_settings()
    if not settings.mem0_api_key:
        raise RuntimeError("MEM0_API_KEY not configured")
    return MemoryClient(api_key=settings.mem0_api_key)


def _get_client() -> MemoryClient:
    return _get_client_cached()


MemoryRecord = dict[str, Any]


def _get_user_profile_sync(user_id: str) -> list[MemoryRecord]:
    return cast(list[MemoryRecord], _get_client().get_all(user_id=user_id))


def _add_memory_sync(user_id: str, messages: list[MemoryRecord]) -> None:
    _get_client().add(messages, user_id=user_id)


async def get_user_profile(user_id: str) -> list[MemoryRecord]:
    return await asyncio.to_thread(_get_user_profile_sync, user_id)


async def add_memory(user_id: str, messages: list[MemoryRecord]) -> None:
    await asyncio.to_thread(_add_memory_sync, user_id, messages)


def is_configured() -> bool:
    """Whether user memories are stored in the configured Mem0 service."""
    return bool(get_settings().mem0_api_key)


def _delete_user_memories_sync(user_id: str) -> Any:
    # Mem0's Platform MemoryClient supports delete_all(user_id=...). Keep the
    # user filter explicit so account deletion cannot cross tenant boundaries.
    return _get_client().delete_all(user_id=user_id)


async def delete_user_memories(user_id: str) -> None:
    """Delete every Mem0 memory for this user; errors must reach the caller."""
    await asyncio.to_thread(_delete_user_memories_sync, user_id)
