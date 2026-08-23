# PUBLIC INTERFACE
# ─────────────────────────────────────────────────────────
# MessagingDoc — the filled worksheet
# Problem, Solution, ICPLine, ValueProp, Differentiator,
# ElevatorPitch, ObjectionLine, MessageTest — its sections
# build_messaging_doc(simulation_id, org_id) -> MessagingDoc
# ─────────────────────────────────────────────────────────
"""The messaging worksheet, filled from what the room actually said.

GTM Module 1 says everything downstream — the deck, the demo, the website,
the outbound sequence, the ad — is derived from seven elements, so a defect
in the messaging is inherited by every asset built on it. The playbook then
hands the founder a blank worksheet, and a blank worksheet is filled from
memory: the problem the founder believes buyers have, the value props the
founder finds impressive, the differentiators nobody checked against a
competitor. The document reads well and is untested.

Saibyl has already run the test. `canonical_objections` holds what the room
raised, ranked by load-bearing score with the buyers' verbatim sentences
attached; `simulation_analysis.scoreboard` holds which version of the pitch
won when several were tried, or the refusal to name one when the intervals
overlap. This module fills the worksheet from those, so the ordering and the
emphasis are the measurement's rather than the founder's.

Four rules make it worth more than the blank version:

**Never invent a number, a customer, a case study or a benchmark.** Same
discipline as `services/website/revise.py`: where a value prop needs a metric
the input does not contain, the document writes `[TODO: your number]` and
counts the gaps. A visible placeholder is honest; a plausible invention is a
statistic the founder will say out loud to someone who can check it.

**Measured facts are attached here, from the database, never echoed by the
model.** The model returns objection *keys* and prose; the counts, the
load-bearing scores, the quotes and the scoreboard's verdict are attached
from the rows. A model asked to restate a score will eventually round it.

**Competitors come from the founder or from the buyers, never from the
model.** The allowed set is `icp_profiles.competitors`, plus any name the
model nominates that literally appears in a measured quote, plus the two that
are always real and always missing from the analysis — doing nothing and
building it in-house. A differentiator argued against a company that does not
exist is worse than no differentiator.

**A run with no measured objections refuses.** A messaging document generated
with nothing measured is exactly the document the founder would have written
alone, with Saibyl's name on it. That refusal is the whole difference.
"""
from __future__ import annotations

import json
from typing import Any

import structlog
from pydantic import BaseModel, Field

from app.core.database import get_supabase_admin
from app.core.llm_client import llm_structured
from app.services.gtm.facts import (
    MISSING_EXAMPLE,
    MISSING_NUMBER,
    count_placeholders,
    founder_material,
    scrub_unsourced,
)

log = structlog.get_logger()

# How many objections the worksheet's objections section carries.
#
# Deliberately shorter than the answer pack's ten. This section exists to say
# what the *messaging* has to pre-empt, and a messaging document listing ten
# objections has quietly become an objection matrix — which is a different
# module, priced and built separately.
MAX_OBJECTIONS = 6

# Verbatim quotes carried per objection. Two proves the objection is real and
# shows its range without turning a worksheet into a transcript.
QUOTES_PER_OBJECTION = 2

# The playbook's hard count: more than three and none of them are remembered.
VALUE_PROP_COUNT = 3

# The three-differentiator test needs exactly three to be a test at all.
DIFFERENTIATOR_COUNT = 3

# The competitors every founder has and no competitive analysis includes.
ALWAYS_REAL_ALTERNATIVES = ("Doing nothing", "Building it in-house")

# What the model writes where a fact would go and the input does not have one.
# Two markers rather than one because a missing metric and a missing customer
# story are filled by different people on different days.
# Both now live in `gtm.facts`, so the prompts that ask for them, the
# substitution that writes them and the counter that reports them cannot drift
# apart. Re-exported here because the prompt text below interpolates them.
__all__ = ["MISSING_EXAMPLE", "MISSING_NUMBER", "build_messaging_doc"]


