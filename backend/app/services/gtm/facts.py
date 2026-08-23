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

import structlog
from pydantic import BaseModel

log = structlog.get_logger()

#: What the model was told to write when the material is silent. Defined here
#: so the prompts, the substitution and the counter cannot drift apart.
MISSING_NUMBER = "[TODO: your number]"
MISSING_EXAMPLE = "[TODO: your example]"

_TIME_UNIT = (
    r"seconds?|minutes?|hours?|days?|weeks?|months?|quarters?|years?"
    r"|hrs?|mins?"
)

#: A magnitude, written as a letter *or* as a word. Letters only was a
#: three-order-of-magnitude hole: "$3 million" ended its span at "$3", keyed as
#: 3, and any bare 3 in the material — "3 entities" — licensed it. "A $20
#: billion market" and "$3 million a year in wasted spend" are the cheapest
#: sentences a model can write and the most damaging ones a cold email can
#: carry, and both reported zero replacements.
#:
#: Always used with a trailing `\b`, for the reason `_CLAIM_SPAN` gives below.
_MAGNITUDE = r"(?:thousand|million|billion|trillion|mm|bn|k|m)"

#: Money the writer spelled out instead of prefixing. "9,000 USD" matched no
#: claim branch at all, so it was never checked against anything.
_CURRENCY_WORD = r"(?:USD|EUR|GBP|dollars?)"

#: A number anywhere, for reading the material. The magnitude is captured
#: rather than swallowed so *both* readings are sourced: material stating
#: "$3 million" covers copy writing "$3 million" and copy writing "3".
_ANY_NUMBER = re.compile(
    r"(\d[\d,]*(?:\.\d+)?)(?:\s*(" + _MAGNITUDE + r"))?\b", re.I
)

#: A span that makes a claim. Whole spans are replaced rather than the digits
#: inside them, so a range never degrades into "[TODO: your number]-50 hours".
_CLAIM_SPAN = re.compile(
    r"(?:"
    # money, with an optional magnitude and an optional range partner.
    #
    # `\b` after the magnitude, and the magnitude optional rather than the
    # boundary — the same boundary `_DIGITS` needed and this pattern did not
    # get. Without it the span eats the first letter of the next word: "$35
    # kit" matched as "$35 k", which keys as 35,000, is absent from the
    # material, and so scrubbed a correctly-sourced price *and* left
    # "[TODO: your number]it" in shipped copy.
    r"[$£€]\s?\d[\d,]*(?:\.\d+)?(?:\s*" + _MAGNITUDE + r"\b)?"
    r"(?:\s*[-–—]\s*[$£€]?\s?\d[\d,]*(?:\.\d+)?(?:\s*" + _MAGNITUDE + r"\b)?)?"
    r"|"
    # money named rather than prefixed: "9,000 USD", "3 million dollars"
    r"\d[\d,]*(?:\.\d+)?(?:\s*" + _MAGNITUDE + r"\b)?\s*" + _CURRENCY_WORD + r"\b"
    r"|"
    # percentage, with an optional range partner. Spelled out as well as
    # signed: "Cuts 40 percent of the manual work" is the same claim as 40%.
    r"\d[\d,]*(?:\.\d+)?\s*(?:[-–—]\s*\d[\d,]*(?:\.\d+)?\s*)?(?:%|per\s?cent\b|pct\b)"
    r"|"
    # a number carrying a unit of time: "17 hours", "30-50 hours", "45-minute"
    r"\d[\d,]*(?:\.\d+)?\s*\+?"
    r"(?:\s*[-–—]\s*\d[\d,]*(?:\.\d+)?\s*\+?)?"
    r"[\s-]*(?:" + _TIME_UNIT + r")\b"
    r")",
    re.I,
)

#: The magnitude carries a `\b` and is optional — without the boundary this
#: reads "8 months" as "8 m", i.e. eight million, and then reports a duration
#: the material plainly states as unsourced.
_DIGITS = re.compile(
    r"\d[\d,]*(?:\.\d+)?(?:\s*" + _MAGNITUDE + r"\b)?", re.I
)

