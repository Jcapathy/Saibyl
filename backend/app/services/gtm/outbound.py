# PUBLIC INTERFACE
# ─────────────────────────────────────────────────────────
# OutboundStep, ArchetypeSequence, OutboundSequences — the artifact
# build_outbound_sequences(simulation_id, org_id) -> OutboundSequences
# available_inputs(simulation_id, org_id) -> SequenceInputs
# SEQUENCE_SKELETON, PAIN_SLOTS, MAX_ARCHETYPES
# TODO_NUMBER, TODO_EXAMPLE, MERGE_TOKENS
# ─────────────────────────────────────────────────────────
"""The outbound sequence: multi-touch copy aimed at pains the room actually said.

Every outbound playbook hands a founder the same skeleton — eight to twelve
touches over two weeks, three channels, three pains hit twice each — and then
leaves the hardest part blank. The founder fills the pain slots by guessing,
and a sequence built on guessed pain is a sequence the list learns to ignore.

Saibyl already measured the pain. `canonical_objections` holds what real
buyers raised, ranked by load-bearing score — reach × intensity × spread across
kinds of buyer, deliberately not raw frequency, because the loudest objection
and the one that kills the deal are usually different objections. So the three
pain slots are filled from the measurement, in its order, with the buyers' own
sentences attached as the evidence that the slot is real.

**The skeleton is code; only the copy is generated.** Step numbers, day
offsets, channels, which slot each touch addresses and whether it is the first
or second framing of that slot all live in `SEQUENCE_SKELETON` below. A model
asked to design the cadence *and* write it will quietly produce four touches —
the number most sequences stop at, and the reason most sequences fail — and
nothing downstream would notice. Asking it only for words makes the cadence a
thing a founder can read and argue with before spending credits, the same
argument `query_compiler` makes for keeping the discovery queries
deterministic.

**Fact discipline, inherited from `revise.py` and `answer_pack.py`.** The model
may use only what the founder's own material and the buyers' own words support.
Where a line needs a number, a customer, a case study, a logo or a benchmark
that is not in the input, it writes exactly `[TODO: your number]` or
`[TODO: your example]`. Cold outbound is the one place a fabricated statistic
travels furthest — it goes out under the founder's name, at volume, to people
who can check — so a visible placeholder the founder fills is the only
acceptable form of a missing fact here.

**This module writes copy. It never sends anything, and it stores no contacts
at all.** Read `privacy.py`: it is binding and it is not a feature flag. Name,
role, employer and public profile URL are the only personal fields Saibyl may
ever store, the gate that permits even those is off by default, and personal
email, phone and postal address are forbidden outright. Nothing here touches
`gtm_contacts` or any other personal record. The copy carries merge tokens —
`{{first_name}}`, `{{company}}` — which the founder resolves in their own
tooling, from their own list, and sends from their own inbox. There is no
sending path in this module and adding one would need its own argument about
consent, suppression and unsubscribe handling, not this file's.

**Deliverability, sending domains and inbox warm-up are out of scope.** The
playbook covers them and is right to: domain reputation is the constraint that
silently caps a whole engine, and a response-rate problem cannot be diagnosed
while messages are not arriving. But that is the founder's own infrastructure —
their domains, their mailboxes, their reputation — and Saibyl neither holds nor
can observe any of it. Saying so is more useful than half-implementing a
warm-up schedule this product cannot execute or verify.

**No measured objections means refuse.** A sequence generated with nothing
measured is exactly the document the founder would have written alone, with
three invented pains in it and the product's name on the end. Generic outbound
is the thing this exists to not be, so the absence is reported rather than
papered over.
"""
from __future__ import annotations

import json
from typing import Any

import structlog
from pydantic import BaseModel, Field

from app.core.database import get_supabase_admin
from app.core.llm_client import llm_structured
from app.services.gtm.facts import (
    count_placeholders,
    founder_material,
    scrub_unsourced,
)
from app.services.gtm.schema import contains_personal_contact_detail

