# PUBLIC INTERFACE
# ─────────────────────────────────────────────────────────
# load_all_packs() -> list[PersonaPack]
# get_pack(pack_id: str, org_id: str | None) -> PersonaPack
# list_available_packs(org_id: str | None) -> list[PackSummary]
# is_builtin_pack_id(pack_id: str) -> bool
# PackLookupError
# Archetype, ArchetypeContext, PersonaPack, Demographics, Personality,
# BehaviorTraits, ICP_PACK_PREFIX
# ─────────────────────────────────────────────────────────
from __future__ import annotations

import json
from pathlib import Path

import structlog
from pydantic import BaseModel, Field

logger = structlog.get_logger()


class PackLookupError(RuntimeError):
    """The pack store could not be reached. **Not** the same as "no such pack".

    `get_pack` raises `KeyError` when a pack does not exist and this when the
    question could not be answered. Callers act on the two differently and must
    be able to: `run_prepare_agents` skips a `KeyError` and runs with the packs
    it did find, which is right for a pack the founder deleted and catastrophic
    for a database blip — the run would complete, the report would render, and
    the audience would silently be whichever subset of packs happened to load.
    That is the miss-indistinguishable-from-absence shape this module already
    carries two other fixes for.
    """

PACKS_DIR = Path(__file__).resolve().parents[4] / "data" / "persona_packs"

# Pack ids with this prefix are compiled ICP profiles, stored in `icp_profiles`
# rather than `custom_persona_packs`. The profile and the pack it compiles to
# live in one row so that an edit and the pack the next run uses cannot drift.
ICP_PACK_PREFIX = "icp_"

# Built-in packs, read from disk once per process.
#
# **Only packs from `PACKS_DIR` ever go in here.** Custom and compiled-ICP packs
# come out of the database and are tenant-owned; writing them into a
# process-global dict made two things true that must not be. A custom pack whose
# id equalled a built-in's overwrote the built-in for **every** organisation
# served by that worker, so one tenant's edit silently changed another tenant's
# audience — and even without a collision, `get_pack` checks this dict first, so
# the first org to load a custom pack served it to every subsequent caller of
# that id. Both are cross-tenant, both are invisible: the run completes, the
# report renders, and the agents are simply not the agents the founder
# configured.
#
# Built-in packs are files and cannot change under a running process, which is
# what makes caching them safe. Everything else is re-read, on the same
# reasoning `_load_icp_pack` already documents.
_pack_cache: dict[str, PersonaPack] = {}


class Demographics(BaseModel):
    age_range: list[int]
    gender_distribution: dict[str, float]
    education: list[str]
    income_bracket: str


class Personality(BaseModel):
    mbti_pool: list[str]
    big5: dict[str, float]


class BehaviorTraits(BaseModel):
    posts_per_week: list[int | float]
    typical_content: list[str]
    sentiment_baseline: float
    influence_multiplier: float


class ArchetypeContext(BaseModel):
    """Founder-lens grounding carried alongside an archetype.

    The 16 built-in packs describe *people* — age, Big Five, posting cadence.
    A synthesized ICP describes a *buying situation*: what this archetype uses
    today, what it would cost them to switch, what makes them stop reading. That
    is the part worth paying an Opus pass for, and none of it fits in a pack's
    demographic fields.

    Optional and absent on every built-in pack, so the packs on disk keep
    validating unchanged. Present, it reaches the agent-generation prompt — an
    ICP whose incumbent tooling never gets into an agent's head is a relabelled
    generic pack, which is the failure mode DECISIONS §3 rejected packs to avoid.
    """

    role: str = ""
    seniority: str = ""
    budget_authority: str = ""
    incumbent_tooling: list[str] = Field(default_factory=list)
    switching_cost: str = ""
    evaluation_criteria: list[str] = Field(default_factory=list)
    skepticism_triggers: list[str] = Field(default_factory=list)
    goals: list[str] = Field(default_factory=list)
    pains: list[str] = Field(default_factory=list)

    # Adversarial archetypes only. `competitor_name` is set only when uploaded
    # competitor material licensed the name — see icp_schema.
    competitor_name: str | None = None
    core_argument: str = ""
    talking_points: list[str] = Field(default_factory=list)


class Archetype(BaseModel):
    id: str
    label: str
    weight: float
    demographics: Demographics
    personality: Personality
    platform_preferences: dict[str, float]
    behavior_traits: BehaviorTraits
    interests: list[str]
    political_lean: str
    values: list[str]

    # Set only by compiled ICP packs. An adversarial agent is labelled synthetic
    # in every report and export (PRD §4), so the flag has to survive from the
    # pack all the way onto the agent row — inferring it later from a label is
    # exactly the kind of string-matching this codebase has been removing.
    is_adversarial: bool = False
    adversarial_role: str | None = None
    context: ArchetypeContext | None = None


class PersonaPack(BaseModel):
    id: str
    name: str
    version: str
    category: str
    description: str
    archetypes: list[Archetype]


