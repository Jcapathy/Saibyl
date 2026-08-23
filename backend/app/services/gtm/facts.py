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
    # money, with optional k/m and an optional range partner.
    #
    # `[km]\b`, not `[km]?` — the same boundary `_DIGITS` needed and this
    # pattern did not get. Without it the span eats the first letter of the
    # next word: "$35 kit" matched as "$35 k", which keys as 35,000, is absent
    # from the material, and so scrubbed a correctly-sourced price *and* left
    # "[TODO: your number]it" in shipped copy.
    r"[$£€]\s?\d[\d,]*(?:\.\d+)?(?:\s*[km]\b)?"
    r"(?:\s*[-–—]\s*[$£€]?\s?\d[\d,]*(?:\.\d+)?(?:\s*[km]\b)?)?"
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

#: `[km]\b` and not `[km]?` — without the boundary this reads "8 months" as
#: "8 m", i.e. eight million, and then reports a duration the material plainly
#: states as unsourced.
_DIGITS = re.compile(r"\d[\d,]*(?:\.\d+)?\s*(?:[km]\b)?", re.I)

#: A meeting length is not a claim about the product, and this copy is full of
#: them — "Can we book 20 minutes?", "a 30-minute intro". Scrubbing those
#: produces "Can we book [TODO: your number]?": a nonsense blank in the one
#: line that has to work, and it catches nothing, because a meeting length was
#: never a claim.
#:
#: The first version of this exemption anchored on the characters immediately
#: before the number, and a live check found it failing on most real copy —
#: "set up **a** 30-minute call" defeated it with an article, and "worth",
#: "takes" and "got" were not verbs it knew. Eight damaged meeting asks reached
#: generated sequences. It now searches a window rather than anchoring, and the
#: verb list carries the words outbound copy actually uses.
_BOOKING_BEFORE = re.compile(
    r"(?:book|book in|grab|spare|schedule|hop on|jump on|set up|carve out|"
    r"give (?:me|us)|steal|worth|takes?|got|get|have|spend|free up|block|"
    r"find|need|want)\b",
    re.I,
)

#: A bare meeting length standing as its own clause — "15 minutes—let's settle
#: it.", "(20 minutes, free tier)". Both halves of the verb-before /
#: noun-after test fail here by construction: the sentence split leaves
#: `before` empty and the punctuation that follows carries no noun. Two of
#: these reached sendable copy, one of them a line meant to be read down a
#: phone. A duration alone in a clause is an offer of time, not a claim about
#: a product — nothing measurable is being asserted.
_STANDS_ALONE = re.compile(r"^\s*[—–\-,)(]|^\s*$")

#: A lookback or lookahead window in a request — "the worst denial you've seen
#: in the last 6 months", "anything in the next two weeks". Not a claim about
#: the product, and scrubbing it leaves a sentence that asks for nothing.
_WINDOW_BEFORE = re.compile(
    r"(?:in|over|within|during)\s+the\s+(?:last|past|next|coming)\s*$"
    r"|(?:^|\s)(?:last|past|next|coming)\s+$",
    re.I,
)
_MEETING_AFTER = re.compile(
    r"(?:call|chat|meeting|demo|intro|conversation|sync|slot|window|"
    r"walkthrough|screen ?share|session)\b",
    re.I,
)
_CONTEXT_CHARS = 34

#: A rate is always a claim and can never be a meeting ask. This is what keeps
#: the widened verb list above from swallowing real fabrications: "Most
#: controllers **spend** 30-50 hours **a month**" contains a booking verb, and
#: is still checked, because no one books a meeting "a month".
_RATE_AFTER = re.compile(
    r"^\W*(?:an?|per|each|every)\s+(?:day|week|month|quarter|year|hour)\b", re.I
)

#: A meeting is minutes, or an hour or two. The other half of the guard: it
#: stops "tuning **takes** 500 hours" being exempted by its verb, while leaving
#: "**takes** 15 minutes" alone.
_SENTENCE_SPLIT = re.compile(r"[.!?\n]")

#: Every "<number> <time unit>" the material states, so a duration can be
#: matched on both halves rather than on its digits alone. The range form is
#: read as two pairs: "15-20 hours" sources both 15 hours and 20 hours.
_DURATION_IN_TEXT = re.compile(
    r"(\d[\d,]*(?:\.\d+)?)\s*(?:[-–—]\s*\d[\d,]*(?:\.\d+)?\s*)?\+?[\s-]*"
    r"(" + _TIME_UNIT + r")\b",
    re.I,
)
_DURATION_RANGE = re.compile(
    r"(\d[\d,]*(?:\.\d+)?)\s*[-–—]\s*(\d[\d,]*(?:\.\d+)?)\s*\+?[\s-]*"
    r"(" + _TIME_UNIT + r")\b",
    re.I,
)

