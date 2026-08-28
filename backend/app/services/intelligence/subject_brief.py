# PUBLIC INTERFACE
# ─────────────────────────────────────────────────────────
# SUBJECT_BRIEF_CHARS
# ensure_subject_brief(sim) -> SubjectBrief            [async, once per run]
# load_subject_brief(simulation_id) -> SubjectBrief | None
# project_has_subject_material(project_id) -> bool
# run_will_carry_subject_brief(sim) -> bool            [quote time]
# ─────────────────────────────────────────────────────────
"""The uploaded material, distilled into the subject agents react to.

**The defect this exists to close.** A founder uploaded a 14,028-character deck.
It extracted cleanly. `run_prepare_agents` then put `doc_context[:2000]` — 14% of
it — into the *agent-generation* prompt, where it shaped who the agents were and
nothing else, and `topic_block()` handed those agents a subject consisting of the
one-line `prediction_goal`. So ninety-six agents spent five rounds arguing about
a sentence, and the report the founder paid for was about their sentence rather
than about their product.

The decision that fixes it: **uploaded material becomes the subject agents react
to, and the description frames the start of the conversation.** Both reach the
agents, with distinct roles — see `BasePlatformAdapter.topic_block`.

Four things in here are load-bearing.

**The brief is bounded, and bounded by construction.** `AGENT_ACTION` is the
largest stage in the run by call count — 243 calls on a 27-agent/3-round/3-arena
run, 500 on the standard shape — and `topic_block()` is rebuilt per call with no
caching between agents. Pasting 14,000 characters there would multiply the
dominant cost line by roughly five. The renderer caps every field and then
hard-slices the result at `SUBJECT_BRIEF_CHARS`, so the bound is a property of
the code rather than a request made of a model. The precedent is
`ASSET_BODY_IN_PROMPT = 700`, which rides in the same block and is priced per
asset; this is priced the same way (`SUBJECT_BRIEF_ACTION` in `agent_pricing`).

**It is distilled once, persisted, and re-read.** Every round and every arena of
a run reads the same row. A subject that changed between rounds would not be one
subject, and the run's whole output is a comparison of reactions to it. A
re-simulation inherits its parent's brief verbatim — including inheriting the
*absence* of one — because the inoculation loop's entire claim is that the only
difference between parent and child is the material the team published.

**It may only contain what the material says.** Both of this codebase's
free-writing stages invented evidence the moment they were unconstrained: the
report wrote "~58% of all SMB objections on Reddit" (HANDOFF §5 bug #5) and the
asset drafter asserted a 14-case dataset with a Spearman's ρ of 0.74 (§1b). A
distillation that "improves" the pitch is fabricating the product — and unlike
those two, every agent in the run then reacts to the fabrication, so it is not a
sentence in an artifact, it is the whole measurement. The prompt states the rule
and `_unsourced_numbers` is the check, using the same sourced-number test the
asset drafter uses.

**Competitor material can never become the subject.** DECISIONS §7: a competitor
is grounded only in material the user uploaded *and labelled* as competitor
material, and that label exists to license a name in an adversarial agent's
mouth — never to describe the founder's own product. Only the `own` bucket is
read here, and `gather_material` is what buckets it.

**A project with no usable material fails loudly.** Not silently: the run still
completes on `prediction_goal` alone, which is the old behaviour, and the row
records exactly why in a form a human can read afterwards.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any

import structlog

from app.core.database import get_supabase_admin
from app.core.llm_client import _extract_json, llm_complete
from app.services.billing.usage_ledger import usage_context

logger = structlog.get_logger()


# The rendered brief's ceiling, in characters. Every action prompt in the run
# carries it, so this number is a cost decision as much as a product one.
#
# **Why 1,200.** The brief has to carry four facts an audience needs before it
# can react — what it is, who it is for, what it claims, what it costs — plus the
# name to react to. Truncating the whole to fit a tighter budget drops them from
# the bottom, and the bottom is the price, which is the single most objectionable
# fact in any pitch: a run that loses it stops measuring the objection founders
# most need to see. So the budget is the sum of five fields at their natural
# length rather than a round number chosen first —
#
#     name             80
#     what it is      260
#     who it is for   220
#     what it claims  380
#     what it costs   190          = 1,130, plus 63 of labels and newlines = 1,193
#
# — and 1,200 is that with the arithmetic's own rounding inside it.
#
# For scale against the precedent that shares this block: one pre-positioned
# inoculation asset is capped at `ASSET_BODY_IN_PROMPT = 700` characters and
# measured 224 input tokens per action. The brief is ~1.7 of those, which is the
# right ratio — an asset is supporting material, and this is the thing being
# reacted to. `SUBJECT_BRIEF_ACTION` in `agent_pricing.py` carries the arithmetic
# from these characters to the tokens the quote charges for.
SUBJECT_BRIEF_CHARS = 1_200

# Per-field caps, applied before the whole is capped. Ordered as rendered.
_FIELD_LIMITS: tuple[tuple[str, str, int], ...] = (
    ("name", "", 80),
    ("what_it_is", "What it is: ", 260),
    ("who_its_for", "Who it is for: ", 220),
    ("what_it_claims", "What it claims: ", 380),
    ("what_it_costs", "What it costs: ", 190),
)

# The distillation call's output ceiling. The response is five short strings, so
# this is headroom rather than a target — but it is also what
# `SUBJECT_DISTILLATION`'s output figure is priced at, because there is no live
# measurement of this stage yet and a ceiling cannot under-quote.
_DISTIL_MAX_TOKENS = 900

# Material kinds that may describe the subject. **Not a list to be extended
# casually** — `competitor` is deliberately absent and adding it would present a
# competitor's own positioning to every agent as the founder's product, which is
# the exact failure DECISIONS §7's labelling rule exists to prevent. `market` is
# absent for the weaker version of the same reason: category context is not a
# description of this team's product, and a brief built from an analyst report
# would put the analyst's framing in the founder's mouth. `idea_brief` clears
# the bar both of those fail: the guided idea form's answers are the founder's
# own description of their product, composed into a document rather than
# uploaded as one (PRD_V3 §3). The two website kinds clear it the same way:
# the page is the founder's own published words, fetched rather than uploaded
# (PRD_V3 §4c — the audience must react to the page itself).
_SUBJECT_MATERIAL_KINDS = frozenset(
    {"own", "idea_brief", "website_url", "website_html"}
)

# Statuses persisted on `subject_briefs.status`. Kept in step with the CHECK
# constraint in migration 028.
STATUS_READY = "ready"
STATUS_INHERITED = "inherited"
STATUS_NO_MATERIAL = "no_material"
STATUS_MATERIAL_UNUSABLE = "material_unusable"
STATUS_DISTILLATION_FAILED = "distillation_failed"

# A figure, not a digit inside a word.
#
# The boundaries are load-bearing and were added after a rendered brief lost its
# entire `who_its_for` line: the bare `\d+(?:\.\d+)?%?` the asset drafter uses
# matches the **2 in "B2B"**, so a perfectly grounded sentence about B2B founders
# was dropped as a fabricated statistic. `S3`, `K8s`, `GPT-4o`, `IPv6` and `Web3`
# are the same shape. Nothing is lost in the other direction — an invented
# statistic is never spelled inside a word — so this is strictly narrower with no
# weaker guarantee.
#
# **Both sides use this regex**: the sourced set is built from the material with
# it too, so "sourced" and "asserted" are the same question asked twice.
_NUMBER_RE = re.compile(r"(?<![A-Za-z0-9.])\d+(?:\.\d+)?%?(?![A-Za-z0-9])")


@dataclass
class SubjectBrief:
    """What a run's agents are reacting to, and where it came from.

    `text` is empty for every status except `ready` and an `inherited` row whose
    parent had one. An empty brief is not an error state on its own — a run with
    no uploads legitimately has none — but it always carries a `reason`, because
    "this project uploaded nothing" and "this project uploaded a deck that never
    reached the agents" are opposite facts and used to produce identical logs.
    """

    simulation_id: str
    status: str
    text: str = ""
    reason: str = ""
    source_document_ids: list[str] = field(default_factory=list)
    inherited_from: str | None = None

    @property
    def present(self) -> bool:
        return bool(self.text.strip())


# ---------------------------------------------------------------------------
# Reading what is already there
# ---------------------------------------------------------------------------

def load_subject_brief(simulation_id: str) -> SubjectBrief | None:
    """This run's stored brief, or None if it has never been distilled.

    Raises rather than returning None on a failed read. The two answers have
    opposite consequences — None means "distil one", which is a main-model call
    the run has already been charged for — and collapsing them would double-bill
    a database blip.
    """
    rows = (
        get_supabase_admin()
        .table("subject_briefs")
        .select("simulation_id, status, brief, reason, source_document_ids, inherited_from")
        .eq("simulation_id", simulation_id)
        .limit(1)
        .execute()
    ).data or []
    if not rows:
        return None

    row = rows[0]
    return SubjectBrief(
        simulation_id=simulation_id,
        status=row.get("status") or STATUS_NO_MATERIAL,
        text=row.get("brief") or "",
        reason=row.get("reason") or "",
        source_document_ids=list(row.get("source_document_ids") or []),
        inherited_from=row.get("inherited_from"),
    )


def _store(
    brief: SubjectBrief,
    project_id: str | None,
    org_id: str | None,
    model: str | None = None,
) -> SubjectBrief:
    """Persist a brief, upserting on the run it belongs to."""
    get_supabase_admin().table("subject_briefs").upsert(
        {
            "simulation_id": brief.simulation_id,
            "project_id": project_id,
            "organization_id": org_id,
            "status": brief.status,
            "brief": brief.text,
            "reason": brief.reason,
            "source_document_ids": brief.source_document_ids,
            "inherited_from": brief.inherited_from,
            "char_count": len(brief.text),
            "model": model,
        },
        on_conflict="simulation_id",
    ).execute()
    return brief


# ---------------------------------------------------------------------------
# Is there anything to distil?
# ---------------------------------------------------------------------------

def _subject_material_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """The documents that may describe the subject, out of a project's uploads.

    One definition, shared by the quote-time predicate and the failure message
    the distillation writes when it finds nothing. Two copies of "usable
    material" would be the two-sources-of-truth class (HANDOFF §2a), and the
    consequence here is a run quoted for a brief it never carries.

    NULL `material_kind` predates the column and reads as `own`, matching
    `gather_material`.
    """
    usable = []
    for doc in rows:
        kind = doc.get("material_kind") or "own"
        if kind not in _SUBJECT_MATERIAL_KINDS:
            continue
        if doc.get("processing_status") != "complete":
            continue
        usable.append(doc)
    return usable


def _project_documents(project_id: str) -> list[dict[str, Any]]:
    return (
        get_supabase_admin()
        .table("documents")
        .select("id, filename, material_kind, processing_status, extracted_char_count")
        .eq("project_id", project_id)
        .execute()
    ).data or []


def project_has_subject_material(project_id: str | None) -> bool:
    """Whether this project has material a brief could be built from.

    Cheap on purpose — one query over `documents`, no storage reads — because it
    is called at quote time, before any credits are deducted, and the quote path
    must not pay for a storage round trip per upload to price a run.

    It can therefore disagree with the distillation in one direction: a document
    that is `complete` but whose extraction is empty passes here and is dropped
    there. That over-quotes the run by the brief's surcharge and logs
    `subject_brief_unavailable`, which is the safe direction and a visible one.
    """
    if not project_id:
        return False
    return bool(_subject_material_rows(_project_documents(project_id)))


def run_will_carry_subject_brief(sim: dict[str, Any]) -> bool:
    """Quote-time answer to "does this run carry a subject brief?".

    Takes the simulation row rather than an id so the start endpoint — which has
    already loaded it — pays for no extra read, exactly as `reuse_agents` and
    `inoculation_assets` are derived there today.

    A re-simulation inherits its parent's brief, so the question for a child is
    whether the *parent* carried one. It is answered from the stored row rather
    than re-derived from the project's material, because the parent's material
    may have changed since and the child is charged for what it will actually
    send.
    """
    parent_id = sim.get("parent_simulation_id")
    if parent_id:
        try:
            parent = load_subject_brief(str(parent_id))
        except Exception:
            logger.exception(
                "subject_brief_parent_lookup_failed",
                simulation_id=sim.get("id"),
                parent_simulation_id=parent_id,
                detail="quoting this re-simulation without a subject brief; if the "
                       "parent carried one the child is under-quoted by its surcharge",
            )
            return False
        return bool(parent and parent.present)

    return project_has_subject_material(sim.get("project_id"))


# ---------------------------------------------------------------------------
# Distil
# ---------------------------------------------------------------------------

_DISTIL_PROMPT = """You are compiling the SUBJECT of a synthetic-audience simulation.

