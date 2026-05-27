from functools import lru_cache
from supabase import create_client, Client
from config import get_settings


@lru_cache
def get_supabase() -> Client:
    settings = get_settings()
    if not settings.supabase_url or not settings.supabase_service_role_key:
        raise RuntimeError("Supabase URL and service role key must be configured")
    return create_client(settings.supabase_url, settings.supabase_service_role_key)
