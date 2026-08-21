# PUBLIC INTERFACE
# ─────────────────────────────────────────────────────────
# MeasuredObjection, FounderContext
# partition_by_freshness(firms, now) -> (fresh, withheld)
# build_shortlist(context, firms, *, now=None, limit=MAX_MATCHES) -> Shortlist
# MATCH_WEIGHTS, MAX_MATCHES, MIN_SHARED_TOKENS, normalise_key(value)
# ─────────────────────────────────────────────────────────
"""Match a founder to firms, and say why in both sides' words.

Anyone can buy a list of family offices. The defensible part is that Saibyl
knows things about this founder no list vendor does — the objections real
buyers actually raised, ranked by what costs deals — so the match can be made
against evidence rather than against a sector tag.

Four things happen here, in this order, and the order is the argument:

1. **Freshness first.** `partition_by_freshness` runs before any matching, so a
   record past `stale_after` is never scored, never ranked and never seen by
   the rest of this module. Every commercial investor database is partly wrong
   the day it ships; the difference between this one and those is that a
   decayed record is named and withheld instead of quietly ranked third.

2. **Sector and stage** — the ordinary filter, and the table stakes.

3. **Thesis against the founder's own material**, with the overlap quoted both
   ways. The same reference-anchored idea as the website check's critics:
   findings carry both sides' actual language, so the founder can check the
   claim against two pages rather than trusting a score.

4. **The objection bridge** — the strongest signal and unique to this product.
   If buyers' top objection is regulatory risk, a firm whose published thesis
   names regulated markets is a materially better match than a generic AI
   investor, and the reason quotes the buyer sentence next to the thesis
   sentence. This is weighted highest for that reason.

**Refusals count.** A firm that publishes the stages it invests at, and does not
list this founder's, is reported as a refusal quoting its own stated range —
never dropped, and never replaced with a firm that would have said the same
thing on the call. The product already refuses to name a winner when confidence
intervals overlap; this is that discipline pointed at investors.

**There is no model call in this module.** The match is deterministic over
stored records, which makes every reason reproducible from the two records it
quotes and makes the whole thing testable without a network. A generation pass
would produce warmer prose and would also be able to write a reason that is not
in either source, which is the one failure this feature cannot survive.
"""
from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import Literal

import structlog
from pydantic import BaseModel, Field, model_validator

from app.services.capital.schema import (
    FamilyOffice,
    MatchDimension,
    MatchReason,
    Shortlist,
    ShortlistEntry,
    StaleRecord,
    as_utc,
    reject_personal_data,
)

log = structlog.get_logger()

# How many matches a shortlist returns. A founder pays for the answer to "who
# would fund this", and past roughly this many the list stops being an answer
# and starts being a list — which is exactly what per-record pricing would have
# rewarded and per-shortlist pricing does not.
MAX_MATCHES = 25

# Content tokens two texts must share before their overlap is quotable. One
# shared four-letter word is a coincidence at this vocabulary size; the same
# argument `gtm/scoring._phrase_hit_rate` makes for requiring half a phrase.
MIN_SHARED_TOKENS = 2

# Weights over the six dimensions. **The magnitudes are declared priors and the
# ordering is the argued part**, exactly as in `gtm/scoring.py` — there is no
# outcome data yet, because no founder has yet reported which recommendation led
# to a conversation. What keeps these from repeating the `viral_but_off_message`
# defect (a threshold invented rather than measured, which then fired on two of
# three variants) is that they gate nothing: they order a list the founder reads
# top to bottom, every reason is shown with both quotes, and no entry is hidden
# by a low score. A refusal is decided by the firm's published position, never
# by a score falling under a bar.
#
#   objection_bridge (0.40)  The signal no list vendor has. It is the founder's
#                            measured evidence meeting the firm's published
#                            position, and the design doc calls it the strongest
#                            available for that reason.
#   thesis           (0.25)  Both sides' own words overlapping. Weaker than the
#                            bridge because a thesis overlap can be two parties
#                            using the same fashionable noun.
#   sector           (0.15)  Table stakes: necessary, and nearly free to satisfy.
#   stage            (0.10)  Also table stakes, and mostly expressed as a
#                            refusal rather than as a positive.
#   check_size       (0.05)  Rarely published, so it discriminates rarely.
#   geography        (0.05)  The same.
MATCH_WEIGHTS: dict[str, float] = {
    "objection_bridge": 0.40,
    "thesis": 0.25,
    "sector": 0.15,
    "stage": 0.10,
    "check_size": 0.05,
    "geography": 0.05,
}