_MINUTE_UNIT = re.compile(r"\b(?:minutes?|mins?|seconds?|secs?)\b", re.I)
_HOUR_UNIT = re.compile(r"\bhours?|hrs?\b", re.I)
MAX_MEETING_HOURS = 2

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


def _canonical_unit(unit: str) -> str:
    """`hrs`, `Hours`, `hour` are one unit."""
    text = unit.strip().lower().rstrip(".")
    text = {"hrs": "hour", "hr": "hour", "mins": "minute", "min": "minute",
            "secs": "second", "sec": "second"}.get(text, text)
    return text[:-1] if text.endswith("s") else text


def sourced_durations(material: str) -> set[tuple[str, str]]:
    """Durations the material states, as (number, unit) pairs.

    A duration has to match **both halves**. Checking the digits alone meant
    material containing "8 months" and "12 years" licensed a cold email
    claiming clinics "bleed **8-12 days** waiting on prior auth" — a market
    benchmark nobody had measured, assembled out of two unrelated numbers. The
    number is not the claim; the number *and its unit* are.
    """
    text = material or ""
    pairs: set[tuple[str, str]] = set()
    for raw, unit in _DURATION_IN_TEXT.findall(text):
        pairs.add((_key(raw), _canonical_unit(unit)))
    # A range states both ends: "15-20 hours a month" sources 15 hours and 20
    # hours, so copy quoting either end is reporting what the buyer said.
    for low, high, unit in _DURATION_RANGE.findall(text):
        canonical = _canonical_unit(unit)
        pairs.add((_key(low), canonical))
        pairs.add((_key(high), canonical))
    return pairs


def _is_meeting_ask(span: str, before: str, after: str) -> bool:
    """Whether this span asks for someone's time rather than claiming a fact.

    Three conditions, and all of them are load-bearing:

    1. **Not a rate.** "a month", "per week" — nobody books a meeting for a
       month. This is what allows the verb list to be generous: "controllers
       spend 30-50 hours a month" carries a booking verb and is still checked.
    2. **A meeting-sized duration.** Minutes, or an hour or two. Without this,
       "tuning takes 500 hours" would be exempted by its own verb.
    3. **Booking language around it** — a verb before ("set up", "worth",
       "got") or a meeting noun after ("call", "walkthrough"), searched in a
       window rather than anchored, because an article or an adjective sits
       between them more often than not.
    """
    if _RATE_AFTER.match(after):
        return False

    # "…the worst denial you've seen in the last 6 months" asks a question; it
    # claims nothing. Checked before the size test, because a window is often
    # months or years.
    if _WINDOW_BEFORE.search(before):
        return True

    if _MINUTE_UNIT.search(span):
        meeting_sized = True
    elif _HOUR_UNIT.search(span):
        values = [float(_key(n)) for n in _DIGITS.findall(span) if _key(n).replace(".", "").isdigit()]
        meeting_sized = bool(values) and max(values) <= MAX_MEETING_HOURS
    else:
        meeting_sized = False
    if not meeting_sized:
        return False

    # A meeting-sized duration alone in its clause offers time; it asserts
    # nothing. Only reached once the rate and size tests above have passed, so
    # "30-50 hours a month" and "500 hours" cannot arrive here.
    if not before.strip() and _STANDS_ALONE.match(after):
        return True

    return bool(_BOOKING_BEFORE.search(before) or _MEETING_AFTER.search(after))


def _duration_supported(span: str, durations: set[tuple[str, str]]) -> bool:
    """Whether every number in a duration span was stated with *this* unit."""
    match = _DURATION_IN_TEXT.search(span)
    if match is None:
        return False
    unit = _canonical_unit(match.group(2))
    return all(
        (_key(number), unit) in durations
        for number in _DIGITS.findall(span)
        if number.strip()
    )


_HAS_CURRENCY = re.compile(r"[$£€]")


