from pathlib import Path

from app.services.engine.personas.pack_loader import (
    get_pack,
    list_available_packs,
    reload_packs,
)

PACK_DIR = Path(__file__).resolve().parents[1] / "data" / "persona_packs"


def _pack_files_on_disk() -> list[Path]:
    return sorted(PACK_DIR.glob("*.json"))


def test_load_all_packs_matches_files_on_disk():
    """Pack count is derived from disk so adding a pack doesn't break the suite."""
    packs = reload_packs()
    assert len(packs) == len(_pack_files_on_disk())
    assert len(packs) > 0


def test_each_pack_has_archetypes():
    packs = reload_packs()
    for pack in packs:
        assert len(pack.archetypes) >= 2, f"Pack {pack.id} has fewer than 2 archetypes"


def test_archetype_weights_sum_to_one():
    packs = reload_packs()
    for pack in packs:
        total = sum(a.weight for a in pack.archetypes)
        assert 0.95 <= total <= 1.05, f"Pack {pack.id} weights sum to {total}"


def test_get_pack_by_id():
    reload_packs()
    pack = get_pack("enterprise-it-buyer")
    assert pack.name == "Enterprise IT Buyer"
    assert pack.category == "professional"


def test_get_pack_unknown_raises():
    reload_packs()
    import pytest
    with pytest.raises(KeyError):
        get_pack("nonexistent-pack")


def test_list_available_packs_returns_summaries():
    reload_packs()
    summaries = list_available_packs()
    assert len(summaries) == len(_pack_files_on_disk())
    for s in summaries:
        assert s.id
        assert s.name
        assert s.archetype_count >= 2
        assert len(s.archetype_labels) == s.archetype_count


def test_pack_has_required_fields():
    packs = reload_packs()
    for pack in packs:
        assert pack.id
        assert pack.name
        assert pack.version
        assert pack.category
        assert pack.description
        for arch in pack.archetypes:
            assert arch.id
            assert arch.label
            assert arch.demographics
            assert arch.personality
            assert arch.personality.mbti_pool
            assert arch.behavior_traits
            assert arch.interests
