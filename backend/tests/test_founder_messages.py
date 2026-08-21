"""A founder never reads a Python exception (P1-7).

Caught live during the sample-product exercise. A run's analysis failed and
the API handed the customer:

    409 {"detail": "RemoteProtocolError: Server disconnected"}

Six pipelines write `f"[{name}] {type(exc).__name__}: {exc}"` into columns the
UI renders. Fixing each writer is the deeper change and should still happen —
a worker that knows what failed can say something far more useful than any
generic sentence. But the serving boundary is the one place every stored
message passes on its way to a person, which makes it the one place the rule
can be enforced rather than remembered.

**The risk this test exists to bound is over-reach.** Replacing a sentence
somebody wrote for a founder with a generic one is a real loss, so the filter
matches the *shape* of an exception rather than the presence of the word
"error". The second block below is the important half.
"""
from __future__ import annotations

import pytest

from app.core.messages import founder_safe, looks_like_a_traceback

FALLBACK = "We could not finish this. Your work is safe — try again."


# ---------------------------------------------------------------------------
# The machine's words, which no founder should see
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("raw", [
    # The one served to a real customer.
    "RemoteProtocolError: Server disconnected",
    # P1-7's canonical example, from the register.
    "[run_simulation] KeyError: 'organization_id'",
    "[website_check] ValueError: not enough values to unpack",
    # What the outbound worker showed before that fix.
    "1 validation error for _Generated\n  Invalid JSON: expected `,` or `}`",
    "2 validation errors for Shortlist",
    "TimeoutError: ",
    "httpx.ReadTimeout: timed out",
    "Traceback (most recent call last):\n  File \"app.py\", line 1",
])
def test_a_raw_exception_is_replaced(raw):
    assert looks_like_a_traceback(raw), f"not recognised as machine text: {raw!r}"
    assert founder_safe(raw, FALLBACK) == FALLBACK


def test_an_empty_or_missing_message_falls_back():
    assert founder_safe(None, FALLBACK) == FALLBACK
    assert founder_safe("", FALLBACK) == FALLBACK
    assert founder_safe("   ", FALLBACK) == FALLBACK


# ---------------------------------------------------------------------------
# The sentences somebody wrote on purpose, which must survive
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("written", [
    # Real messages from this codebase's workers and routes.
    "This run has no measured objections yet, so there is nothing to build "
    "answers from.",
    "https://acme.example/ did not finish loading within 45 seconds. The site "
    "may be slow or blocking automated visits — try again.",
    "We could not finish building your answers. Your run and its objections "
    "are safe — try building it again.",
    "There is no current family-office record to match against.",
    "This check stopped before it finished. Nothing was left half-saved.",
    # The dangerous near-miss: a founder sentence that talks *about* an error.
    "We hit an error reading your page. Try again in a moment.",
    "Something went wrong. Error codes are in the log if you contact us.",
])
def test_a_sentence_written_for_a_founder_is_left_alone(written):
    assert not looks_like_a_traceback(written), (
        f"a founder-readable sentence was mistaken for machine text: {written!r}"
    )
    assert founder_safe(written, FALLBACK) == written


def test_a_word_ending_in_error_mid_sentence_is_not_a_traceback():
    """`ValueError` at the start is machine text. "value error" in prose is
    not, and neither is a sentence that happens to mention one."""
    assert not looks_like_a_traceback(
        "The page returned a ValueError to its own console, which we ignored."
    )


@pytest.mark.parametrize(("module_path", "func"), [
    ("app.api.simulations", "_mark_simulation_failed"),
    ("app.api.clearance", "_mark_clearance_failed"),
])
def test_the_spawn_failure_handlers_no_longer_store_the_exception(module_path, func):
    """These two are the source, not the symptom.

    Both wrote `f"[{name}] {type(exc).__name__}: {exc}"` straight into a
    column the UI renders. The filter at the serving boundary catches what
    they stored; stopping them storing it is the actual fix, and it keeps the
    detail where it is useful — the log.
    """
    import importlib
    import inspect

    module = importlib.import_module(module_path)
    source = inspect.getsource(getattr(module, func))

    assert "type(exc).__name__" not in source or "log." in source, (
        "the exception type is still being written somewhere a founder reads"
    )
    assert '"error_message": f"[{name}]' not in source, (
        f"{module_path}.{func} still stores a raw exception as the founder's "
        f"error message"
    )
    assert "log." in source, "the exception is no longer recorded anywhere"


def test_the_filter_is_wired_into_the_analysis_route():
    """The route that served the real one."""
    import inspect

    from app.api import analysis

    source = inspect.getsource(analysis.simulation_analysis)
    assert "founder_safe" in source, (
        "the analysis route serves its stored error_message unfiltered again"
    )
