# PUBLIC INTERFACE
# ─────────────────────────────────────────────────────────
# VerticalBrief, VERTICALS, DEFAULT_VERTICAL
# classify_vertical(text) -> str
# brief_for(vertical_id) -> VerticalBrief
# brief_section(vertical_id) -> str   # the prompt block
# ─────────────────────────────────────────────────────────
"""What a category demands of a page, and why it is not a palette.

A medical SaaS and a consumer fintech should not produce the same page, and
until now they did: the revision generator had no idea what kind of company it
was designing for. It inherited the founder's existing design DNA and polished
it, which means a generic page came back as a *better-executed generic page*.

**The reason categories differ is not taste. It is what the buyer has to
believe before they act, and what the page must therefore prove.** A hospital's
procurement officer landing on a page that looks like a consumer app does not
think "refreshing" — they think these people have not met a compliance review.
A founder evaluating a payments product wants to feel that somebody here is
careful with money before they will read a feature list. Category convention is
a trust signal, and in regulated markets deviation reads as risk rather than as
personality.

**What this module deliberately is not: a lookup table of colours per
industry.** "Medical means blue and a stethoscope icon" is exactly the
stereotype slop that makes a generated page look generated, and it is worse
than no guidance because it is confidently wrong. Every entry below is written
as *who signs off, what they must believe, what evidence the page must carry,
and what would read as a red flag* — the arguments a designer would make.
Visual direction is stated only where it follows from one of those, and is
phrased as a pressure rather than a value: "density carries competence here"
rather than "use 13px".

**Classification is a hint, never a verdict.** `classify_vertical` reads the
founder's own material and returns the best match or `general`, and the brief
it selects is added to a prompt that already carries the founder's real
content. A wrong guess costs a paragraph of irrelevant emphasis; it cannot
override what the page actually says. That asymmetry is why keyword matching is
honest enough here and a model call is not warranted.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field


@dataclass(frozen=True)
class VerticalBrief:
    """The design argument for one category."""

    id: str
    label: str
    # Who actually signs the cheque, in their own terms.
    buyer: str
    # What they must believe before they will act on anything the page says.
    must_believe: str
    # What the page has to show. Absence is itself a signal to this buyer.
    evidence: tuple[str, ...]
    # What reads as a warning sign to this buyer specifically.
    red_flags: tuple[str, ...]
    # Visual pressure that follows from the above — never a value, always a
    # direction with its reason attached.
    direction: str
    # Words that suggest this category in the founder's own material.
    signals: tuple[str, ...] = field(default=())


VERTICALS: dict[str, VerticalBrief] = {
    "health": VerticalBrief(
        id="health",
        label="Health and clinical software",
        buyer="A clinician, practice administrator or hospital procurement lead — rarely the person who found you, and always someone who can be blamed for the choice.",
        must_believe="That this is safe for patients, defensible in an audit, and will not create work for compliance.",
        evidence=(
            "Named regulatory posture stated plainly (HIPAA, HITRUST, FDA class where it applies) — and if none applies, say why, because silence reads as evasion.",
            "Who is accountable: a real company, real people, a real address.",
            "What happens to patient data, in one sentence a non-technical administrator can repeat to their board.",
            "Clinical evidence or pilot outcomes where they exist; an honest 'not yet studied' where they do not.",
        ),
        red_flags=(
            "Growth-marketing urgency — countdown timers, 'limited spots', exclamation marks. In this category urgency reads as a company that will cut corners.",
            "Stock photography of smiling clinicians. This buyer sees it daily and it signals nothing.",
            "Claims of outcomes with no study, sample size or source attached.",
        ),
        direction="Calm, high-contrast, generous line length, plain type. Restraint IS the signal: this buyer reads visual quiet as institutional seriousness, and every decorative flourish spends credibility they were about to extend.",
        signals=(
            "patient", "clinic", "clinical", "ehr", "emr", "hipaa", "provider",
            "physician", "nurse", "hospital", "telehealth", "care team",
            "diagnosis", "medical", "health system", "prior authorization",
        ),
    ),
    "fintech": VerticalBrief(
        id="fintech",
        label="Financial products and infrastructure",
        buyer="A finance lead, treasurer or founder deciding whether to route money through you — and a compliance reviewer behind them who never appears on the call.",
        must_believe="That you are careful, that the money is traceable, and that you will still exist next year.",
        evidence=(
            "Who holds the funds and under what licence or partner bank — the single question this buyer is actually asking.",
            "Security posture as fact rather than adjective: SOC 2 with its date, encryption specifics, who has access.",
            "Pricing shown in full, including the spread or fee that is usually buried. Hiding it is the category's original sin and this buyer expects it.",
            "Real numbers with units and periods: volume processed, uptime with its measurement window.",
        ),
        red_flags=(
            "Any unexplained number. In this category an unsourced statistic actively subtracts trust rather than adding it.",
            "Playful or novelty typography. This buyer maps whimsy onto carelessness with money.",
            "Vague 'bank-grade security' language, which says nothing and signals that nothing specific is true.",
        ),
        direction="Precise and data-dense. Tabular numbers, tight alignment, visible structure. This is the one category where MORE information reads as more trustworthy — whitespace that a consumer product would call elegant reads here as having nothing to disclose.",
        signals=(
            "payments", "payout", "ledger", "treasury", "invoice", "banking",
            "fintech", "underwriting", "kyc", "aml", "compliance", "settlement",
            "card", "lending", "capital", "reconciliation", "financial",
        ),
    ),
    "devtools": VerticalBrief(
        id="devtools",
        label="Developer tools and infrastructure",
        buyer="An engineer who will try it before they talk to anyone, and who is hostile to being marketed at.",
        must_believe="That it works, that they can see how, and that they will not be trapped.",
        evidence=(
            "Real code on the page — the actual call, not a screenshot of one.",
            "The install or first-run path, visible without signing up.",
            "Honest limits: what it does not do, what scale it breaks at, what it costs at volume.",
            "Links to docs and source that go to real docs and real source.",
        ),
        red_flags=(
            "A page that will not say what the product does without a demo call.",
            "Benchmarks with no methodology, which this audience will assume are cherry-picked because they usually are.",
            "Abstract enterprise language where a code sample belongs.",
        ),
        direction="Monospace carries weight here, dark surfaces are idiomatic rather than edgy, and the code block is the hero image. Density is expected; this reader scrolls fast and skips prose to find the snippet.",
        signals=(
            "api", "sdk", "cli", "developer", "open source", "self-host",
            "kubernetes", "latency", "throughput", "webhook", "runtime",
            "deploy", "observability", "infrastructure", "framework",
        ),
    ),
    "consumer": VerticalBrief(
        id="consumer",
        label="Consumer products",
        buyer="One person deciding for themselves, in under a minute, usually on a phone.",
        must_believe="That they will feel or achieve something specific, and that leaving is easy.",
        evidence=(
            "The thing itself, shown rather than described — a real screen, a real result.",
            "Price and cancellation terms without hunting.",
            "Other people, credibly: real reviews with names, not five anonymous stars.",
        ),
        red_flags=(
            "Enterprise vocabulary — 'platform', 'solution', 'leverage' — which tells a person this was not written for them.",
            "A wall of feature bullets before any sense of what it feels like to use.",
        ),
        direction="Emotional and visual, phone-first, one decision per screen. Personality is an asset here in a way it is not in health or finance — this is the category where a distinctive voice earns attention rather than spending trust.",
        signals=(
            "app store", "subscription", "personal", "everyday", "habit",
            "consumer", "family", "fitness", "wellness", "creator", "hobby",
        ),
    ),
    "b2b_saas": VerticalBrief(
        id="b2b_saas",
        label="Business software",
        buyer="A team lead who will have to justify the line item and run the rollout.",
        must_believe="That it solves a problem they can name, that their team will adopt it, and that switching is survivable.",
        evidence=(
            "The specific workflow it replaces, named in the buyer's language.",
            "What integrates, concretely — this is the question that kills deals late.",
            "Pricing, or the honest reason there is none shown.",
            "Proof from companies that look like theirs.",
        ),
        red_flags=(
            "Undifferentiated category language that would fit any competitor's page.",
            "Logos with no story attached, which read as a list somebody bought.",
        ),
        direction="Structured and scannable: a clear hierarchy, a workflow made visible, screenshots that show real data rather than lorem rows. Competence over personality, but not to the point of anonymity.",
        signals=(
            "workflow", "team", "workspace", "collaboration", "b2b", "saas",
            "dashboard", "integration", "onboarding", "seat", "admin",
        ),
    ),
    "marketplace": VerticalBrief(
        id="marketplace",
        label="Marketplaces and two-sided platforms",
        buyer="Two different people with opposite interests, both of whom must believe the other side is already here.",
        must_believe="That there is liquidity — supply if they are demand, demand if they are supply.",
        evidence=(
            "Live evidence of the other side: real listings, real counts, recent activity.",
            "What it costs each side, stated separately.",
            "How trust and disputes are handled, because both sides are asking.",
        ),
        red_flags=(
            "A page that addresses only one side, leaving the other unsure it is for them.",
            "Placeholder or obviously seeded listings, which signal an empty market.",
        ),
        direction="Show the inventory. The single strongest design move is real supply visible above the fold; every abstraction away from actual listings weakens the liquidity claim.",
        signals=(
            "marketplace", "buyers and sellers", "listings", "vendors",
            "two-sided", "supply", "demand", "commission", "booking",
        ),
    ),
}

DEFAULT_VERTICAL = "general"

_GENERAL = VerticalBrief(
    id=DEFAULT_VERTICAL,
    label="General",
    buyer="The buyer described in the founder's own material.",
    must_believe="That this solves a problem they recognise, and that the people behind it are real.",
    evidence=(
        "What it does, in one sentence, above the fold.",
        "Who it is for, named specifically enough that the wrong reader leaves.",
        "Evidence for any claim that carries a number.",
        "A single, obvious next action.",
    ),
    red_flags=(
        "Language that would fit any company in any category.",
        "Numbers with no source.",
    ),
    direction="Follow the founder's own material and the reference site they admire. With no category signal, inventing a house style is guessing at a buyer nobody has described.",
)


def brief_for(vertical_id: str) -> VerticalBrief:
    return VERTICALS.get(vertical_id, _GENERAL)


def classify_vertical(text: str) -> str:
    """Best-effort category from the founder's own words.

    Scored by distinct signal hits rather than total occurrences, so a page
    that says "payments" nine times does not outrank one that genuinely spans
    four of a category's concepts. Ties and thin evidence resolve to
    `general`, because a confidently wrong category brief is worse than none:
    it would push a page toward conventions its buyer does not hold.
    """
    if not text:
        return DEFAULT_VERTICAL

    haystack = text.lower()
    scores: dict[str, int] = {}
    for vid, brief in VERTICALS.items():
        hits = sum(
            1
            for signal in brief.signals
            if re.search(rf"(?<![a-z]){re.escape(signal)}(?![a-z])", haystack)
        )
        if hits:
            scores[vid] = hits

    if not scores:
        return DEFAULT_VERTICAL

    ranked = sorted(scores.items(), key=lambda kv: (-kv[1], kv[0]))
    best_id, best = ranked[0]

    # Two distinct concepts is the floor. One stray mention of "capital" in a
    # devtools page is not a fintech.
    if best < 2:
        return DEFAULT_VERTICAL

    # And the winner must lead by more than one concept.
    #
    # A medical-billing product hits "patient/clinical/hospital" and
    # "payments/ledger/settlement/KYC" almost equally, and it genuinely sits
    # between two sets of conventions — 4-to-3 is not evidence for either. A
    # single-signal margin is noise, so the honest answer is that we do not
    # know which conventions govern, and the general brief tells the generator
    # to follow the founder's own material instead of a category's.
    runner_up = ranked[1][1] if len(ranked) > 1 else 0
    if best - runner_up < 2:
        return DEFAULT_VERTICAL
    return best_id


def brief_section(vertical_id: str) -> str:
    """The block that goes into the generator's prompt."""
    brief = brief_for(vertical_id)
    evidence = "\n".join(f"- {line}" for line in brief.evidence)
    flags = "\n".join(f"- {line}" for line in brief.red_flags)
    return (
        f"WHAT THIS CATEGORY DEMANDS — {brief.label}\n"
        f"\n"
        f"Who decides: {brief.buyer}\n"
        f"What they must believe first: {brief.must_believe}\n"
        f"\n"
        f"The page must carry:\n{evidence}\n"
        f"\n"
        f"Reads as a warning sign to THIS buyer:\n{flags}\n"
        f"\n"
        f"Visual pressure: {brief.direction}\n"
        f"\n"
        f"This describes what the buyer needs, not a house style. Use only "
        f"facts the founder's own material supports — where the category asks "
        f"for evidence the material does not contain, write the placeholder "
        f"rather than inventing the fact. A page that claims a certification "
        f"it does not hold is worse than one that omits it."
    )