#: A meeting length is not a claim about the product, and this copy is full of
#: them — "Can we book 20 minutes?", "a 30-minute intro". Scrubbing those
#: produces "Can we book [TODO: your number]?": a nonsense blank in the one
#: line that has to work, and it catches nothing, because a meeting length was
#: never a claim.
#:
#: **The test used to be the other way round and it kept failing.** It asked
#: whether booking language sat around the number, and every live check found
#: another phrasing the list did not know: an article ("set up **a** 30-minute
#: call"), then "worth", "takes", "got", then "I'll **keep it to** 15 minutes",
#: "20 minutes next week?", "Any interest in 15 minutes?", "30 minutes with
#: your ops lead would settle it". Widening the list moved the boundary rather
#: than removing it, because the list can never be finished — cold copy asks
#: for time in as many ways as there are ways to be polite.
#:
#: So a meeting-sized duration is an offer of someone's time *by default*, and
#: what has to be recognised instead is the small, closed set of shapes that
#: make a duration a measurement: a rate ("2 hours/week"), a duration used as
#: an adjective on something that is not a meeting ("a 45-minute manual hunt"),
#: and the savings verbs a benefit claim is written with ("saves 90 minutes").
#: Those are shapes, not vocabulary, and there are few enough of them to state.
#: Language that makes a duration an offer of someone's time. Generous on
#: purpose — the cost of missing one is a placeholder in a call-to-action,
#: which is visible and fixable, while the cost of exempting by default is an
#: invented benchmark in a stranger's inbox.
#:
#: "keep it to" and "hold it to" are here because real copy asks that way and
#: the earlier list did not know them.
_BOOKING_BEFORE = re.compile(
    r"(?:book|book in|grab|spare|schedule|hop on|jump on|set up|carve out|"
    r"give (?:me|us)|steal|worth|takes?|took|got|get|have|spend|free up|"
    r"block|find|need|want|keep it to|hold it to|no more than|under|"
    r"buy me|borrow|pencil)\b",
    re.I,
)

#: The claim shape a savings or waste verb makes: "we save you 90 minutes",
#: "you lose 40 minutes a close". Checked before the exemption, because this is
#: an assertion about the product whatever else surrounds it.
_CLAIM_BEFORE = re.compile(
    r"\b(?:sav(?:e|es|ed|ing)|shav(?:e|es|ed|ing)|wast(?:e|es|ed|ing)|"
    r"los(?:e|es|ing)|lost|bleed(?:s|ing)?|burn(?:s|ed|ing)?)\b",
    re.I,
)

#: A duration written as an adjective — "a 45-minute manual hunt", "a 5-minute
#: triage". The hyphen is what says the duration is measuring the noun after
#: it, so unless that noun is a meeting, this is a benchmark rather than an
#: offer of time.
_ATTRIBUTIVE = re.compile(r"\d\s*[-–—]\s*(?:" + _TIME_UNIT + r")\b", re.I)

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

#: The two things that make a duration an ask when no booking verb is present.
#:
#: This is the discriminator that lets the default be "check" without mangling
#: real calls to action. Asks are **interrogative or scheduled**; product
#: claims are **declarative**. "20 minutes next week?" and "Would 20 minutes on
#: Tuesday work?" carry a question mark and a day; "Reviews are done in 20
#: minutes." and "Month-end close drops to 2 hours." carry neither, and both of
#: those are invented benchmarks that reached sendable copy when this function
#: briefly exempted by default.
#:
#: "with you / with your <person>" counts too: time spent together is a
#: meeting, which is what "30 minutes with your ops lead would settle it" is.
#: A bare meeting length standing as its own clause — "15 minutes—let's settle
#: it.", "(20 minutes, free tier)". Both halves of the verb-before /
#: noun-after test fail here by construction: the sentence split leaves
#: `before` empty and the punctuation that follows carries no noun. Two of
#: these reached sendable copy, one a line meant to be read down a phone.
_STANDS_ALONE = re.compile(r"^\s*[—–\-,)(]|^\s*$")

_ASK_MARK = re.compile(r"\?")
_SCHEDULING_NEAR = re.compile(
    r"\b(?:today|tomorrow|tonight|monday|tuesday|wednesday|thursday|friday|"
    r"this week|next week|the week|say when|let me know when|when(?:\?|\b)|"
    r"your calendar|my calendar|diary|availability)\b"
    r"|\bwith (?:you|your)\b",
    re.I,
)
_CONTEXT_CHARS = 34

#: A rate is always a claim and can never be a meeting ask: nobody books a
#: meeting "a month".
#:
#: The forms matter as much as the units. Reading only "a/per/each/every" plus
#: a unit meant "we free up 2 hours**/week** for every controller", "you get 2
#: hours/week back" and "it takes 2 hours **weekly**" all walked through the
#: one guard that keeps a booking verb honest — and "/week", "/month" and
#: "weekly" are the forms a savings claim is actually written in.
_RATE_AFTER = re.compile(
    r"^\W*(?:an?|per|each|every)\s+(?:day|week|month|quarter|year|hour)s?\b"
    r"|^\s*/\s*(?:day|week|month|quarter|year|hour|wk|mo|yr|hr)s?\b"
    r"|^\W*(?:daily|weekly|monthly|quarterly|yearly|annually|hourly)\b",
    re.I,
)

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