class ProblemDimension(BaseModel):
    """One named dimension of the problem, with its concrete sub-causes.

    The playbook's shape — one compressed headline, then three named
    dimensions — is what survives translation into a slide, an email and an
    ad. A single paragraph does not.
    """

    name: str
    sub_causes: list[str] = Field(default_factory=list)


class Problem(BaseModel):
    headline: str = ""
    dimensions: list[ProblemDimension] = Field(default_factory=list)
    impact: str = Field(
        default="",
        description="The quantified consequence. A placeholder where the input has no figure.",
    )
    # Which measured objections evidence that this is the problem buyers feel.
    # Filtered against the real keys here; a key nobody raised is dropped.
    evidence_objection_keys: list[str] = Field(default_factory=list)


class Solution(BaseModel):
    """Two one-sentence statements. The one-sentence constraint is the point:
    if it takes two, the prioritisation decision has not been made yet."""

    what_we_do_high_level: str = ""
    what_we_do_specific: str = ""
    how_we_do_it: str = Field(
        default="",
        description="The sentence that makes the claim credible. Skipping it is why a pitch reads as marketing.",
    )


class ICPLine(BaseModel):
    who: str = ""
    # An ICP that excludes nothing is not an ICP, so the exclusion is a field
    # rather than a sentence the model may skip.
    not_for: str = ""


class ValueProp(BaseModel):
    """One of exactly three. Category is the memory hook; the statement is the
    substance; the source is what makes it checkable."""

    category: str = ""
    statement: str = ""
    source: str = Field(
        default="",
        description="What in the input supports this — the founder's own words, or what buyers said.",
    )
    # Set only when the prop answers a measured objection. Validated against
    # the real keys here: a model citing an objection nobody raised is the
    # exact failure this module exists to prevent, so the citation is cleared
    # rather than shown.
    source_objection_key: str | None = None


class Differentiator(BaseModel):
    """A distinction plus what the customer gets from it — never a feature."""

    distinction: str = ""
    client_benefit: str = ""
    # Which alternatives can also claim this one. Filtered to names the
    # founder or the buyers supplied; the set-level test is computed from
    # these lists rather than asserted by the model.
    rivals_who_can_claim_it: list[str] = Field(default_factory=list)


class ElevatorPitch(BaseModel):
    problem: str = ""
    solution: str = ""
    value: str = ""
    differentiator: str = ""
    # The most frequently dropped element and the most consequential: a pitch
    # without an ask is a monologue.
    call_to_action: str = ""

    # The measured version this was built from, when the room named a winner.
    # Attached here, never taken from the model.
    from_variant_key: str | None = None
    from_variant_label: str | None = None
    # Set when several versions were tested and the scoreboard refused to name
    # a winner. Carries the scoreboard's own sentence.
    caveat: str | None = None


class ObjectionLine(BaseModel):
    """What the messaging has to survive, in the order that costs deals."""

    objection_key: str
    label: str
    # Measured, carried through from the rows.
    agents_raising: int = 0
    load_bearing_score: float = 0.0
    quotes: list[str] = Field(default_factory=list)

    how_the_messaging_answers_it: str = ""


class MessageTest(BaseModel):
    """What happened when several versions of the pitch met one room.

    None on a run that tested a single message: one version is not a
    comparison, and a one-row result invites a reader to treat it as one.
    """

    versions_tested: int = 0
    winner_variant_key: str | None = None
    winner_label: str | None = None
    # The scoreboard's own words, carried verbatim. Rewriting a refusal is how
    # "the intervals overlap" becomes "version B edged ahead".
    verdict: str = ""
    named_a_winner: bool = False


class MessagingDoc(BaseModel):
    problem: Problem
    solution: Solution
    icp: ICPLine
    value_props: list[ValueProp]
    differentiators: list[Differentiator]
    # Computed from the differentiators' rival lists, not claimed by the
    # model: either no alternative claims all three, or the set is not
    # defensible yet and this says who breaks it.
    differentiation_verdict: str = ""
    elevator_pitch: ElevatorPitch
    objections: list[ObjectionLine]
    message_test: MessageTest | None = None

    # The only names this document is allowed to argue against.
    alternatives: list[str] = Field(default_factory=list)

    # What the document was built from, and what is still missing. Both are
    # rendered: a founder should be able to see the coverage without reading
    # the whole worksheet.
    built_from_objections: int = 0
    placeholders_to_fill: int = 0
    notes: list[str] = Field(default_factory=list)