log = structlog.get_logger()

# The placeholders a missing fact becomes. Written exactly, so a founder can
# find every one of them with a search before the first send.
TODO_NUMBER = "[TODO: your number]"
TODO_EXAMPLE = "[TODO: your example]"

# The only personalization the copy may carry. Tokens, never values: the module
# has no list, no contacts and no way to resolve them, which is the privacy
# position stated in the docstring made structural rather than promised.
MERGE_TOKENS: tuple[str, ...] = (
    "{{first_name}}",
    "{{company}}",
    "{{sender.first_name}}",
)

CHANNEL_EMAIL = "email"
CHANNEL_LINKEDIN = "linkedin"
CHANNEL_PHONE = "phone"

# Buyer archetypes that get a sequence, most-weighted first.
#
# **This is a price ceiling, not a taste judgement.** A sequence is one model
# call per archetype, and `outbound_sequence_credits()` is one fixed price for
# the build. An ICP profile may hold six buyer archetypes, so an uncapped build
# would make six calls against a price sized for fewer and be served at a loss —
# the failure mode the whole cost model exists to prevent.
#
# Four, from the arithmetic the price was set with: `OUTBOUND_SEQUENCE_COGS_USD`
# is $0.50, sized against the report's measured per-section cost of ≈$0.145
# (7,450 in / 4,320 out on the main model). One archetype's sequence is smaller
# than a report section — roughly 3,000 tokens of input and 2,500 of output for
# sixteen short blocks — so four calls sit inside $0.50 with headroom, and six
# would not.
#
# A profile with more than this gets a note saying so. Silently covering four of
# six archetypes is the kind of omission a founder discovers by noticing a buyer
# missing, which is far worse than being told.
MAX_ARCHETYPES = 4

class _Touch(BaseModel):
    """One step of the skeleton. Structure only — never copy."""

    step: int
    # Days after the first touch. The playbook's own offsets.
    day: int
    channel: str
    purpose: str
    # 1, 2 or 3 — which measured objection this touch answers. None on the
    # opening, the follow-ups, the calls and the breakup, which carry no pain.
    pain_slot: int | None = None
    # 1 = the objection head on. 2 = the same objection, framed differently.
    angle: int | None = None


# The 14-day, 16-touch sequence, exactly as the playbook lays it out. Steps 1–6
# open on value; 7–14 walk three pains, each hit twice on different channels
# with a different framing; 15–16 break up.
#
# **Angle 2 is not the angle 1 touch sent twice.** It is the same measured
# objection framed differently, which is the whole reason the second touch is
# worth sending. A sequence that repeats itself trains the reader to skip it.
SEQUENCE_SKELETON: tuple[_Touch, ...] = (
    _Touch(step=1, day=1, channel=CHANNEL_EMAIL,
           purpose="Open on value. Three points at most, in their language."),
    _Touch(step=2, day=1, channel=CHANNEL_LINKEDIN,
           purpose="Connection request. No pitch in it."),
    _Touch(step=3, day=1, channel=CHANNEL_PHONE,
           purpose="Call. A talk track to work from, not a script to read out."),
    _Touch(step=4, day=3, channel=CHANNEL_EMAIL,
           purpose="Short follow-up. No new argument, no new ask."),
    _Touch(step=5, day=3, channel=CHANNEL_LINKEDIN,
           purpose="The same value points, in their feed rather than their inbox."),
    _Touch(step=6, day=3, channel=CHANNEL_PHONE, purpose="Call."),
    _Touch(step=7, day=4, channel=CHANNEL_EMAIL,
           purpose="The first objection, head on.", pain_slot=1, angle=1),
    _Touch(step=8, day=4, channel=CHANNEL_LINKEDIN,
           purpose="Short follow-up on the connection."),
    _Touch(step=9, day=6, channel=CHANNEL_EMAIL,
           purpose="The second objection, head on.", pain_slot=2, angle=1),
    _Touch(step=10, day=6, channel=CHANNEL_LINKEDIN,
           purpose="The first objection again, framed differently.", pain_slot=1, angle=2),
    _Touch(step=11, day=7, channel=CHANNEL_EMAIL,
           purpose="The third objection, head on.", pain_slot=3, angle=1),
    _Touch(step=12, day=7, channel=CHANNEL_LINKEDIN,
           purpose="The second objection again, framed differently.", pain_slot=2, angle=2),
    _Touch(step=13, day=10, channel=CHANNEL_PHONE, purpose="Call."),
    _Touch(step=14, day=10, channel=CHANNEL_LINKEDIN,
           purpose="The third objection again, framed differently.", pain_slot=3, angle=2),
    _Touch(step=15, day=14, channel=CHANNEL_EMAIL,
           purpose="The breakup. It gives them a cheap way to answer, which is why it works."),
    _Touch(step=16, day=14, channel=CHANNEL_LINKEDIN, purpose="The breakup, in their feed."),
)

