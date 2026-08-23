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
- **"N of M" counts** — "13 of 25 people". Checked two ways: both halves must
  be in the evidence, *and* N must not exceed M. Membership on its own is
  nearly inert on real evidence, which is integer-rich enough — the seeded
  findings carry a count for every objection — to contain almost any small
  number the model reaches for. "31 of 25 people" is impossible whatever the
  evidence holds, and that is the half that does not depend on luck.

  What is deliberately *not* checked is whether counts sharing a denominator
  sum past it. "18 of 25 raised pricing and 13 of 25 raised the migration" is
  ordinary correct reporting — an objection count is per objection, and people
  raise more than one — so a sum rule would fire on the sections that read the
  evidence properly. That is the false positive this file cannot afford, since
  every hit spends an Opus call and can swap a correct section for a shorter
  one.

Bare integers are ignored on purpose. A report is thick with round numbers,
list positions, years and archetype counts, and flagging those would bury a
real finding under noise. All four fabrications above are caught by the three
shapes above.

**Rounding is not fabrication.** A stated figure is sourced when *some*
evidence value rounds to it at the precision written: `-0.47` is supported by
a measured `-0.4653`, and `81%` by `80.56`. Percentages also match a
proportion, so `80.56%` is supported by `0.8056`. Only a figure that no
measured value can round to is reported.

**Neither is arithmetic on measured values.** Two shapes are derived, not
invented, and the first version of this file called both fabrications — on the
one sentence form that *three* separate prompts mandate:

- **The sign lives in the verb.** `_supported` compares signed Decimals, and
  English does not: "Sentiment declined 0.44 points across the run" reports a
  measured `trajectory_delta` of **-0.44**. `REPORT_SYSTEM_PROMPT` rule 3 and
  `CONCLUSION_PROMPT` both require exactly that sentence. So a magnitude is
  sourced by a measured value of either sign.
- **A difference between two measured values is a measurement.** "Sentiment
  hit -0.62 on Reddit against -0.11 on Hacker News — a 0.51 gap between the
  two" is `EXECUTIVE_SUMMARY_PROMPT` Part B's own worked example, word for
  word, and 0.51 appears nowhere in any artifact. So a figure that is the
  difference of two *other measured figures the same sentence already states*
  is sourced.

  Sentence-local on purpose, and this is the half worth defending. Differencing
  every pair in the evidence would license nearly any decimal in range — a
  6,000-character findings blob holds hundreds of numbers — and turn the
  checker off while leaving it switched on. The mandated shape states both
  operands and their gap in one breath, so that is all this reads. A gap whose
  operands are themselves invented is not rescued: an operand must be sourced
  before it can anchor anything.

Both are one-sided by design: they can only ever *clear* a figure. The four
fabrications that shipped are still caught, and each is pinned in
`test_report_facts`.
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


#: A `-` that directly follows a digit or a `%` is a *range separator*, never a
#: sign. `_normalise` folds en-dashes to hyphens, so the correctly-reported CI
#: "0.659–0.765" arrives here as "0.659-0.765"; without this the upper bound
#: read as -0.765, absent from the evidence and duly reported as invented.
#:
#: It guards **every** number pattern in this module, because the first version
#: of this fix guarded one of them and the identical defect stayed in the other
#: three:
#:
#: - `_DECIMAL` carried `(?<!\d)(?<!\d )`. The second lookbehind blocked the
#:   match at the `-` whenever a digit and a space preceded it, so the engine
#:   restarted one character later and read the sign off: "Round 3 -0.41" — the
#:   round-by-round form `REACT_PROMPT` requires — reported a measured -0.41 as
#:   an invented +0.41, and a correct monotonic arc came back with every figure
#:   in it flagged.
#: - `_PERCENT` had no guard at all, so "(95% CI 12.3%-45.6%, n=25 agents)" —
#:   the exact string `_scoreboard_block` writes — yielded "-45.6".
#: - `_ANY_NUMBER` and `_PCT_IN_TEXT` read the *evidence*, and must split a
#:   range the same way, or a bound the model quoted correctly is missing from
#:   the sourced set and is reported anyway.
#:
#: A `-` after a space is still a sign: "-0.42 (95% CI -0.61 to -0.23)" is the
#: format the prompt mandates, and every figure in it survives.
_NOT_A_SIGN = r"(?<![\d%])"