class PackSummary(BaseModel):
    id: str
    name: str
    category: str
    description: str
    archetype_count: int
    archetype_labels: list[str]


def load_all_packs() -> list[PersonaPack]:
    """Load the built-in persona packs from disk into the process cache."""
    global _pack_cache
    if _pack_cache:
        return list(_pack_cache.values())

    _pack_cache = {}
    if not PACKS_DIR.exists():
        logger.warning("persona_packs_dir_missing", path=str(PACKS_DIR))
        return []

    for json_file in sorted(PACKS_DIR.glob("*.json")):
        try:
            data = json.loads(json_file.read_text(encoding="utf-8"))
            pack = PersonaPack.model_validate(data)
            _pack_cache[pack.id] = pack
            logger.info("pack_loaded", pack_id=pack.id, archetypes=len(pack.archetypes))
        except Exception as e:
            logger.error("pack_load_failed", file=json_file.name, error=str(e))

    logger.info("all_packs_loaded", count=len(_pack_cache))
    return list(_pack_cache.values())


def is_builtin_pack_id(pack_id: str) -> bool:
    """True when `pack_id` names one of the 16 packs on disk.

    Public because the org library has to refuse a pack that claims a built-in's
    id at *write* time, and reaching into `_pack_cache` from another module
    would make a second place that knows how built-ins are stored.
    """
    if not _pack_cache:
        load_all_packs()
    return pack_id in _pack_cache


def get_pack(pack_id: str, org_id: str | None = None) -> PersonaPack:
    """Get a persona pack by id, within an organization.

    **`pack_id` alone is not an identity for anything except a built-in.**
    Built-in ids are globally unique because they are filenames. Every other
    tier is tenant-owned and its id is unique only *within* an organization —
    `custom_persona_packs` and `persona_packs` both constrain
    `UNIQUE(organization_id, pack_id)`, which says precisely that. Resolving one
    of those by `pack_id` alone therefore asks a question with more than one
    correct answer, and the previous implementation took `result.data[0]`: org
    B could be served org A's audience, and nothing would error.

    This is the same defect class as HANDOFF §1a's `username` — a lookup keyed
    on something that is not unique in the space it is used in — so it is fixed
    the same way §1a fixed that one: the identity is carried to the boundary
    rather than reconstructed at it. The org reaches the `.eq()` in the query,
    so no call site can forget to filter and no composite string has to be
    parsed back apart.

    `org_id=None` resolves **built-ins only**, and raises `KeyError` for
    anything else. Fail-closed is the point: a caller with no organization in
    hand has not proved a right to any organization's data, and defaulting to
    "search everyone's packs" is how the leak existed in the first place.
    `icp_synthesizer._prior_archetype` is the one caller that legitimately wants
    this — the 16 built-ins are the only priors DECISIONS §3 blends from.

    Raises:
        KeyError: no such pack for this organization.
        PackLookupError: the store could not be reached, which is a different
            thing and must not be read as absence.
    """
    if not _pack_cache:
        load_all_packs()
    if pack_id in _pack_cache:
        return _pack_cache[pack_id]

    if org_id is None:
        raise KeyError(
            f"Persona pack '{pack_id}' is not a built-in, and no organization "
            f"was supplied to resolve a tenant-owned pack"
        )

    if pack_id.startswith(ICP_PACK_PREFIX):
        pack = _load_icp_pack(pack_id, org_id)
        if pack:
            return pack
        raise KeyError(f"ICP profile '{pack_id}' not found")

    # The org's promoted library, then its LLM-generated custom packs. Order is
    # arbitrary only because the two id spaces are disjoint in practice; if a
    # slug ever exists in both for one org, the library — the thing the founder
    # deliberately curated — is the one they meant.
    from app.services.engine.personas import persona_store

    pack = persona_store.load_org_pack(org_id, pack_id)
    if pack:
        return pack

    pack = _load_custom_pack(pack_id, org_id)
    if pack:
        return pack

    raise KeyError(f"Persona pack '{pack_id}' not found")


def _load_icp_pack(pack_id: str, org_id: str) -> PersonaPack | None:
    """Load a compiled ICP pack from `icp_profiles`, scoped to one org.

    `icp_profiles.pack_id` carries a global UNIQUE constraint (020), so it does
    not *collide* across orgs the way a slug does — but a globally unique id is
    not an authorisation, and without the org filter any caller holding an
    `icp_<uuid-hex>` could read another organization's compiled audience. The
    filter costs nothing and removes the question.

    Deliberately not cached in `_pack_cache`: a founder can edit their ICP
    between runs, and a process-lifetime cache would serve the pre-edit audience
    to whichever API worker happened to have loaded it first. Built-in packs are
    files and cannot change under a running process; this one can.
    """
    from app.core.database import get_supabase_admin

    try:
        admin = get_supabase_admin()
        result = (
            admin.table("icp_profiles")
            .select("pack_data")
            .eq("pack_id", pack_id)
            .eq("organization_id", org_id)
            .limit(1)
            .execute()
        )
    except Exception as e:
        logger.error("icp_pack_lookup_failed", pack_id=pack_id, org_id=org_id, error=str(e))
        raise PackLookupError(f"could not read icp_profiles for '{pack_id}'") from e

    if not result.data:
        return None
    return PersonaPack.model_validate(result.data[0]["pack_data"])


