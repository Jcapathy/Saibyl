# PUBLIC INTERFACE
# ─────────────────────────────────────────────────────────
# AnswerPack, MatrixRow, Battlecard — the artifact
# build_answer_pack(simulation_id, org_id) -> AnswerPack
# ─────────────────────────────────────────────────────────
"""The objection matrix: what to say when a real person raises it out loud.

Every GTM playbook tells a founder to build an objection matrix, and every
founder builds it the same way — sitting alone, imagining what a buyer might
say. The result is a document of invented objections answered with invented
confidence, and the first real call disproves it.

Saibyl already measured the objections. `canonical_objections` holds them
ranked by load-bearing score — reach × intensity × spread across kinds of
buyer, which is deliberately not raw frequency, because the loudest objection
and the one that kills the deal are usually different objections. Each row
carries the verbatim sentences buyers actually said. So the matrix can be
built from evidence instead of imagination, ordered by what actually costs
deals, with the buyer's own words attached as the proof that the row is real.

**This is not the inoculation loop, and the difference matters.** Inoculation
drafts *published material* — a page, a FAQ — pre-positions it in front of a
copied audience, and re-runs the room to prove the objection moved. That
answers "does saying this change what buyers think?". This module answers a
different question: "the objection just came up on a call, what do I say?".
One is material you publish and test; the other is a script a human uses live
and no simulation can score. They share an input and nothing else.

**Fact discipline, inherited from `revise.py`.** The model may use only what
the founder's own material and the buyers' own words support. Where a response
needs a number, a customer name or a case study that does not exist in the
input, it writes `[TODO: your number]` rather than inventing one. A matrix
that hands a founder a fabricated statistic to say on a sales call is worse
than no matrix: it is a lie with the founder's name on it, delivered to the
one audience that can check.

**Competitors come from the founder, never from the model.** Battlecards are
generated only for names already in `icp_profiles.competitors` or named in the
buyers' quotes, plus the two that are always real and always forgotten — doing
nothing, and building it in-house. Asking a model to name a founder's
competitors is how a battlecard ends up arguing against a company that does
not exist.
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

log = structlog.get_logger()

# How many objections the matrix covers. The tail past this is single-agent
# noise that would pad the document and dilute the ranking that makes it
# useful — a founder rehearses the ones that cost deals, not all of them.
MAX_ROWS = 10

# Verbatim quotes carried per row. Two is enough to prove the objection is
# real and show its range without turning a script into a transcript.
QUOTES_PER_ROW = 2

# The competitors every founder has and no battlecard deck includes.
ALWAYS_REAL_ALTERNATIVES = ("Doing nothing", "Building it in-house")


class MatrixRow(BaseModel):
    """One objection, and the four moves that answer it on a call."""

    objection_key: str
    label: str
    # The measured facts, carried through rather than restated by the model.
    agents_raising: int = 0
    load_bearing_score: float = 0.0
    evidence_quotes: list[str] = Field(default_factory=list)

    acknowledge: str = Field(description="Say this first. Never argue with the objection.")
    explore: str = Field(description="The question that finds out what is really being asked.")
    respond: str = Field(description="The answer, using only what the material supports.")
    confirm: str = Field(description="The question that checks the objection is actually resolved.")
    # Stated when the honest answer is that this one cannot be talked away.
    when_to_walk: str | None = None


class Battlecard(BaseModel):
    """One alternative the buyer is really choosing between."""

    rival: str
    they_say: str
    the_honest_read: str = Field(
        description="Where the rival genuinely wins. A card with no concession is not usable."
    )
    where_we_win: str
    proof_needed: str | None = None


class AnswerPack(BaseModel):
    rows: list[MatrixRow]
    battlecards: list[Battlecard]
    # Named so a founder knows what this was built from and when.
    built_from_objections: int = 0
    notes: list[str] = Field(default_factory=list)
    #: Blanks the founder still has to fill before using this on a call. The
    #: messaging doc and the outbound sequences both surfaced one and this did
    #: not, so a pack shipped with eleven `[TODO: …]` in it and nothing saying
    #: so.
    placeholders_to_fill: int = 0


class _Generated(BaseModel):
    """What the model returns. Measured fields are added afterwards, not asked
    for — a model asked to echo a score will eventually round it."""

    rows: list[dict[str, Any]]
    battlecards: list[Battlecard]
    notes: list[str] = Field(default_factory=list)


SYSTEM = """You write objection-handling scripts for founders to use on real \
sales calls. You are given objections that were actually measured — real \
buyers raised them, and their verbatim words are attached.