# What a firm has published about one dimension: it fits, it rules the
# founder out, or it says nothing. A Literal rather than a bare str so a
# typo in one of the three is a type error and not a silently-never-taken
# branch — "not_stated" mistyped as "notstated" would turn every silent
# firm into a refusal.
Position = Literal["match", "refusal", "not_stated"]

_TOKEN = re.compile(r"[a-z0-9]+")
_SENTENCE = re.compile(r"[^.!?\n]+[.!?]?")
_NON_ALNUM = re.compile(r"[^a-z0-9]+")

# Tokens shorter than this carry no signal and match everything.
_MIN_TOKEN_CHARS = 4

# Four-letter-and-longer words that still say nothing about a subject. Without
# these, a thesis and a deck "overlap" on `that`, `with` and `their`, and the
# module quotes two sentences whose only shared property is being written in
# English — which is worse than no reason, because it looks like one.
_STOPWORDS: frozenset[str] = frozenset({
    "about", "across", "after", "against", "already", "also", "although", "always",
    "among", "another", "around", "because", "been", "before", "being", "below",
    "besides", "between", "both", "cannot", "could", "does", "doing", "done",
    "during", "each", "either", "else", "even", "ever", "every", "from", "further",
    "have", "having", "here", "however", "into", "itself", "just", "less", "like",
    "many", "more", "most", "much", "must", "neither", "never", "next", "often",
    "once", "only", "onto", "other", "others", "over", "perhaps", "rather", "same",
    "should", "since", "some", "still", "such", "than", "that", "their", "them",
    "then", "there", "these", "they", "this", "those", "through", "thus", "toward",
    "towards", "under", "until", "upon", "very", "were", "what", "when", "where",
    "whether", "which", "while", "with", "within", "without", "would", "your",
    "yours",
})


def _stem(token: str) -> str:
    """Crudely fold plurals and tenses so `market` and `markets` are one token.

    Deliberately crude, and deliberately not a stemmer library. The job here is
    not linguistic accuracy — it is that a firm writing "regulated markets" and
    a buyer saying "the regulated market we sell into" should be recognised as
    the same subject. A real stemmer would also fold `regulation` onto `regul`
    and start matching words that share a root but not a meaning, which
    produces a quoted reason that reads as nonsense to the founder holding both
    pages.
    """
    for suffix in ("ing", "ies", "es", "ed", "s"):
        if token.endswith(suffix) and len(token) - len(suffix) >= _MIN_TOKEN_CHARS:
            base = token[: -len(suffix)]
            return f"{base}y" if suffix == "ies" else base
    return token


def _tokens(text: str) -> set[str]:
    return {
        _stem(t)
        for t in _TOKEN.findall((text or "").casefold())
        if len(t) >= _MIN_TOKEN_CHARS and t not in _STOPWORDS
    }


def _sentences(text: str) -> list[str]:
    return [s.strip() for s in _SENTENCE.findall(text or "") if s.strip()]


def _best_sentence(text: str, wanted: set[str]) -> str:
    """The sentence of `text` that shares the most with `wanted`, verbatim.

    Verbatim is the point: this string is rendered to the founder next to the
    other side's, and a summary of a thesis cannot be checked against the page
    it came from.
    """
    best = ""
    best_shared = 0
    for sentence in _sentences(text):
        shared = len(_tokens(sentence) & wanted)
        if shared > best_shared:
            best, best_shared = sentence, shared
    return best