class _PitchDraft(BaseModel):
    """The pitch's prose only. It deliberately has no field for the winning
    variant or the caveat — those are attached from the scoreboard, and a
    model that cannot name a winner cannot name the wrong one."""

    problem: str = ""
    solution: str = ""
    value: str = ""
    differentiator: str = ""
    call_to_action: str = ""


class _ObjectionDraft(BaseModel):
    objection_key: str = ""
    how_the_messaging_answers_it: str = ""


class _Generated(BaseModel):
    """What the model returns. Measured fields are absent by construction."""

    problem: Problem = Field(default_factory=Problem)
    solution: Solution = Field(default_factory=Solution)
    icp: ICPLine = Field(default_factory=ICPLine)
    value_props: list[ValueProp] = Field(default_factory=list)
    differentiators: list[Differentiator] = Field(default_factory=list)
    elevator_pitch: _PitchDraft = Field(default_factory=_PitchDraft)
    objections: list[_ObjectionDraft] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


SYSTEM = f"""You fill in a go-to-market messaging worksheet for a founder. \
The objections in your input were measured — real buyers raised them and \
their verbatim words are attached — and where several versions of the pitch \
were tested, the result of that test is attached too.

Rules you may not break:
- Use ONLY what the founder's own material and the buyers' own words \
support. Where a sentence needs a number, a customer name, a case study or a \
benchmark that is not in the input, write exactly {MISSING_NUMBER} or \
{MISSING_EXAMPLE}. Never invent a statistic, a customer, a logo or a \
benchmark. A placeholder is honest; an invented figure is one the founder \
will say out loud to someone who can check it.
- Never name a competitor that is not in the ALTERNATIVES list you are \
given. If you believe one is missing, say so in notes instead of naming it.
- The problem statement is one compressed headline plus up to three named \
dimensions, each with concrete sub-causes. Chain the pain to its \
consequence: the logical layer justifies, the emotional layer motivates.
- The solution is two separate ONE-SENTENCE statements: what we do (a \
high-level version and a specific version) and how we do it. If it takes two \
sentences, the prioritisation has not been made.
- The ICP line names who this is for AND who it is not for. An ICP that \
excludes nothing is not an ICP.
- Exactly {VALUE_PROP_COUNT} value propositions, each with a category that \
acts as the memory hook (Fast / Easy / Efficient / Safe / Compliant or \
similar), a statement in the form [business driver] + [movement] + [metric], \
and a source naming what in the input supports it. Where a prop answers one \
of the measured objections, set source_objection_key to that objection's key.
- Exactly {DIFFERENTIATOR_COUNT} differentiators, chosen so that most \
alternatives have one, some have two, and none have all three. For each, \
list which of the ALTERNATIVES can also claim it — honestly. A set no \
competitor breaks is the only defensible set, and claiming one you do not \
have gets the founder caught.
- A differentiator names the distinction and then says what the customer \
gets from it. A feature list is not a differentiator.
- The elevator pitch is written for a perfect buyer who knows nothing about \
this product and has seconds. It must end with an ask.
- For each measured objection, say what the messaging does about it — which \
line pre-empts it, or that the messaging cannot and it has to be handled on \
the call."""


def _load_objections(simulation_id: str, org_id: str) -> list[dict[str, Any]]:
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
        .limit(MAX_OBJECTIONS)
        .execute()
    ).data or []


