"""A revision that never reached a model does not keep 5,000 credits.

`POST /website/revision` deducts 5,000 at create — the most expensive artifact
in the product, against the check's 1,750 — and `run_page_revision` has four
ways to end before `generate_revision` is ever entered:

  - the check it builds on is not finished,
  - `capture_website(url)` raises (the founder's own page is slow to wake),
  - the admired site's capture raises,
  - the admired site answers with a bot wall under `MIN_REFERENCE_DOM_CHARS`.

`grep -c refund revision_tasks.py` was **0**. The check worker beside it has
refunded the byte-for-byte identical `WebsiteCaptureError` branch since the day
that defect was found there — "the founder was being told to try again at the
same price for work we had not done" — and the same fix was never carried one
file over. The reaper cannot cover the gap either: `page_revisions` refunds only
from `queued`, and the row is `generating` before the first capture.

The gate is `_record_failure` having landed. The reaper refunds a `queued`
`page_revisions` row it closes, nothing on the row records that a refund was
paid, and a wedged capture can raise here after that has already happened — so
whoever wins the compare-and-set owns the outcome, and the loser pays nothing.
"""
from __future__ import annotations

import inspect

import pytest

from app.workers import revision_tasks, website_tasks

ORG = "11111111-1111-1111-1111-111111111111"
REV = "55555555-5555-5555-5555-555555555555"


class _Recorder:
    def __init__(self) -> None:
        self.refunds: list[tuple[str, int, str]] = []


@pytest.fixture
def spy(monkeypatch) -> _Recorder:
    rec = _Recorder()
    monkeypatch.setattr(
        revision_tasks, "refund_credits",
        lambda org, credits, *, reason: rec.refunds.append((str(org), credits, reason)),
    )
    return rec


def test_a_capture_that_never_loaded_the_page_gives_the_5000_back(spy):
    revision_tasks._refund_before_any_model_call(
        REV, ORG, {"credits_charged": 5000},
        reason="revision_capture_failed_before_any_model_call",
    )

    assert spy.refunds == [
        (ORG, 5000, "revision_capture_failed_before_any_model_call")
    ]


def test_a_revision_row_with_no_recorded_charge_refunds_nothing(spy):
    """`credits_charged` absent must not grant credits out of thin air."""
    revision_tasks._refund_before_any_model_call(
        REV, ORG, {}, reason="revision_capture_failed_before_any_model_call"
    )

    assert spy.refunds == [(ORG, 0, "revision_capture_failed_before_any_model_call")]


def test_every_pre_model_exit_in_the_revision_worker_refunds():
    """Pinned on the source, like the check worker's twin test, because standing
    up the worker, its Supabase client and a browser runtime would test the mocks.

    What matters is which `return`s are covered. All four of these sit above
    `generate_revision`, so no `llm_vision` call and no critic has run at any of
    them.
    """
    source = inspect.getsource(revision_tasks.run_page_revision)
    pre_model = source[: source.index("generate_revision(")]

    # Every early exit above the model call is guarded-and-refunded.
    assert pre_model.count("_refund_before_any_model_call(") == 4, (
        "a pre-model exit in the revision worker keeps the founder's 5,000 credits"
    )
    # And each one is gated on the close having landed, never fired blind.
    assert "if _record_failure(" in pre_model
    assert pre_model.count("if _record_failure(") == 4


def test_the_revision_refund_stops_at_the_model_call():
    """A revision that dies inside `generate_revision` has spent real vision
    calls. A rule that quietly sometimes pays is worse than one that says
    plainly when it does."""
    source = inspect.getsource(revision_tasks.run_page_revision)
    after_model = source[source.index("generate_revision("):]

    assert "_refund_before_any_model_call(" not in after_model, (
        "a revision that had already spent on the model was refunded anyway"
    )


def test_the_close_is_what_authorises_the_refund():
    """`_record_failure` returns whether *this* call closed the row.

    The reaper refunds `page_revisions` from `queued`; a worker that paid
    without checking would hand back 10,000 against a 5,000 charge.
    """
    assert (
        inspect.signature(revision_tasks._record_failure).return_annotation == "bool"
    )
    source = inspect.getsource(revision_tasks._record_failure)
    assert "return _advance(" in source


def test_both_workers_refund_every_capture_that_precedes_a_model_call():
    """The twin, stated as one rule over both files.

    The check worker refunded its own page's capture failure and not the
    admired site's — but nothing has been spent at either: `upload_screenshots`
    and `run_critic_gauntlet` are both below them, and `capture_website` starts
    a browser, not a model. A founder whose admired site turned a reader away
    was charged 1,750 credits for it.
    """
    for worker, entry in (
        (website_tasks, website_tasks.run_website_check),
        (revision_tasks, revision_tasks.run_page_revision),
    ):
        source = inspect.getsource(entry)
        # Everything above the first model-touching call.
        boundary = min(
            i for i in (
                source.find("run_critic_gauntlet("),
                source.find("generate_revision("),
            ) if i != -1
        )
        pre_model = source[:boundary]
        captures = pre_model.count("except WebsiteCaptureError")
        refunds = pre_model.count("refund_credits(") + pre_model.count(
            "_refund_before_any_model_call("
        )
        assert refunds >= captures, (
            f"{worker.__name__}: {captures} capture-failure exits before any "
            f"model call, only {refunds} of them refund"
        )
        # And what is handed back is the row's real charge, never a constant.
        assert "credits_charged" in inspect.getsource(worker), (
            f"{worker.__name__}: the refund does not read the recorded charge"
        )