Below is the material a team uploaded about their own product. Restate it as the
team would present it out loud to someone who has thirty seconds: what it is, who
it is for, what it claims, and what it costs.

An audience of synthetic buyers and sceptics will react to what you write and
nothing else. Every objection they raise will be an objection to your words.

RULES
- **Only what the material says.** You have no knowledge of this product beyond
  the text below. Do not add a benefit, a differentiator, a customer, a metric,
  an integration or a roadmap item that is not in it.
- **Do not improve the pitch.** If the material is vague about who it is for,
  your answer is vague about who it is for. Sharpening it invents a product the
  team does not have, and the run then measures reactions to your version.
- **Omit any field the material does not state.** Leave it out of the JSON
  entirely. An omitted field is correct; a guessed one is a fabrication every
  agent in the run will argue with. In particular, do not invent a price.
- **No number that is not in the material.** Not a customer count, not a
  percentage, not a benchmark, not a funding figure, not a team size.
- Write in the team's register, in their words where they have them. This is
  their pitch, not a review of it and not advice about it.
- No preamble, no framing, no "this document describes". State the thing.

Length limits, which are enforced by truncation — write inside them:
  name             up to 80 characters
  what_it_is       up to 250 characters
  who_its_for      up to 210 characters
  what_it_claims   up to 370 characters
  what_it_costs    up to 180 characters

