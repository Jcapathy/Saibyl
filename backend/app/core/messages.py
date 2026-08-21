# PUBLIC INTERFACE
# ─────────────────────────────────────────────────────────
# founder_safe(message, fallback) -> str
# looks_like_a_traceback(message) -> bool
# ─────────────────────────────────────────────────────────
"""A founder never reads a Python exception.

P1-7 in the pre-launch register: six pipelines write
`f"[{name}] {type(exc).__name__}: {exc}"` into a column the UI renders, which
is how somebody ends up reading `KeyError: 'organization_id'` in monospace on
a page they paid for. Caught live during the sample-product exercise, where a
run's analysis failed and the API returned:

    409 {"detail": "RemoteProtocolError: Server disconnected"}

**Why this is a filter and not six edits.** Fixing each writer is the deeper
change and should still happen — a worker that knows *what* failed can say
something far more useful than any generic sentence. But there are six of
them, new ones keep being written, and every one is a place to forget. The
serving boundary is the one place every stored message passes through on its
way to a person, so it is the one place the rule can be enforced rather than
remembered.

**What it does not do.** It does not touch messages that were written for a
founder — the great majority, and the good pattern this codebase already
uses. It replaces only text that is recognisably a machine's, and the raw text
stays in the database, where we can still read it.
"""
from __future__ import annotations

import re

# `RemoteProtocolError: Server disconnected`
# `[run_simulation] KeyError: 'organization_id'`
# `1 validation error for _Generated`
_RAW_EXCEPTION = re.compile(
    r"""
    ^\s*
    (?:\[[^\]]+\]\s*)?          # an optional [worker_name] tag
    (?:
        # A class name by convention: KeyError, RemoteProtocolError,
        # httpx.ReadTimeout. `Timeout` is in the list because httpx and
        # asyncio both name exceptions that way and neither ends in "Error".
        [A-Za-z_][A-Za-z0-9_.]* (?:Error|Exception|Warning|Timeout)\b
        # A dotted module path followed by a class name and a colon —
        # `httpx.ReadTimeout:`, `pydantic_core._pydantic_core.ValidationError:`.
        # Prose does not produce this shape.
      | [a-z_][A-Za-z0-9_]* (?:\.[A-Za-z0-9_]+)+ \s*:
      | \d+\s+validation\s+errors?\s+for\b
    )
    """,
    re.VERBOSE,
)

_TRACEBACK_MARKERS = (
    "Traceback (most recent call last)",
    "\n  File \"",
    "pydantic.dev/",
)


def looks_like_a_traceback(message: str) -> bool:
    """Is this text a machine talking to a machine?

    Deliberately narrow. A false positive costs a founder a specific sentence
    somebody wrote for them and replaces it with a general one, which is a
    real loss — so the pattern matches the *shape* of an exception at the
    start of the string, not merely the presence of the word "error"
    somewhere in it. "We hit an error reading your page" is a sentence and
    must survive.
    """
    if not message:
        return False
    if any(marker in message for marker in _TRACEBACK_MARKERS):
        return True
    return bool(_RAW_EXCEPTION.match(message))


def founder_safe(message: str | None, fallback: str) -> str:
    """The message to show a person, given whatever was stored."""
    text = (message or "").strip()
    if not text:
        return fallback
    return fallback if looks_like_a_traceback(text) else text