# Derived from the skeleton rather than written twice. A fifth pain slot added
# above would otherwise load four objections and leave the fifth touch pain-less
# with nothing failing — the two-sources-of-truth class, with a founder-visible
# gap on the end of it.
PAIN_SLOTS: int = max((t.pain_slot or 0) for t in SEQUENCE_SKELETON)

# Verbatim quotes carried per objection. Two proves the objection is real and
# shows its range without turning a prompt into a transcript.
QUOTES_PER_OBJECTION = 2


class OutboundStep(BaseModel):
    """One touch: when it goes, on what channel, why, and what it says."""

    step: int
    day: int
    channel: str
    purpose: str

    # Which measured objection this touch answers, and how hard it landed.
    # **Attached from the database, never echoed by the model** — a model asked
    # to repeat a score will eventually round it.
    objection_key: str | None = None
    objection_label: str | None = None
    agents_raising: int = 0
    load_bearing_score: float = 0.0
    evidence_quotes: list[str] = Field(default_factory=list)
    angle: int | None = None

    # Empty on LinkedIn and phone steps, which have no subject line. Empty is
    # the real value there, not a missing one.
    subject: str = ""
    body: str


class ArchetypeSequence(BaseModel):
    """One buyer archetype's sequence."""

    archetype_id: str
    archetype_label: str
    role: str = ""
    seniority: str = ""
    # What they would have to rip out to buy. The most load-bearing field in
    # the profile, and the thing the copy has to speak to net of.
    incumbent_tooling: list[str] = Field(default_factory=list)

    steps: list[OutboundStep] = Field(default_factory=list)
    # Objection keys in measured rank order — pain slot 1, 2, 3.
    pains_addressed: list[str] = Field(default_factory=list)
    # How many `[TODO: …]` placeholders the founder has to fill before sending.
    # Counted rather than hidden: a sequence with fourteen of them is not ready,
    # and the founder should learn that here rather than from a reply.
    placeholders_to_fill: int = 0
    notes: list[str] = Field(default_factory=list)


class OutboundSequences(BaseModel):
    sequences: list[ArchetypeSequence] = Field(default_factory=list)
    # How many measured objections filled the pain slots. Rendered, so a founder
    # can see the sequence walks what the room raised rather than three pains we
    # chose.
    built_from_objections: int = 0

    # The message the room picked, if a message test ran and the scoreboard was
    # willing to name a winner. None is common and is not a failure.
    winning_variant_key: str | None = None
    winning_variant_label: str | None = None
    winning_message: str | None = None

    notes: list[str] = Field(default_factory=list)


class _GeneratedStep(BaseModel):
    """One step's copy, as the model returns it.

    `step` is the only structural field asked for, and it is asked for as a key
    to match on rather than as a decision — the day, the channel and the pain
    are already decided in `SEQUENCE_SKELETON`.
    """

    step: int
    subject: str = ""
    body: str = ""


