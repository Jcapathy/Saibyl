# PUBLIC INTERFACE
# ─────────────────────────────────────────────────────────
# synthesize_icp(project_id, org_id, *, adversarial=True, platforms=None,
#                created_by=None, name=None) -> dict   [persists icp_profiles]
# compile_pack(profile, pack_id, platforms=None, adversarial_share=0.0) -> PersonaPack
# compile_packs(profile, base_pack_id, platforms=None,
#               adversarial_share=0.0) -> list[PersonaPack]
# rebalance_adversarial(archetypes, share) -> list[Archetype]
# gather_material(project_id) -> ProjectMaterial
# source_text(admin, document_row) -> str
# recompile_profile(profile_row) -> dict
# ─────────────────────────────────────────────────────────
"""Derive the audience from the founder's own material (DECISIONS_V2 §3).

Sixteen generic packs cannot represent "developers evaluating an observability
tool who already pay for Datadog", and the founder is the wrong person to ask
which of sixteen packs matches their buyer — that judgment is what they are
paying for. So one main-model pass reads what they uploaded and proposes an ICP,
which the founder then corrects.

Three things in here are load-bearing.

**Synthesis proposes; the engine consumes a pack.** The profile is the founder's
object and a `PersonaPack` is the engine's, and `compile_pack` is the only
bridge. Nothing downstream of `run_prepare_agents` learns that ICPs exist.

**The built-in packs are priors, not the answer.** A synthesized archetype says
what a buyer cares about and what they would have to rip out; the nearest
built-in archetype supplies the Big Five vector and posting cadence. Asking a
language model to invent psychometrics per project produces numbers with no
referent that then propagate into every agent in the run.

**The adversarial guardrail is enforced here, in data.** A competitor may be
named only from a document the user uploaded and marked as competitor material.
`_ground_adversarial` drops the name from any archetype whose grounding is not
in that set, before the profile is validated — so a confabulated incumbent
cannot reach agent generation, which is the last point at which it is still
removable. PRD §4, DECISIONS §7: these do not get relaxed to improve output.
"""
from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from typing import Any

import structlog

from app.core.config import settings
from app.core.database import get_supabase_admin
from app.core.llm_client import _extract_json, llm_complete
from app.services.billing.usage_ledger import usage_context
from app.services.engine.personas.icp_schema import (
    ADVERSARIAL_ROLES,
    AdversarialArchetype,
    Competitor,
    ICPArchetype,
    ICPProfile,
)
from app.services.engine.personas.pack_loader import (
    Archetype,
    ArchetypeContext,
    BehaviorTraits,
    Demographics,
    Personality,
    PersonaPack,
    get_pack,
    load_all_packs,
)
from app.services.refs import enum_ref

logger = structlog.get_logger()

# Characters of uploaded material fed to the synthesis pass, per bucket.
#
# Sized against the input rather than the context window: a founder's PRD, deck
# and landing page are a few tens of thousands of characters, and material past
# that is usually appendices and changelogs. Truncating at a stated limit and
# logging it beats silently sending 400k characters of PDF furniture at Opus
# rates.
_OWN_MATERIAL_CHARS = 24_000
_COMPETITOR_MATERIAL_CHARS = 12_000
_MARKET_MATERIAL_CHARS = 6_000

# The floor a single source must clear to be worth including.
#
# The budget used to be spent first-come: documents were read in upload order
# until the bucket was full, and everything after that was skipped by a bare
# `continue` with no log. One 200-row CRM export uploaded before the deck could
# therefore consume the entire `own` budget, and the deck — the densest ICP
# material a founder ever sends — contributed nothing, silently. Sources now
# share the bucket (`_fair_share`), and a source whose share would fall below
# this floor is excluded **by name, with a reason**, because a 300-character
# fragment of a spreadsheet is not a source, it is noise that looks like one.
_MIN_SOURCE_CHARS = 1_000

# The synthesis pass writes a whole profile in one object, and bug #7 in Phase 1
# was a main-model stage silently hitting exactly this ceiling and returning
# unparseable JSON. The retry below halves the archetype budget rather than
# raising the ceiling, because an ICP with twelve archetypes is not a better ICP.
_SYNTHESIS_MAX_TOKENS = 8_000
_MAX_ARCHETYPES = 6
_MAX_ADVERSARIAL = 4
_RETRY_ARCHETYPES = 3
_RETRY_ADVERSARIAL = 2

# Influence by seniority. The engine's `influence_multiplier` weights how far an
# agent's posts travel; a VP's opinion of a tool genuinely carries further in a
# buying conversation than an IC's, and this is the one place that asymmetry is
# expressible.
_INFLUENCE_BY_SENIORITY = {
    "ic": 1.0,
    "manager": 1.5,
    "director": 2.0,
    "vp": 2.5,
    "c_level": 3.0,
    "founder": 3.0,
}

# Used only when an archetype names no usable prior pack. Deliberately bland:
# a neutral default that is visibly a default beats a specific-looking
# demographic profile nobody chose.
_FALLBACK_DEMOGRAPHICS = Demographics(
    age_range=[28, 52],
    gender_distribution={"male": 0.5, "female": 0.45, "nonbinary": 0.05},
    education=["Bachelors", "Masters", "Self-taught"],
    income_bracket="$70k-$180k",
)
_FALLBACK_PERSONALITY = Personality(
    mbti_pool=["INTJ", "ENTJ", "ISTJ", "ENTP"],
    big5={"openness": 0.6, "conscientiousness": 0.7, "extraversion": 0.5},
)


@dataclass
class ProjectMaterial:
    """What the project has uploaded, split by what it licenses.

    The split is the point. `own` describes the product; `competitor` is the
    only thing that may put a competitor's name in an agent's mouth; `market`
    is category context and licenses neither.
    """

    own: str = ""
    competitor: str = ""
    market: str = ""
    own_ids: list[str] = field(default_factory=list)
    competitor_ids: list[str] = field(default_factory=list)
    market_ids: list[str] = field(default_factory=list)

    # Documents the classifier proposed as competitor material that no human has
    # confirmed. They are **not** in `competitor_ids` and license no name — see
    # `services/ingestion/classifier.py` and DECISIONS_V2 §7. Carried so the
    # product can ask, and so "this project has competitor material nobody
    # labelled" stops being indistinguishable from "this project has none".
    unconfirmed_competitor_ids: list[str] = field(default_factory=list)

    # Every document the pass did not read, with why. A source contributing zero
    # characters is the defect this structure exists to make visible.
    excluded: list[dict[str, Any]] = field(default_factory=list)

    @property
    def all_ids(self) -> list[str]:
        return [*self.own_ids, *self.competitor_ids, *self.market_ids]

    @property
    def has_competitor_material(self) -> bool:
        return bool(self.competitor.strip())

    @property
    def is_empty(self) -> bool:
        return not (self.own.strip() or self.competitor.strip() or self.market.strip())


# ---------------------------------------------------------------------------
# Material
# ---------------------------------------------------------------------------

_MATERIAL_LIMITS = {
    "own": _OWN_MATERIAL_CHARS,
    "competitor": _COMPETITOR_MATERIAL_CHARS,
    "market": _MARKET_MATERIAL_CHARS,
}