def _load_context(simulation_id: str, org_id: str) -> dict[str, Any]:
    """The product's own words, and the rivals the founder already named."""
    admin = get_supabase_admin()
    sim = (
        admin.table("simulations")
        .select("name, prediction_goal, project_id, icp_profile_id")
        .eq("id", simulation_id)
        .eq("organization_id", org_id)
        .single()
        .execute()
    ).data or {}

    competitors: list[str] = []
    summary = ""
    founder = ""
    if sim.get("icp_profile_id"):
        icp = (
            admin.table("icp_profiles")
            # `profile` too — the founder's price lives in whichever summary
            # the run populated (see `facts.founder_material`).
            .select("competitors, product_summary, profile")
            .eq("id", sim["icp_profile_id"])
            .single()
            .execute()
        ).data or {}
        raw = icp.get("competitors")
        if isinstance(raw, list):
            competitors = [str(c).strip() for c in raw if str(c).strip()]
        summary = str(icp.get("product_summary") or "")
        founder = founder_material(icp)

    return {
        "name": sim.get("name") or "",
        "goal": sim.get("prediction_goal") or "",
        "summary": summary,
        # The founder's own words only, never the room's — the authority for
        # which money figures this document may state.
        "founder_material": founder,
        "competitors": competitors,
    }


def _load_message_test(simulation_id: str, org_id: str) -> dict[str, Any]:
    """The versions that were tested, and what the scoreboard concluded.

    Both halves are needed and they come from different places: the copy is
    in `simulation_variants` because that is what the founder wrote, and the
    verdict is in the analysis artifact because that is what was measured.
    Reading the winner's copy out of the scoreboard instead would tie this
    module to the artifact's shape for no gain.
    """
    admin = get_supabase_admin()
    variants = (
        admin.table("simulation_variants")
        .select("variant_key, label, content, position")
        .eq("simulation_id", simulation_id)
        .eq("organization_id", org_id)
        .order("position")
        .execute()
    ).data or []

    rows = (
        admin.table("simulation_analysis")
        .select("artifact")
        .eq("simulation_id", simulation_id)
        .eq("organization_id", org_id)
        .limit(1)
        .execute()
    ).data or []

    artifact = rows[0].get("artifact") if rows else None
    if isinstance(artifact, str):
        try:
            artifact = json.loads(artifact)
        except ValueError:
            artifact = None
    scoreboard = (artifact or {}).get("scoreboard") if isinstance(artifact, dict) else None
    scoreboard = scoreboard if isinstance(scoreboard, dict) else {}

    return {
        "variants": variants,
        "winner_variant_key": scoreboard.get("winner_variant_key"),
        "verdict": str(scoreboard.get("verdict") or ""),
    }


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


def _named_alternatives(competitors: list[str]) -> list[str]:
    """What the founder already named, plus the two that are always real.

    Built in one place because it is used twice — once as the list the model
    is allowed to write about, once as the base the model's nominations are
    checked against — and a prompt that permitted a name the filter then
    dropped would look like the model disobeying an instruction it followed.
    """
    return list(dict.fromkeys([*competitors, *ALWAYS_REAL_ALTERNATIVES]))


def _allowed_alternatives(
    named: list[str],
    objections: list[dict[str, Any]],
    nominated: list[str],
) -> list[str]:
    """Every name this document may argue against, and nothing else.

    Two sources, in descending order of how much they are trusted: the names
    the founder gave (plus the always-real pair), and any name the model
    nominated that a buyer literally said out loud. That second one is checked
    against the quote text rather than believed — the model may notice a rival
    in the room's own words, but it may not conjure one, and the difference is
    a substring match away.
    """
    spoken = " ".join(
        [str(row.get("summary") or "") for row in objections]
        + [q for row in objections for q in _quotes(row)]
    ).lower()

    allowed = list(named)
    known = {name.lower() for name in allowed}
    for name in nominated:
        cleaned = str(name).strip()
        if not cleaned or cleaned.lower() in known:
            continue
        if cleaned.lower() in spoken:
            allowed.append(cleaned)
            known.add(cleaned.lower())
        else:
            # The failure mode: a battlecard, or here a differentiator,
            # written against a company that does not exist.
            log.warning("messaging_doc_dropped_invented_competitor", name=cleaned)
    return list(dict.fromkeys(allowed))


