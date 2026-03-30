# PUBLIC INTERFACE
# ─────────────────────────────────────────────────────────
# load_all_packs() -> list[PersonaPack]
# get_pack(pack_id: str) -> PersonaPack
# list_available_packs() -> list[PackSummary]
# ─────────────────────────────────────────────────────────
from __future__ import annotations

import json
from pathlib import Path

import structlog
from pydantic import BaseModel

logger = structlog.get_logger()

PACKS_DIR = Path(__file__).resolve().parents[4] / "data" / "persona_packs"

# In-memory cache
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
    """Load all persona packs from disk into memory cache."""
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
    """Get a specific persona pack by ID (built-in or custom)."""
    if not _pack_cache:
        load_all_packs()
    if pack_id in _pack_cache:
        return _pack_cache[pack_id]
    # Check custom packs in DB
    pack = _load_custom_pack(pack_id)
    if pack:
        return pack
    raise KeyError(f"Persona pack '{pack_id}' not found")


def _load_custom_pack(pack_id: str) -> PersonaPack | None:
    """Load a single custom pack from DB by pack_id."""
    try:
        from app.core.database import get_supabase_admin
        admin = get_supabase_admin()
        result = admin.table("custom_persona_packs").select("pack_data").eq("pack_id", pack_id).execute()
        if result.data:
            pack = PersonaPack.model_validate(result.data[0]["pack_data"])
            _pack_cache[pack.id] = pack
            return pack
    except Exception as e:
        logger.warning("custom_pack_load_failed", pack_id=pack_id, error=str(e))
    return None


def load_custom_packs_for_org(org_id: str) -> list[PersonaPack]:
    """Load all custom packs for an organization from DB."""
    try:
        from app.core.database import get_supabase_admin
        admin = get_supabase_admin()
        result = admin.table("custom_persona_packs").select("pack_data").eq("organization_id", org_id).execute()
        packs = []
        for row in result.data:
            try:
                pack = PersonaPack.model_validate(row["pack_data"])
                _pack_cache[pack.id] = pack
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