def _fair_share(demands: list[int], budget: int) -> list[int]:
    """Split `budget` across `demands` so no source is starved by another.

    Water-filling: everyone gets an equal share, anyone who wants less than
    their share releases the remainder, and the remainder is re-divided among
    those who still want more. A short landing page therefore comes through
    whole while a 400-page PDF is the thing that gets truncated, which is the
    opposite of what first-come-first-served did.
    """
    allocation = [0] * len(demands)
    wanting = {i for i, demand in enumerate(demands) if demand > 0}
    remaining = budget

    while wanting and remaining > 0:
        share = remaining // len(wanting)
        if share == 0:
            break
        satisfied = [i for i in wanting if demands[i] - allocation[i] <= share]
        if not satisfied:
            for i in wanting:
                allocation[i] += share
                remaining -= share
            break
        for i in satisfied:
            take = demands[i] - allocation[i]
            allocation[i] += take
            remaining -= take
            wanting.discard(i)

    return allocation


def source_text(admin: Any, doc: dict[str, Any]) -> str:
    """The extracted text for one document.

    Read from `processed_text_path`, which `services/ingestion/pipeline.py`
    writes for every media type. Rows that predate it — and only those — are
    re-extracted here, which works for PDF/DOCX/text and is exactly the set of
    things the old single-path pipeline could produce. The fallback is logged so
    a project that is silently paying for re-extraction on every synthesis is
    visible rather than merely slow.

    Public, and shared with `workers/simulation_tasks.run_prepare_agents`, which
    had its own copy that read `storage_path` and decoded the raw bytes as UTF-8
    — mojibake for every PDF. "The text of a document" is one question and this
    is its one answer.
    """
    text_path = doc.get("processed_text_path")
    if text_path:
        raw = admin.storage.from_("project-media").download(text_path)
        return raw.decode("utf-8", errors="replace")

    from app.services.engine.document_processor import _extract_text

    logger.info(
        "icp_material_legacy_extraction",
        document_id=doc["id"],
        filename=doc.get("filename"),
        file_type=doc.get("file_type"),
        detail="row has no processed_text_path; re-extracting from the stored object",
    )
    file_bytes = admin.storage.from_("project-media").download(doc["storage_path"])
    text, _, _ = _extract_text(file_bytes, doc.get("file_type") or "txt")
    return text