def _three_way_verdict(
    differentiators: list[Differentiator],
    alternatives: list[str],
) -> str:
    """Run the playbook's test over the set, and report what it found.

    The test is a property of the *set*, not of any one differentiator: most
    competitors have one, some have two, none have all three. A model asked
    whether its own set passes will say yes, so the answer is computed from
    the rival lists it filled in and stated in the document either way. A set
    that fails is still useful — it tells the founder to go find the
    combination the competitor cannot match.
    """
    if len(differentiators) < DIFFERENTIATOR_COUNT:
        return (
            f"The three-differentiator test could not be run: the document has "
            f"{len(differentiators)} of the {DIFFERENTIATOR_COUNT} it needs."
        )

    claimed = [set(d.rivals_who_can_claim_it) for d in differentiators]
    breakers = [name for name in alternatives if all(name in group for group in claimed)]
    if breakers:
        return (
            f"Not defensible yet: {', '.join(breakers)} can claim all three. "
            f"Find the combination they cannot match."
        )
    return (
        "Defensible: no alternative named here claims all three, which is what "
        "makes the set hold up under comparison."
    )


def _count_placeholders(payload: str) -> int:
    """Every blank, not just the two spellings this module names.

    Counting only `MISSING_NUMBER` and `MISSING_EXAMPLE` meant a document
    reported `placeholders_to_fill: 0` while its elevator pitch — the most
    copied line in it — read "down to [TODO: validated time savings]". A
    counter that says zero is worse than no counter: a founder reads it as a
    promise the copy is ready to send.
    """
    return count_placeholders(payload)


def _variant_lines(variants: list[dict[str, Any]]) -> str:
    return "\n".join(
        f"- {v.get('variant_key')}: {v.get('label') or '(unnamed)'} — {v.get('content') or ''}"
        for v in variants
    )


