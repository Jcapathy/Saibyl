from types import SimpleNamespace
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


def new_auth_client() -> Client:
    """A throwaway anon client for one request's auth call.

    **Never `get_supabase()` for anything that signs a user in.** That client is
    a process-wide singleton and supabase-auth stores the session *on the
    client*: `sign_in_with_password` ends in `self._save_session(...)`, and so
    does the `_call_refresh_token` behind `refresh_session`. So the one shared
    object holds whichever user authenticated most recently, for everyone.

    That is a tenancy hole, not an inefficiency. `auth.sign_out()` takes no
    argument — it reads `self.get_session()` and revokes *that* token globally —
    so Alice pressing Log Out at 10:02 revoked Bob's refresh tokens on every
    device because Bob had logged in at 10:01, and left Alice's own token live.

    A fresh client per request has no shared session to confuse: each one holds
    only the session its own call created and is discarded with the response.
    Login, refresh and logout are all rate-limited and rare, so the cost is one
    client construction on a path that is already making a network round-trip.
    """
    return create_client(
        settings.supabase_url,
        settings.supabase_anon_key,
    )


def get_supabase_admin() -> Client:
    global _supabase_admin
    if _supabase_admin is None:
        _supabase_admin = create_client(
            settings.supabase_url,
            settings.supabase_service_role_key,
        )
    return _supabase_admin


# What `maybe_one` answers with when the query matched nothing. A stand-in
# rather than `None`, so every `if not result.data:` guard already written
# against `.single()` keeps working unchanged.
_NO_ROW = SimpleNamespace(data=None)


def maybe_one(query_builder):
    """Execute a query that expects one row; answer `data=None` if there is none.

    **`.single()` does not do this, and every `if not result.data: raise 404`
    written under one is dead code.** PostgREST answers a singular request
    matching zero rows with `406 PGRST116`, and postgrest-py's
    `SyncSingleRequestBuilder.execute()` raises `APIError` on any non-2xx — so
    `.data` is never reached. There is no `APIError` exception handler anywhere
    in `app/`, so it surfaced as an unhandled **500**: `GET /api/simulations/
    <uuid-that-does-not-exist>` returned a server error, not the written
    refusal sitting on the next line. 35 `.single()` calls across 11 API modules
    had the same dead guard.

    Two things followed. A founder opening a bookmarked or shared link to a run,
    report or shortlist that has since been deleted got a raw 500 instead of a
    sentence. And the deliberate "a hidden surface must not confirm itself" 404
    policy — `admin.py`, the crisis flag, the capital/answer-pack/messaging-doc
    detail routes — was inverted into server errors, while on launch weekend
    every stale id also became a Sentry server-fault burying the real ones.

    `.maybe_single()` swallows exactly the zero-row case ("The result contains 0
    rows") and nothing else: more than one row still raises, as it should, and
    so does every other API error. It returns `None` rather than a response,
    which is its own foot-gun — `result.data` on `None` is an `AttributeError`
    and therefore a 500 again — so this wrapper is the only way it is called.

    Usage is the same shape as before, minus the `.single()`:

        result = maybe_one(admin.table("simulations").select("*").eq("id", id))
        if not result.data:
            raise HTTPException(404, "Simulation not found")
    """
    return query_builder.maybe_single().execute() or _NO_ROW


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