def gather_material(project_id: str) -> ProjectMaterial:
    """Read every kind of upload the project has, bucketed by material kind.

    Three things this has to get right, all of them the same failure underneath.

    **Every upload kind is in scope.** Images, video, spreadsheets, decks and
    linked articles used to land in `project_assets`, which this function never
    read — so a founder could upload a deck as slide images and a customer
    spreadsheet and have their ICP synthesized from neither. One upload surface
    now writes to `documents`; see `services/ingestion/pipeline.py`.

    **The budget is shared, not raced.** See `_MIN_SOURCE_CHARS`.

    **What was left out is on the record.** Every exclusion — over budget, too
    small a share, unprocessed, failed extraction — is counted, named, and
    returned on `ProjectMaterial.excluded`. The previous version dropped
    documents with a bare `continue`, so a source contributing zero characters
    and a project with no such source produced identical logs.
    """
    admin = get_supabase_admin()
    rows = (
        admin.table("documents")
        .select(
            "id, filename, file_type, media_type, storage_path, processed_text_path, "
            "extracted_char_count, material_kind, material_kind_suggested, processing_status"
        )
        .eq("project_id", project_id)
        .order("created_at", desc=False)
        .execute()
    ).data or []

    excluded: list[dict[str, Any]] = []
    unconfirmed_competitors: list[str] = []
    ready: dict[str, list[dict[str, Any]]] = {"own": [], "competitor": [], "market": []}
    idea_brief_ids: set[str] = set()

    for doc in rows:
        # NULL predates the column and is read as 'own'. An unlabelled document
        # can never be the thing that authorises naming a competitor — and a
        # *suggested* kind is not a label, so it is recorded for confirmation
        # and never bucketed (DECISIONS_V2 §7). An idea brief is the founder's
        # own description of their product, composed from the guided form
        # rather than uploaded (PRD_V3 §3) — stated here rather than left to
        # the unknown-kind fallback below, and remembered by id because the
        # source floor treats it differently.
        kind = doc.get("material_kind") or "own"
        if kind == "idea_brief":
            idea_brief_ids.add(doc["id"])
            kind = "own"
        if kind not in ready:
            kind = "own"
        if doc.get("material_kind_suggested") == "competitor" and kind != "competitor":
            unconfirmed_competitors.append(doc["id"])

        status = doc.get("processing_status")
        if status != "complete":
            excluded.append({
                "document_id": doc["id"],
                "filename": doc.get("filename"),
                "media_type": doc.get("media_type"),
                "reason": f"processing_status={status}",
            })
            continue
        ready[kind].append(doc)

    buckets: dict[str, list[str]] = {"own": [], "competitor": [], "market": []}
    ids: dict[str, list[str]] = {"own": [], "competitor": [], "market": []}
    chars_by_media_type: dict[str, int] = {}
    truncated: list[str] = []

    for kind, all_docs in ready.items():
        limit = _MATERIAL_LIMITS[kind]

        # A bucket can hold more sources than it has characters to give them.
        # Sharing regardless would put every source below the floor and the
        # bucket would contribute *nothing* — the same zero-characters failure
        # in a new shape. So the bucket is capped at the number of sources it
        # can actually fund, in upload order, and the overflow is excluded by
        # name rather than diluted into uselessness.
        capacity = max(1, limit // _MIN_SOURCE_CHARS)
        docs = all_docs[:capacity]
        for doc in all_docs[capacity:]:
            excluded.append({
                "document_id": doc["id"],
                "filename": doc.get("filename"),
                "media_type": doc.get("media_type") or "document",
                "reason": (
                    f"{kind} bucket holds {len(all_docs)} sources and can fund "
                    f"{capacity} at the {_MIN_SOURCE_CHARS}-character floor; "
                    "this one is past that, in upload order"
                ),
            })

        # A row written before `extracted_char_count` existed reports no demand.
        # Claiming the whole bucket is the honest guess — it is the only value
        # that cannot starve the document — and the allocator then trims it back
        # to a fair share against everything else in the bucket.
        demands = [int(d.get("extracted_char_count") or limit) for d in docs]
        allocation = _fair_share(demands, limit)

        for doc, demand, budget in zip(docs, demands, allocation, strict=True):
            media_type = doc.get("media_type") or "document"
            # The floor exists to drop a fragment of a big upload that would
            # arrive as noise. An idea brief is short because the form is
            # short, and it is often the project's *only* material — dropping
            # it below the floor would ground the synthesis in nothing at all.
            if budget < _MIN_SOURCE_CHARS and doc["id"] not in idea_brief_ids:
                excluded.append({
                    "document_id": doc["id"],
                    "filename": doc.get("filename"),
                    "media_type": media_type,
                    "reason": (
                        f"{kind} budget of {limit} characters is shared by "
                        f"{len(docs)} sources; this one's share of {budget} is "
                        f"below the {_MIN_SOURCE_CHARS}-character floor"
                    ),
                })
                continue

            try:
                text = source_text(admin, doc)
            except Exception as exc:
                logger.warning(
                    "icp_material_read_failed",
                    document_id=doc["id"],
                    filename=doc.get("filename"),
                    media_type=media_type,
                    error=str(exc),
                    error_type=type(exc).__name__,
                )
                excluded.append({
                    "document_id": doc["id"],
                    "filename": doc.get("filename"),
                    "media_type": media_type,
                    "reason": f"read failed: {exc}",
                })
                continue

            snippet = text[:budget]
            if not snippet.strip():
                excluded.append({
                    "document_id": doc["id"],
                    "filename": doc.get("filename"),
                    "media_type": media_type,
                    "reason": "extraction is empty",
                })
                continue

            was_truncated = len(text) > len(snippet)
            if was_truncated:
                truncated.append(doc["id"])

            # The media type is stated in the header. An image description and a
            # spreadsheet dump read very differently as evidence, and a synthesis
            # pass told only "### customers.xlsx" has to infer that from the text.
            header = f"### {doc.get('filename') or 'document'} ({media_type})"
            if was_truncated:
                header += f" — first {len(snippet)} of {len(text)} characters"
            buckets[kind].append(f"{header}\n{snippet}")
            ids[kind].append(doc["id"])
            chars_by_media_type[media_type] = (
                chars_by_media_type.get(media_type, 0) + len(snippet)
            )

            logger.info(
                "icp_material_source_included",
                document_id=doc["id"],
                filename=doc.get("filename"),
                media_type=media_type,
                material_kind=kind,
                included_chars=len(snippet),
                available_chars=len(text),
                demand_chars=demand,
                truncated=was_truncated,
            )

    material = ProjectMaterial(
        own="\n\n".join(buckets["own"]),
        competitor="\n\n".join(buckets["competitor"]),
        market="\n\n".join(buckets["market"]),
        own_ids=ids["own"],
        competitor_ids=ids["competitor"],
        market_ids=ids["market"],
        unconfirmed_competitor_ids=unconfirmed_competitors,
        excluded=excluded,
    )

    logger.info(
        "icp_material_gathered",
        project_id=project_id,
        documents_in_project=len(rows),
        own_docs=len(ids["own"]),
        competitor_docs=len(ids["competitor"]),
        market_docs=len(ids["market"]),
        own_chars=len(material.own),
        competitor_chars=len(material.competitor),
        market_chars=len(material.market),
        # Which upload kinds actually reached the model. A kind present in the
        # project and absent from here is the bug this whole change exists for.
        chars_by_media_type=chars_by_media_type,
        truncated_documents=len(truncated),
        excluded_documents=len(excluded),
    )
    if excluded:
        logger.warning(
            "icp_material_excluded",
            project_id=project_id,
            count=len(excluded),
            excluded=excluded,
            detail="these uploads contributed nothing to the ICP",
        )
    if unconfirmed_competitors:
        # Not an error: refusing to act on an unconfirmed suggestion is the
        # guardrail working. It is logged because the alternative — a project
        # whose competitor material is all sitting unlabelled — is otherwise
        # indistinguishable from a project that uploaded none, and the second is
        # the one everybody assumes.
        logger.info(
            "icp_competitor_material_unconfirmed",
            project_id=project_id,
            document_ids=unconfirmed_competitors,
            detail=(
                "classified as competitor material but not labelled by a human; "
                "not bucketed as competitor and licensing no competitor name"
            ),
        )
    return material


# ---------------------------------------------------------------------------
# The synthesis pass
# ---------------------------------------------------------------------------

def _prior_pack_catalogue() -> str:
    """The built-in packs, offered to the model as priors to name."""
    lines = []
    for pack in load_all_packs():
        archetypes = ", ".join(f"{a.id} ({a.label})" for a in pack.archetypes)
        lines.append(f"- {pack.id} — {pack.name}: {archetypes}")
    return "\n".join(lines)


def _synthesis_prompt(
    material: ProjectMaterial,
    *,
    adversarial: bool,
    platforms: list[str],
    max_archetypes: int,
    max_adversarial: int,
) -> str:
    competitor_block = (
        f"""
COMPETITOR MATERIAL — uploaded by the user and marked as competitor material.
Document ids, in order: {json.dumps(material.competitor_ids)}
{material.competitor}
"""
        if material.has_competitor_material
        else """
COMPETITOR MATERIAL: none uploaded.
"""
    )

    market_block = f"\nMARKET / CATEGORY MATERIAL\n{material.market}\n" if material.market.strip() else ""

    if adversarial and material.has_competitor_material:
        adversarial_rule = f"""
Produce up to {max_adversarial} adversarial archetypes. You MAY name a
competitor, but ONLY one that appears in the COMPETITOR MATERIAL above, and you
MUST list the document ids you took the name from in "grounded_in". Any claim
about that competitor must be traceable to a sentence in that material. If you
want to say something about a competitor that the material does not say, do not
say it — make the argument about the category or the cost of switching instead.
"""
    elif adversarial:
        adversarial_rule = f"""
Produce up to {max_adversarial} adversarial archetypes. No competitor material
was uploaded, so you MUST NOT name any company, product, or open-source project.
Set "competitor_name" to null and leave "grounded_in" empty on every one. Make
the arguments about the category, the status quo, and the cost of switching —
"we already have a process for this", "this is a spreadsheet problem",
"you can build this in a weekend" — never about a named alternative.
"""
    else:
        adversarial_rule = '\nProduce no adversarial archetypes: return "adversarial": [].\n'

    return f"""You are constructing the ideal-customer profile for a product, from the
material its team uploaded. This drives a synthetic-audience simulation, so the
archetypes must be specific enough that two of them would disagree with each
other about the product.

PRODUCT MATERIAL — the team's own PRD, deck, landing page, pricing.
{material.own or "(none uploaded)"}
{competitor_block}{market_block}

BUILT-IN PERSONA PACKS you may cite as demographic priors. Pick the nearest one
per archetype and name its pack id and archetype id; the simulation takes
psychometrics from it. Cite null if none is close.
{_prior_pack_catalogue()}

PLATFORMS this run will simulate: {", ".join(platforms) or "unspecified"}

RULES
- Everything you assert must come from the material above. Where the material
  does not say, put the question in "gaps" instead of inventing an answer.
- Produce at most {max_archetypes} buyer/user archetypes. Fewer, sharper
  archetypes beat more generic ones.
- "incumbent_tooling" is what this archetype uses TODAY for this job — including
  "spreadsheets", "nothing", or "an internal script". A B2B buyer evaluates a
  product net of what they would have to rip out, so this field does more work
  than any other.
- "skepticism_triggers" are the things that make this archetype stop reading.
- "disposition" is -1..1: how they lean BEFORE seeing the pitch, from switching
  cost and prior burns — not how much you think they will like it.
- "rationale" is one or two plain sentences for the founder, who has never heard
  the phrase "ideal customer profile": why THIS is one of their buyers. It must
  point at something the material above actually says — a feature, a price, a
  claim, a named tool, a stated problem — and say what that implies about who
  buys. Do not restate the role, the seniority or the switching cost; those are
  shown next to it already, and a sentence that repeats them reads to a founder
  as evidence while containing none. Write it in the founder's own words, not in
  sales vocabulary. If the material does not support a reason, return "" and put
  the question in "gaps" — an empty rationale is better than a plausible one.
{adversarial_rule}
Return ONLY a JSON object:
{{
  "name": "short name for this ICP",
  "product_summary": "1-2 sentences: what the product is and who it is for",
  "category": "the market category in the team's own words",
  "competitors": [
    {{"name": "...", "positioning": "what the material says they do",
      "mentioned_in": ["document-id", ...]}}
  ],
  "archetypes": [
    {{
      "id": "kebab-case-id",
      "label": "Human readable label",
      "weight": 0.4,
      "rationale": "1-2 sentences citing the material, or \\"\\"",
      "role": "their job",
      "seniority": "ic|manager|director|vp|c_level|founder",
      "budget_authority": "none|influencer|recommender|approver|owner",
      "incumbent_tooling": ["..."],
      "switching_cost": "low|moderate|high|prohibitive",
      "evaluation_criteria": ["...", "..."],
      "skepticism_triggers": ["...", "..."],
      "goals": ["..."],
      "pains": ["..."],
      "platforms": ["platform ids from the list above"],
      "prior_pack_id": "pack-id or null",
      "prior_archetype_id": "archetype-id or null",
      "disposition": 0.0
    }}
  ],
  "adversarial": [
    {{
      "id": "kebab-case-id",
      "label": "Human readable label",
      "weight": 0.3,
      "rationale": "1-2 sentences citing the material: why this cohort is in the room",
      "role": "{'|'.join(ADVERSARIAL_ROLES)}",
      "competitor_name": "name or null",
      "grounded_in": ["document-id", ...],
      "core_argument": "one sentence, about the category or the switch",
      "talking_points": ["...", "..."],
      "platforms": ["..."],
      "prior_pack_id": "pack-id or null",
      "prior_archetype_id": "archetype-id or null",
      "disposition": -0.4
    }}
  ],
  "gaps": ["what the material never says, that a buyer would ask"]
}}"""


async def _run_synthesis(
    material: ProjectMaterial,
    *,
    adversarial: bool,
    platforms: list[str],
    max_archetypes: int,
    max_adversarial: int,
) -> dict[str, Any]:
    prompt = _synthesis_prompt(
        material,
        adversarial=adversarial,
        platforms=platforms,
        max_archetypes=max_archetypes,
        max_adversarial=max_adversarial,
    )
    raw = await llm_complete(
        messages=[{"role": "user", "content": prompt}],
        max_tokens=_SYNTHESIS_MAX_TOKENS,
        temperature=0.4,
    )
    return json.loads(_extract_json(raw))


async def _synthesize_profile(
    material: ProjectMaterial,
    *,
    adversarial: bool,
    platforms: list[str],
) -> ICPProfile:
    """One main-model pass, with one narrower retry.

    The retry exists because Phase 1's canonicalizer failed exactly this way:
    a single main-model call whose output hit `max_tokens` and returned JSON
    that could not be parsed, on the run that mattered. Retrying narrower is the
    fix that also improves the output — three sharp archetypes are a better ICP
    than six vague ones, so the degraded path is not much of a degradation.
    """
    try:
        data = await _run_synthesis(
            material,
            adversarial=adversarial,
            platforms=platforms,
            max_archetypes=_MAX_ARCHETYPES,
            max_adversarial=_MAX_ADVERSARIAL,
        )
    except (json.JSONDecodeError, ValueError) as exc:
        logger.warning("icp_synthesis_parse_failed", error=str(exc), retrying=True)
        data = await _run_synthesis(
            material,
            adversarial=adversarial,
            platforms=platforms,
            max_archetypes=_RETRY_ARCHETYPES,
            max_adversarial=_RETRY_ADVERSARIAL,
        )

    return _build_profile(data, material, adversarial=adversarial)


def _build_profile(
    data: dict[str, Any],
    material: ProjectMaterial,
    *,
    adversarial: bool,
) -> ICPProfile:
    """Validate the model's output into an `ICPProfile`, grounding it first."""
    allowed_docs = set(material.competitor_ids)

    competitors = [
        Competitor(
            name=str(c.get("name") or "").strip(),
            positioning=str(c.get("positioning") or "").strip(),
            mentioned_in=[d for d in (c.get("mentioned_in") or []) if d in allowed_docs],
        )
        for c in (data.get("competitors") or [])
        if str(c.get("name") or "").strip()
    ]
    ungrounded = [c.name for c in competitors if not c.is_grounded]
    if ungrounded:
        # Kept in the profile but flagged, so the founder can see what the model
        # believed and correct it. Nothing downstream reads an ungrounded
        # competitor: `named_competitors` filters them and the adversarial
        # grounding pass below cannot cite them.
        logger.warning(
            "icp_competitor_ungrounded",
            competitors=ungrounded,
            detail="named without a competitor-material document; not usable for grounding",
        )

    # Computed once and shared: the vocabulary a rationale has to draw on to
    # count as citing the material rather than restating the archetype.
    material_words = _content_words(
        f"{material.own}\n{material.competitor}\n{material.market}"
    )

    archetypes = [
        _build_archetype(a, i, material_words)
        for i, a in enumerate(data.get("archetypes") or [])
    ]
    archetypes = [a for a in archetypes if a is not None][:_MAX_ARCHETYPES]

    adversarial_list: list[AdversarialArchetype] = []
    if adversarial:
        for i, a in enumerate(data.get("adversarial") or []):
            built = _build_adversarial(a, i, allowed_docs, material_words)
            if built is not None:
                adversarial_list.append(built)
        adversarial_list = adversarial_list[:_MAX_ADVERSARIAL]

    return ICPProfile(
        name=str(data.get("name") or "Synthesized ICP").strip()[:120],
        product_summary=str(data.get("product_summary") or "").strip(),
        category=str(data.get("category") or "").strip(),
        archetypes=archetypes,
        adversarial=adversarial_list,
        competitors=competitors,
        gaps=[str(g).strip() for g in (data.get("gaps") or []) if str(g).strip()],
    )


# ---------------------------------------------------------------------------
# The rationale, and the floor under it
# ---------------------------------------------------------------------------

_RATIONALE_MAX_CHARS = 320

# Words carrying no evidential content. Deliberately short: this set is
# subtracted from the *evidence* a rationale offers, so every word added to it
# makes the check stricter, and a stricter check drops good rationales. Only
# words that cannot be the thing a rationale cites belong here.
_RATIONALE_STOPWORDS = frozenset("""
about above after again against also although always among another any anyone
anything are around because been before being below between both cannot could
does doing done down during each either else even ever every from further have
having here however into itself just less like likely many might more most much
must never once only onto other others ours over perhaps rather really same
seem seems several should since some someone something still such than that
their theirs them themselves then there therefore these they thing things this
those though through thus under until upon very were what when where whether
which while whom will with within without would your yours
""".split())


def _content_words(text: str) -> set[str]:
    """Lowercased words of four characters or more, minus the stopwords.

    Four is where English function words mostly stop and nouns start; it is a
    floor for a cheap overlap test, not a linguistic claim.
    """
    word = []
    words: set[str] = set()
    for ch in text.lower():
        if ch.isalpha():
            word.append(ch)
            continue
        if len(word) >= 4:
            words.add("".join(word))
        word = []
    if len(word) >= 4:
        words.add("".join(word))
    return words - _RATIONALE_STOPWORDS


def _grounded_rationale(
    value: Any,
    *,
    own_vocabulary: str,
    material_words: set[str],
    label: str,
) -> str:
    """Keep the rationale only if it cites the material rather than the archetype.

    The audience-review surface asks a founder — who has not heard the term ICP
    — whether each synthesized buyer looks right. A sentence that restates the
    role back at them ("a platform engineering lead who evaluates platform
    engineering tools") *looks* like the evidence they were asked to judge and
    contains none, and the frontend was correct to leave the space empty rather
    than render filler. This is the same failure as Phase 1's bug #5 and Phase
    2's fabricated statistic, one notch quieter: not an invented number, an
    invented reason.

    So the floor is one sentence long: the rationale must name **at least one
    thing the uploaded material says that the archetype's own fields do not
    already say**. Everything the model wrote is otherwise kept verbatim — this
    drops, it does not rewrite, because a rewritten rationale is the product
    asserting a reason on its own account.

    Deliberately narrow, in the same way `_evidence_claims` is: it cannot tell a
    thoughtful rationale from a fluent one. It catches the restatement, which is
    the failure the empty space existed to avoid, and it is a floor under the
    prompt rather than a substitute for it.
    """
    text = " ".join(str(value or "").split())[:_RATIONALE_MAX_CHARS]
    if not text:
        return ""

    evidence = (_content_words(text) & material_words) - _content_words(own_vocabulary)
    if not evidence:
        logger.warning(
            "icp_rationale_dropped",
            archetype=label,
            rationale=text[:160],
            detail=(
                "cites nothing in the uploaded material that the archetype's own "
                "fields do not already state; dropped rather than shown as evidence"
            ),
        )
        return ""
    return text


def _slug(value: str, fallback: str) -> str:
    cleaned = "".join(ch if ch.isalnum() else "-" for ch in value.lower()).strip("-")
    while "--" in cleaned:
        cleaned = cleaned.replace("--", "-")
    return cleaned[:48] or fallback


def _build_archetype(
    data: dict[str, Any],
    index: int,
    material_words: set[str],
) -> ICPArchetype | None:
    label = str(data.get("label") or data.get("role") or "").strip()
    if not label:
        return None

    # The archetype's own vocabulary, against which the rationale must add
    # something. `role` is the field a lazy rationale paraphrases, and the rest
    # are the fields the review UI already renders next to it.
    own_vocabulary = " ".join([
        label,
        str(data.get("role") or ""),
        str(data.get("seniority") or ""),
        str(data.get("switching_cost") or ""),
        *(str(v) for v in (data.get("incumbent_tooling") or [])),
        *(str(v) for v in (data.get("evaluation_criteria") or [])),
        *(str(v) for v in (data.get("skepticism_triggers") or [])),
        *(str(v) for v in (data.get("goals") or [])),
        *(str(v) for v in (data.get("pains") or [])),
    ])

    try:
        return ICPArchetype(
            id=_slug(str(data.get("id") or label), f"archetype-{index + 1}"),
            label=label[:80],
            weight=max(float(data.get("weight") or 1.0), 0.01),
            rationale=_grounded_rationale(
                data.get("rationale"),
                own_vocabulary=own_vocabulary,
                material_words=material_words,
                label=label,
            ),
            role=str(data.get("role") or label)[:120],
            seniority=data.get("seniority") or "manager",
            budget_authority=data.get("budget_authority") or "influencer",
            incumbent_tooling=_str_list(data.get("incumbent_tooling")),
            switching_cost=data.get("switching_cost") or "moderate",
            evaluation_criteria=_str_list(data.get("evaluation_criteria")),
            skepticism_triggers=_str_list(data.get("skepticism_triggers")),
            goals=_str_list(data.get("goals")),
            pains=_str_list(data.get("pains")),
            platforms=_str_list(data.get("platforms")),
            prior_pack_id=data.get("prior_pack_id") or None,
            prior_archetype_id=data.get("prior_archetype_id") or None,
            disposition=_clamp(data.get("disposition"), -1.0, 1.0, 0.0),
        )
    except ValueError as exc:
        logger.warning("icp_archetype_rejected", label=label, error=str(exc))
        return None


def _build_adversarial(
    data: dict[str, Any],
    index: int,
    allowed_docs: set[str],
    material_words: set[str],
) -> AdversarialArchetype | None:
    """Build one adversarial archetype, grounding it before validation.

    The name is dropped rather than the archetype: an unnamed category skeptic
    is still a useful cohort and is exactly what PRD §4 asks for when there is
    no competitor material. Dropping the whole archetype would quietly remove
    the adversarial cohort from runs that most need it.
    """
    label = str(data.get("label") or "").strip()
    if not label:
        return None

    # The five roles are rendered to the model as a list, so they come back
    # decorated, cased and `-`/`_`-swapped — `"Incumbent Power User"`,
    # `"incumbent-power-user"`, `"[sunk_cost_consultant]"`. A bare `not in`
    # compare read every one of those as unrecognised and **silently** made it a
    # `category_skeptic`, which collapses four distinct cohorts into one bloc.
    # The split is what the Founder lens is for: on the live run the entire
    # negative headline was one cohort, and a run whose four roles had merged
    # would have reported that as the market's verdict.
    #
    # `enum_ref` returns None on a genuine miss so the miss is countable, and
    # the default is applied here, loudly, rather than hidden in a lookup.
    role = enum_ref(data.get("role"), ADVERSARIAL_ROLES)
    if role is None:
        if data.get("role"):
            logger.warning(
                "icp_adversarial_role_unrecognised",
                archetype=label,
                returned=str(data.get("role"))[:60],
                allowed=list(ADVERSARIAL_ROLES),
                detail=(
                    "role did not resolve to one of the five; defaulted to "
                    "category_skeptic. Repeated misses collapse the cohort split "
                    "the lens is built on."
                ),
            )
        else:
            logger.info("icp_adversarial_role_absent", archetype=label)
        role = "category_skeptic"

    name, grounded = _ground_adversarial(data, allowed_docs, label)

    own_vocabulary = " ".join([
        label,
        role,
        str(data.get("core_argument") or ""),
        *(str(v) for v in (data.get("talking_points") or [])),
    ])

    try:
        return AdversarialArchetype(
            id=_slug(str(data.get("id") or label), f"adversarial-{index + 1}"),
            label=label[:80],
            weight=max(float(data.get("weight") or 1.0), 0.01),
            rationale=_grounded_rationale(
                data.get("rationale"),
                own_vocabulary=own_vocabulary,
                material_words=material_words,
                label=label,
            ),
            role=role,
            competitor_name=name,
            grounded_in=grounded,
            core_argument=str(data.get("core_argument") or "").strip()[:400],
            talking_points=_str_list(data.get("talking_points")),
            platforms=_str_list(data.get("platforms")),
            prior_pack_id=data.get("prior_pack_id") or None,
            prior_archetype_id=data.get("prior_archetype_id") or None,
            disposition=_clamp(data.get("disposition"), -1.0, 1.0, -0.4),
        )
    except ValueError as exc:
        logger.warning("icp_adversarial_rejected", label=label, error=str(exc))
        return None


def _ground_adversarial(
    data: dict[str, Any],
    allowed_docs: set[str],
    label: str,
) -> tuple[str | None, list[str]]:
    """Return the competitor name only if uploaded material licenses it.

    This is the guardrail. A model asked about a named competitor will
    confabulate — that is not a tuning problem, it is what the model is for —
    so the name survives only when the model cited a document the user marked
    as competitor material. Everything else becomes an unnamed skeptic.
    """
    name = str(data.get("competitor_name") or "").strip() or None
    grounded = [d for d in (data.get("grounded_in") or []) if d in allowed_docs]

    if name and not grounded:
        logger.warning(
            "icp_adversarial_name_stripped",
            archetype=label,
            competitor=name,
            detail=(
                "named a competitor with no competitor-material document; "
                "reduced to an unnamed skeptic"
            ),
        )
        return None, []
    if not name:
        return None, []
    return name, grounded


def _str_list(value: Any, limit: int = 8) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(v).strip()[:200] for v in value if str(v).strip()][:limit]


