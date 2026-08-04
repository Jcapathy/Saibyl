"""The org pack library, and the tenancy boundary it puts weight on.

A pack id is a slug. `custom_persona_packs` and `persona_packs` both constrain
`UNIQUE(organization_id, pack_id)`, which is the schema saying out loud that a
pack id is unique only *within* an organization — so a lookup by pack id alone
has more than one correct answer, and the old one returned `result.data[0]`.
Same class as HANDOFF §1a's `username`: a key that is not an identity in the
space it is used in.

Nothing about that failure is visible at runtime. The run completes, the report
renders, and the agents are simply not the agents the founder configured — which
is why the tests below assert on *which org's* pack came back, not on whether a
pack came back.
"""
from __future__ import annotations

import copy
from datetime import datetime, timedelta

import pytest
from structlog.testing import capture_logs

from app.services.engine.personas import pack_loader, persona_store
from app.services.engine.personas.pack_loader import (
    ICP_PACK_PREFIX,
    PackLookupError,
    PersonaPack,
    get_pack,
    reload_packs,
)

BUILTIN_ID = "enterprise-it-buyer"


def _dt(value: str) -> datetime:
    return datetime.fromisoformat(str(value).replace("Z", "+00:00"))


# ---------------------------------------------------------------------------
# A supabase stand-in that actually applies `.eq()`
#
# A fake that ignores filters cannot fail the test this file exists for: the
# defect *was* a missing filter, so a stub that returns its canned rows
# regardless of `.eq("organization_id", …)` would pass against both the broken
# and the fixed implementation.
# ---------------------------------------------------------------------------

class _Result:
    def __init__(self, data):
        self.data = data


class _FakeTable:
    def __init__(self, store: dict[str, list[dict]], name: str, fail: str | None):
        self._store = store
        self._name = name
        self._fail = fail
        self._op = "select"
        self._filters: list[tuple[str, object]] = []
        self._contains: list[tuple[str, list]] = []
        self._in: list[tuple[str, list]] = []
        self._limit: int | None = None
        self._payload: dict | None = None

    # -- builder ---------------------------------------------------------
    def select(self, *_a, **_kw):
        self._op = "select"
        return self

    def eq(self, column, value):
        self._filters.append((column, value))
        return self

    def contains(self, column, value):
        self._contains.append((column, value))
        return self

    def in_(self, column, values):
        self._in.append((column, list(values)))
        return self

    def order(self, *_a, **_kw):
        return self

    def limit(self, n):
        self._limit = n
        return self

    def insert(self, payload):
        self._op = "insert"
        self._payload = payload
        return self

    def update(self, payload):
        self._op = "update"
        self._payload = payload
        return self

    def delete(self):
        self._op = "delete"
        return self

    # -- execution -------------------------------------------------------
    def _rows(self):
        return self._store.setdefault(self._name, [])

    def _matches(self, row) -> bool:
        if any(row.get(col) != val for col, val in self._filters):
            return False
        if any(row.get(col) not in allowed for col, allowed in self._in):
            return False
        return all(
            all(item in (row.get(col) or []) for item in wanted)
            for col, wanted in self._contains
        )

    def execute(self):
        if self._fail:
            raise RuntimeError(self._fail)

        rows = self._rows()
        if self._op == "insert":
            new = dict(self._payload)
            new.setdefault("id", f"row-{len(rows) + 1}")
            key = (new.get("organization_id"), new.get("pack_id"))
            if any((r.get("organization_id"), r.get("pack_id")) == key for r in rows):
                raise RuntimeError("duplicate key value violates unique constraint")
            rows.append(new)
            return _Result([copy.deepcopy(new)])

        selected = [r for r in rows if self._matches(r)]
        if self._limit is not None:
            selected = selected[: self._limit]

        if self._op == "update":
            for row in selected:
                row.update(self._payload)
            return _Result([copy.deepcopy(r) for r in selected])
        if self._op == "delete":
            for row in selected:
                rows.remove(row)
            return _Result([copy.deepcopy(r) for r in selected])
        return _Result([copy.deepcopy(r) for r in selected])


class _FakeAdmin:
    def __init__(self, store, fail=None):
        self.store = store
        self.fail = fail

    def table(self, name):
        return _FakeTable(self.store, name, self.fail)


@pytest.fixture
def store(monkeypatch):
    """An empty database, wired into every lazy `get_supabase_admin()` import."""
    import app.core.database as database

    data: dict[str, list[dict]] = {}
    monkeypatch.setattr(database, "get_supabase_admin", lambda: _FakeAdmin(data))
    reload_packs()
    return data


