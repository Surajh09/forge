from functools import lru_cache

from supabase import Client, create_client

from app.config import get_settings


@lru_cache
def get_db() -> Client:
    """Supabase client using the service-role key.

    RLS is enabled on every table with no policies, so this key is the only
    path to the data. Tenant isolation is enforced by the repos, which scope
    every query by clerk_org_id.
    """
    settings = get_settings()
    return create_client(settings.supabase_url, settings.supabase_service_role_key)