def _clamp(value: Any, low: float, high: float, default: float) -> float:
    try:
        return max(low, min(high, float(value)))
    except (TypeError, ValueError):
        return default


# ---------------------------------------------------------------------------
# Compilation: profile -> PersonaPack
# ---------------------------------------------------------------------------

def _prior_archetype(pack_id: str | None, archetype_id: str | None) -> Archetype | None:
    """The built-in archetype whose psychometrics this ICP archetype inherits.

    The prior supplies the Big Five vector, the demographics and the posting
    cadence — everything that shapes how the agent *behaves* rather than what it
    wants. Substituting a different prior therefore substitutes a different
    person, quietly, in every agent generated from this archetype.

    So the two ways of not finding one are kept distinguishable. Naming no
    archetype is a legitimate absence and the pack's heaviest member is the
    right stand-in for "the typical member of this pack". Naming an archetype
    the pack does not have is a **miss** — the model referred to something, and
    handing back an unrelated profile under that name is the shape of defect
    this codebase keeps finding.
    """
    if not pack_id:
        return None
    try:
        pack = get_pack(pack_id)
    except KeyError:
        logger.info("icp_prior_pack_unknown", pack_id=pack_id)
        return None

    if archetype_id:
        wanted = enum_ref(archetype_id, {a.id for a in pack.archetypes})
        for archetype in pack.archetypes:
            if archetype.id == wanted:
                return archetype
        logger.warning(
            "icp_prior_archetype_unknown",
            pack_id=pack_id,
            archetype_id=str(archetype_id)[:60],
            available=[a.id for a in pack.archetypes],
            detail=(
                "named an archetype this pack does not contain; falling back to "
                "the pack's heaviest archetype, which carries a different "
                "psychometric profile into every agent built from it"
            ),
        )

    # Named a pack but not a usable archetype: the pack's heaviest archetype is
    # the closest thing to "the typical member of this pack".
    return max(pack.archetypes, key=lambda a: a.weight, default=None)


