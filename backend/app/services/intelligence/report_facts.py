# PUBLIC INTERFACE
# ─────────────────────────────────────────────────────────
# unsourced_figures(evidence, answer) -> list[UnsourcedFigure]
# figure_complaint(figures) -> str
# UnsourcedFigure
# ─────────────────────────────────────────────────────────
"""Figures a report section states that its own evidence never contained.

`REACT_PROMPT` already carries this rule, under a heading that says it is not
style guidance:

    Every sentiment, stance, intensity, or objection figure you state MUST
    come from simulation_analytics.

It is ignored. Two live runs on 2026-08-22 produced paid sections whose
numbers contradicted the artifact they were drawn from:

- A platform table reported **Reddit -0.35 / Twitter-X -0.19**. The measured
  values were **twitter_x -0.4653 (80.56% oppose)** and **reddit -0.091
  (41.03% oppose)** — both invented, and the *direction reversed*. The
  section's entire thesis was built on the inversion, and its two block
  quotes were attributed to the wrong platform and the wrong round.
- Another reported "**~6 buyers engaged on both platforms**" in a run where
  each agent posts to exactly one platform, "~13 of 25 and ~18 of 25 active"
  (31 of 25 people), and "5 of 8 / 6 of 8" (11 of 8).

The tell is consistent and worth naming: **the numbers are exact wherever the
model is reading a field, and invented wherever the narrative needs one.**
Section 1, written straight off the headline block, was correct in both runs.
So this is not a model that cannot count — it is a model filling a rhetorical
slot, and no wording of the instruction fixes that. The same lesson as
`website/claims.py`: when a prompt has already been overridden, the answer is
a verifier, not a better sentence.

**The contract this checks.** A section is written by a ReACT loop whose
`evidence` list holds the seeded measured findings plus every tool observation
returned to it. That string is *precisely* what the model was shown, including
its truncation. So a figure the model states and the evidence does not contain
is one the model supplied itself.

**What is checked, and what deliberately is not.** Only figures wearing the
clothes of a measurement:

- **decimals** — sentiment means, confidence bounds, deltas
- **percentages** — stance splits, shares
- **"N of M" counts** — "13 of 25 people"

Bare integers are ignored on purpose. A report is thick with round numbers,
list positions, years and archetype counts, and flagging those would bury a
real finding under noise. All four fabrications above are caught by the three
shapes above.

**Rounding is not fabrication.** A stated figure is sourced when *some*
evidence value rounds to it at the precision written: `-0.47` is supported by
a measured `-0.4653`, and `81%` by `80.56`. Percentages also match a
proportion, so `80.56%` is supported by `0.8056`. Only a figure that no
measured value can round to is reported.
"""
from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation

from pydantic import BaseModel

#: Never send more than this many to the model or record more than this many.
#: A section that trips dozens has one systemic problem, not thirty.
MAX_FIGURES = 20

#: Below this, there is nothing to check against and everything would be
#: reported. A section with no evidence has a different problem.
MIN_EVIDENCE_CHARS = 200

_QUOTE_CHARS = 200


class UnsourcedFigure(BaseModel):
    """One measured-looking figure with no basis in the section's evidence."""

    kind: str  # "decimal" | "percentage" | "count"
    text: str  # the figure as written
    quote: str  # the sentence it sits in


# Any number at all, for building the sourced set out of tool observations.
# Commas are thousands separators here, never decimal points — the evidence is
# JSON and English, not a European locale.
_ANY_NUMBER = re.compile(r"-?\d[\d,]*(?:\.\d+)?")