def _pack(pack_id: str = "smb-buyers", name: str = "SMB Buyers") -> PersonaPack:
    """A minimal but real PersonaPack, built off a built-in so it validates."""
    data = copy.deepcopy(pack_loader.get_pack(BUILTIN_ID).model_dump())
    data["id"] = pack_id
    data["name"] = name
    return PersonaPack.model_validate(data)


# ---------------------------------------------------------------------------
# The boundary
# ---------------------------------------------------------------------------

def test_a_pack_saved_by_one_org_cannot_be_loaded_by_another(store):
    """The whole risk of the library, in one assertion.

    Both orgs use the slug `smb-buyers`, which is exactly what the library makes
    normal. Org B asking for it must get *its own* pack, never org A's.
    """
    persona_store.save_org_pack("org-a", _pack(name="A's buyers"), None)
    persona_store.save_org_pack("org-b", _pack(name="B's buyers"), None)

    assert get_pack("smb-buyers", "org-a").name == "A's buyers"
    assert get_pack("smb-buyers", "org-b").name == "B's buyers"


def test_an_orgs_pack_is_unresolvable_from_an_org_that_does_not_own_it(store):
    persona_store.save_org_pack("org-a", _pack(pack_id="org-a-only"), None)

    assert get_pack("org-a-only", "org-a").id == "org-a-only"
    with pytest.raises(KeyError):
        get_pack("org-a-only", "org-b")


def test_an_identity_free_lookup_cannot_reach_a_tenant_pack(store):
    """`get_pack(pack_id)` with no org resolves built-ins and nothing else.

    Fail-closed is the structural half of the fix: a caller that never proved
    which organization it is acting for cannot be served tenant data by
    forgetting an argument. Threading org through every call site is the other
    half, and conventions get forgotten.
    """
    persona_store.save_org_pack("org-a", _pack(pack_id="org-a-only"), None)

    with pytest.raises(KeyError):
        get_pack("org-a-only")
    # Built-ins are files, globally unique, and stay reachable without an org —
    # `icp_synthesizer._prior_archetype` resolves its priors this way.
    assert get_pack(BUILTIN_ID).name == "Enterprise IT Buyer"


def test_a_custom_pack_lookup_is_scoped_to_its_org(store):
    """`custom_persona_packs` carries the same constraint and had the same hole."""
    for org, name in (("org-a", "A custom"), ("org-b", "B custom")):
        pack = _pack(pack_id="shared-slug", name=name)
        store.setdefault("custom_persona_packs", []).append({
            "organization_id": org,
            "pack_id": "shared-slug",
            "pack_data": pack.model_dump(mode="json"),
        })

    assert get_pack("shared-slug", "org-a").name == "A custom"
    assert get_pack("shared-slug", "org-b").name == "B custom"
    with pytest.raises(KeyError):
        get_pack("shared-slug", "org-c")


def test_an_icp_pack_is_scoped_to_its_org(store):
    """`icp_profiles.pack_id` is globally unique, which is not authorisation."""
    pack_id = f"{ICP_PACK_PREFIX}deadbeef"
    store["icp_profiles"] = [{
        "organization_id": "org-a",
        "pack_id": pack_id,
        "pack_data": _pack(pack_id=pack_id).model_dump(mode="json"),
    }]

    assert get_pack(pack_id, "org-a").id == pack_id
    with pytest.raises(KeyError):
        get_pack(pack_id, "org-b")


# ---------------------------------------------------------------------------
# Built-ins are a shared global and stay one
# ---------------------------------------------------------------------------

def test_an_org_pack_cannot_be_saved_under_a_builtin_id(store):
    """The built-in wins, and the library entry gets an id it can be served under.

    Storing it under the built-in's id would write a row that is never readable —
    `get_pack` checks `_pack_cache` first — so the founder's pack would exist in
    the product and never run.
    """
    pack_id = persona_store.save_org_pack("org-a", _pack(pack_id=BUILTIN_ID), None)

    assert pack_id != BUILTIN_ID
    assert get_pack(BUILTIN_ID, "org-a").name == "Enterprise IT Buyer"
    assert get_pack(pack_id, "org-a").id == pack_id


def test_a_shadowing_row_written_around_the_store_is_never_served(store):
    """Belt and braces: a direct DB write cannot displace a built-in either."""
    shadow = _pack(pack_id=BUILTIN_ID, name="Hijacked").model_dump(mode="json")
    store["persona_packs"] = [{
        "id": "row-1",
        "organization_id": "org-a",
        "pack_id": BUILTIN_ID,
        "pack_data": shadow,
    }]

    with capture_logs() as logs:
        assert persona_store.load_org_packs("org-a") == []
    assert "org_pack_shadows_builtin" in {entry["event"] for entry in logs}
    assert get_pack(BUILTIN_ID, "org-a").name == "Enterprise IT Buyer"