def _scrub_text(
    text: str,
    sourced: set[str],
    durations: set[tuple[str, str]],
    replaced: list[str],
    prices: set[str] | None = None,
) -> str:
    """One string, with unsupported claim spans replaced by the placeholder."""
    if not text:
        return text

    # Regions the model already marked as blanks. Substituting inside one
    # nests a marker in a marker, and `count_placeholders` stops at the first
    # `]` — so the outer marker is truncated and the rest of its text is
    # orphaned in the shipped artifact. A live run delivered
    # "[TODO: … 2x/week tutoring at [TODO: your number]/hour is [TODO: your
    # number]/month …]". A blank the model wrote is already honest; there is
    # nothing in it left to verify.
    blanks = [m.span() for m in _PLACEHOLDER.finditer(text)]

    def _inside_a_blank(start: int, end: int) -> bool:
        return any(low <= start and end <= high for low, high in blanks)

    def _one(match: re.Match[str]) -> str:
        span = match.group(0)
        if _inside_a_blank(match.start(), match.end()):
            return span
        # Context stops at the sentence edge. Searching a flat window let
        # "Can we book 20 minutes?" reach forward and exempt the "45-minute
        # manual hunt" in the sentence after it — a booking verb licenses the
        # ask it belongs to, not everything near it.
        before = _SENTENCE_SPLIT.split(
            text[max(0, match.start() - _CONTEXT_CHARS) : match.start()]
        )[-1]
        after = _SENTENCE_SPLIT.split(
            text[match.end() : match.end() + _CONTEXT_CHARS]
        )[0]
        if _is_meeting_ask(span, before, after):
            return span

        # A duration must match its unit as well as its digits; money and
        # percentages are matched on the number, since the symbol already says
        # what it measures.
        numbers = [n for n in _DIGITS.findall(span) if n.strip()]
        if _DURATION_IN_TEXT.search(span):
            if _duration_supported(span, durations):
                return span
        elif prices is not None and _HAS_CURRENCY.search(span):
            # A price is a fact about the product, so the founder's own words
            # are its only authority. Checking money against the whole prompt
            # meant a buyer's arithmetic slip — "$3,600/year" for a product
            # priced at $1,200 per entity per month — was "sourced", and the
            # messaging doc restated it as the product's per-entity figure.
            # Twelve times off, laundered through the room.
            if numbers and all(_key(n) in prices for n in numbers):
                return span
        elif numbers and all(_key(n) in sourced for n in numbers):
            return span

        replaced.append(span.strip())
        return MISSING_NUMBER

    return _CLAIM_SPAN.sub(_one, text)


def scrub_unsourced[M: BaseModel](
    payload: M, material: str, *, product_material: str = ""
) -> tuple[M, list[str]]:
    """The generated payload with invented figures turned into placeholders.

    Walks every string in the model, including nested lists and dicts, because
    the shapes differ across the three builders and a field list would rot the
    first time one gained a sentence.

    Safe to run on a `_Generated` model specifically: those carry no quote
    fields by construction, so the buyers' own words — which legitimately
    contain numbers the material also contains — are never reached from here.
    """
    sourced = sourced_numbers(material)
    durations = sourced_durations(material)
    replaced: list[str] = []

    # Only narrow money to the founder's words when the founder actually stated
    # a price. If they did not, every money figure would be scrubbed, which
    # trades a rare laundered price for a document full of blanks.
    prices = (
        sourced_numbers(product_material)
        if product_material and _HAS_CURRENCY.search(product_material)
        else None
    )

    def walk(value: object) -> object:
        if isinstance(value, str):
            return _scrub_text(value, sourced, durations, replaced, prices)
        if isinstance(value, list):
            return [walk(item) for item in value]
        if isinstance(value, dict):
            return {key: walk(item) for key, item in value.items()}
        return value

    scrubbed = walk(payload.model_dump())
    return type(payload).model_validate(scrubbed), replaced


def founder_material(icp_row: dict) -> str:
    """Everything the *founder* said about their own product, and nothing the
    room said about it.

    Two fields, because the price lives in whichever one the run happened to
    populate: the `product_summary` column, and the `product_summary` key
    inside the `profile` blob. A live devtools run had the column at 314
    characters with no price in it while `$40 per developer per month` sat in
    the blob — so the money check found no price to anchor on, silently fell
    back to the whole prompt, and the 12x-off-price defence was inert.

    Deliberately excludes `archetypes`, `adversarial` and `gaps`: those are the
    buyers' side, and letting them in is the laundering route this exists to
    close.
    """
    if not isinstance(icp_row, dict):
        return ""
    parts = [str(icp_row.get("product_summary") or "")]
    profile = icp_row.get("profile")
    if isinstance(profile, dict):
        parts.append(str(profile.get("product_summary") or ""))
    return "\n".join(part for part in parts if part.strip())


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