# What gets checked in the answer. `~` and `−` (the real minus sign, which
# models emit in prose) are folded before matching.
#
# `(?!\d)` on the decimal is load-bearing and was missing at first: without it
# the engine backtracks to satisfy the percent lookahead, matching "80.5"
# inside "80.56%" — a figure nobody wrote, reported as a fabrication, in the
# one place precision matters most.
#
# The two lookbehinds stop a *range* being read as a negative number.
# `_normalise` folds en-dashes to hyphens, so the correctly-reported CI
# "0.659–0.765" became "0.659-0.765" and the upper bound was read as -0.765 —
# absent from the evidence, and duly reported as invented. Both figures were
# right, and the section that wrote them had followed the measurement rules
# exactly. A minus sign directly after a digit, or after a digit and a space,
# is a range separator.
_DECIMAL = re.compile(r"(?<!\d)(?<!\d )-?\d[\d,]*\.\d+(?!\d)(?!\s*%)")
_PERCENT = re.compile(r"-?\d[\d,]*(?:\.\d+)?(?=\s*%)")
_COUNT_OF = re.compile(r"\b(\d[\d,]*)\s+(?:of|out of)\s+(\d[\d,]*)\b", re.I)

# Where a *share* may legitimately come from. Checking percentages against
# every number in the evidence is useless: a run of 25 agents licenses "25%",
# 3 rounds licenses "3%", and the fabricated "~25% accept" sailed through on
# exactly that coincidence. A percentage is sourced only by a value that is
# itself a share — written with a % sign, or held by a field named like one.
#: `95% CI` is a confidence label, not a share, and `REACT_PROMPT` *requires*
#: that exact format ("-0.42 (95% CI -0.61 to -0.23, 47 people)"). Left in, it
#: fires on every correctly-written section — the worst kind of false positive,
#: because it punishes the sections that followed the rules.
_CONFIDENCE_LABEL = re.compile(
    r"(-?\d[\d,]*(?:\.\d+)?)\s*%\s*(?:ci\b|c\.i\.|confidence)", re.I
)

_PCT_IN_TEXT = re.compile(r"(-?\d[\d,]*(?:\.\d+)?)\s*%")
_PCT_FIELD = re.compile(
    r'"[a-z0-9_]*(?:pct|percent|rate|ratio|share)[a-z0-9_]*"\s*:\s*'
    r"(-?\d[\d,]*(?:\.\d+)?)",
    re.I,
)


def _to_decimal(raw: str) -> Decimal | None:
    try:
        return Decimal(raw.replace(",", ""))
    except (InvalidOperation, ValueError):
        return None


def _normalise(text: str) -> str:
    """Fold the characters that make the same figure look like two."""
    return (
        (text or "")
        .replace("−", "-")  # U+2212, which models use in prose
        .replace("–", "-")
        .replace("—", "-")
        .replace("~", "")
        .replace("≈", "")
    )


def sourced_values(evidence: str) -> set[Decimal]:
    """Every number the section was actually shown."""
    values: set[Decimal] = set()
    for raw in _ANY_NUMBER.findall(_normalise(evidence)):
        value = _to_decimal(raw)
        if value is not None:
            values.add(value)
    return values


def sourced_shares(evidence: str) -> set[Decimal]:
    """Values in the evidence that are actually shares.

    Deliberately narrow. The alternative — matching a percentage against every
    number present — is what let "Reddit ~25% accept" pass on a run that
    happened to have 25 agents. When the evidence contains no share at all,
    percentage checking is skipped rather than guessed at.
    """
    text = _normalise(evidence)
    values: set[Decimal] = set()
    for raw in _PCT_IN_TEXT.findall(text) + _PCT_FIELD.findall(text):
        value = _to_decimal(raw)
        if value is not None:
            values.add(value)
    return values


def _places(written: str) -> int:
    """Decimal places in the figure as the model chose to write it."""
    cleaned = written.replace(",", "")
    return len(cleaned.split(".", 1)[1]) if "." in cleaned else 0


def _supported(stated: Decimal, written: str, sourced: set[Decimal],
               *, as_percentage: bool = False) -> bool:
    """Whether any measured value rounds to what was written.

    Rounding at the *stated* precision is the whole trick. A model that reads
    -0.4653 and writes "-0.47" has reported the measurement; one that writes
    "-0.35" has not, and no amount of tolerance should blur those together.
    """
    places = _places(written)
    for value in sourced:
        try:
            if round(value, places) == stated:
                return True
            # A share may be shown either way round: 80.56 or 0.8056.
            if as_percentage and round(value * 100, places) == stated:
                return True
        except (InvalidOperation, ValueError):
            continue
    return False


