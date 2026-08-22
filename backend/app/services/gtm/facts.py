# PUBLIC INTERFACE
# ─────────────────────────────────────────────────────────
# scrub_unsourced(payload, material) -> (payload, list[str])
# sourced_numbers(material) -> set[str]
# count_placeholders(text) -> int
# MISSING_NUMBER, MISSING_EXAMPLE
# ─────────────────────────────────────────────────────────
"""Numbers in GTM copy that the material never contained.

All three builders already carry the rule, in almost identical words:

    Where a response needs a number, a customer name, a case study or a
    benchmark that is not in the input, write exactly [TODO: your number] or
    [TODO: your example]. Never invent a statistic, a customer, or a
    comparison.

All three overrode it, on live runs, in copy meant to be sent to strangers:

- *"We track this — customers are seeing 10+ hours per month back"* — for a
  product at `pre_launch_positioning`, which has no customers.
- *"We built volume pricing into the model"* — for a product with none. The
  ICP's own gaps list had asked whether volume discounts existed; the system
  asked the question and then answered it with an invention.
- *"You don't pay for the 500 hours it takes to tune an in-house system"* —
  the string "500" appears nowhere in 110,575 characters of source material.
- *"your model's safety layer catches 80% of attacks… the other 20%"* — the
  80% was real but a buyer said it about **their own hand-built regex filter**;
  the 20% appears nowhere.
- *"the difference between a $3,600/year luxury and actual reconciliation
  relief"* — 12× off the founder's stated price, laundered in from one
  agent's arithmetic slip and then quoted as evidence in four sequences.

**Why the quotes are clean and the prose is not.** Every `_Generated` model in
this package deliberately has no quote field: quotes are attached afterwards
from measured rows, so a model-invented quote has nowhere to land. It works —
159 of 159 and 80 of 80 quotes were verbatim across two audits. The free prose
beside them had no such boundary. This module is that boundary.

**What it does on a hit.** It substitutes `MISSING_NUMBER`, which is precisely
what the prompt asked the model to write in the first place. That is better
than dropping the sentence (which mangles sendable copy) and better than a
warning nobody reads: the placeholder is visible in the artifact, it is
counted in `placeholders_to_fill`, and it turns a false claim into an honest
blank the founder can fill.

**What counts as a claim.** Money, percentages, and a number carrying a unit
of time — the three shapes every fabrication above wears. A bare count is
ignored, so "three things to say next" survives untouched; replacing that with
a placeholder would be its own kind of damage.
"""
from __future__ import annotations

import re

from pydantic import BaseModel

#: What the model was told to write when the material is silent. Defined here
#: so the prompts, the substitution and the counter cannot drift apart.
MISSING_NUMBER = "[TODO: your number]"
MISSING_EXAMPLE = "[TODO: your example]"

_TIME_UNIT = (
    r"seconds?|minutes?|hours?|days?|weeks?|months?|quarters?|years?"
    r"|hrs?|mins?"
)

#: A number anywhere, for reading the material.
_ANY_NUMBER = re.compile(r"\d[\d,]*(?:\.\d+)?\s*[km]?\b", re.I)

#: A span that makes a claim. Whole spans are replaced rather than the digits
#: inside them, so a range never degrades into "[TODO: your number]-50 hours".
_CLAIM_SPAN = re.compile(
    r"(?:"
    # money, with optional k/m and an optional range partner
    r"[$£€]\s?\d[\d,]*(?:\.\d+)?\s*[km]?"
    r"(?:\s*[-–—]\s*[$£€]?\s?\d[\d,]*(?:\.\d+)?\s*[km]?)?"
    r"|"
    # percentage, with an optional range partner
    r"\d[\d,]*(?:\.\d+)?\s*(?:[-–—]\s*\d[\d,]*(?:\.\d+)?\s*)?%"
    r"|"
    # a number carrying a unit of time: "17 hours", "30-50 hours", "45-minute"
    r"\d[\d,]*(?:\.\d+)?\s*\+?"
    r"(?:\s*[-–—]\s*\d[\d,]*(?:\.\d+)?\s*\+?)?"
    r"[\s-]*(?:" + _TIME_UNIT + r")\b"
    r")",
    re.I,
)

