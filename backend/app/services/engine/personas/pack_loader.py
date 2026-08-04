# PUBLIC INTERFACE
# ─────────────────────────────────────────────────────────
# load_all_packs() -> list[PersonaPack]
# get_pack(pack_id: str) -> PersonaPack
# list_available_packs() -> list[PackSummary]
# Archetype, ArchetypeContext, PersonaPack, Demographics, Personality,
# BehaviorTraits, ICP_PACK_PREFIX
# ─────────────────────────────────────────────────────────
from __future__ import annotations

import json
from pathlib import Path

import structlog
from pydantic import BaseModel, Field

logger = structlog.get_logger()

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


def get_pack(pack_id: str) -> PersonaPack:
    """Get a specific persona pack by ID (built-in, custom, or compiled ICP).

    Built-ins are checked first and are the only cached tier, so a tenant pack
    can never displace one. Custom and ICP packs cost a query per call, which is
    the price of not serving one organization's audience to another.
    """
    if not _pack_cache:
        load_all_packs()
    if pack_id in _pack_cache:
        return _pack_cache[pack_id]
    if pack_id.startswith(ICP_PACK_PREFIX):
        pack = _load_icp_pack(pack_id)
        if pack:
            return pack
        raise KeyError(f"ICP profile '{pack_id}' not found")
    # Check custom packs in DB
    pack = _load_custom_pack(pack_id)
    if pack:
        return pack
    raise KeyError(f"Persona pack '{pack_id}' not found")


def _load_icp_pack(pack_id: str) -> PersonaPack | None:
    """Load a compiled ICP pack from `icp_profiles`.

    Deliberately not cached in `_pack_cache`: a founder can edit their ICP
    between runs, and a process-lifetime cache would serve the pre-edit audience
    to whichever API worker happened to have loaded it first. Built-in packs are
    files and cannot change under a running process; this one can.
    """
    try:
        from app.core.database import get_supabase_admin
        admin = get_supabase_admin()
        result = (
            admin.table("icp_profiles")
            .select("pack_data")
            .eq("pack_id", pack_id)
            .limit(1)
            .execute()
        )
        if result.data:
            return PersonaPack.model_validate(result.data[0]["pack_data"])
    except Exception as e:
        logger.warning("icp_pack_load_failed", pack_id=pack_id, error=str(e))
    return None


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


def _load_custom_pack(pack_id: str) -> PersonaPack | None:
    """Load a single custom pack from DB by pack_id.

    Not cached: `_pack_cache` is process-global and this row is tenant-owned.
    See the cache's own comment for what caching it did.
    """
    try:
        from app.core.database import get_supabase_admin
        admin = get_supabase_admin()
        result = admin.table("custom_persona_packs").select("pack_data").eq("pack_id", pack_id).execute()
        if result.data:
            pack = PersonaPack.model_validate(result.data[0]["pack_data"])
            if _shadows_builtin(pack):
                return None
            return pack
    except Exception as e:
        logger.warning("custom_pack_load_failed", pack_id=pack_id, error=str(e))
    return None


def load_custom_packs_for_org(org_id: str) -> list[PersonaPack]:
    """Load all custom packs for an organization from DB.

    Not cached, for the same reason as `_load_custom_pack`: these rows belong to
    one organization and `_pack_cache` belongs to the process.
    """
    try:
        from app.core.database import get_supabase_admin
        admin = get_supabase_admin()
        result = admin.table("custom_persona_packs").select("pack_data").eq("organization_id", org_id).execute()
        packs = []
        for row in result.data:
            try:
                pack = PersonaPack.model_validate(row["pack_data"])
                if _shadows_builtin(pack, org_id):
                    continue
                packs.append(pack)
            except Exception as e:
                logger.warning("custom_pack_parse_failed", error=str(e))
        return packs
    except Exception as e:
        logger.warning("custom_packs_load_failed", org_id=org_id, error=str(e))
        return []


def list_available_packs(org_id: str | None = None) -> list[PackSummary]:
    """List all available packs (built-in + custom for org)."""
    if not _pack_cache:
        load_all_packs()

    summaries = [
        PackSummary(
            id=p.id,
            name=p.name,
            category=p.category,
            description=p.description,
            archetype_count=len(p.archetypes),
            archetype_labels=[a.label for a in p.archetypes],
        )
        for p in _pack_cache.values()
    ]

    # Include custom packs from DB if org_id provided
    if org_id:
        custom = load_custom_packs_for_org(org_id)
        existing_ids = {s.id for s in summaries}
        for p in custom:
            if p.id not in existing_ids:
                summaries.append(PackSummary(
                    id=p.id,
                    name=p.name,
                    category=p.category,
                    description=p.description,
                    archetype_count=len(p.archetypes),
                    archetype_labels=[a.label for a in p.archetypes],
                ))

    return summaries


def reload_packs() -> list[PersonaPack]:
    """Force reload all packs from disk."""
    global _pack_cache
    _pack_cache = {}
    return load_all_packs()