def _platform_preferences(platforms: list[str], run_platforms: list[str]) -> dict[str, float]:
    chosen = [p for p in platforms if not run_platforms or p in run_platforms]
    if not chosen:
        chosen = run_platforms or platforms
    if not chosen:
        return {}
    return {p: 0.8 for p in chosen}


def _compile_buyer(archetype: ICPArchetype, run_platforms: list[str]) -> Archetype:
    prior = _prior_archetype(archetype.prior_pack_id, archetype.prior_archetype_id)
    return Archetype(
        id=archetype.id,
        label=archetype.label,
        weight=archetype.weight,
        demographics=prior.demographics if prior else _FALLBACK_DEMOGRAPHICS,
        personality=prior.personality if prior else _FALLBACK_PERSONALITY,
        platform_preferences=_platform_preferences(archetype.platforms, run_platforms),
        behavior_traits=BehaviorTraits(
            posts_per_week=prior.behavior_traits.posts_per_week if prior else [1, 4],
            # What this archetype posts about, in their own terms. Feeds the
            # agent-generation prompt directly, which is why it carries the
            # evaluation criteria and pains rather than generic topic nouns.
            typical_content=(
                archetype.evaluation_criteria[:3]
                + archetype.pains[:2]
                + [f"{archetype.role} tooling"]
            )[:6],
            sentiment_baseline=archetype.disposition,
            influence_multiplier=_INFLUENCE_BY_SENIORITY.get(archetype.seniority, 1.5),
        ),
        interests=(archetype.goals + archetype.evaluation_criteria)[:8],
        political_lean="center",
        values=(archetype.evaluation_criteria + archetype.goals)[:6],
        context=ArchetypeContext(
            role=archetype.role,
            seniority=archetype.seniority,
            budget_authority=archetype.budget_authority,
            incumbent_tooling=archetype.incumbent_tooling,
            switching_cost=archetype.switching_cost,
            evaluation_criteria=archetype.evaluation_criteria,
            skepticism_triggers=archetype.skepticism_triggers,
            goals=archetype.goals,
            pains=archetype.pains,
        ),
    )