_MINUTE_UNIT = re.compile(r"\b(?:minutes?|mins?)\b", re.I)
_SECOND_UNIT = re.compile(r"\b(?:seconds?|secs?)\b", re.I)
_HOUR_UNIT = re.compile(r"\bhours?|hrs?\b", re.I)
MAX_MEETING_HOURS = 2
#: The same ceiling in the unit copy usually writes it in. Minutes had no
#: ceiling at all, so "the month-end close takes 900 minutes of manual work"
#: was exempted by its verb while the identical claim in hours was scrubbed —
#: and minutes is the unit a model reaches for when it invents a per-task
#: benchmark.
MAX_MEETING_MINUTES = 120

_PLACEHOLDER = re.compile(r"\[TODO:[^\]]*\]", re.I)


#: Longest suffix first, so "million" is not read as an "m" with a tail.
_MAGNITUDE_FACTORS: tuple[tuple[str, int], ...] = (
    ("trillion", 1_000_000_000_000),
    ("billion", 1_000_000_000),
    ("million", 1_000_000),
    ("thousand", 1_000),
    ("mm", 1_000_000),
    ("bn", 1_000_000_000),
    ("k", 1_000),
    ("m", 1_000_000),
)


def _key(raw: str) -> str:
    """A number reduced to what makes it the same number.

    `$1,200`, `1200` and `1.2k` are one figure; separators and magnitude
    suffixes are notation. Trailing zeros go too, so material stating `2.9`
    covers copy writing `2.90`.

    The magnitude *word* counts as notation too. Reading only `k` and `m` meant
    "$3 million" keyed as 3, so a material saying "3 entities" licensed it.
    """
    text = raw.strip().lower().replace(",", "").replace(" ", "")
    multiplier = 1
    for suffix, factor in _MAGNITUDE_FACTORS:
        if text.endswith(suffix) and text[: -len(suffix)]:
            multiplier, text = factor, text[: -len(suffix)]
            break
    try:
        value = float(text) * multiplier
    except ValueError:
        return text
    if value.is_integer():
        return str(int(value))
    return f"{value:.6f}".rstrip("0").rstrip(".")


def sourced_numbers(material: str) -> set[str]:
    """Every number the generator was actually shown.

    A figure written with a magnitude is read both ways — "$3 million" sources
    3,000,000 *and* 3 — because the material is what licenses copy, and copy
    quoting either form is quoting what it was given.
    """
    values: set[str] = set()
    for digits, magnitude in _ANY_NUMBER.findall(material or ""):
        if not digits.strip():
            continue
        values.add(_key(digits))
        if magnitude:
            values.add(_key(f"{digits}{magnitude}"))
    return values


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


def _meeting_sized(span: str) -> bool:
    """Whether this duration could be a meeting at all.

    A meeting is twenty minutes, or an hour or two. Hours were capped from the
    start — otherwise "tuning **takes** 500 hours" is exempted by its own verb
    — and minutes and seconds were not, which is the same hole in the units
    copy actually invents benchmarks in: "the close takes 900 minutes",
    "setup takes 90 seconds", "45 seconds per line item".

    Seconds have no cap because no meeting is ever booked in them. A duration
    in seconds is a claim about how fast something runs.
    """
    values = [
        float(_key(n))
        for n in _DIGITS.findall(span)
        if _key(n).replace(".", "").isdigit()
    ]
    if _SECOND_UNIT.search(span):
        return False
    if _MINUTE_UNIT.search(span):
        return bool(values) and max(values) <= MAX_MEETING_MINUTES
    if _HOUR_UNIT.search(span):
        return bool(values) and max(values) <= MAX_MEETING_HOURS
    return False