def normalise_key(value: str) -> str:
    """`Pre-Seed`, `pre seed` and `preseed` are one stage."""
    return _NON_ALNUM.sub("", (value or "").casefold())


class MeasuredObjection(BaseModel):
    """One objection real buyers raised, with a sentence one of them said.

    Comes from `canonical_objections` — measured, ranked by load-bearing score
    rather than by raw frequency, because the loudest objection and the one that
    kills the deal are usually different objections.
    """

    objection_key: str
    label: str
    quote: str = ""
    load_bearing_score: float = 0.0

    @model_validator(mode="after")
    def _carries_no_personal_data(self) -> MeasuredObjection:
        for field, value in (("label", self.label), ("quote", self.quote)):
            verdict = reject_personal_data(field, value)
            if verdict is not None:
                raise ValueError(verdict)
        return self


class FounderContext(BaseModel):
    """What Saibyl knows about the founder, as the match's other side.

    Validated for personal contact detail like everything else in this package,
    and that is not an over-reach onto the founder's own data: sentences from
    `material` and from the objection quotes are **copied into the shortlist and
    stored**, so an address in a pasted deck footer becomes an address in
    Saibyl's database by way of a field nobody thought of as contact data. The
    record is refused whole rather than trimmed, for `privacy.py`'s reason: a
    record that needed editing to be lawful is a record whose source was the
    wrong kind of page, and the founder can see and fix theirs.
    """

    product_name: str = ""
    sector: str = ""
    stage: str = ""
    # The founder's own words about the product — the side of the comparison
    # that gets quoted back to them.
    material: str = ""
    check_size_needed: int | None = None
    geography: str | None = None
    objections: list[MeasuredObjection] = Field(default_factory=list)

    @model_validator(mode="after")
    def _carries_no_personal_data(self) -> FounderContext:
        for field, value in (
            ("product_name", self.product_name),
            ("sector", self.sector),
            ("stage", self.stage),
            ("material", self.material),
            ("geography", self.geography),
        ):
            verdict = reject_personal_data(field, value)
            if verdict is not None:
                raise ValueError(verdict)
        return self


def partition_by_freshness(
    firms: list[FamilyOffice],
    now: datetime,
) -> tuple[list[FamilyOffice], list[StaleRecord]]:
    """Split the bank into what may be asserted and what may not.

    **This is the reader, and the rule lives in it rather than in a comment.**
    Nothing downstream re-checks `stale_after`, because nothing downstream ever
    sees a stale record — which is the only version of this rule that survives a
    new caller. `Shortlist` refuses to hold one as a second line of defence, so
    a path that bypasses this function fails loudly instead of shipping a stale
    claim quietly.
    """
    moment = as_utc(now)
    fresh: list[FamilyOffice] = []
    withheld: list[StaleRecord] = []
    for firm in firms:
        if firm.is_stale(moment):
            withheld.append(StaleRecord(
                firm_name=firm.firm_name,
                retrieved_at=firm.retrieved_at,
                stale_after=firm.stale_after,
            ))
        else:
            fresh.append(firm)
    if withheld:
        log.info(
            "capital_records_withheld_stale",
            withheld=len(withheld),
            fresh=len(fresh),
            as_of=moment.isoformat(),
        )
    return fresh, withheld


def _reason(
    dimension: MatchDimension,
    firm_quote: str,
    founder_quote: str,
    explanation: str,
) -> MatchReason | None:
    """Build a reason, or drop it.

    Returns None rather than raising when either quote fails validation — a
    single unusable quote must not destroy an otherwise good shortlist, which is
    the same trade-off `privacy.py` makes at a different granularity (it drops
    the record; here the reason *is* the record). The drop is logged, because a
    reason that silently disappears is a match that silently gets weaker.
    """
    try:
        return MatchReason(
            dimension=dimension,
            firm_quote=firm_quote.strip(),
            founder_quote=founder_quote.strip(),
            explanation=explanation,
        )
    except ValueError as exc:
        log.info("capital_reason_dropped", dimension=dimension, error=str(exc))
        return None