def _compile_adversarial(archetype: AdversarialArchetype, run_platforms: list[str]) -> Archetype:
    prior = _prior_archetype(archetype.prior_pack_id, archetype.prior_archetype_id)
    return Archetype(
        id=archetype.id,
        label=archetype.label,
        weight=archetype.weight,
        demographics=prior.demographics if prior else _FALLBACK_DEMOGRAPHICS,
        personality=prior.personality if prior else _FALLBACK_PERSONALITY,
        platform_preferences=_platform_preferences(archetype.platforms, run_platforms),
        behavior_traits=BehaviorTraits(
            posts_per_week=prior.behavior_traits.posts_per_week if prior else [2, 6],
            typical_content=(
                [archetype.core_argument] if archetype.core_argument else []
            ) + archetype.talking_points[:4],
            sentiment_baseline=archetype.disposition,
            # Incumbent-aligned voices arrive first and arrive credentialed
            # (PRD §4). Understating their reach would model the cohort as
            # present but inaudible, which is not the phenomenon.
            influence_multiplier=prior.behavior_traits.influence_multiplier if prior else 2.0,
        ),
        interests=archetype.talking_points[:8],
        political_lean="center",
        values=archetype.talking_points[:6],
        is_adversarial=True,
        adversarial_role=archetype.role,
        context=ArchetypeContext(
            role=archetype.role.replace("_", " "),
            competitor_name=archetype.competitor_name,
            core_argument=archetype.core_argument,
            talking_points=archetype.talking_points,
        ),
    )


def rebalance_adversarial(archetypes: list[Archetype], share: float) -> list[Archetype]:
    """Re-weight a pack so the adversarial cohort takes `share` of the swarm.

    `run_prepare_agents` allocates agents by weight and knows nothing about
    cohorts, so a cohort share has to be expressed as weight or not at all.
    Expressing it here keeps one allocation rule instead of two.

    Applied at prepare time as well as at compile time, because the run's
    configured share is the authoritative one: an ICP is reused across runs and
    a founder who wants to see what happens at 40% incumbents should not have to
    re-synthesize their audience to find out.

    Mutates and returns the same objects — they are freshly-compiled or freshly
    loaded per call, never the shared `_pack_cache` entries, which hold built-in
    packs that carry no adversarial archetypes at all.
    """
    attackers = [a for a in archetypes if a.is_adversarial]
    if not attackers:
        return archetypes

    buyers = [a for a in archetypes if not a.is_adversarial]
    if not buyers:
        # An all-adversarial pack is not a market. Nothing constructs one today;
        # if something ever does, leaving the weights alone is the honest
        # outcome — scaling them to a share of a swarm with no buyers in it
        # would produce a number that means nothing.
        logger.warning("icp_pack_all_adversarial", archetypes=len(attackers))
        return archetypes

    buyer_total = sum(a.weight for a in buyers) or 1.0

    if share <= 0:
        # The cohort exists in the pack but takes none of the swarm. Dropping it
        # instead would make a compiled pack depend on the share of whichever
        # run happened to compile it first.
        #
        # Buyers are normalised here as well as on the share > 0 path. Without
        # it a pack's total weight was whatever its raw archetype weights
        # summed to, and `run_prepare_agents` allocates agents across *all*
        # selected packs by weight — so with multiple packs in one run, a pack
        # that happened to carry more archetypes took a larger share of the
        # swarm than one that carried fewer, at share 0 only. One rule at both
        # ends: a pack is worth 1.0 of the swarm, whatever is inside it.
        for archetype in buyers:
            archetype.weight = archetype.weight / buyer_total
        for archetype in attackers:
            archetype.weight = 0.0001
        return archetypes

    attacker_total = sum(a.weight for a in attackers) or 1.0
    for archetype in buyers:
        archetype.weight = archetype.weight / buyer_total * (1.0 - share)
    for archetype in attackers:
        archetype.weight = archetype.weight / attacker_total * share
    return archetypes


