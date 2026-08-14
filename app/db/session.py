from supabase import create_client, Client
from app.core.config import settings

def get_supabase_client() -> Client:
    url: str = settings.SUPABASE_URL
    # We use the Service Role Key here so the backend can bypass RLS for administrative actions,
    # or you can use the Anon key if you want RLS to apply based on JWTs passed to Supabase.
    key: str = settings.SUPABASE_SERVICE_ROLE_KEY or settings.SUPABASE_ANON_KEY
    if not url or not key:
        raise ValueError("Supabase credentials not found in environment variables.")
    return create_client(url, key)