def _sentence_around(haystack: str, start: int, end: int) -> str:
    """The sentence holding a figure, so a founder can find it."""
    left = max((haystack.rfind(m, 0, start) for m in (". ", "\n", "! ", "? ")), default=-1)
    left = 0 if left == -1 else left + 1
    rights = [p for p in (haystack.find(m, end) for m in (". ", "\n", "! ", "? ")) if p != -1]
    right = min(rights) + 1 if rights else min(len(haystack), end + _QUOTE_CHARS)
    quote = " ".join(haystack[left:right].split())
    if len(quote) <= _QUOTE_CHARS:
        return quote
    offset = max(0, (start - left) - 60)
    return "…" + quote[offset : offset + _QUOTE_CHARS].strip() + "…"


def unsourced_figures(evidence: str, answer: str) -> list[UnsourcedFigure]:
    """Measured-looking figures in `answer` absent from `evidence`.

    Pure: no model call, no network, no database. Same inputs, same findings.
    """
    text = _normalise(answer or "")
    if not text.strip() or len((evidence or "").strip()) < MIN_EVIDENCE_CHARS:
        return []

    sourced = sourced_values(evidence)
    if not sourced:
        return []

    found: list[UnsourcedFigure] = []
    seen: set[tuple[str, str]] = set()

    def _add(kind: str, written: str, start: int, end: int) -> None:
        key = (kind, written)
        if key in seen:
            return
        seen.add(key)
        found.append(
            UnsourcedFigure(kind=kind, text=written, quote=_sentence_around(text, start, end))
        )

    # Counts first: "18 of 25" is read as a pair, so its parts are not then
    # re-reported as loose numbers.
    for match in _COUNT_OF.finditer(text):
        for group in (1, 2):
            written = match.group(group)
            stated = _to_decimal(written)
            if stated is not None and not _supported(stated, written, sourced):
                _add("count", match.group(0), match.start(), match.end())
                break

    for match in _DECIMAL.finditer(text):
        written = match.group(0)
        stated = _to_decimal(written)
        if stated is not None and not _supported(stated, written, sourced):
            _add("decimal", written, match.start(), match.end())

    shares = sourced_shares(evidence)
    if shares:
        labels = {m.start(1) for m in _CONFIDENCE_LABEL.finditer(text)}
        for match in _PERCENT.finditer(text):
            if match.start() in labels:
                continue
            written = match.group(0)
            stated = _to_decimal(written)
            if stated is not None and not _supported(
                stated, written, shares, as_percentage=True
            ):
                _add("percentage", written + "%", match.start(), match.end())

    order = {"decimal": 0, "percentage": 1, "count": 2}
    found.sort(key=lambda f: (order.get(f.kind, 9), f.text))
    return found[:MAX_FIGURES]


# ── the correction pass ──────────────────────────────────────────────

_COMPLAINT_HEAD = """\
STOP — the section you just wrote states figures that appear nowhere in the
evidence you were given. Each line below is a number you supplied yourself:"""

_COMPLAINT_TAIL = """\
Rewrite the section. For every figure above: replace it with the measured
value from the evidence, or remove the sentence that depends on it. Do not
substitute a different invented number, and do not estimate one by reading
post text — if the evidence does not contain the figure, the honest section
does not state it.

This matters more than it looks. These numbers sit under bold **Evidence:**
headings in a document a founder pays for and makes decisions from. A reversed
sentiment score is not a rounding slip; it tells them the opposite of what the
room actually did.

Keep every figure that was already correct, keep the structure, and return the
corrected section as ANSWER: followed by the markdown."""


def figure_complaint(figures: list[UnsourcedFigure]) -> str:
    """The retry's complaint, quoting the section's own sentences back at it."""
    lines = [_COMPLAINT_HEAD, ""]
    for figure in figures:
        lines.append(f'- {figure.text} — you wrote: "{figure.quote}"')
    lines += ["", _COMPLAINT_TAIL]
    return "\n".join(lines)