def _names_the_same_thing(published: str, wanted: str) -> bool:
    """Whether two labels denote the same sector or place.

    Two tests, because published taxonomies do not agree with founders' words.
    Either the normalised labels nest ("Fintech" inside "Fintech and
    insurance"), or they share a content token. The nesting test requires the
    shorter label to be at least `_MIN_TOKEN_CHARS` long: without that, a firm
    listing "AI" matches anything whose normalised text happens to contain the
    letters `ai`, which is a match a founder cannot see the reason for.
    """
    published_key, wanted_key = normalise_key(published), normalise_key(wanted)
    if not published_key or not wanted_key:
        return False
    shorter = min(len(published_key), len(wanted_key))
    if shorter >= _MIN_TOKEN_CHARS and (
        published_key in wanted_key or wanted_key in published_key
    ):
        return True
    return bool(_tokens(published) & _tokens(wanted))


def _first_label_reason(
    dimension: MatchDimension,
    published_labels: list[str],
    wanted: str,
    explanation: str,
) -> MatchReason | None:
    """The first published label that denotes what the founder said, quoted.

    Keeps trying after a label that fails quote validation rather than stopping
    at it. Returning on the first *attempt* would let one unusable label hide a
    perfectly good one behind it.
    """
    if not published_labels or not (wanted or "").strip():
        return None
    for published in published_labels:
        if not _names_the_same_thing(published, wanted):
            continue
        reason = _reason(dimension, published, wanted, explanation)
        if reason is not None:
            return reason
    return None


def _sector_reason(firm: FamilyOffice, context: FounderContext) -> MatchReason | None:
    return _first_label_reason(
        "sector",
        firm.sectors,
        context.sector,
        "The firm publishes this sector and it is the founder's.",
    )


def _geography_reason(firm: FamilyOffice, context: FounderContext) -> MatchReason | None:
    return _first_label_reason(
        "geography",
        firm.geography,
        context.geography or "",
        "The firm states it invests here.",
    )


def _thesis_reason(firm: FamilyOffice, context: FounderContext) -> MatchReason | None:
    """The firm's published words against the founder's, quoted both ways."""
    shared = _tokens(firm.thesis) & _tokens(context.material)
    if len(shared) < MIN_SHARED_TOKENS:
        return None
    firm_quote = _best_sentence(firm.thesis, shared)
    founder_quote = _best_sentence(context.material, shared)
    if not firm_quote or not founder_quote:
        return None
    terms = ", ".join(sorted(shared)[:4])
    return _reason(
        "thesis",
        firm_quote,
        founder_quote,
        f"Both describe the same subject: {terms}.",
    )


def _objection_bridge(firm: FamilyOffice, context: FounderContext) -> MatchReason | None:
    """The founder's measured objections against the firm's published thesis.

    Taken in load-bearing order and the first bridge wins, because the objection
    that costs the most deals is the one worth choosing an investor over. A firm
    whose thesis names the thing buyers keep pushing back on is not a better
    guess than a generic AI investor — it is a firm that has already written
    down that it takes the risk this founder is being priced on.
    """
    thesis_tokens = _tokens(firm.thesis)
    if not thesis_tokens:
        return None
    for objection in sorted(
        context.objections, key=lambda o: -float(o.load_bearing_score)
    ):
        source = f"{objection.label} {objection.quote}".strip()
        shared = _tokens(source) & thesis_tokens
        if len(shared) < MIN_SHARED_TOKENS:
            continue
        firm_quote = _best_sentence(firm.thesis, shared)
        founder_quote = _best_sentence(objection.quote, shared) or objection.quote
        if not firm_quote or not founder_quote.strip():
            continue
        reason = _reason(
            "objection_bridge",
            firm_quote,
            founder_quote,
            f"Buyers' '{objection.label}' objection is the thing this firm's "
            f"published thesis says it invests into.",
        )
        # Keep going when a quote was unusable: the next objection down is a
        # weaker bridge than this one, and a weaker bridge beats none.
        if reason is not None:
            return reason
    return None