def _is_meeting_ask(span: str, before: str, after: str, raw_after: str = "") -> bool:
    """Whether this span offers someone's time rather than claiming a fact.

    A meeting-sized duration is an offer of time unless one of a closed set of
    shapes makes it a measurement:

    1. **A rate.** "a month", "per week", "/week", "weekly" — nobody books a
       meeting for a month, so "controllers spend 30-50 hours a month" is
       checked however politely it is phrased.
    2. **Bigger than a meeting.** 500 hours, 900 minutes, any number of
       seconds. See `_meeting_sized`.
    3. **A savings verb before it.** "we save you 90 minutes" asserts a
       benefit; it does not ask for time.
    4. **Used as an adjective on something that is not a meeting.** "a
       45-minute manual hunt", "a 5-minute triage" — the hyphen says the
       duration is measuring the noun after it. A booking verb before, or a
       meeting noun after, says the noun *is* the meeting ("a 30-minute
       technical call", "grab a 15-minute slot") and the offer stands.

    Everything else — "20 minutes next week?", "I'll keep it to 15 minutes",
    "30 minutes with your ops lead would settle it" — is an ask, and the ask is
    the one line in this copy that has to work.
    """
    if _RATE_AFTER.match(after):
        return False

    # "…the worst denial you've seen in the last 6 months" asks a question; it
    # claims nothing. Checked before the size test, because a window is often
    # months or years.
    if _WINDOW_BEFORE.search(before):
        return True

    if not _meeting_sized(span):
        return False

    if _CLAIM_BEFORE.search(before):
        return False

    if _ATTRIBUTIVE.search(span) and not (
        _BOOKING_BEFORE.search(before) or _MEETING_AFTER.search(after)
    ):
        return False

    # A duration alone in its clause offers time — "15 minutes—let's settle
    # it.", "(20 minutes, free tier)". Both halves of the test below fail here
    # by construction: the sentence split leaves `before` empty and the
    # punctuation after carries no noun.
    if not before.strip() and _STANDS_ALONE.match(after):
        return True

    # **The default is to CHECK, not to exempt.** The guards above disqualify
    # the shapes we know are claims; they cannot enumerate the shapes we do
    # not. This function briefly ended `return True`, and six invented product
    # benchmarks walked straight through it — "Reviews are done in 20
    # minutes.", "Setup is 15 minutes.", "Month-end close drops to 2 hours." —
    # all previously caught, none carrying a rate, a hyphen or a savings verb.
    #
    # The two failure directions are not symmetrical. Exempting wrongly sends
    # an invented benchmark to a stranger under the founder's name, which is
    # the failure this module exists to prevent. Checking wrongly leaves a
    # placeholder in a call-to-action, which is visible, counted, and fixable
    # in seconds. So an offer of time has to look like one.
    if _BOOKING_BEFORE.search(before) or _MEETING_AFTER.search(after):
        return True

    # No booking verb, so the clause has to look like an ask another way:
    # interrogative, or scheduled, or time spent with someone.
    #
    # The question mark is read from `raw_after` rather than `after`, because
    # `_SENTENCE_SPLIT` treats `?` as a boundary and consumes it — so "Any
    # interest in 15 minutes?" arrives here with an empty `after` and its one
    # distinguishing mark already thrown away.
    context = f"{before} {span} {after}"
    return bool(
        _ASK_MARK.search(raw_after[:4]) or _SCHEDULING_NEAR.search(context)
    )


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


#: Money, whichever way it is written. The symbols alone left "9,000 USD" and
#: "40 dollars a seat" outside the price check — and outside the test that
#: decides whether the founder stated a price at all.
_HAS_CURRENCY = re.compile(r"[$£€]|\b" + _CURRENCY_WORD + r"\b", re.I)


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
        raw_after = text[match.end() : match.end() + _CONTEXT_CHARS]
        after = _SENTENCE_SPLIT.split(raw_after)[0]
        if _is_meeting_ask(span, before, after, raw_after):
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
    #
    # **Logged when it cannot engage, because silence here reads as safety.**
    # Measured on 2026-08-23: all three sample runs reached this with no price
    # anywhere in the founder-side material, so the narrowing was inert on
    # every one of them — while the code above looked like a live guard. The
    # cause is upstream: the intake truncates `projects.description` and the
    # ICP synthesis drops pricing from `product_summary`, so the founder's
    # stated price survives only inside the buyer archetypes, which this
    # function must not read. Until intake preserves it, this warning is the
    # only thing distinguishing "no laundering happened" from "nothing was
    # watching".
    prices = None
    if product_material and _HAS_CURRENCY.search(product_material):
        prices = sourced_numbers(product_material)
    elif product_material:
        log.warning(
            "gtm_price_narrowing_inactive",
            reason="founder material states no price",
            material_chars=len(product_material),
        )
    else:
        log.warning("gtm_price_narrowing_inactive", reason="no founder material")

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