def compile_pack(
    profile: ICPProfile,
    pack_id: str,
    platforms: list[str] | None = None,
    adversarial_share: float = 0.0,
) -> PersonaPack:
    """Compile an ICP profile into the pack the engine runs."""
    run_platforms = platforms or []
    buyers = [_compile_buyer(a, run_platforms) for a in profile.archetypes]
    attackers = [_compile_adversarial(a, run_platforms) for a in profile.adversarial]
    archetypes = rebalance_adversarial(buyers + attackers, adversarial_share)

    return PersonaPack(
        id=pack_id,
        name=profile.name,
        version="1.0",
        category="synthesized-icp",
        description=profile.product_summary or f"Synthesized ICP: {profile.name}",
        archetypes=archetypes,
    )


# ---------------------------------------------------------------------------
# Segmentation: one profile -> several packs
# ---------------------------------------------------------------------------

# The two axes a B2B audience actually splits on, and the only two the ICP
# schema records for every archetype.
#
# Seniority, because what a practitioner and an approver each need to hear is
# different in kind, not degree — one is asking "will this work", the other
# "what does this cost me if it doesn't". Switching cost, because DECISIONS §7's
# central claim is that a B2B buyer evaluates net of what they would rip out;
# an archetype with nothing to rip out and one facing a prohibitive migration
# are not the same buyer wearing different job titles.
#
# Deliberately not clustered on free text (goals, pains, incumbent tooling).
# Those are model-written strings, and clustering on them would make the number
# of packs a function of the model's phrasing on the day.
_SENIORITY_SEGMENT = {
    "ic": "practitioner",
    "manager": "practitioner",
    "director": "decision_maker",
    "vp": "decision_maker",
    "c_level": "decision_maker",
    "founder": "decision_maker",
}
_SWITCHING_SEGMENT = {
    "low": "low_switching_cost",
    "moderate": "low_switching_cost",
    "high": "high_switching_cost",
    "prohibitive": "high_switching_cost",
}

_SEGMENT_LABELS = {
    "practitioner": "practitioners",
    "decision_maker": "decision makers",
    "low_switching_cost": "low switching cost",
    "high_switching_cost": "entrenched",
}


def _segment_key(archetype: ICPArchetype) -> tuple[str, str]:
    """Which pack an archetype belongs in.

    `enum_ref` rather than `.get(...)` with a default: seniority and switching
    cost come back from the model restated, and an unrecognised value silently
    becoming `practitioner` / `low_switching_cost` would merge two segments into
    one and report a clean split. The miss is defaulted here, loudly.
    """
    seniority = enum_ref(archetype.seniority, set(_SENIORITY_SEGMENT))
    if seniority is None:
        logger.warning(
            "icp_segment_seniority_unrecognised",
            archetype=archetype.id,
            returned=str(archetype.seniority)[:40],
            allowed=sorted(_SENIORITY_SEGMENT),
        )
        seniority = "manager"

    switching = enum_ref(archetype.switching_cost, set(_SWITCHING_SEGMENT))
    if switching is None:
        logger.warning(
            "icp_segment_switching_cost_unrecognised",
            archetype=archetype.id,
            returned=str(archetype.switching_cost)[:40],
            allowed=sorted(_SWITCHING_SEGMENT),
        )
        switching = "moderate"

    return _SENIORITY_SEGMENT[seniority], _SWITCHING_SEGMENT[switching]


def _segment_slug(key: tuple[str, str]) -> str:
    return f"{key[0]}-{key[1]}".replace("_", "-")


def _segment_name(key: tuple[str, str]) -> str:
    return f"{_SEGMENT_LABELS[key[0]].capitalize()}, {_SEGMENT_LABELS[key[1]]}"