def _shadows_builtin(pack: PersonaPack, org_id: str | None = None) -> bool:
    """True when a tenant pack claims a built-in's id. Loud, and refused.

    The built-in wins, because a shared global must never be replaced by tenant
    data. But the tenant's pack then never runs, and a pack that silently never
    runs is the same lookup-miss-indistinguishable-from-absence shape as the
    overwrite it replaced — so the collision is reported at ERROR with both the
    id and the owner, which is what makes it fixable.
    """
    if pack.id not in _pack_cache:
        return False
    logger.error(
        "custom_pack_shadows_builtin",
        pack_id=pack.id,
        organization_id=org_id,
        detail=(
            "a custom pack claims a built-in pack's id. The built-in is served "
            "and the custom pack is ignored; rename the custom pack. It must "
            "never be cached, because the cache is process-global and shared by "
            "every organization this worker serves."
        ),
    )
    return True


def _load_custom_pack(pack_id: str, org_id: str) -> PersonaPack | None:
    """Load one custom pack, by `(organization_id, pack_id)` — its actual key.

    `custom_persona_packs` constrains `UNIQUE(organization_id, pack_id)`, so
    `pack_id` alone selects a *set*. This used to query on `pack_id` and take
    `result.data[0]`, which meant the row served depended on the query plan
    rather than on who was asking. Production has 5 custom packs across 2
    organizations and no colliding slug today, so nothing has leaked yet — the
    org library is what makes shared slugs the expected case.

    Not cached: `_pack_cache` is process-global and this row is tenant-owned.
    See the cache's own comment for what caching it did.
    """
    from app.core.database import get_supabase_admin

    try:
        admin = get_supabase_admin()
        result = (
            admin.table("custom_persona_packs")
            .select("pack_data")
            .eq("pack_id", pack_id)
            .eq("organization_id", org_id)
            .limit(1)
            .execute()
        )
    except Exception as e:
        logger.error("custom_pack_lookup_failed", pack_id=pack_id, org_id=org_id, error=str(e))
        raise PackLookupError(f"could not read custom_persona_packs for '{pack_id}'") from e

    if not result.data:
        return None
    pack = PersonaPack.model_validate(result.data[0]["pack_data"])
    if _shadows_builtin(pack, org_id):
        return None
    return pack


def load_custom_packs_for_org(org_id: str) -> list[PersonaPack]:
    """Load all custom packs for an organization from DB.

    Not cached, for the same reason as `_load_custom_pack`: these rows belong to
    one organization and `_pack_cache` belongs to the process.
    """
    from app.core.database import get_supabase_admin

    try:
        admin = get_supabase_admin()
        result = (
            admin.table("custom_persona_packs")
            .select("pack_data")
            .eq("organization_id", org_id)
            .execute()
        )
    except Exception as e:
        logger.error("custom_packs_lookup_failed", org_id=org_id, error=str(e))
        raise PackLookupError(f"could not list custom_persona_packs for org {org_id}") from e

    packs = []
    for row in result.data:
        try:
            pack = PersonaPack.model_validate(row["pack_data"])
        except Exception as e:
            # One corrupt row must not hide the rest of the org's library, but
            # it is an ERROR: a pack the founder can see in the product and the
            # engine cannot parse is a run that silently omits an audience.
            logger.error("custom_pack_parse_failed", org_id=org_id, error=str(e))
            continue
        if _shadows_builtin(pack, org_id):
            continue
        packs.append(pack)
    return packs


def _summary(pack: PersonaPack) -> PackSummary:
    return PackSummary(
        id=pack.id,
        name=pack.name,
        category=pack.category,
        description=pack.description,
        archetype_count=len(pack.archetypes),
        archetype_labels=[a.label for a in pack.archetypes],
    )


def list_available_packs(org_id: str | None = None) -> list[PackSummary]:
    """List the packs an organization can run: built-ins + its library + custom.

    Without `org_id` this is the 16 built-ins and nothing else, for the same
    fail-closed reason `get_pack` has: no organization, no tenant data.
    """
    if not _pack_cache:
        load_all_packs()

    summaries = [_summary(p) for p in _pack_cache.values()]
    if not org_id:
        return summaries

    from app.services.engine.personas import persona_store

    seen = {s.id for s in summaries}
    for pack in persona_store.load_org_packs(org_id) + load_custom_packs_for_org(org_id):
        if pack.id in seen:
            continue
        seen.add(pack.id)
        summaries.append(_summary(pack))

    return summaries


def reload_packs() -> list[PersonaPack]:
    """Force reload all packs from disk."""
    global _pack_cache
    _pack_cache = {}
    return load_all_packs()