MATERIAL
{material}

Return ONLY JSON, omitting any field the material does not support:
{{"name": "...", "what_it_is": "...", "who_its_for": "...",
  "what_it_claims": "...", "what_it_costs": "..."}}"""


def _unsourced_numbers(text: str, sourced: set[str]) -> list[str]:
    """Figures in the brief that the material does not contain.

    The same check the asset drafter runs, narrowed to the case that matters
    here. It is stricter than `_evidence_claims` — any number, not only one
    wearing the clothes of a research finding — because a brief has no room for
    incidental arithmetic: every figure in it is a claim about the product, and
    an invented price or customer count becomes the thing a hundred agents argue
    about for five rounds.
    """
    return [n for n in _NUMBER_RE.findall(text) if n not in sourced]


def _render(fields: dict[str, str], sourced: set[str]) -> tuple[str, list[str]]:
    """The brief as agents see it, bounded, and the fields that were dropped.

    Bounded twice on purpose. Per-field caps stop one long answer eating the
    others — the failure the whole-string slice would produce is losing the price
    line, which is the field most likely to be objected to. The final slice is
    what makes `SUBJECT_BRIEF_CHARS` a fact about the code rather than a claim
    about the arithmetic above it.
    """
    lines: list[str] = []
    dropped: list[str] = []

    for key, label, limit in _FIELD_LIMITS:
        value = str(fields.get(key) or "").strip()
        if not value:
            continue
        unsourced = _unsourced_numbers(value, sourced)
        if unsourced:
            # Dropped rather than kept-with-a-caveat: this is the subject, and a
            # subject carrying a number the material does not contain is a
            # product the team does not sell. The asset drafter drops a whole
            # asset for the same reason; a field is the smaller unit here.
            dropped.append(f"{key} ({', '.join(unsourced[:5])})")
            continue
        lines.append(f"{label}{value[:limit]}")

    return "\n".join(lines)[:SUBJECT_BRIEF_CHARS], dropped


async def _distil(
    simulation_id: str,
    org_id: str | None,
    material_text: str,
    sourced: set[str],
) -> tuple[str, list[str], str]:
    """One main-model pass over the team's own material. Returns (brief, dropped, model).

    Main model, not the fast one, despite being cheap to route either way. This
    is the judgment call DECISIONS §14 reserves Opus for: it is once per run, and
    it decides what every agent in the run reacts to. A garbled or embellished
    brief does not degrade one answer, it invalidates the measurement.
    """
    from app.core.config import settings

    model = settings.llm_model
    with usage_context(
        "subject_distillation", simulation_id=simulation_id, organization_id=org_id
    ):
        raw = await llm_complete(
            messages=[{
                "role": "user",
                "content": _DISTIL_PROMPT.format(material=material_text),
            }],
            max_tokens=_DISTIL_MAX_TOKENS,
            # Low, not zero. This is transcription with judgment about what to
            # keep, and the creative range of the model is the last thing wanted.
        )

    fields = json.loads(_extract_json(raw))
    if not isinstance(fields, dict):
        raise ValueError(f"distillation returned {type(fields).__name__}, not an object")

    text, dropped = _render(fields, sourced)
    return text, dropped, model


# ---------------------------------------------------------------------------
# The entry point
# ---------------------------------------------------------------------------

async def ensure_subject_brief(sim: dict[str, Any]) -> SubjectBrief:
    """This run's subject brief: read it if it exists, otherwise build it once.

    Called by `run_simulation` before any adapter is initialised, so every arena
    and every round of the run is handed the same string. Re-entrant by design —
    a run that was stopped and restarted re-reads its stored brief rather than
    paying for a second main-model pass and handing its agents a different
    subject than the events already in the database were produced against.
    """
    simulation_id = str(sim["id"])
    project_id = sim.get("project_id")
    org_id = sim.get("organization_id")

    existing = load_subject_brief(simulation_id)
    if existing is not None:
        logger.info(
            "subject_brief_reused",
            simulation_id=simulation_id,
            status=existing.status,
            chars=len(existing.text),
            detail="stored brief re-read; the subject does not change between rounds",
        )
        return existing

    parent_id = sim.get("parent_simulation_id")
    if parent_id:
        return _inherit(simulation_id, str(parent_id), project_id, org_id)

    return await _build(simulation_id, project_id, org_id)


def _inherit(
    simulation_id: str,
    parent_id: str,
    project_id: str | None,
    org_id: str | None,
) -> SubjectBrief:
    """A re-simulation takes its parent's subject, whatever it is.

    Including taking its absence. The loop's claim is that parent and child
    differ only in the material the team published between them; distilling a
    fresh brief for the child would change the subject as well, and every
    before/after delta in the artifact would be measuring both at once. A parent
    that ran before this existed therefore produces a child that also runs
    without a brief — which is worse output and a valid comparison, and the
    alternative is better output and an invalid one.
    """
    parent = load_subject_brief(parent_id)

    if parent is None or not parent.present:
        reason = (
            f"the parent run carries no subject brief "
            f"({parent.status if parent else 'never distilled'}), so this "
            "re-simulation runs without one too — changing the subject between "
            "parent and child would make the before/after comparison measure two "
            "changes at once"
        )
        logger.warning(
            "subject_brief_not_inherited",
            simulation_id=simulation_id,
            parent_simulation_id=parent_id,
            parent_status=parent.status if parent else None,
            detail=reason,
        )
        return _store(
            SubjectBrief(
                simulation_id=simulation_id,
                status=STATUS_INHERITED,
                reason=reason,
                inherited_from=parent_id,
            ),
            project_id,
            org_id,
        )

    logger.info(
        "subject_brief_inherited",
        simulation_id=simulation_id,
        parent_simulation_id=parent_id,
        chars=len(parent.text),
        source_documents=len(parent.source_document_ids),
    )
    return _store(
        SubjectBrief(
            simulation_id=simulation_id,
            status=STATUS_INHERITED,
            text=parent.text,
            reason="copied verbatim from the parent run",
            source_document_ids=parent.source_document_ids,
            inherited_from=parent_id,
        ),
        project_id,
        org_id,
    )


def _no_material_reason(project_id: str | None) -> tuple[str, bool]:
    """Why this project produced no subject, and whether it uploaded anything.

    Returns (reason, uploaded_something). The flag is returned rather than
    re-derived by the caller from the text of the reason: a log level decided by
    substring-matching a message this function also writes is one edit away from
    silently downgrading the loudest signal in the module, and "a value nothing
    checks is a value nothing is enforcing" applies to a caller's own strings
    too.

    The reason is specific rather than "no material found". The founder in the
    defect that prompted this module *had* uploaded a deck; a message that cannot
    tell "you uploaded nothing" from "your deck is still processing" from
    "everything you uploaded is labelled as a competitor's" sends them nowhere.
    """
    if not project_id:
        return ("this run has no project, so there is no uploaded material to read", False)

    try:
        rows = _project_documents(project_id)
    except Exception:
        # Loud, and it claims nothing about what the project holds. Treated as
        # "uploaded something" so the failure is reported at error level: an
        # unreadable documents table is not evidence that a founder uploaded
        # nothing.
        logger.exception("subject_material_lookup_failed", project_id=project_id)
        return ("the project's documents could not be read", True)

    if not rows:
        return ("this project has no uploaded documents", False)

    competitor = [d for d in rows if (d.get("material_kind") or "own") == "competitor"]
    market = [d for d in rows if (d.get("material_kind") or "own") == "market"]
    unprocessed = [
        d for d in rows
        if (d.get("material_kind") or "own") in _SUBJECT_MATERIAL_KINDS
        and d.get("processing_status") != "complete"
    ]

    parts = [f"{len(rows)} document(s) in this project, none usable as the subject"]
    if competitor:
        parts.append(
            f"{len(competitor)} labelled competitor material, which may never "
            "describe the subject (DECISIONS §7)"
        )
    if market:
        parts.append(
            f"{len(market)} labelled market context, which describes the category "
            "rather than this product"
        )
    if unprocessed:
        statuses = sorted({str(d.get("processing_status")) for d in unprocessed})
        parts.append(f"{len(unprocessed)} not finished processing ({', '.join(statuses)})")
    return ("; ".join(parts), True)


async def _build(
    simulation_id: str,
    project_id: str | None,
    org_id: str | None,
) -> SubjectBrief:
    """Distil the project's own material into a subject, or say why it could not."""
    from app.services.engine.personas.icp_synthesizer import gather_material

    material = gather_material(project_id) if project_id else None
    own = (material.own if material else "").strip()

    if not own:
        # ERROR, not warning, when the project *has* documents: material was
        # uploaded and did not reach the agents, which is precisely the defect
        # this module closes. A project with no documents at all is an ordinary
        # unlensed run and says so at warning level.
        reason, has_documents = _no_material_reason(project_id)
        log = logger.error if has_documents else logger.warning
        log(
            "subject_brief_unavailable",
            simulation_id=simulation_id,
            project_id=project_id,
            reason=reason,
            detail=(
                "this run's agents see only `prediction_goal` as their subject — "
                "the pre-brief behaviour. Nothing is silently degraded: the run "
                "completes and this row records why."
            ),
        )
        return _store(
            SubjectBrief(
                simulation_id=simulation_id,
                status=STATUS_MATERIAL_UNUSABLE if has_documents else STATUS_NO_MATERIAL,
                reason=reason,
            ),
            project_id,
            org_id,
        )

    # Every number the team's own material contains. Anything statistical outside
    # this set is something the model produced rather than read. Competitor and
    # market text are deliberately excluded from both the prompt and this set —
    # a figure sourced from a competitor's page is not sourced for a claim about
    # this product.
    sourced = set(_NUMBER_RE.findall(own))

    try:
        text, dropped, model = await _distil(simulation_id, org_id, own, sourced)
    except Exception as exc:
        reason = f"distillation failed: {type(exc).__name__}: {exc}"
        logger.exception(
            "subject_brief_distillation_failed",
            simulation_id=simulation_id,
            project_id=project_id,
            material_chars=len(own),
            detail=(
                "the run continues on `prediction_goal` alone, which is the "
                "pre-brief behaviour, and was charged for a brief it will not carry"
            ),
        )
        return _store(
            SubjectBrief(
                simulation_id=simulation_id,
                status=STATUS_DISTILLATION_FAILED,
                reason=reason[:2000],
            ),
            project_id,
            org_id,
        )

    if dropped:
        logger.warning(
            "subject_brief_fields_dropped",
            simulation_id=simulation_id,
            dropped=dropped,
            detail=(
                "these fields asserted figures the uploaded material does not "
                "contain and were removed from the subject; every agent in the "
                "run would otherwise have reacted to an invented claim"
            ),
        )

    if not text.strip():
        reason = (
            "the distillation returned nothing usable"
            + (f"; every field was dropped as unsourced: {', '.join(dropped)}" if dropped else "")
        )
        logger.error(
            "subject_brief_empty",
            simulation_id=simulation_id,
            project_id=project_id,
            material_chars=len(own),
            dropped=dropped,
            detail="the run falls back to `prediction_goal` as its subject",
        )
        return _store(
            SubjectBrief(
                simulation_id=simulation_id,
                status=STATUS_DISTILLATION_FAILED,
                reason=reason,
            ),
            project_id,
            org_id,
        )

    brief = SubjectBrief(
        simulation_id=simulation_id,
        status=STATUS_READY,
        text=text,
        reason="",
        source_document_ids=list(material.own_ids) if material else [],
    )
    logger.info(
        "subject_brief_distilled",
        simulation_id=simulation_id,
        project_id=project_id,
        material_chars=len(own),
        brief_chars=len(text),
        budget_chars=SUBJECT_BRIEF_CHARS,
        source_documents=len(brief.source_document_ids),
        fields_dropped=len(dropped),
    )
    return _store(brief, project_id, org_id, model=model)