def compile_packs(
    profile: ICPProfile,
    base_pack_id: str,
    platforms: list[str] | None = None,
    adversarial_share: float = 0.0,
) -> list[PersonaPack]:
    """Compile an ICP into one pack per coherent buyer segment.

    `simulations.persona_pack_ids` is already a list and `run_prepare_agents`
    already loops over it, so this is a compile-and-register change and nothing
    in the runner moves. What it buys is a founder being able to run *the
    entrenched decision makers* on their own, instead of averaging them into one
    blended audience where the segment that would have killed the deal is 15% of
    the swarm and invisible in the headline.

    Returns a single pack — identical to `compile_pack` — when the profile does
    not split, so the one-pack case stays exactly what it was.

    ## The adversarial share is the hazard, and this is how it is held

    `run_prepare_agents` calls `rebalance_adversarial` **per pack** and then
    allocates agents across every pack's archetypes by raw weight. Rebalancing
    normalises a pack containing both cohorts to a total weight of 1.0, of which
    `share` is adversarial. So:

    * **Every pack must contain adversarial archetypes.** A pack with none is
      returned untouched by `rebalance_adversarial`, keeps whatever its raw
      weights summed to, and dilutes the cohort across the run by an amount
      nobody can see. Partitioning the cohort so some segments have none — the
      obvious design — is the one that must not be used.
    * **Every pack gets `ceil(K / N)` of the K adversarial archetypes, dealt
      round-robin.** Every archetype therefore appears at least once across the
      run, and no pack faces an empty cohort.
    * Each dealt archetype gets a per-segment id suffix. `run_prepare_agents`
      builds `entity_id` as `f"{archetype.id}_{platform}_{i}"`, and HANDOFF §1a
      is the record of what happens here when two agents share one identity.

    **Why deal rather than copy the whole cohort into every pack.** Copying
    preserves the cohort's internal mix exactly, and it was measured to be
    materially worse where it counts. `run_prepare_agents` apportions agents
    with `max(1, round(weight / total * n))` per archetype and then truncates on
    a running remainder, so its accuracy degrades as the archetype count grows —
    and copying multiplies that count by N. Across 480 configurations (3–6
    buyers, 2–4 adversarial, 2–4 packs, 30–200 agents, 20–50% share):

    | design | worst deviation from the configured share | cases worse than one pack |
    |---|---|---|
    | one blended pack | 0.100 | — |
    | copy the cohort into every pack | **0.200** | 178 / 480 |
    | deal `ceil(K/N)` per pack | 0.100 | 83 / 480 |

    Dealing holds the same error bound as the single-pack case; copying doubles
    it. The cost is that an archetype dealt into a pack of two carries half the
    weight of one dealt into a pack of one, so the cohort's *internal* mix
    shifts by up to 2×. The share — the number the product claims accuracy on —
    does not.

    That 0.100 worst case belongs to `run_prepare_agents`, not to this function:
    independent per-archetype rounding with no remainder redistribution cannot
    be accurate on a 30-agent swarm. Largest-remainder apportionment there would
    make both columns exact.

    Each pack is worth an equal share of the swarm when several run together,
    because pack-level normalisation is what preserves the cohort share. Segment
    sizes therefore do not carry over; the founder chooses which audiences to
    run, and that choice is the point of splitting them.
    """
    run_platforms = platforms or []
    segments: dict[tuple[str, str], list[ICPArchetype]] = {}
    for archetype in profile.archetypes:
        segments.setdefault(_segment_key(archetype), []).append(archetype)

    if len(segments) <= 1:
        logger.info(
            "icp_packs_not_segmented",
            pack_id=base_pack_id,
            archetypes=len(profile.archetypes),
            detail="every buyer archetype falls in one segment; emitting one pack",
        )
        return [compile_pack(profile, base_pack_id, platforms, adversarial_share)]

    # Heaviest segment first, then by slug, so the order does not depend on dict
    # insertion — which is the order the model happened to emit archetypes in.
    ordered = sorted(
        segments.items(),
        key=lambda item: (-sum(a.weight for a in item[1]), _segment_slug(item[0])),
    )

    cohort = profile.adversarial
    # Ceiling division: N × per_pack ≥ K, so every adversarial archetype is
    # dealt at least once and no pack is left without a cohort.
    per_pack = -(-len(cohort) // len(ordered)) if cohort else 0
    dealt = 0

    packs: list[PersonaPack] = []
    for key, members in ordered:
        slug = _segment_slug(key)
        buyers = [_compile_buyer(a, run_platforms) for a in members]

        attackers: list[Archetype] = []
        for _ in range(per_pack):
            compiled = _compile_adversarial(cohort[dealt % len(cohort)], run_platforms)
            dealt += 1
            compiled.id = f"{compiled.id}--{slug}"
            attackers.append(compiled)

        archetypes = rebalance_adversarial(buyers + attackers, adversarial_share)
        if not attackers:
            # No adversarial cohort at all, so `rebalance_adversarial` is a
            # no-op and the pack keeps its raw buyer weights. Normalised here so
            # packs still carry equal swarm weight — `run_prepare_agents`
            # allocates across every selected pack by weight, and without this a
            # segment that happened to hold more archetypes would quietly take a
            # larger share of the swarm.
            buyer_total = sum(a.weight for a in buyers) or 1.0
            for archetype in buyers:
                archetype.weight = archetype.weight / buyer_total
        packs.append(
            PersonaPack(
                id=f"{base_pack_id}__{slug}",
                name=f"{profile.name} — {_segment_name(key)}",
                version="1.0",
                category="synthesized-icp",
                description=(
                    f"{_segment_name(key)} segment of {profile.name}: "
                    + ", ".join(a.label for a in members)
                ),
                archetypes=archetypes,
            )
        )

    logger.info(
        "icp_packs_compiled",
        base_pack_id=base_pack_id,
        packs=len(packs),
        segments=[_segment_slug(key) for key, _ in ordered],
        buyers_per_pack=[len(members) for _, members in ordered],
        adversarial_in_cohort=len(cohort),
        adversarial_per_pack=per_pack,
        adversarial_share=adversarial_share,
    )
    return packs


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------

async def synthesize_icp(
    project_id: str,
    org_id: str,
    *,
    adversarial: bool = True,
    platforms: list[str] | None = None,
    adversarial_share: float = 0.0,
    created_by: str | None = None,
    name: str | None = None,
) -> dict[str, Any]:
    """Synthesize an ICP for a project and persist it.

    Metered as its own stage. ICP synthesis is per-project and reusable across
    runs, so folding it into every run quote would overcharge the second run and
    undercharge the first — and Phase 1's bug #6 was a whole stage that was
    measured but never priced, which is the failure this avoids repeating.
    """
    material = gather_material(project_id)
    if material.is_empty:
        raise ValueError(
            "No processed documents in this project. ICP synthesis reads the "
            "material you upload — a PRD, landing page, deck, or pricing page — "
            "and cannot be run against an empty project."
        )

    with usage_context("icp_synthesis", organization_id=org_id):
        profile = await _synthesize_profile(
            material,
            adversarial=adversarial,
            platforms=platforms or [],
        )

    if name:
        profile.name = name[:120]

    pack_id = f"icp_{uuid.uuid4().hex}"
    pack = compile_pack(profile, pack_id, platforms, adversarial_share)

    prior_pack_ids = sorted({
        a.prior_pack_id
        for a in [*profile.archetypes, *profile.adversarial]
        if a.prior_pack_id
    })

    admin = get_supabase_admin()
    row = (
        admin.table("icp_profiles")
        .insert({
            "project_id": project_id,
            "organization_id": org_id,
            "name": profile.name,
            "product_summary": profile.product_summary,
            "profile": profile.model_dump(mode="json"),
            "pack_data": pack.model_dump(mode="json"),
            "pack_id": pack_id,
            "prior_pack_ids": prior_pack_ids,
            "source_document_ids": material.all_ids,
            "competitors": [c.model_dump(mode="json") for c in profile.competitors],
            "synthesis_model": settings.llm_model,
            "created_by": created_by,
        })
        .execute()
    ).data[0]

    segment_pack_ids = _persist_segment_packs(
        profile,
        base_pack_id=pack_id,
        org_id=org_id,
        icp_profile_id=row["id"],
        platforms=platforms,
        adversarial_share=adversarial_share,
    )

    logger.info(
        "icp_synthesized",
        project_id=project_id,
        pack_id=pack_id,
        segment_pack_ids=segment_pack_ids,
        archetypes=len(profile.archetypes),
        adversarial=len(profile.adversarial),
        named_competitors=len(profile.named_competitors),
        gaps=len(profile.gaps),
    )
    # `segment_pack_ids` is carried on the response, not on the row. The link
    # from a segment pack back to the profile lives in the store, keyed by
    # `source_icp_profile_id`, so a column here would be a second copy of it.
    return {**row, "segment_pack_ids": segment_pack_ids}


def _persist_segment_packs(
    profile: ICPProfile,
    *,
    base_pack_id: str,
    org_id: str,
    icp_profile_id: str,
    platforms: list[str] | None,
    adversarial_share: float,
) -> list[str]:
    """Store one pack per buyer segment and return their ids.

    The blended pack in `icp_profiles.pack_data` is unchanged and remains what
    `get_pack(icp_…)` resolves; these are additional, selectable audiences.

    Persistence belongs to `personas/persona_store.py`. If that module is not
    present the packs are compiled and **not** stored, and that is reported at
    ERROR with the ids that were lost — an empty list returned quietly would
    make "this ICP does not segment" and "the store is missing" the same
    observation, which is the failure class this file is full of comments about.
    """
    try:
        from app.services.engine.personas.persona_store import save_org_pack
    except ImportError:
        save_org_pack = None

    packs = compile_packs(profile, base_pack_id, platforms, adversarial_share)
    if len(packs) <= 1:
        return []

    if save_org_pack is None:
        logger.error(
            "persona_store_unavailable",
            icp_profile_id=icp_profile_id,
            compiled_packs=[p.id for p in packs],
            detail=(
                "personas/persona_store.save_org_pack is not importable; "
                f"{len(packs)} segment packs were compiled and discarded. The "
                "blended pack is unaffected."
            ),
        )
        return []

    # `save_org_pack` returns the id the pack is stored under, which is the id
    # `get_pack` will have to resolve. The ids `compile_packs` mints are
    # therefore proposals: if the store assigns its own, it must write it onto
    # the stored `pack_data.id` too, or a run will load a pack whose `id` does
    # not match the row it came from — and `run_prepare_agents` stamps
    # `pack.id` onto every agent row as `persona_pack_id`.
    stored: list[str] = []
    for pack in packs:
        stored.append(save_org_pack(org_id, pack, icp_profile_id))
    return stored


def recompile_profile(
    profile_row: dict[str, Any],
    platforms: list[str] | None = None,
    adversarial_share: float = 0.0,
) -> dict[str, Any]:
    """Re-derive `pack_data` after a founder edits the profile.

    Called on edit rather than on read. A pack recompiled at read time would
    make a re-simulation's audience depend on when it was read, and the
    inoculation loop's entire claim is that the audience did not change between
    the two runs.
    """
    profile = ICPProfile.model_validate(profile_row["profile"])
    pack = compile_pack(profile, profile_row["pack_id"], platforms, adversarial_share)
    return pack.model_dump(mode="json")
