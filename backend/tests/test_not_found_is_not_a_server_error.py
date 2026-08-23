"""A deleted id gets a written refusal, not a 500.

`postgrest`'s `SyncSingleRequestBuilder.execute()` raises `APIError` on any
non-2xx, and PostgREST answers a singular request matching zero rows with
`406 / PGRST116`. So `.data` is never reached, and every

    result = admin.table(...).eq("id", id).single().execute()
    if not result.data:
        raise HTTPException(404, "Simulation not found")

is dead code: the 404 on line two is unreachable. There is no `APIError`
exception handler anywhere in `app/`, so it surfaced as an unhandled **500**.
35 `.single()` calls across 11 API modules carried the same dead guard.

Two consequences. A founder opening a bookmarked or shared link to a run,
report or shortlist that has since been deleted saw a raw server error instead
of a sentence. And the deliberate "a hidden surface must not confirm itself"
404 policy was inverted into server errors — while on launch weekend every
stale id became a Sentry server-fault burying the real ones.
"""
from __future__ import annotations

import httpx
import pytest
from fastapi.routing import APIRoute
from postgrest._sync.request_builder import (
    SyncMaybeSingleRequestBuilder,
    SyncSingleRequestBuilder,
)
from postgrest.exceptions import APIError

from app.core.database import maybe_one

# What PostgREST actually returns for a singular request matching zero rows.
PGRST116 = {
    "code": "PGRST116",
    "details": "The result contains 0 rows",
    "hint": None,
    "message": "JSON object requested, multiple (or no) rows returned",
}


class _ZeroRows:
    """A request whose response is the real 406 body, byte for byte."""

    def send(self):
        return httpx.Response(
            406,
            json=PGRST116,
            request=httpx.Request("GET", "http://x/rest/v1/simulations"),
        )


def test_single_raises_rather_than_answering_with_no_data():
    """The mechanism, proved against the installed library rather than assumed."""
    with pytest.raises(APIError) as caught:
        SyncSingleRequestBuilder(_ZeroRows()).execute()

    assert caught.value.code == "PGRST116"


def test_maybe_one_answers_with_no_data_instead():
    """And `maybe_one` normalises the `None` that `.maybe_single()` returns,
    which is its own foot-gun: `None.data` is an `AttributeError`, i.e. a 500
    again."""
    assert SyncMaybeSingleRequestBuilder(_ZeroRows()).execute() is None

    class _Query:
        def maybe_single(self):
            return SyncMaybeSingleRequestBuilder(_ZeroRows())

    result = maybe_one(_Query())

    assert result is not None
    assert result.data is None
    # The guard every call site already had now actually runs.
    assert not result.data


def test_a_row_that_does_exist_still_comes_back():
    class _One:
        def maybe_single(self):
            class _R:
                data = {"id": "sim-1"}

                def execute(self):
                    return self
            return _R()

    assert maybe_one(_One()).data == {"id": "sim-1"}


# `app.api.reports` still reads rows through `.single()` — 8 call sites, the
# same dead 404 under every one of them.
#
# It is excluded here because that module was being edited by another change in
# the same release and converting it from here would have overwritten that work,
# not because the defect is different there. It is not: `GET /api/reports/{id}`
# for a deleted report is a 500 today, exactly as `GET /api/simulations/{id}`
# was.
#
# **Delete this line when `reports.py` moves to `maybe_one`, and the scan below
# covers it with no other change.** Naming the module rather than the seven
# routes is deliberate: a new route added to `reports.py` inherits the
# exemption, but a new route anywhere else fails immediately.
_KNOWN_UNCONVERTED_MODULES = {"app.api.reports"}


def test_no_api_handler_reads_a_row_through_single():
    """The rule, over the whole router tree, so the next one fails here.

    Scanned rather than listed: 35 call sites is exactly the size at which a
    hand-maintained list misses one, and the last three rounds of this review
    were all defects that came from a fix applied to one of two places.
    """
    import inspect

    from app.main import create_app

    offenders = []
    for route in create_app().routes:
        if not isinstance(route, APIRoute):
            continue
        if getattr(route.endpoint, "__module__", "") in _KNOWN_UNCONVERTED_MODULES:
            continue
        try:
            source = inspect.getsource(route.endpoint)
        except (OSError, TypeError):
            continue
        if ".single()" in source:
            offenders.append(f"{sorted(route.methods)[0]} {route.path}")

    assert not offenders, (
        f"handlers whose not-found path is a 500 rather than a 404: {offenders}"
    )


def test_the_exemption_still_describes_something_real():
    """A stale exemption is worse than none: it silently covers a fixed module.

    When `reports.py` is converted this fails, and the fix is to delete the
    exemption — which is the whole point of asserting it from both sides.
    """
    import inspect

    from app.api import reports

    assert ".single()" in inspect.getsource(reports), (
        "app.api.reports no longer uses .single() — remove it from "
        "_KNOWN_UNCONVERTED_MODULES so the scan covers it"
    )