class _Generated(BaseModel):
    steps: list[_GeneratedStep] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


_TOKEN_LIST = ", ".join(MERGE_TOKENS)

SYSTEM = f"""You write cold outbound copy for founders. You are given a fixed \
sequence structure and a set of objections that were actually measured — real \
buyers raised them, and their verbatim words are attached.

You write the words for each step. You do NOT decide the cadence: the step \
numbers, the days, the channels and which objection each step answers are \
given to you and are not yours to change, add to, or drop.

Rules you may not break:
- Use ONLY what the founder's material and the buyers' quotes support. Where a \
line needs a number, a customer name, a case study, a logo or a benchmark that \
is not in the input, write exactly {TODO_NUMBER} or {TODO_EXAMPLE}. Never \
invent a statistic, a customer, a logo or a comparison. Cold email is read by \
the one audience that can check.
- Never write a person's name, email address, phone number or postal address. \
Personalize only with these tokens, exactly as written: {_TOKEN_LIST}. You have \
no list and must not invent one.
- Email bodies: 80 words or fewer. Shorter is better. One idea, one ask.
- Email steps get a subject line. LinkedIn and phone steps get an empty \
subject — do not invent one.
- Phone steps are a talk track a human works from, not a paragraph read aloud.
- An objection is answered, never argued with. Say the concern back in the \
buyer's own terms first so they hear that it landed.
- Where a step is marked angle 2, it is the SAME objection framed differently \
from the angle 1 step above it. Different opening, different evidence, \
different ask. A second touch that restates the first is why sequences get \
ignored.
- The breakup is short, warm and gives them a cheap way to say no. It is the \
highest-replying step in most sequences and it earns that by not being a \
final ask.
- Natural tone. It has to read like a person wrote it, because a person is \
about to send it under their own name."""


def _quotes(row: dict[str, Any]) -> list[str]:
    raw = row.get("quotes")
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except ValueError:
            return []
    out: list[str] = []
    for quote in (raw or [])[:QUOTES_PER_OBJECTION]:
        text = quote.get("text") if isinstance(quote, dict) else quote
        if text and str(text).strip():
            out.append(str(text).strip())
    return out


def _load_objections(simulation_id: str, org_id: str) -> list[dict[str, Any]]:
    """The measured objections that fill the pain slots, most load-bearing first.

    Limited to the number of slots the skeleton actually has. The tail past that
    is not dropped for tidiness — there is nowhere in a 16-touch sequence to put
    it, and loading more would report a `built_from_objections` figure larger
    than the number of objections the copy addresses.
    """
    admin = get_supabase_admin()
    return (
        admin.table("canonical_objections")
        .select(
            "objection_key, label, summary, quotes, agent_count, "
            "cohort_spread, load_bearing_score"
        )
        .eq("simulation_id", simulation_id)
        .eq("organization_id", org_id)
        .order("load_bearing_score", desc=True)
        .limit(PAIN_SLOTS)
        .execute()
    ).data or []


