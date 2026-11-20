from __future__ import annotations

import asyncio
from functools import lru_cache
from typing import TYPE_CHECKING, Any, cast

if TYPE_CHECKING:
    from mem0 import MemoryClient
from config import get_settings
from services.llm_router import llm_is_enabled, require_llm_enabled


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
    require_llm_enabled()
    if not get_settings().mem0_provider_spend_limit_confirmed:
        raise RuntimeError("Mem0 model usage is disabled until its provider spend limit is confirmed")
    return cast(list[MemoryRecord], _get_client().get_all(user_id=user_id))


def _add_memory_sync(user_id: str, messages: list[MemoryRecord]) -> None:
    require_llm_enabled()
    if not get_settings().mem0_provider_spend_limit_confirmed:
        raise RuntimeError("Mem0 model usage is disabled until its provider spend limit is confirmed")
    _get_client().add(messages, user_id=user_id)


async def get_user_profile(user_id: str) -> list[MemoryRecord]:
    return await asyncio.to_thread(_get_user_profile_sync, user_id)


async def add_memory(user_id: str, messages: list[MemoryRecord]) -> None:
    await asyncio.to_thread(_add_memory_sync, user_id, messages)


def is_configured() -> bool:
    """Whether model-backed Mem0 usage has explicit provider-side spend control."""
    settings = get_settings()
    return bool(llm_is_enabled(settings) and settings.mem0_api_key and settings.mem0_provider_spend_limit_confirmed)


def model_features_enabled() -> bool:
    """Whether the global gate permits model-backed optional services."""
    return llm_is_enabled()


def has_credentials() -> bool:
    """Whether service operations such as deletion can reach Mem0."""
    return bool(get_settings().mem0_api_key)


def _delete_user_memories_sync(user_id: str) -> Any:
    # Mem0's Platform MemoryClient supports delete_all(user_id=...). Keep the
    # user filter explicit so account deletion cannot cross tenant boundaries.
    return _get_client().delete_all(user_id=user_id)


async def delete_user_memories(user_id: str) -> None:
    """Delete every Mem0 memory for this user; errors must reach the caller."""
    await asyncio.to_thread(_delete_user_memories_sync, user_id)