Rules you may not break:
- Use ONLY what the founder's material and the buyers' quotes support. Where a \
response needs a number, a customer name, a case study or a benchmark that is \
not in the input, write exactly [TODO: your number] or [TODO: your example]. \
Never invent a statistic, a customer, or a comparison.
- The acknowledgement never argues. It states the concern back in the buyer's \
own terms so they hear that it landed.
- The explore step is a QUESTION, and it is the most important line. Most \
objections are a symptom of something more specific.
- The respond step answers what the explore question would uncover, in the \
founder's plain voice. No slogans.
- The confirm step is a question that would reveal the objection is still \
there if it is.
- When an objection is genuinely disqualifying — the buyer is wrong for this \
product — say so in when_to_walk instead of manufacturing a rebuttal. A \
matrix that pretends every objection is winnable teaches founders to argue \
with people who were never going to buy.
- Battlecards must concede where the rival genuinely wins. A card with no \
concession gets a founder caught."""


def _load_objections(simulation_id: str, org_id: str) -> list[dict[str, Any]]:
    admin = get_supabase_admin()
    rows = (
        admin.table("canonical_objections")
        .select(
            "objection_key, label, summary, quotes, agent_count, "
            "cohort_spread, load_bearing_score, first_round_seen"
        )
        .eq("simulation_id", simulation_id)
        .eq("organization_id", org_id)
        .order("load_bearing_score", desc=True)
        .limit(MAX_ROWS)
        .execute()
    ).data or []
    return rows


def _competitor_name(row: Any) -> str:
    """The rival's name, from the shape the column actually holds.

    `icp_profiles.competitors` is written as
    `[c.model_dump(mode="json") for c in profile.competitors]` — dicts of
    `name`, `positioning` and `mentioned_in` — by both writers of that column.
    `str(row)` therefore produced "{'name': 'Datadog', 'positioning': 'APM
    incumbent', 'mentioned_in': ['9f3e…']}", which went into the prompt's
    allow-list as the only name the model was permitted to write about, and
    into the battlecard the founder reads out loud, internal document UUID and
    all. Plain strings are still accepted: this column has held both.
    """
    if isinstance(row, dict):
        return str(row.get("name") or "").strip()
    return str(row or "").strip()


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
            # `profile` too: the founder's stated price lives in whichever of
            # the two summaries the run populated, and the money check has no
            # anchor without it (see `facts.founder_material`).
            .select("competitors, product_summary, profile")
            .eq("id", sim["icp_profile_id"])
            .single()
            .execute()
        ).data or {}
        raw = icp.get("competitors")
        if isinstance(raw, list):
            competitors = [name for name in map(_competitor_name, raw) if name]
        summary = str(icp.get("product_summary") or "")
        founder = founder_material(icp)

    return {
        "name": sim.get("name") or "",
        "goal": sim.get("prediction_goal") or "",
        "summary": summary,
        # The founder's own words only — never the room's. Used to decide which
        # money figures this document may state, not to build the prompt.
        "founder_material": founder,
        "competitors": competitors,
    }


def _quotes(row: dict[str, Any]) -> list[str]:
    raw = row.get("quotes")
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except ValueError:
            return []
    out: list[str] = []
    for q in (raw or [])[:QUOTES_PER_ROW]:
        text = q.get("text") if isinstance(q, dict) else q
        if text and str(text).strip():
            out.append(str(text).strip())
    return out


def _fact_material(context: dict[str, Any], objections: list[dict[str, Any]]) -> str:
    """The only text a figure in this pack is allowed to come from.

    Deliberately **not** the prompt. The prompt carries this module's own
    bookkeeping — "raised by: 14 buyers", "across 3 kinds of buyer" — and
    scrubbing against it made those counts license anything that landed on the
    same number: "we are 14% cheaper", "$3 per entity per month". A count this
    module printed is not evidence for a claim the model wrote.
    """
    parts = [
        str(context.get("name") or ""),
        str(context.get("goal") or ""),
        str(context.get("summary") or ""),
    ]
    for row in objections:
        parts.append(str(row.get("label") or ""))
        parts.append(str(row.get("summary") or ""))
        parts.extend(_quotes(row))
    return "\n".join(part for part in parts if part.strip())


async def build_answer_pack(simulation_id: str, org_id: str) -> AnswerPack:
    """The matrix, built from what the room actually said."""
    objections = _load_objections(simulation_id, org_id)
    if not objections:
        # No measured objections is not an empty document — it is a run that
        # cannot support one, and saying so beats generating a plausible
        # matrix from nothing.
        raise ValueError(
            "This run has no measured objections yet, so there is nothing to "
            "build answers from."
        )

    context = _load_context(simulation_id, org_id)
    rivals = list(dict.fromkeys([*context["competitors"], *ALWAYS_REAL_ALTERNATIVES]))

    lines = []
    for row in objections:
        quotes = _quotes(row)
        spread = row.get("cohort_spread") or {}
        lines.append(
            f"- key: {row.get('objection_key')}\n"
            f"  objection: {row.get('label')}\n"
            f"  summary: {row.get('summary') or ''}\n"
            f"  raised by: {row.get('agent_count', 0)} buyers"
            f"  across {len(spread) if isinstance(spread, dict) else 0} kinds of buyer\n"
            f"  their words: {' | '.join(quotes) if quotes else '(none recorded)'}"
        )

    user = (
        f"PRODUCT: {context['name']}\n"
        f"WHAT THE FOUNDER WANTED TO KNOW: {context['goal']}\n"
        f"THE PRODUCT IN THE FOUNDER'S WORDS: {context['summary'] or '(not supplied)'}\n\n"
        f"MEASURED OBJECTIONS, most load-bearing first:\n"
        + "\n".join(lines)
        + "\n\nALTERNATIVES TO WRITE BATTLECARDS FOR (use only these):\n"
        + "\n".join(f"- {r}" for r in rivals)
        + "\n\nReturn JSON: {\"rows\": [{\"objection_key\", \"acknowledge\", "
        '"explore", "respond", "confirm", "when_to_walk"}], '
        '"battlecards": [{"rival", "they_say", "the_honest_read", '
        '"where_we_win", "proof_needed"}], "notes": [str]}'
    )

    generated = await llm_structured(
        [{"role": "system", "content": SYSTEM}, {"role": "user", "content": user}],
        _Generated,
    )

    # Every figure in the script must come from the founder's words or the
    # buyers' own. SYSTEM says so above and was overridden anyway, in copy
    # meant to be read aloud on a call: a $150k loaded salary, a $700 labour
    # cost and a 17-hour payback, none of them in the input, for a product that
    # has never been sold. Invented figures become the placeholder the prompt
    # asked for, which is honest and countable.
    #
    # Checked against `_fact_material` rather than `user`, because the prompt
    # states its own agent counts and those are not evidence for a price.
    generated, invented = scrub_unsourced(
        generated,
        _fact_material(context, objections),
        product_material=str(context.get("founder_material") or ""),
    )
    if invented:
        log.warning(
            "answer_pack_scrubbed_invented_figures",
            simulation_id=simulation_id,
            count=len(invented),
            figures=invented[:10],
        )

    # ── Battlecards: the model's rivals are verified, not believed ──
    #
    # The docstring's promise, enforced rather than assumed. `rivals` was
    # interpolated into the prompt and nothing checked what came back, so a
    # battlecard could argue against a company that does not exist — in the one
    # artifact a founder reads out loud on a live call. The check is the
    # messaging doc's `_allowed_alternatives`: the founder's list, plus any
    # name a buyer actually said, matched against the quote text rather than
    # taken on trust.
    spoken = " ".join(
        [str(row.get("summary") or "") for row in objections]
        + [quote for row in objections for quote in _quotes(row)]
    ).lower()
    allowed = {name.lower() for name in rivals}
    battlecards: list[Battlecard] = []
    for card in generated.battlecards:
        name = str(card.rival or "").strip()
        if name and (name.lower() in allowed or name.lower() in spoken):
            battlecards.append(card)
        else:
            log.warning(
                "answer_pack_dropped_invented_rival",
                simulation_id=simulation_id,
                rival=name,
            )

    # The measured numbers are attached here, from the database rows — never
    # taken from the model's echo of them.
    by_key = {str(o.get("objection_key")): o for o in objections}
    rows: list[MatrixRow] = []
    for item in generated.rows:
        key = str(item.get("objection_key") or "")
        source = by_key.get(key)
        if not source:
            # A row for an objection nobody raised is the failure mode this
            # module exists to prevent, so it is dropped rather than shown.
            log.warning("answer_pack_dropped_unmatched_row", key=key)
            continue
        rows.append(
            MatrixRow(
                objection_key=key,
                label=str(source.get("label") or key),
                agents_raising=int(source.get("agent_count") or 0),
                load_bearing_score=float(source.get("load_bearing_score") or 0.0),
                evidence_quotes=_quotes(source),
                acknowledge=str(item.get("acknowledge") or ""),
                explore=str(item.get("explore") or ""),
                respond=str(item.get("respond") or ""),
                confirm=str(item.get("confirm") or ""),
                when_to_walk=(str(item["when_to_walk"]) if item.get("when_to_walk") else None),
            )
        )

    # Keep the measured order. The model's ordering is a suggestion; the
    # ranking is the product.
    order = {str(o.get("objection_key")): i for i, o in enumerate(objections)}
    rows.sort(key=lambda r: order.get(r.objection_key, 999))

    pack = AnswerPack(
        rows=rows,
        battlecards=battlecards,
        built_from_objections=len(objections),
        notes=generated.notes,
    )
    # Counted on the finished pack, so it includes both the blanks the model
    # wrote and the ones substituted for an invented figure above.
    pack.placeholders_to_fill = count_placeholders(pack.model_dump_json())

    log.info(
        "answer_pack_built",
        simulation_id=simulation_id,
        rows=len(rows),
        battlecards=len(battlecards),
        placeholders=pack.placeholders_to_fill,
    )
    return pack