def _load_context(simulation_id: str, org_id: str) -> dict[str, Any]:
    """The product's own words and the buyer archetypes to write to.

    **Buyer archetypes only.** `profile.adversarial` holds the incumbent-aligned
    cohort, which exists so a simulation contains the objection a pure-buyer
    swarm misses (DECISIONS §7). It is not an audience to sell to, and writing
    outbound to "sunk-cost consultants who defend the incumbent" would hand a
    founder a sequence aimed at people whose entire position is that they are
    not buying. `query_compiler` skips them for the same reason.
    """
    admin = get_supabase_admin()
    sim = (
        admin.table("simulations")
        .select("name, prediction_goal, icp_profile_id")
        .eq("id", simulation_id)
        .eq("organization_id", org_id)
        .single()
        .execute()
    ).data or {}

    summary = ""
    founder = ""
    category = ""
    archetypes: list[dict[str, Any]] = []
    if sim.get("icp_profile_id"):
        icp = (
            admin.table("icp_profiles")
            .select("profile, product_summary")
            .eq("id", sim["icp_profile_id"])
            .single()
            .execute()
        ).data or {}
        summary = str(icp.get("product_summary") or "")
        profile = icp.get("profile")
        if isinstance(profile, str):
            try:
                profile = json.loads(profile)
            except ValueError:
                profile = {}
        # The founder's own words only, never the room's — the authority for
        # which money figures sendable copy may state. The price lives in
        # whichever summary the run populated (see `facts.founder_material`).
        founder = founder_material({"product_summary": summary, "profile": profile})
        if isinstance(profile, dict):
            category = str(profile.get("category") or "")
            raw = profile.get("archetypes")
            if isinstance(raw, list):
                archetypes = [a for a in raw if isinstance(a, dict) and a.get("id")]

    # Most-weighted first, so a cap takes the largest share of the audience
    # rather than whichever archetype synthesis happened to emit first.
    archetypes.sort(key=lambda a: float(a.get("weight") or 0.0), reverse=True)

    return {
        "name": sim.get("name") or "",
        "goal": sim.get("prediction_goal") or "",
        "summary": summary,
        "founder_material": founder,
        "category": category,
        "archetypes": archetypes,
    }


class SequenceInputs(BaseModel):
    """What this run can support a sequence from, counted before anything is charged."""

    objections: int = 0
    archetypes: int = 0


def available_inputs(simulation_id: str, org_id: str) -> SequenceInputs:
    """Count the two inputs a sequence cannot be written without.

    Public because the route refuses on these figures *before* it charges, and
    the builder refuses on them again before it works. Both refusals are
    deliberate — a route that only charged would take money for a build that
    cannot happen, and a builder that only trusted the route would generate from
    nothing the first time it was called from anywhere else. What must not be
    duplicated is the *definition*: "a buyer archetype" is decided here, once,
    so a change to it cannot move the builder without moving the refusal.
    """
    admin = get_supabase_admin()
    counted = (
        admin.table("canonical_objections")
        .select("id", count="exact")
        .eq("simulation_id", simulation_id)
        .eq("organization_id", org_id)
        .execute()
    )
    objections = counted.count if counted.count is not None else len(counted.data or [])
    return SequenceInputs(
        objections=int(objections or 0),
        archetypes=len(_load_context(simulation_id, org_id)["archetypes"]),
    )


def _load_winning_message(simulation_id: str, org_id: str) -> dict[str, Any]:
    """The variant the scoreboard named, or nothing.

    **The scoreboard's refusal is honoured.** `winner_variant_key` is None
    whenever the top two arenas' intervals overlap, and the top row of the
    ranking is display order rather than a claim. Reading the ranking's first
    entry when the scoreboard declined to name a winner would launder sampling
    noise into the opening line of every email the founder sends — which is the
    exact failure `variant_scoreboard` refuses in order to prevent.
    """
    admin = get_supabase_admin()
    rows = (
        admin.table("simulation_analysis")
        .select("artifact")
        .eq("simulation_id", simulation_id)
        .eq("organization_id", org_id)
        .limit(1)
        .execute()
    ).data or []
    artifact = (rows[0].get("artifact") if rows else None) or {}
    board = artifact.get("scoreboard") if isinstance(artifact, dict) else None
    key = board.get("winner_variant_key") if isinstance(board, dict) else None
    if not key:
        return {}

    variant = (
        admin.table("simulation_variants")
        .select("variant_key, label, content")
        .eq("simulation_id", simulation_id)
        .eq("organization_id", org_id)
        .eq("variant_key", key)
        .single()
        .execute()
    ).data or {}
    content = str(variant.get("content") or "").strip()
    if not content:
        # The scoreboard named an arena whose copy is gone. Reporting no winner
        # is honest; reporting a winner with no message is a UI element that
        # renders empty next to a claim that a test decided it.
        log.warning("outbound_winner_has_no_copy", simulation_id=simulation_id, variant=key)
        return {}
    return {
        "key": str(key),
        "label": str(variant.get("label") or ""),
        "content": content,
    }


