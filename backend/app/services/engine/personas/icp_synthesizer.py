# PUBLIC INTERFACE
# ─────────────────────────────────────────────────────────
# synthesize_icp(project_id, org_id, *, adversarial=True, platforms=None,
#                created_by=None, name=None) -> dict   [persists icp_profiles]
# compile_pack(profile, pack_id, platforms=None, adversarial_share=0.0) -> PersonaPack
# rebalance_adversarial(archetypes, share) -> list[Archetype]
# gather_material(project_id) -> ProjectMaterial
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

def gather_material(project_id: str) -> ProjectMaterial:
    """Read the project's processed documents, bucketed by material kind.

    Text extraction goes through `document_processor._extract_text`, which knows
    about PDF and DOCX. `run_prepare_agents` does its own `bytes.decode('utf-8')`
    on the same files, which produces mojibake for every non-text upload — that
    is a separate known issue, but it is why this path does not reuse it.
    """
    from app.services.engine.document_processor import _extract_text

    admin = get_supabase_admin()
    docs = (
        admin.table("documents")
        .select("id, filename, file_type, storage_path, material_kind")
        .eq("project_id", project_id)
        .eq("processing_status", "complete")
        .order("created_at", desc=False)
        .execute()
    ).data or []

    buckets: dict[str, list[str]] = {"own": [], "competitor": [], "market": []}
    ids: dict[str, list[str]] = {"own": [], "competitor": [], "market": []}
    limits = {
        "own": _OWN_MATERIAL_CHARS,
        "competitor": _COMPETITOR_MATERIAL_CHARS,
        "market": _MARKET_MATERIAL_CHARS,
    }
    used = {"own": 0, "competitor": 0, "market": 0}

    for doc in docs:
        # NULL predates the column and is read as 'own'. An unlabelled document
        # can never be the thing that authorises naming a competitor.
        kind = doc.get("material_kind") or "own"
        if kind not in buckets:
            kind = "own"
        if used[kind] >= limits[kind]:
            continue
        try:
            file_bytes = admin.storage.from_("project-media").download(doc["storage_path"])
            text, _, _ = _extract_text(file_bytes, doc["file_type"])
        except Exception as exc:
            logger.warning(
                "icp_material_read_failed",
                document_id=doc["id"],
                filename=doc.get("filename"),
                error=str(exc),
            )
            continue

        remaining = limits[kind] - used[kind]
        snippet = text[:remaining]
        if not snippet.strip():
            continue
        used[kind] += len(snippet)
        buckets[kind].append(f"### {doc.get('filename') or 'document'}\n{snippet}")
        ids[kind].append(doc["id"])

    material = ProjectMaterial(
        own="\n\n".join(buckets["own"]),
        competitor="\n\n".join(buckets["competitor"]),
        market="\n\n".join(buckets["market"]),
        own_ids=ids["own"],
        competitor_ids=ids["competitor"],
        market_ids=ids["market"],
    )
    logger.info(
        "icp_material_gathered",
        project_id=project_id,
        own_docs=len(ids["own"]),
        competitor_docs=len(ids["competitor"]),
        market_docs=len(ids["market"]),
        own_chars=len(material.own),
        competitor_chars=len(material.competitor),
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

    archetypes = [_build_archetype(a, i) for i, a in enumerate(data.get("archetypes") or [])]
    archetypes = [a for a in archetypes if a is not None][:_MAX_ARCHETYPES]

    adversarial_list: list[AdversarialArchetype] = []
    if adversarial:
        for i, a in enumerate(data.get("adversarial") or []):
            built = _build_adversarial(a, i, allowed_docs)
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


def _slug(value: str, fallback: str) -> str:
    cleaned = "".join(ch if ch.isalnum() else "-" for ch in value.lower()).strip("-")
    while "--" in cleaned:
        cleaned = cleaned.replace("--", "-")
    return cleaned[:48] or fallback


def _build_archetype(data: dict[str, Any], index: int) -> ICPArchetype | None:
    label = str(data.get("label") or data.get("role") or "").strip()
    if not label:
        return None
    try:
        return ICPArchetype(
            id=_slug(str(data.get("id") or label), f"archetype-{index + 1}"),
            label=label[:80],
            weight=max(float(data.get("weight") or 1.0), 0.01),
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

    try:
        return AdversarialArchetype(
            id=_slug(str(data.get("id") or label), f"adversarial-{index + 1}"),
            label=label[:80],
            weight=max(float(data.get("weight") or 1.0), 0.01),
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

    if share <= 0:
        # The cohort exists in the pack but takes none of the swarm. Dropping it
        # instead would make a compiled pack depend on the share of whichever
        # run happened to compile it first.
        for archetype in attackers:
            archetype.weight = 0.0001
        return archetypes

    buyer_total = sum(a.weight for a in buyers) or 1.0
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

    logger.info(
        "icp_synthesized",
        project_id=project_id,
        pack_id=pack_id,
        archetypes=len(profile.archetypes),
        adversarial=len(profile.adversarial),
        named_competitors=len(profile.named_competitors),
        gaps=len(profile.gaps),
    )
    return row


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