# ---------------------------------------------------------------------------
# Promotion
# ---------------------------------------------------------------------------

def test_promoting_reslugs_off_the_icp_prefix(store):
    """`icp_<hex>` means "look me up in icp_profiles" and must not be reused."""
    pack_id = persona_store.save_org_pack(
        "org-a", _pack(pack_id=f"{ICP_PACK_PREFIX}abc", name="Design Leads"), "profile-1"
    )

    assert not pack_id.startswith(ICP_PACK_PREFIX)
    assert pack_id == "design-leads"
    assert get_pack(pack_id, "org-a").id == pack_id


def test_the_stored_body_always_carries_the_stored_id(store):
    """Two sources of truth for one value is the §2a class this avoids."""
    pack_id = persona_store.save_org_pack(
        "org-a", _pack(pack_id=f"{ICP_PACK_PREFIX}abc", name="Design Leads"), "profile-1"
    )
    row = store["persona_packs"][0]

    assert row["pack_id"] == pack_id
    assert row["pack_data"]["id"] == pack_id


def test_repromoting_one_profile_refreshes_in_place(store):
    """An explicit re-promote may move a library pack; an ICP edit may not.

    Keeping the id stable matters because `simulations.persona_pack_ids` stores
    it with no foreign key, so a new id on every re-promote would strand every
    existing reference.
    """
    first = persona_store.save_org_pack("org-a", _pack(name="Design Leads"), "profile-1")
    second = persona_store.save_org_pack("org-a", _pack(name="Design Leads v2"), "profile-1")

    assert first == second
    assert len(store["persona_packs"]) == 1
    assert get_pack(first, "org-a").name == "Design Leads v2"


def test_two_profiles_with_the_same_name_get_distinct_ids(store):
    """Two ICPs called "Buyers" both re-slug to `buyers`, and both must land."""
    a = persona_store.save_org_pack(
        "org-a", _pack(pack_id=f"{ICP_PACK_PREFIX}aaa", name="Buyers"), "profile-1"
    )
    b = persona_store.save_org_pack(
        "org-a", _pack(pack_id=f"{ICP_PACK_PREFIX}bbb", name="Buyers"), "profile-2"
    )

    assert {a, b} == {"buyers", "buyers-2"}
    assert get_pack("buyers", "org-a").name == "Buyers"
    assert get_pack("buyers-2", "org-a").name == "Buyers"


def test_a_handmade_pack_that_collides_is_refused_not_renamed(store):
    """No provenance to match on, so silently making it `…-2` would lose work."""
    persona_store.save_org_pack("org-a", _pack(pack_id="buyers"), None)

    with pytest.raises(persona_store.PackIdConflictError):
        persona_store.save_org_pack("org-a", _pack(pack_id="buyers"), None)


def test_renaming_does_not_move_the_pack_id(store):
    pack_id = persona_store.save_org_pack("org-a", _pack(pack_id="buyers"), None)
    persona_store.rename_org_pack("org-a", pack_id, "Enterprise Buyers")

    row = store["persona_packs"][0]
    assert row["pack_id"] == pack_id
    assert row["name"] == "Enterprise Buyers"
    # The name the agent-generation prompt reads moves with it.
    assert row["pack_data"]["name"] == "Enterprise Buyers"


def test_renaming_another_orgs_pack_does_nothing(store):
    persona_store.save_org_pack("org-a", _pack(pack_id="buyers"), None)

    assert persona_store.rename_org_pack("org-b", "buyers", "Stolen") is None
    assert store["persona_packs"][0]["name"] == "SMB Buyers"


def test_deleting_another_orgs_pack_does_nothing(store):
    persona_store.save_org_pack("org-a", _pack(pack_id="buyers"), None)

    assert persona_store.delete_org_pack("org-b", "buyers") is False
    assert persona_store.delete_org_pack("org-a", "buyers") is True
    assert store["persona_packs"] == []


# ---------------------------------------------------------------------------
# A miss and a failure are different answers
# ---------------------------------------------------------------------------

def test_a_store_failure_is_not_reported_as_a_missing_pack(monkeypatch):
    """`run_prepare_agents` skips a KeyError and runs with what it found.

    That is right for a pack the founder deleted and catastrophic for a database
    blip: the run would complete against a silently reduced audience. So an
    unreachable store raises `PackLookupError`, which nothing catches.
    """
    import app.core.database as database

    monkeypatch.setattr(
        database, "get_supabase_admin", lambda: _FakeAdmin({}, fail="connection reset")
    )
    reload_packs()

    with pytest.raises(PackLookupError):
        get_pack("some-org-pack", "org-a")