def _skeleton_block(pains: dict[int, dict[str, Any]]) -> str:
    """The structure the model writes into, with each pain slot's evidence."""
    lines: list[str] = []
    for touch in SEQUENCE_SKELETON:
        if touch.pain_slot and touch.pain_slot not in pains:
            # Fewer objections were measured than the skeleton has slots. The
            # touch is dropped rather than filled with a generic one — a
            # sequence of 16 touches where three are about nothing is worse
            # than a sequence of 13 that are all about something.
            continue
        line = f"- step {touch.step} | day {touch.day} | {touch.channel} | {touch.purpose}"
        if touch.pain_slot:
            pain = pains[touch.pain_slot]
            quotes = _quotes(pain)
            line += (
                f"\n    objection to answer: {pain.get('label') or ''}"
                f"\n    what buyers actually said: "
                f"{' | '.join(quotes) if quotes else '(none recorded)'}"
                f"\n    framing: angle {touch.angle}"
            )
            if touch.angle == 2:
                line += " — same objection as its angle 1 step, framed differently"
        lines.append(line)
    return "\n".join(lines)


def _archetype_block(archetype: dict[str, Any]) -> str:
    def _listed(field: str) -> str:
        values = archetype.get(field)
        if not isinstance(values, list):
            return "(not stated)"
        cleaned = [str(v).strip() for v in values if str(v).strip()]
        return ", ".join(cleaned) if cleaned else "(not stated)"

    return (
        f"label: {archetype.get('label') or ''}\n"
        f"role: {archetype.get('role') or ''}\n"
        f"seniority: {archetype.get('seniority') or ''}\n"
        f"budget authority: {archetype.get('budget_authority') or ''}\n"
        f"what they run today: {_listed('incumbent_tooling')}\n"
        f"what they judge on: {_listed('evaluation_criteria')}\n"
        f"what makes them distrust a pitch: {_listed('skepticism_triggers')}\n"
        f"their goals: {_listed('goals')}\n"
        f"their stated pains: {_listed('pains')}"
    )


def _user_prompt(
    context: dict[str, Any],
    archetype: dict[str, Any],
    pains: dict[int, dict[str, Any]],
    winner: dict[str, Any],
) -> str:
    winning = (
        f"THE MESSAGE THIS ROOM PICKED — a message test ran and the measurement "
        f"named this version. Steps 1 and 5 lead with its argument, in these "
        f"words where they fit:\n{winner['content']}\n\n"
        if winner
        else "NO MESSAGE TEST NAMED A WINNER for this run. Lead with the "
        "founder's own words below rather than a version nothing measured.\n\n"
    )
    return (
        f"PRODUCT: {context['name']}\n"
        f"CATEGORY: {context['category'] or '(not stated)'}\n"
        f"WHAT THE FOUNDER WANTED TO KNOW: {context['goal']}\n"
        f"THE PRODUCT IN THE FOUNDER'S WORDS: "
        f"{context['summary'] or '(not supplied)'}\n\n"
        f"{winning}"
        f"THE BUYER YOU ARE WRITING TO:\n{_archetype_block(archetype)}\n\n"
        f"THE SEQUENCE. Write copy for every step listed and no others:\n"
        f"{_skeleton_block(pains)}\n\n"
        'Return JSON: {"steps": [{"step": int, "subject": str, "body": str}], '
        '"notes": [str]}'
    )


