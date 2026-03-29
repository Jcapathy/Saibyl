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
    """Get a specific persona pack by ID."""
    if not _pack_cache:
        load_all_packs()
    if pack_id not in _pack_cache:
        raise KeyError(f"Persona pack '{pack_id}' not found")
    return _pack_cache[pack_id]


def list_available_packs() -> list[PackSummary]:
    """List all available packs with summary info."""
    if not _pack_cache:
        load_all_packs()
    return [
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


def reload_packs() -> list[PersonaPack]:
    """Force reload all packs from disk."""
    global _pack_cache
    _pack_cache = {}
    return load_all_packs()