# Any number at all, for building the sourced set out of tool observations.
# Commas are thousands separators here, never decimal points — the evidence is
# JSON and English, not a European locale.
_ANY_NUMBER = re.compile(_NOT_A_SIGN + r"-?\d[\d,]*(?:\.\d+)?")

# What gets checked in the answer. `~` and `−` (the real minus sign, which
# models emit in prose) are folded before matching.
#
# `(?!\d)` on the decimal is load-bearing and was missing at first: without it
# the engine backtracks to satisfy the percent lookahead, matching "80.5"
# inside "80.56%" — a figure nobody wrote, reported as a fabrication, in the
# one place precision matters most.
_DECIMAL = re.compile(_NOT_A_SIGN + r"-?\d[\d,]*\.\d+(?!\d)(?!\s*%)")
_PERCENT = re.compile(_NOT_A_SIGN + r"-?\d[\d,]*(?:\.\d+)?(?=\s*%)")
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

_PCT_IN_TEXT = re.compile(_NOT_A_SIGN + r"(-?\d[\d,]*(?:\.\d+)?)\s*%")
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

    Sign is the one thing not compared, because English does not put it in the
    number. "Sentiment declined 0.44 points across the run" — the shape
    `REPORT_SYSTEM_PROMPT` rule 3 and `CONCLUSION_PROMPT` both mandate — states
    a measured `trajectory_delta` of -0.44 with the sign carried by the verb,
    and was reported as an invention. This is also the standing repair for the
    sign-parsing bugs `_NOT_A_SIGN` documents: every one of them showed up as a
    measured value flagged with its sign read off.

    What it gives up, stated plainly: a section that writes a measured -0.4653
    as "+0.4653" is no longer reported. That was never this check's job — it
    reports figures with no basis in the evidence, and both shipped inversions
    were caught because the *values* were invented, not because their signs
    were wrong. Trading a sign-only miss for a false alarm on every correctly
    written trajectory sentence is the right side of that trade.
    """
    places = _places(written)
    for value in sourced:
        for candidate in (value, -value):
            try:
                if round(candidate, places) == stated:
                    return True
                # A share may be shown either way round: 80.56 or 0.8056.
                if as_percentage and round(candidate * 100, places) == stated:
                    return True
            except (InvalidOperation, ValueError):
                continue
    return False


def _sentence_span(haystack: str, start: int, end: int) -> tuple[int, int]:
    """Bounds of the sentence holding a figure.

    One definition, shared by the founder-facing quote and by the derived-figure
    check below, so the sentence a complaint quotes is exactly the sentence its
    operands were read from.
    """
    left = max((haystack.rfind(m, 0, start) for m in (". ", "\n", "! ", "? ")), default=-1)
    left = 0 if left == -1 else left + 1
    rights = [p for p in (haystack.find(m, end) for m in (". ", "\n", "! ", "? ")) if p != -1]
    right = min(rights) + 1 if rights else min(len(haystack), end + _QUOTE_CHARS)
    return left, right


def _sentence_around(haystack: str, start: int, end: int) -> str:
    """The sentence holding a figure, so a founder can find it."""
    left, right = _sentence_span(haystack, start, end)
    quote = " ".join(haystack[left:right].split())
    if len(quote) <= _QUOTE_CHARS:
        return quote
    offset = max(0, (start - left) - 60)
    return "…" + quote[offset : offset + _QUOTE_CHARS].strip() + "…"


#: How many measured operands in one sentence get paired up. Pairing is
#: quadratic and a "sentence" with no terminator is whatever text is within
#: `_QUOTE_CHARS` of the figure, so this is a ceiling, not a target: the shape
#: being recognised states two operands and their gap, and a third rarely
#: helps.
_MAX_DERIVED_ANCHORS = 8

#: A number written as a share, so an operand may be checked against the
#: evidence's shares as well as its raw values.
_TRAILING_PCT = re.compile(r"[ \t]*%")


def _derived_from_sentence(
    stated: Decimal,
    written: str,
    text: str,
    start: int,
    end: int,
    sourced: set[Decimal],
    shares: set[Decimal],
) -> bool:
    """Whether the figure is the gap between two measured values beside it.

    "Sentiment hit -0.62 on Reddit against -0.11 on Hacker News — a 0.51 gap
    between the two" is `EXECUTIVE_SUMMARY_PROMPT` Part B's worked example, and
    0.51 is in no artifact anywhere: it is -0.11 minus -0.62. Same for the
    mandated "declined 0.59 points from -0.05 to -0.64", and for "ran 28.1
    points above" a stated pair of shares. An arithmetic difference between two
    measured values is not a fabrication, and flagging it spends an Opus call
    to talk the model out of the comparison the founder paid for.

    Both operands must be *stated in the same sentence* and each must itself be
    sourced. That is what keeps this from becoming a hole: differencing every
    pair in the evidence would license nearly any decimal in range, and a gap
    resting on invented operands is still reported — the operands as
    fabrications, the gap along with them.
    """
    left, right = _sentence_span(text, start, end)
    sentence = text[left:right]
    places = _places(written)

    anchors: list[Decimal] = []
    for match in _ANY_NUMBER.finditer(sentence):
        if left + match.start() == start:
            continue  # a figure is not its own operand
        raw = match.group(0)
        value = _to_decimal(raw)
        if value is None:
            continue
        if _supported(value, raw, sourced) or (
            shares
            and _TRAILING_PCT.match(sentence, match.end())
            and _supported(value, raw, shares, as_percentage=True)
        ):
            anchors.append(value)
            if len(anchors) >= _MAX_DERIVED_ANCHORS:
                break

    for index, first in enumerate(anchors):
        for second in anchors[index + 1 :]:
            for difference in (first - second, second - first):
                try:
                    if round(difference, places) == stated:
                        return True
                except (InvalidOperation, ValueError):
                    continue
    return False


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
        part = _to_decimal(match.group(1))
        whole = _to_decimal(match.group(2))

        # The arithmetic, before the membership check. "31 of 25 people" is
        # impossible whatever the evidence holds, and membership alone cannot
        # see that: real evidence is integer-rich — the seeded measured
        # findings carry an objection count for every objection — so both
        # halves of an invented pair are almost always present somewhere in it,
        # and the check was inert on every run that was not hand-trimmed.
        if part is not None and whole is not None and part > whole:
            _add("count", match.group(0), match.start(), match.end())
            continue

        for group in (1, 2):
            written = match.group(group)
            stated = _to_decimal(written)
            if stated is not None and not _supported(stated, written, sourced):
                _add("count", match.group(0), match.start(), match.end())
                break

    # The derived-figure escape applies to decimals and percentages alike, and
    # is wired into both branches deliberately: "a 0.51 gap" and "28.1 points
    # above" are the same sentence written twice, and the mandated form puts
    # the gap on either side of the % sign depending on what is being compared.
    shares = sourced_shares(evidence)

    for match in _DECIMAL.finditer(text):
        written = match.group(0)
        stated = _to_decimal(written)
        if stated is None or _supported(stated, written, sourced):
            continue
        if _derived_from_sentence(
            stated, written, text, match.start(), match.end(), sourced, shares
        ):
            continue
        _add("decimal", written, match.start(), match.end())

    if shares:
        labels = {m.start(1) for m in _CONFIDENCE_LABEL.finditer(text)}
        for match in _PERCENT.finditer(text):
            if match.start() in labels:
                continue
            written = match.group(0)
            stated = _to_decimal(written)
            if stated is None or _supported(
                stated, written, shares, as_percentage=True
            ):
                continue
            if _derived_from_sentence(
                stated, written, text, match.start(), match.end(), sourced, shares
            ):
                continue
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