def _placeholder_count(steps: list[OutboundStep], notes: list[str]) -> int:
    """How many blanks the founder still has to fill before any of this sends.

    Counts the `[TODO: …]` *shape*, not the two spellings this module names.
    All four live sequences reported `placeholders_to_fill: 0` while carrying
    `[TODO: benchmark hours saved]`, `[TODO: customer name]` and `[TODO: entity
    count]` — on copy whose whole purpose is to be sent to a stranger.

    **Notes are counted too.** Covering step copy alone still undercounted a
    live sequence 11 against 13, because two markers sat in the notes — and a
    note is where the model puts the thing it could not source, which is
    exactly what this number is for.
    """
    step_text = "\n".join(f"{step.subject}\n{step.body}" for step in steps)
    return count_placeholders(step_text) + count_placeholders("\n".join(notes))


def _assemble(
    generated: _Generated,
    pains: dict[int, dict[str, Any]],
    archetype_id: str,
) -> list[OutboundStep]:
    """Bind the model's copy to the skeleton, dropping anything that does not fit."""
    by_step = {item.step: item for item in generated.steps}
    steps: list[OutboundStep] = []

    for touch in SEQUENCE_SKELETON:
        if touch.pain_slot and touch.pain_slot not in pains:
            continue
        copy = by_step.get(touch.step)
        if copy is None or not copy.body.strip():
            # A step with no words is not a touch a founder can send, and
            # rendering an empty card in the middle of a sequence reads as a
            # product bug rather than as a model that skipped one.
            log.warning(
                "outbound_step_missing_copy", archetype_id=archetype_id, step=touch.step
            )
            continue

        body = copy.body.strip()
        subject = copy.subject.strip() if touch.channel == CHANNEL_EMAIL else ""
        # **The privacy boundary, enforced rather than promised.** `privacy.py`
        # forbids Saibyl storing a personal email address, phone number or
        # postal address, and copy is stored like anything else. A step that
        # carries one is dropped whole rather than trimmed — the same rule
        # `rejects_as_personal_data` applies to a contact record, and for the
        # same reason: text that needed editing to be storable came from a
        # model that was inventing.
        #
        # The scan is deliberately over-broad and that is safe here precisely
        # because this module forbids the model from writing raw numbers at
        # all: a step that trips the phone pattern is a step that wrote a
        # number where `[TODO: your number]` belonged.
        if contains_personal_contact_detail(subject) or contains_personal_contact_detail(body):
            log.warning(
                "outbound_step_dropped_contact_detail",
                archetype_id=archetype_id,
                step=touch.step,
            )
            continue

        pain = pains.get(touch.pain_slot) if touch.pain_slot else None
        steps.append(
            OutboundStep(
                step=touch.step,
                day=touch.day,
                channel=touch.channel,
                purpose=touch.purpose,
                # Measured figures come from the database rows here, never from
                # the model's copy of them.
                objection_key=str(pain.get("objection_key")) if pain else None,
                objection_label=str(pain.get("label") or "") if pain else None,
                agents_raising=int(pain.get("agent_count") or 0) if pain else 0,
                load_bearing_score=float(pain.get("load_bearing_score") or 0.0) if pain else 0.0,
                evidence_quotes=_quotes(pain) if pain else [],
                angle=touch.angle,
                subject=subject,
                body=body,
            )
        )

    unknown = sorted(set(by_step) - {t.step for t in SEQUENCE_SKELETON})
    if unknown:
        # A seventeenth touch the model invented. Dropped rather than appended:
        # the cadence is the part a founder reviewed before paying.
        log.warning(
            "outbound_steps_dropped_off_skeleton", archetype_id=archetype_id, steps=unknown
        )
    return steps