_DIGITS = re.compile(r"\d[\d,]*(?:\.\d+)?\s*[km]?", re.I)

#: A meeting length is not a claim about the product, and this copy is full of
#: them — "Can we book 20 minutes?", "a 30-minute intro". Scrubbing those
#: produces "Can we book [TODO: your number]?", which is worse than the thing
#: being prevented: a nonsense blank in the one line that asks for the meeting.
#: Distinguished by context, not by length, so "a 45-minute manual hunt" — an
#: actual invented benchmark — is still caught.
_BOOKING_BEFORE = re.compile(
    r"(?:book|grab|spare|schedule|hop on|jump on|set up|carve out|"
    r"give (?:me|us)|steal)\W+$",
    re.I,
)
_MEETING_AFTER = re.compile(
    r"^\W*(?:call|chat|meeting|demo|intro|conversation|sync|slot|window)\b", re.I
)
_CONTEXT_CHARS = 26

_PLACEHOLDER = re.compile(r"\[TODO:[^\]]*\]", re.I)


def _key(raw: str) -> str:
    """A number reduced to what makes it the same number.

    `$1,200`, `1200` and `1.2k` are one figure; separators and magnitude
    suffixes are notation. Trailing zeros go too, so material stating `2.9`
    covers copy writing `2.90`.
    """
    text = raw.strip().lower().replace(",", "").replace(" ", "")
    multiplier = 1
    if text.endswith("k"):
        multiplier, text = 1_000, text[:-1]
    elif text.endswith("m"):
        multiplier, text = 1_000_000, text[:-1]
    try:
        value = float(text) * multiplier
    except ValueError:
        return text
    if value.is_integer():
        return str(int(value))
    return f"{value:.6f}".rstrip("0").rstrip(".")


def sourced_numbers(material: str) -> set[str]:
    """Every number the generator was actually shown."""
    return {_key(raw) for raw in _ANY_NUMBER.findall(material or "") if raw.strip()}


def _scrub_text(text: str, sourced: set[str], replaced: list[str]) -> str:
    """One string, with unsupported claim spans replaced by the placeholder."""
    if not text:
        return text

    def _one(match: re.Match[str]) -> str:
        span = match.group(0)
        before = text[max(0, match.start() - _CONTEXT_CHARS) : match.start()]
        after = text[match.end() : match.end() + _CONTEXT_CHARS]
        if _BOOKING_BEFORE.search(before) or _MEETING_AFTER.match(after):
            return span
        numbers = [n for n in _DIGITS.findall(span) if n.strip()]
        if numbers and all(_key(n) in sourced for n in numbers):
            return span
        replaced.append(span.strip())
        return MISSING_NUMBER

    return _CLAIM_SPAN.sub(_one, text)


def scrub_unsourced[M: BaseModel](payload: M, material: str) -> tuple[M, list[str]]:
    """The generated payload with invented figures turned into placeholders.

    Walks every string in the model, including nested lists and dicts, because
    the shapes differ across the three builders and a field list would rot the
    first time one gained a sentence.

    Safe to run on a `_Generated` model specifically: those carry no quote
    fields by construction, so the buyers' own words — which legitimately
    contain numbers the material also contains — are never reached from here.
    """
    sourced = sourced_numbers(material)
    replaced: list[str] = []

    def walk(value: object) -> object:
        if isinstance(value, str):
            return _scrub_text(value, sourced, replaced)
        if isinstance(value, list):
            return [walk(item) for item in value]
        if isinstance(value, dict):
            return {key: walk(item) for key, item in value.items()}
        return value

    scrubbed = walk(payload.model_dump())
    return type(payload).model_validate(scrubbed), replaced


def count_placeholders(text: str) -> int:
    """How many blanks the founder still has to fill.

    Counts the *shape*, not two specific literals. The previous version matched
    only `[TODO: your number]` and `[TODO: your example]`, so artifacts
    reported `placeholders_to_fill: 0` while carrying `[TODO: validated time
    savings]`, `[TODO: benchmark hours saved]`, `[TODO: customer name]` and
    `[TODO: entity count]` — a counter that says zero is worse than no counter,
    because a founder reads it as a promise that the copy is ready to send.
    """
    return len(_PLACEHOLDER.findall(text or ""))