def _stage_position(firm: FamilyOffice, context: FounderContext) -> Position:
    """`match`, `refusal`, or `not_stated`.

    `not_stated` is a real and common state, not a soft yes: a firm that
    publishes no stages has taken no public position, and recording that as a
    match would manufacture agreement out of silence.
    """
    if not firm.stages or not context.stage.strip():
        return "not_stated"
    published = {normalise_key(s) for s in firm.stages if normalise_key(s)}
    return "match" if normalise_key(context.stage) in published else "refusal"


def _check_position(firm: FamilyOffice, context: FounderContext) -> Position:
    need = context.check_size_needed
    if need is None or (firm.check_size_low is None and firm.check_size_high is None):
        return "not_stated"
    if firm.check_size_low is not None and need < firm.check_size_low:
        return "refusal"
    if firm.check_size_high is not None and need > firm.check_size_high:
        return "refusal"
    return "match"


def _stage_reason(firm: FamilyOffice, context: FounderContext) -> MatchReason | None:
    return _reason(
        "stage",
        ", ".join(firm.stages),
        context.stage,
        "The firm publishes this stage and it is the founder's.",
    )


def _check_reason(firm: FamilyOffice, context: FounderContext) -> MatchReason | None:
    low = firm.check_size_low
    high = firm.check_size_high
    if low is not None and high is not None:
        published = f"${low:,}-${high:,}"
    elif low is not None:
        published = f"from ${low:,}"
    elif high is not None:
        published = f"up to ${high:,}"
    else:
        # `_check_position` only answers "match" when one bound is published,
        # so this is unreachable; it exists so a future edit to that function
        # cannot make this one silently render "None".
        return None
    return _reason(
        "check_size",
        published,
        f"${context.check_size_needed:,}",
        "The cheque the founder needs is inside the range the firm publishes.",
    )


def _refusal_sentences(
    firm: FamilyOffice,
    context: FounderContext,
    stage_position: Position,
    check_position: Position,
) -> list[str]:
    """What the firm stated, in terms the founder can check against its page."""
    stated: list[str] = []
    if stage_position == "refusal":
        stated.append(
            f"{firm.firm_name} publishes its stages as "
            f"{', '.join(firm.stages)} — not {context.stage}."
        )
    if check_position == "refusal":
        low = f"${firm.check_size_low:,}" if firm.check_size_low is not None else "no floor"
        high = f"${firm.check_size_high:,}" if firm.check_size_high is not None else "no ceiling"
        stated.append(
            f"{firm.firm_name} publishes a cheque range of {low} to {high}; "
            f"you need ${context.check_size_needed:,}."
        )
    return stated


_ACCESS_NOTES = {
    "warm_intro_only": "This firm states it takes introductions only.",
    "no_inbound": "This firm states it takes no inbound at all.",
}