async def build_outbound_sequences(simulation_id: str, org_id: str) -> OutboundSequences:
    """One sequence per buyer archetype, aimed at what the room actually said."""
    objections = _load_objections(simulation_id, org_id)
    if not objections:
        # Not an empty document — a run that cannot support one. Saying so beats
        # generating three invented pains under the product's name.
        raise ValueError(
            "This run has no measured objections yet, so there is nothing to "
            "build a sequence around. A sequence written without them is the "
            "generic outbound this is meant to replace."
        )

    context = _load_context(simulation_id, org_id)
    archetypes = context["archetypes"]
    if not archetypes:
        raise ValueError(
            "This run has no buyer profile attached, so there is nobody to "
            "write a sequence to. Runs built from a synthesized ICP carry one."
        )

    # Pain slots, in the measured ranking. Slot 1 is the most load-bearing
    # objection, not the model's favourite and not the loudest.
    pains = dict(enumerate(objections[:PAIN_SLOTS], start=1))

    winner = _load_winning_message(simulation_id, org_id)

    notes: list[str] = []
    if not winner:
        notes.append(
            "No message test named a winner for this run, so the opening "
            "touches lead with your own words rather than a version the room "
            "picked."
        )
    if len(pains) < PAIN_SLOTS:
        notes.append(
            f"Only {len(pains)} objection(s) were measured, so the sequence "
            f"walks {len(pains)} rather than {PAIN_SLOTS}. The touches for the "
            f"missing ones were dropped rather than filled with a generic one."
        )
    covered = archetypes[:MAX_ARCHETYPES]
    if len(archetypes) > MAX_ARCHETYPES:
        notes.append(
            f"Your profile has {len(archetypes)} buyer archetypes; sequences "
            f"were written for the {MAX_ARCHETYPES} with the largest share of "
            f"the audience."
        )

    sequences: list[ArchetypeSequence] = []
    for archetype in covered:
        user = _user_prompt(context, archetype, pains, winner)
        generated = await llm_structured(
            [
                {"role": "system", "content": SYSTEM},
                {"role": "user", "content": user},
            ],
            _Generated,
        )

        # This is the artifact that gets *sent*, so it is the one where an
        # invented figure stops being a quality problem. Live sequences carried
        # "customers are seeing 10+ hours per month back" for a product with no
        # customers, "we built volume pricing into the model" for one with no
        # volume pricing, and a $3,600/year price 12x off the founder's own —
        # all under notes labelling them "(factual)". A figure not in `user`
        # becomes the placeholder, which cannot be sent by accident.
        generated, invented = scrub_unsourced(
            generated, user, product_material=str(context.get("founder_material") or "")
        )
        if invented:
            log.warning(
                "outbound_scrubbed_invented_figures",
                simulation_id=simulation_id,
                archetype=str(archetype.get("id")),
                count=len(invented),
                figures=invented[:10],
            )

        archetype_id = str(archetype.get("id"))
        steps = _assemble(generated, pains, archetype_id)
        tooling = archetype.get("incumbent_tooling")
        sequences.append(
            ArchetypeSequence(
                archetype_id=archetype_id,
                archetype_label=str(archetype.get("label") or archetype_id),
                role=str(archetype.get("role") or ""),
                seniority=str(archetype.get("seniority") or ""),
                incumbent_tooling=(
                    [str(t) for t in tooling if str(t).strip()]
                    if isinstance(tooling, list)
                    else []
                ),
                steps=steps,
                # Measured rank order, straight off the loaded rows. The model
                # never reorders the pains because it is never asked for them.
                pains_addressed=[
                    str(pains[slot].get("objection_key")) for slot in sorted(pains)
                ],
                placeholders_to_fill=_placeholder_count(steps, generated.notes),
                notes=generated.notes,
            )
        )

    log.info(
        "outbound_sequences_built",
        simulation_id=simulation_id,
        sequences=len(sequences),
        pains=len(pains),
        winner=winner.get("key"),
    )
    return OutboundSequences(
        sequences=sequences,
        built_from_objections=len(pains),
        winning_variant_key=winner.get("key"),
        winning_variant_label=winner.get("label"),
        winning_message=winner.get("content"),
        notes=notes,
    )
