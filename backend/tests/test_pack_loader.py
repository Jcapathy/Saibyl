import copy
from pathlib import Path

import pytest

from app.services.engine.personas import pack_loader
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
    with pytest.raises(KeyError):
        get_pack("nonexistent-pack")


# ---------------------------------------------------------------------------
# The cache is process-global and the packs in it are not
#
# `_pack_cache` is shared by every organization a worker serves. A tenant pack
# written into it does not merely leak — it *replaces* a built-in for every
# other tenant, and nothing errors: the run completes, the report renders, and
# the agents are simply not the agents the founder configured.
# ---------------------------------------------------------------------------

class _Result:
    def __init__(self, data):
        self.data = data


class _Query:
    """Enough of the supabase builder to serve one canned row set."""

    def __init__(self, data):
        self._data = data

    def select(self, *_a, **_kw):
        return self

    def eq(self, *_a, **_kw):
        return self

    def limit(self, *_a, **_kw):
        return self

    def execute(self):
        return _Result(self._data)


def _fake_admin(rows, monkeypatch):
    class _Admin:
        def table(self, _name):
            return _Query(rows)

    import app.core.database as database

    monkeypatch.setattr(database, "get_supabase_admin", lambda: _Admin())


def _clone_of_a_builtin() -> dict:
    """A tenant pack claiming a built-in's id, with different contents."""
    builtin = get_pack("enterprise-it-buyer")
    data = copy.deepcopy(builtin.model_dump())
    data["name"] = "Hijacked"
    data["archetypes"] = data["archetypes"][:2]
    for i, archetype in enumerate(data["archetypes"]):
        archetype["weight"] = 0.5
        archetype["personality"]["big5"] = {k: 0.99 for k in archetype["personality"]["big5"]}
        archetype["label"] = f"Hijacked {i}"
    return data


def _captured_log(monkeypatch) -> list[tuple[str, str]]:
    """Records (level, event) off the module's structlog logger.

    Not `capsys`: structlog writes through a logger bound at configuration time,
    so whether stdout capture sees it depends on what else has run first.
    """
    captured: list[tuple[str, str]] = []

    class _Logger:
        def __getattr__(self, level):
            def record(event, **_kw):
                captured.append((level, event))
            return record

    monkeypatch.setattr(pack_loader, "logger", _Logger())
    return captured


def test_a_custom_pack_cannot_overwrite_a_builtin_for_every_tenant(monkeypatch):
    """The cross-tenant one. Built-in wins, and the collision is reported.

    Silently serving the built-in would swap one lookup miss for another: the
    tenant's pack would simply never run, which is the same
    absence-indistinguishable-from-miss shape as the overwrite.
    """
    reload_packs()
    original = get_pack("enterprise-it-buyer")
    _fake_admin([{"pack_data": _clone_of_a_builtin()}], monkeypatch)
    captured = _captured_log(monkeypatch)

    packs = pack_loader.load_custom_packs_for_org("org-a")

    assert packs == [], "a tenant pack claiming a built-in id was served"
    assert ("error", "custom_pack_shadows_builtin") in captured
    # And the built-in every other organization sees is untouched.
    assert get_pack("enterprise-it-buyer").name == original.name
    assert len(get_pack("enterprise-it-buyer").archetypes) == len(original.archetypes)


def test_get_pack_never_serves_a_shadowing_custom_pack(monkeypatch):
    reload_packs()
    _fake_admin([{"pack_data": _clone_of_a_builtin()}], monkeypatch)

    assert get_pack("enterprise-it-buyer", "org-a").name == "Enterprise IT Buyer"
    assert pack_loader._load_custom_pack("enterprise-it-buyer", "org-a") is None


def test_a_custom_pack_is_never_written_into_the_process_cache(monkeypatch):
    """One organization's audience must not be served to the next caller.

    `get_pack` checks `_pack_cache` first, so a cached tenant pack is returned
    to every subsequent request for that id regardless of who is asking.
    """
    reload_packs()
    builtin_ids = set(pack_loader._pack_cache)
    custom = _clone_of_a_builtin()
    custom["id"] = "org-a-private-pack"
    _fake_admin([{"pack_data": custom}], monkeypatch)

    served = pack_loader._load_custom_pack("org-a-private-pack", "org-a")
    assert served is not None and served.id == "org-a-private-pack"
    assert set(pack_loader._pack_cache) == builtin_ids

    pack_loader.load_custom_packs_for_org("org-a")
    assert set(pack_loader._pack_cache) == builtin_ids


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
