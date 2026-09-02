"""Server-side Marine Supabase client construction."""

from functools import lru_cache

from supabase import Client, create_client

from app.config import get_settings


class SupabaseConfigurationError(RuntimeError):
    pass


@lru_cache
def get_supabase_client() -> Client:
    settings = get_settings()
    if not settings.supabase_url or not settings.supabase_secret_key:
        raise SupabaseConfigurationError("Marine Supabase credentials are not configured.")
    return create_client(
        settings.supabase_url,
        settings.supabase_secret_key.get_secret_value(),
    )