def _entry(firm: FamilyOffice, context: FounderContext) -> ShortlistEntry | None:
    """One firm's verdict, or None when it is simply not relevant.

    None is neither a match nor a refusal. A firm that publishes nothing this
    founder's context touches has not refused them — it has said nothing about
    them — and reporting silence as a refusal would be as dishonest as reporting
    it as a match.
    """
    stage_position = _stage_position(firm, context)
    check_position = _check_position(firm, context)
    refusals = _refusal_sentences(firm, context, stage_position, check_position)

    reasons: list[MatchReason] = []
    components = dict.fromkeys(MATCH_WEIGHTS, 0.0)

    bridge = _objection_bridge(firm, context)
    if bridge is not None:
        components["objection_bridge"] = 1.0

    for name, reason in (
        ("thesis", _thesis_reason(firm, context)),
        ("sector", _sector_reason(firm, context)),
        ("geography", _geography_reason(firm, context)),
        ("stage", _stage_reason(firm, context) if stage_position == "match" else None),
        ("check_size", _check_reason(firm, context) if check_position == "match" else None),
    ):
        if reason is not None:
            reasons.append(reason)
            components[name] = 1.0

    if refusals:
        # Reported as a refusal even when the thesis matched — especially then.
        # "Right thesis, wrong stage" is the most useful thing this module can
        # tell a founder, and it is only sayable because the entry keeps the
        # reasons it did find.
        return ShortlistEntry(
            firm=firm,
            verdict="refusal",
            reasons=reasons,
            objection_bridge=bridge,
            refusal_reason=" ".join(refusals),
            access_note=_ACCESS_NOTES.get(firm.inbound_path.kind),
            score=0.0,
            score_components=components,
        )

    if bridge is not None:
        reasons.insert(0, bridge)
    if not reasons:
        return None

    score = sum(MATCH_WEIGHTS[name] * value for name, value in components.items())
    return ShortlistEntry(
        firm=firm,
        verdict="match",
        reasons=reasons,
        objection_bridge=bridge,
        access_note=_ACCESS_NOTES.get(firm.inbound_path.kind),
        score=round(score, 4),
        score_components={k: round(v, 4) for k, v in components.items()},
    )


def build_shortlist(
    context: FounderContext,
    firms: list[FamilyOffice],
    *,
    now: datetime | None = None,
    limit: int = MAX_MATCHES,
) -> Shortlist:
    """Rank the bank against one founder, and say what was left out and why."""
    moment = as_utc(now) if now is not None else datetime.now(UTC)
    fresh, withheld = partition_by_freshness(firms, moment)

    matches: list[ShortlistEntry] = []
    refusals: list[ShortlistEntry] = []
    for firm in fresh:
        entry = _entry(firm, context)
        if entry is None:
            continue
        (refusals if entry.verdict == "refusal" else matches).append(entry)

    matches.sort(key=lambda e: (-e.score, e.firm.firm_name.casefold()))
    refusals.sort(key=lambda e: e.firm.firm_name.casefold())

    notes: list[str] = []
    if withheld:
        notes.append(
            f"{len(withheld)} record(s) were withheld because they are past "
            f"their verification date. They are named above with the date they "
            f"were retrieved, so you can check them yourself."
        )
    if refusals:
        notes.append(
            f"{len(refusals)} firm(s) publish a position that rules you out. "
            f"They are reported rather than dropped, because a shorter list "
            f"with the same length is a list padded with firms that would have "
            f"said so on the call."
        )
    if len(matches) > limit:
        notes.append(
            f"{len(matches)} firms matched; the {limit} strongest are shown."
        )
        matches = matches[:limit]
    if not matches:
        notes.append(
            "No firm in the bank matches this sector, stage and evidence. That "
            "is a finding about the bank's coverage, not about the company — "
            "and a padded list here would be worse than an empty one."
        )

    shortlist = Shortlist(
        product_name=context.product_name,
        sector=context.sector,
        stage=context.stage,
        check_size_needed=context.check_size_needed,
        as_of=moment,
        matches=matches,
        refusals=refusals,
        withheld_stale=withheld,
        considered=len(firms),
        notes=notes,
    )
    log.info(
        "capital_shortlist_built",
        considered=len(firms),
        fresh=len(fresh),
        matches=len(shortlist.matches),
        refusals=len(refusals),
        withheld_stale=len(withheld),
        with_bridge=sum(1 for e in shortlist.matches if e.objection_bridge is not None),
    )
    return shortlist
