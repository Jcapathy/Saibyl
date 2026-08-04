# PUBLIC INTERFACE
# ─────────────────────────────────────────────────────────
# post_ref(raw)   -> str   — an adapter-side post id an agent typed back
# key_ref(raw)    -> str   — a canonical objection key
# enum_ref(raw, allowed, default=None) -> str | None
# slugify(label)  -> str   — the one definition of key derivation
# DECORATION
# ─────────────────────────────────────────────────────────
"""Normalising values a language model handed back.

**One module, because the alternative has already cost this codebase months.**

Every adapter renders its feed as `[<id>] @author: text` and asks for
`COMMENT <post_id>: …`. The model copies the id *with the brackets it was shown
in* — inconsistently, which is worse than always, because a five-sample check
comes back clean. Every `if p.id == post_id` in the package then failed silently:
reactions never landed, feed ranking degraded to recency-only, and 193 of 193
reply links were lost. Nothing errored, for months.

That was fixed at the adapter boundary. The audit that followed found the same
shape in roughly forty more places, because **the pressure is structural**: any
value we render into a prompt and ask for back will come back decorated the way
we displayed it. Objection keys shown as `[key] label`. Archetype ids shown as
`id (Label)`. Reaction verbs shown pipe-joined. Intent values shown in a list.

So the normalisers live together, and callers import them rather than each
inventing a `.strip()`. The rule this module exists to enforce:

> **A lookup miss and a legitimate absence must not be the same value.**

Nearly every defect the audit found was a `.get()` default, a `continue`, or an
`if/elif` with no `else` — the value was not merely wrong, it was *indistinguishable
from nothing being there*, so no counter moved and the health logs reported
success. `enum_ref` returns `None` on a miss and expects the caller to count it.
"""
from __future__ import annotations

import re

# What a model wraps around a value it was shown in brackets, quotes or a list.
# Edge-stripped only — deliberately not a character filter, because a stray
# separator *inside* an id means the parse was wrong and should be visible
# rather than silently repaired into a plausible different id.
DECORATION = "[]()<>{}\"'`,.:;!? \t\n"


def post_ref(raw: object) -> str:
    """An adapter-side post id an agent typed back, stripped of decoration.

    Mirrors `BasePlatformAdapter.post_ref`, which delegates here so the strip
    set has exactly one definition. It previously appeared as a literal in two
    files; if those drift, the 193-of-193 failure returns silently.
    """
    return str(raw or "").strip(DECORATION)


def slugify(label: str) -> str:
    """The one definition of how a label becomes a key.

    `inoculation.py` had a second, incompatible one — `"-".join(s.lower().split())`
    against the canonicalizer's `re.sub(r"[^a-z0-9]+", "-", ...)`. A *verbatim
    identical* objection produced two different keys, so the loop's
    "agents who changed their mind" list was always empty and the docstring
    excused it as approximate by design. It was not approximate; it was broken.
    """
    slug = re.sub(r"[^a-z0-9]+", "-", str(label).lower()).strip("-")
    return slug[:60] or "objection"


def key_ref(raw: object) -> str:
    """A canonical objection key, normalised for comparison.

    Priors are rendered to the model as ``  {key} — "{label}"``, so the key
    comes back backticked, title-cased, or as the label sitting next to it on
    the same line — the identical copy-back pressure that produced `[<post_id>]`.

    Re-slugged rather than merely stripped, so `Too-Expensive` and
    `too-expensive` resolve together. Callers should try the exact key first,
    then this, then this against `slugify(prior_label)`.
    """
    return slugify(post_ref(raw))


def enum_ref(
    raw: object,
    allowed: set[str] | frozenset[str] | tuple[str, ...],
    default: str | None = None,
) -> str | None:
    """A closed-vocabulary value from a model, or `default` when unrecognised.

    Handles the three ways a model restates a member of a list it was shown:
    surrounding decoration, casing, and `-`/`_`/space interchange.

    **Returns `default` (None unless given) on a miss rather than guessing.** The
    caller is expected to count misses — an unrecognised value that silently
    becomes a valid one is how four adversarial roles collapsed into one bloc,
    and how every Facebook `ANGRY.` became a `LIKE`, inverting the backlash
    signal the product measures.
    """
    cleaned = post_ref(raw).casefold()
    if not cleaned:
        return default
    if cleaned in allowed:
        return cleaned

    # `-`/`_`/space are interchangeable in every vocabulary we render.
    canonical = re.sub(r"[\s\-]+", "_", cleaned)
    if canonical in allowed:
        return canonical
    hyphenated = canonical.replace("_", "-")
    if hyphenated in allowed:
        return hyphenated
    return default
