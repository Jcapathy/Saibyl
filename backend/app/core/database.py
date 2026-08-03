from typing import Any

from supabase import Client, create_client

from app.core.config import settings

# PostgREST caps an unbounded select at 1,000 rows and returns the truncated set
# without erroring. A 250-agent, 10-round run produces well over that, so any
# query that reads a whole simulation must page — see fetch_all.
PAGE_SIZE = 1_000

# Anon client — respects RLS, used for auth-context operations
_supabase_client: Client | None = None

# Admin client — bypasses RLS, used by backend workers
_supabase_admin: Client | None = None


def get_supabase() -> Client:
    global _supabase_client
    if _supabase_client is None:
        _supabase_client = create_client(
            settings.supabase_url,
            settings.supabase_anon_key,
        )
    return _supabase_client


def get_supabase_admin() -> Client:
    global _supabase_admin
    if _supabase_admin is None:
        _supabase_admin = create_client(
            settings.supabase_url,
            settings.supabase_service_role_key,
        )
    return _supabase_admin


def fetch_all(query_builder, page_size: int = PAGE_SIZE) -> list[dict[str, Any]]:
    """Read every row a query matches, paging past PostgREST's 1,000-row cap.

    `query_builder` must be a filtered, ordered select that has not been
    executed. It is re-ranged and re-executed once per page, so the ordering
    must be deterministic or pages will overlap.

    Silent truncation is the failure mode this exists to prevent: an aggregate
    computed over the first 1,000 events of a 2,500-event run looks entirely
    plausible and is wrong.
    """
    rows: list[dict[str, Any]] = []
    offset = 0
    while True:
        page = query_builder.range(offset, offset + page_size - 1).execute().data or []
        rows.extend(page)
        if len(page) < page_size:
            return rows
        offset += page_size
