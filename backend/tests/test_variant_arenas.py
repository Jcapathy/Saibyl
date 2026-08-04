"""N-way matched swarms: the arenas, and the propagation graph they write.

Two things here are load-bearing and neither is visible in a run that looks
fine. **Arena isolation** — if two variants share a feed, the scoreboard still
renders, still has confidence intervals, and measures a conversation the
variants were all in together. **Arena-scoped graph keys** — adapter post ids
are unique only inside the instance that minted them, so a global map would
link variant B's comment to variant A's post and inflate exactly the cascade
metric the virality score weights.
"""
from __future__ import annotations

from app.services.engine.variants import DEFAULT_VARIANT_KEY, Arena, load_arenas
from app.workers.simulation_tasks import _write_round_events

# ── A fake admin client, matching the two call chains the writer uses ──

class _Result:
    def __init__(self, data):
        self.data = data


class _Insert:
    def __init__(self, store, payload):
        self._store, self._payload = store, payload

    def execute(self):
        saved = []
        for row in self._payload:
            row_id = f"db-{len(self._store['rows'])}"
            stored = {**row, "id": row_id}
            self._store["rows"].append(stored)
            saved.append(stored)
        return _Result(saved)


class _Update:
    def __init__(self, store, patch):
        self._store, self._patch = store, patch

    def in_(self, _column, ids):
        self._ids = ids
        return self

    def execute(self):
        for row in self._store["rows"]:
            if row["id"] in self._ids:
                row.update(self._patch)
        return _Result([])


class _Table:
    def __init__(self, store):
        self._store = store

    def insert(self, payload):
        return _Insert(self._store, payload)

    def update(self, patch):
        return _Update(self._store, patch)


class _Admin:
    def __init__(self):
        self.store = {"rows": []}

    def table(self, _name):
        return _Table(self.store)


def _event(event_type, arena, ref, content="x"):
    return {
        "simulation_id": "sim",
        "organization_id": "org",
        "event_type": event_type,
        "agent_id": "agent",
        "platform": arena[0],
        "variant": arena[1],
        "round_number": 1,
        "content": content,
        "metadata": {},
        "_arena": arena,
        "_ref": ref,
    }


# ── The graph ────────────────────────────────────────────

def test_a_post_is_not_its_own_parent():
    """A post's `target_id` is the id it just minted, not something above it."""
    admin, seen = _Admin(), {}
    written, unresolved = _write_round_events(
        admin, [_event("post", ("reddit", "a"), "post_1")], seen
    )

    assert (written, unresolved) == (1, 0)
    assert admin.store["rows"][0].get("target_event_id") is None
    assert seen[("reddit", "a", "post_1")] == "db-0"


def test_a_comment_links_to_the_post_it_replies_to():
    admin, seen = _Admin(), {}
    _write_round_events(admin, [_event("post", ("reddit", "a"), "post_1")], seen)
    _write_round_events(admin, [_event("comment", ("reddit", "a"), "post_1")], seen)

    parent, child = admin.store["rows"]
    assert child["target_event_id"] == parent["id"]


def test_reactions_link_too():
    admin, seen = _Admin(), {}
    _write_round_events(
        admin,
        [
            _event("post", ("reddit", "a"), "post_1"),
            _event("react", ("reddit", "a"), "post_1", content=None),
        ],
        seen,
    )
    assert admin.store["rows"][1]["target_event_id"] == admin.store["rows"][0]["id"]


def test_an_arena_cannot_link_to_another_arenas_post():
    """The defect this keying exists to prevent.

    Both arenas mint a "post_1" because each has its own adapter instance
    counting from zero. A map keyed on the bare id would attach variant B's
    comment to variant A's post — silently merging two isolated conversations
    into one cascade and inflating the metric virality weights most heavily.
    """
    admin, seen = _Admin(), {}
    _write_round_events(admin, [_event("post", ("reddit", "a"), "post_1")], seen)
    _, unresolved = _write_round_events(
        admin, [_event("comment", ("reddit", "b"), "post_1")], seen
    )

    assert unresolved == 1
    assert admin.store["rows"][1].get("target_event_id") is None


def test_the_same_arena_on_two_platforms_stays_separate():
    admin, seen = _Admin(), {}
    _write_round_events(admin, [_event("post", ("reddit", "a"), "post_1")], seen)
    _, unresolved = _write_round_events(
        admin, [_event("comment", ("linkedin", "a"), "post_1")], seen
    )

    assert unresolved == 1


def test_a_reply_to_a_post_from_an_earlier_round_still_links():
    """The map spans the run. A round-4 comment routinely answers a round-1 post."""
    admin, seen = _Admin(), {}
    _write_round_events(admin, [_event("post", ("reddit", "a"), "post_1")], seen)
    for _ in range(3):
        _write_round_events(admin, [_event("post", ("reddit", "a"), "post_9")], seen)
    _, unresolved = _write_round_events(
        admin, [_event("comment", ("reddit", "a"), "post_1")], seen
    )

    assert unresolved == 0
    assert admin.store["rows"][-1]["target_event_id"] == "db-0"


def test_events_are_written_even_when_nothing_links():
    """Losing an edge must never cost the event. The event is the measurement."""
    admin, seen = _Admin(), {}
    written, unresolved = _write_round_events(
        admin,
        [
            _event("comment", ("reddit", "a"), "post_404"),
            _event("post", ("reddit", "a"), None),
        ],
        seen,
    )

    assert written == 2
    assert unresolved == 1


def test_transient_keys_never_reach_the_database():
    admin, seen = _Admin(), {}
    _write_round_events(admin, [_event("post", ("reddit", "a"), "post_1")], seen)

    stored = admin.store["rows"][0]
    assert "_arena" not in stored and "_ref" not in stored


# ── The arenas ───────────────────────────────────────────

def test_a_run_with_no_variants_gets_one_default_arena(monkeypatch):
    """Never an empty list: a run with no arena completes with zero events and
    no error, which is Phase 1's cold-start deadlock in a new place."""
    monkeypatch.setattr(
        "app.services.engine.variants.get_supabase_admin",
        lambda: (_ for _ in ()).throw(RuntimeError("no db in tests")),
    )
    arenas = load_arenas("sim", "Our new pricing")

    assert len(arenas) == 1
    assert arenas[0].variant_key == DEFAULT_VARIANT_KEY
    assert arenas[0].content == "Our new pricing"
    assert arenas[0].is_default


def test_a_variant_falls_back_to_the_run_subject_when_its_body_is_empty():
    """An empty arena would be scored against the others as a real alternative."""
    arena = Arena(variant_key="b", label="Empty", content="")
    assert arena.content == ""  # the model itself does not guess

    # load_arenas is where the fallback lives, because only it knows the subject.
    from app.services.engine import variants as mod

    class _Fake:
        def table(self, _n): return self
        def select(self, _c): return self
        def eq(self, *_a): return self
        def order(self, *_a): return self
        def execute(self):
            return type("R", (), {"data": [
                {"variant_key": "b", "label": "Empty", "content": "  ", "position": 0},
            ]})()

    original = mod.get_supabase_admin
    mod.get_supabase_admin = lambda: _Fake()
    try:
        loaded = load_arenas("sim", "Our new pricing")
    finally:
        mod.get_supabase_admin = original

    assert loaded[0].content == "Our new pricing"