async def build_messaging_doc(simulation_id: str, org_id: str) -> MessagingDoc:
    """The worksheet, filled from the run's measurement."""
    objections = _load_objections(simulation_id, org_id)
    if not objections:
        # The refusal this module is worth having. A messaging document
        # generated with nothing measured is the one the founder would have
        # written alone — invented problems answered with invented confidence
        # — with the product's name on it.
        raise ValueError(
            "This run has no measured objections yet, so there is nothing to "
            "build a messaging document from."
        )

    context = _load_context(simulation_id, org_id)
    test = _load_message_test(simulation_id, org_id)
    variants = test["variants"]

    by_key = {str(o.get("objection_key")): o for o in objections}
    order = {key: i for i, key in enumerate(by_key)}

    winner_key = str(test["winner_variant_key"] or "") or None
    winner: dict[str, Any] | None = None
    if winner_key:
        winner = next(
            (v for v in variants if str(v.get("variant_key")) == winner_key), None
        )
        if winner is None:
            # A winner key with no row behind it is a broken join, not a
            # winner: the document would claim a version won and be unable to
            # say which words it was. Degrade to "no winner named".
            log.warning(
                "messaging_doc_winner_variant_missing",
                simulation_id=simulation_id,
                variant_key=winner_key,
            )
            winner_key = None

    objection_block = "\n".join(
        f"- key: {row.get('objection_key')}\n"
        f"  objection: {row.get('label')}\n"
        f"  summary: {row.get('summary') or ''}\n"
        f"  raised by: {row.get('agent_count', 0)} buyers\n"
        f"  their words: {' | '.join(_quotes(row)) or '(none recorded)'}"
        for row in objections
    )

    if winner is not None:
        message_block = (
            "THE MESSAGE TEST — several versions met the same room and one won. "
            "Build the elevator pitch from the winning version's copy:\n"
            f"WINNER ({winner.get('variant_key')}): {winner.get('content') or ''}\n"
            f"THE MEASURED VERDICT: {test['verdict']}\n"
            "EVERY VERSION TESTED:\n" + _variant_lines(variants)
        )
    elif len(variants) > 1:
        message_block = (
            "THE MESSAGE TEST — several versions met the same room and the "
            "measurement REFUSED TO NAME A WINNER. Do not pick one. Write the "
            "pitch from what the versions share and from the product's own "
            "words, and do not claim any version performed better.\n"
            f"THE MEASURED VERDICT: {test['verdict'] or '(the intervals overlapped)'}\n"
            "EVERY VERSION TESTED:\n" + _variant_lines(variants)
        )
    else:
        message_block = (
            "THE MESSAGE TEST — only one version of the message was tested, so "
            "there is no comparison. Write the pitch from the product's own "
            "words and do not claim any version was better than another."
        )

    named_alternatives = _named_alternatives(context["competitors"])

    user = (
        f"PRODUCT: {context['name']}\n"
        f"WHAT THE FOUNDER WANTED TO KNOW: {context['goal']}\n"
        f"THE PRODUCT IN THE FOUNDER'S WORDS: {context['summary'] or '(not supplied)'}\n\n"
        f"MEASURED OBJECTIONS, most load-bearing first:\n{objection_block}\n\n"
        f"{message_block}\n\n"
        "ALTERNATIVES — the only names you may write about. If a real "
        "competitor is missing, say so in notes rather than naming it:\n"
        + "\n".join(f"- {name}" for name in named_alternatives)
        + '\n\nReturn JSON: {"problem": {"headline", "dimensions": '
        '[{"name", "sub_causes": [str]}], "impact", "evidence_objection_keys": [str]}, '
        '"solution": {"what_we_do_high_level", "what_we_do_specific", "how_we_do_it"}, '
        '"icp": {"who", "not_for"}, '
        '"value_props": [{"category", "statement", "source", "source_objection_key"}], '
        '"differentiators": [{"distinction", "client_benefit", '
        '"rivals_who_can_claim_it": [str]}], '
        '"elevator_pitch": {"problem", "solution", "value", "differentiator", '
        '"call_to_action"}, '
        '"objections": [{"objection_key", "how_the_messaging_answers_it"}], '
        '"notes": [str]}'
    )

    generated = await llm_structured(
        [{"role": "system", "content": SYSTEM}, {"role": "user", "content": user}],
        _Generated,
    )

    # The same discipline the competitor check below applies to names, applied
    # to figures. This document is the best-behaved of the three artifacts —
    # its own notes police claims the answer pack made — and it still converted
    # a buyer's all-entities "15-20 hours a month" into "per month per entity",
    # tripling the stated pain. A figure not in `user` becomes the placeholder
    # the prompt asked for.
    generated, invented = scrub_unsourced(
        generated, user, product_material=str(context.get("founder_material") or "")
    )
    if invented:
        log.warning(
            "messaging_doc_scrubbed_invented_figures",
            simulation_id=simulation_id,
            count=len(invented),
            figures=invented[:10],
        )

    notes = list(generated.notes)

    # ── Competitors: the model's nominations are verified, not believed ──
    nominated = [
        name
        for diff in generated.differentiators
        for name in diff.rivals_who_can_claim_it
    ]
    alternatives = _allowed_alternatives(named_alternatives, objections, nominated)
    allowed = set(alternatives)

    differentiators = [
        Differentiator(
            distinction=diff.distinction,
            client_benefit=diff.client_benefit,
            rivals_who_can_claim_it=[
                name for name in diff.rivals_who_can_claim_it if name in allowed
            ],
        )
        for diff in generated.differentiators[:DIFFERENTIATOR_COUNT]
    ]
    verdict = _three_way_verdict(differentiators, alternatives)

    # ── Value props: three, and every citation checked against the rows ──
    value_props: list[ValueProp] = []
    for prop in generated.value_props[:VALUE_PROP_COUNT]:
        key = str(prop.source_objection_key or "") or None
        if key and key not in by_key:
            # A prop citing an objection nobody raised is the invented
            # evidence this module exists to prevent. The prop survives; the
            # false citation does not.
            log.warning("messaging_doc_dropped_unmatched_source", key=key)
            key = None
        value_props.append(
            ValueProp(
                category=prop.category,
                statement=prop.statement,
                source=prop.source,
                source_objection_key=key,
            )
        )
    if len(value_props) < VALUE_PROP_COUNT:
        # Not padded. A manufactured third value prop is exactly the invention
        # the rest of this module refuses, and it would be the one the founder
        # least suspects because the document looks complete.
        notes.append(
            f"Only {len(value_props)} of the {VALUE_PROP_COUNT} value propositions "
            f"could be supported by this run's input. The playbook asks for three; "
            f"the missing one needs a fact this run did not measure."
        )

    # The measured ranking decides emphasis: the prop that answers the most
    # load-bearing objection leads. Stable, so props with no measured source
    # keep the model's order behind the ones that have evidence.
    value_props.sort(key=lambda p: order.get(p.source_objection_key or "", len(order)))

    # ── Problem evidence: keys only, checked against the rows ──
    problem = Problem(
        headline=generated.problem.headline,
        dimensions=generated.problem.dimensions,
        impact=generated.problem.impact,
        evidence_objection_keys=[
            key for key in generated.problem.evidence_objection_keys if key in by_key
        ],
    )

    # ── Objections: the model's prose, the database's numbers and quotes ──
    lines: list[ObjectionLine] = []
    seen: set[str] = set()
    for item in generated.objections:
        key = str(item.objection_key or "")
        source = by_key.get(key)
        if not source or key in seen:
            if not source:
                log.warning("messaging_doc_dropped_unmatched_objection", key=key)
            continue
        seen.add(key)
        lines.append(
            ObjectionLine(
                objection_key=key,
                label=str(source.get("label") or key),
                agents_raising=int(source.get("agent_count") or 0),
                load_bearing_score=float(source.get("load_bearing_score") or 0.0),
                quotes=_quotes(source),
                how_the_messaging_answers_it=item.how_the_messaging_answers_it,
            )
        )
    # Measured order, not the model's. The ranking is the product.
    lines.sort(key=lambda line: order.get(line.objection_key, len(order)))

    # ── The pitch, and the refusal that must survive into it ──
    message_test: MessageTest | None = None
    if len(variants) > 1:
        message_test = MessageTest(
            versions_tested=len(variants),
            winner_variant_key=winner_key,
            winner_label=(str(winner.get("label") or "") or None) if winner else None,
            verdict=test["verdict"],
            named_a_winner=winner is not None,
        )

    # The refusal, carried into the document. When the scoreboard declined to
    # separate the versions, the pitch says so instead of promoting the top
    # row — an ordering drawn from overlapping intervals is not a winner, and
    # a pitch built on one is noise the founder will repeat for months, in
    # every asset derived from this worksheet.
    caveat: str | None = None
    if len(variants) > 1 and winner is None:
        caveat = test["verdict"] or (
            "The versions tested could not be separated, so no version is "
            "named the winner here."
        )

    pitch = ElevatorPitch(
        problem=generated.elevator_pitch.problem,
        solution=generated.elevator_pitch.solution,
        value=generated.elevator_pitch.value,
        differentiator=generated.elevator_pitch.differentiator,
        call_to_action=generated.elevator_pitch.call_to_action,
        # Attached from the scoreboard, never echoed by the model.
        from_variant_key=winner_key,
        from_variant_label=(str(winner.get("label") or "") or None) if winner else None,
        caveat=caveat,
    )

    doc = MessagingDoc(
        problem=problem,
        solution=generated.solution,
        icp=generated.icp,
        value_props=value_props,
        differentiators=differentiators,
        differentiation_verdict=verdict,
        elevator_pitch=pitch,
        objections=lines,
        message_test=message_test,
        alternatives=alternatives,
        built_from_objections=len(objections),
        notes=notes,
    )
    # Counted after assembly so the number covers every section, including the
    # pitch. Rendered next to the document: a founder should see how many
    # facts they still owe it without reading it twice.
    doc.placeholders_to_fill = _count_placeholders(doc.model_dump_json())

    log.info(
        "messaging_doc_built",
        simulation_id=simulation_id,
        objections=len(lines),
        value_props=len(value_props),
        differentiators=len(differentiators),
        versions_tested=len(variants),
        winner=winner_key,
        placeholders=doc.placeholders_to_fill,
    )
    return doc