def test_an_unapplied_migration_degrades_the_library_and_says_so(monkeypatch):
    """026 is applied by hand, so code can serve before the table exists.

    Treated as an empty library rather than a hard failure — the library is
    checked before custom packs, so raising here would break `get_pack` for every
    custom pack in the product. It is logged at ERROR and matched on one
    condition only; every other failure still raises.
    """
    import app.core.database as database

    monkeypatch.setattr(
        database,
        "get_supabase_admin",
        lambda: _FakeAdmin({}, fail='relation "public.persona_packs" does not exist'),
    )
    reload_packs()

    with capture_logs() as logs:
        assert persona_store.load_org_packs("org-a") == []
    assert "persona_pack_library_table_missing" in {entry["event"] for entry in logs}


# ---------------------------------------------------------------------------
# Listing
# ---------------------------------------------------------------------------

def test_listing_without_an_org_is_builtins_only(store):
    persona_store.save_org_pack("org-a", _pack(pack_id="buyers"), None)

    ids = {s.id for s in pack_loader.list_available_packs()}
    assert "buyers" not in ids
    assert BUILTIN_ID in ids


def test_listing_for_an_org_includes_only_that_orgs_library(store):
    persona_store.save_org_pack("org-a", _pack(pack_id="a-buyers"), None)
    persona_store.save_org_pack("org-b", _pack(pack_id="b-buyers"), None)

    ids = {s.id for s in pack_loader.list_available_packs(org_id="org-a")}
    assert "a-buyers" in ids
    assert "b-buyers" not in ids


# ---------------------------------------------------------------------------
# The snapshot, and the drift it is allowed to have
# ---------------------------------------------------------------------------

def test_editing_the_source_icp_does_not_change_the_promoted_pack(store):
    """A promoted pack is frozen; the ICP's own pack is what recompiles.

    A run configured against a library pack must keep the audience it was
    configured with. The cost of that is drift, which is why the drift is
    reported rather than hidden.
    """
    store["icp_profiles"] = [{
        "id": "profile-1",
        "organization_id": "org-a",
        "pack_id": f"{ICP_PACK_PREFIX}aaa",
        "pack_data": _pack(pack_id=f"{ICP_PACK_PREFIX}aaa", name="Before").model_dump(mode="json"),
        "updated_at": "2026-08-01T00:00:00+00:00",
    }]
    pack_id = persona_store.save_org_pack(
        "org-a", _pack(pack_id=f"{ICP_PACK_PREFIX}aaa", name="Before"), "profile-1"
    )

    # The founder edits the ICP: `PATCH /api/icp/{id}` rewrites this row's own
    # pack_data and bumps updated_at. Nothing touches the library. The bump is
    # taken from the snapshot's own timestamp rather than a literal, so the test
    # does not quietly start passing or failing as the wall clock moves past a
    # hardcoded date.
    profile = store["icp_profiles"][0]
    synced = _dt(store["persona_packs"][0]["source_synced_at"])
    profile["pack_data"]["name"] = "After"
    profile["updated_at"] = (synced + timedelta(seconds=1)).isoformat()

    assert get_pack(pack_id, "org-a").name == "Before"
    assert get_pack(f"{ICP_PACK_PREFIX}aaa", "org-a").name == "After"

    promotions = persona_store.promotions_of_profile("org-a", "profile-1")
    assert [p["source_stale"] for p in promotions] == [True]


def test_a_pack_with_no_source_reports_unknown_staleness_not_fresh(store):
    """`None`, never `False`: no provenance is not the same as up to date."""
    persona_store.save_org_pack("org-a", _pack(pack_id="handmade"), None)
    rows = persona_store.attach_staleness("org-a", persona_store.list_org_pack_rows("org-a"))

    assert rows[0]["source_stale"] is None


def test_the_library_row_reports_what_the_founder_is_deleting(store):
    pack_id = persona_store.save_org_pack("org-a", _pack(pack_id="buyers"), None)
    store["simulations"] = [
        {"id": "sim-1", "organization_id": "org-a", "persona_pack_ids": [pack_id]},
        {"id": "sim-2", "organization_id": "org-a", "persona_pack_ids": ["other"]},
        {"id": "sim-3", "organization_id": "org-b", "persona_pack_ids": [pack_id]},
    ]

    assert persona_store.simulation_ids_using_pack("org-a", pack_id) == ["sim-1"]
