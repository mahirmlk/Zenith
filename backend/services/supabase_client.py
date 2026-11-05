"""Async Supabase client (service-role, server-side only).

Routers `await` every query, so this MUST be the async client:
the sync client's `.execute()` is not awaitable (postgrest 2.x).
Service-role bypasses RLS — every query must still enforce tenant
ownership in code (see backend/security/authorization.py).
"""

from config import get_settings

_client = None


async def get_supabase():
    """Async dependency returning a cached AsyncClient."""
    global _client
    if _client is None:
        from supabase import create_async_client

        settings = get_settings()
        if not settings.supabase_url or not settings.supabase_service_role_key:
            raise RuntimeError("Supabase URL and service role key must be configured")
        _client = await create_async_client(
            settings.supabase_url, settings.supabase_service_role_key
        )
    return _client
