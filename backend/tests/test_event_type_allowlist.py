"""`event_type` is a closed vocabulary, and the graph classifies it positively.

Audit item 12. `_write_round_events` asked `if event_type not in
("comment", "react")` and treated everything else as a post — a **negative**
allow-list over a field that was an unconstrained `str` set independently in
twelve adapters. Discord already emitted a fourth value, `dm`, so the shape was
not hypothetical: a `dm` registered its own message id as a post, and any new
verb would have re-pointed a live parent at itself. The graph stays full, the
counters stay plausible, and every reply under that parent links to the wrong
event.

Two guards, because either alone leaves the hole open: the vocabulary is
constrained where events are *constructed*, and unrecognised values are refused
where they are *classified*.
"""
from __future__ import annotations

import inspect
import re
from datetime import UTC, datetime
from typing import get_args

import pytest
from pydantic import ValidationError

from app.services.platforms.base_adapter import (
    DIRECTED_EVENT_TYPES,
    KNOWN_EVENT_TYPES,
    POST_EVENT_TYPES,
    REPLY_EVENT_TYPES,
    EventType,
    SimulationEvent,
)
from app.services.platforms.registry import PLATFORM_REGISTRY, load_all_adapters
from app.workers import simulation_tasks

load_all_adapters()


def _event(**overrides) -> dict:
    return {
        "event_type": "post",
        "agent_id": "agent-1",
        "agent_username": "alice",
        "platform": "twitter_x",
        "round_number": 1,
        "variant": "a",
        "timestamp": datetime.now(UTC),
        **overrides,
    }


# ── The vocabulary ───────────────────────────────────────

def test_the_three_groups_are_exactly_the_vocabulary():
    """One definition, split three ways. Two lists that can disagree is the
    failure class this codebase produces most often."""
    assert POST_EVENT_TYPES | REPLY_EVENT_TYPES | DIRECTED_EVENT_TYPES == KNOWN_EVENT_TYPES
    assert set(get_args(EventType)) == KNOWN_EVENT_TYPES


def test_the_groups_do_not_overlap():
    """An event type in two groups would be both a parent and a child."""
    groups = (POST_EVENT_TYPES, REPLY_EVENT_TYPES, DIRECTED_EVENT_TYPES)
    assert sum(len(g) for g in groups) == len(KNOWN_EVENT_TYPES)


def test_the_persisted_values_are_unchanged():
    """These strings are stored in `simulation_events.event_type` and read by
    the analysis pipeline, the exporters and the comparison API. Renaming one
    silently reclassifies every historical run."""
    assert KNOWN_EVENT_TYPES == {"post", "comment", "react", "dm"}


def test_the_runner_reuses_the_adapter_vocabulary():
    """Not a second copy in the worker. The runner's own literal tuple is what
    made this a negative allow-list nobody could see was one."""
    assert simulation_tasks._KNOWN_EVENT_TYPES is KNOWN_EVENT_TYPES
    assert simulation_tasks._POST_EVENT_TYPES is POST_EVENT_TYPES


# ── The construction boundary ────────────────────────────

@pytest.mark.parametrize("event_type", sorted(KNOWN_EVENT_TYPES))
def test_every_known_event_type_is_accepted(event_type):
    assert SimulationEvent(**_event(event_type=event_type)).event_type == event_type


def test_an_unknown_event_type_is_refused_at_construction():
    """Loud at the adapter, not silently reclassified in the runner."""
    with pytest.raises(ValidationError):
        SimulationEvent(**_event(event_type="sneeze"))


def test_no_adapter_emits_a_type_outside_the_vocabulary():
    """The pydantic guard fires only on a code path that runs. This one reads
    all twelve adapters whether their branches are exercised or not."""
    emitted: set[str] = set()
    for cls in PLATFORM_REGISTRY.values():
        source = inspect.getsource(cls._decide_action)
        emitted.update(re.findall(r'event_type="([^"]+)"', source))
    assert emitted, "no event types found — the regex stopped matching"
    assert emitted <= KNOWN_EVENT_TYPES, f"undeclared event types: {emitted - KNOWN_EVENT_TYPES}"


# ── The classification boundary ──────────────────────────

class _FakeResult:
    def __init__(self, data):
        self.data = data


class _FakeTable:
    """Enough of the supabase table builder for `_write_round_events`."""

    def __init__(self, log):
        self._log = log
        self._op = None
        self._payload = None

    def insert(self, payload):
        self._op, self._payload = "insert", payload
        return self

    def update(self, patch):
        self._op, self._payload = "update", patch
        return self

    def in_(self, _column, values):
        self._log["updates"].append((self._payload, list(values)))
        return self

    def execute(self):
        if self._op == "insert":
            rows = [
                {"id": f"db-{self._log['n'] + i}"} for i in range(len(self._payload))
            ]
            self._log["n"] += len(self._payload)
            return _FakeResult(rows)
        return _FakeResult([])


class _FakeAdmin:
    def __init__(self):
        self.log = {"n": 0, "updates": []}

    def table(self, _name):
        return _FakeTable(self.log)


def _row(event_type: str, ref: str) -> dict:
    return {
        "event_type": event_type,
        "content": None,
        "_arena": ("twitter_x", "a"),
        "_ref": ref,
    }


def test_an_unknown_event_type_does_not_claim_a_post_ref():
    """The defect, exactly. Under the negative allow-list the unknown row took
    the post path and overwrote the real parent, so the comment below linked to
    the wrong event with nothing out of place anywhere."""
    admin = _FakeAdmin()
    post_event_ids: dict[tuple[str, str, str], str] = {}
    rows = [
        _row("post", "p1"),
        dict(_row("post", "p1"), event_type="sneeze"),
        _row("comment", "p1"),
    ]

    written, unresolved = simulation_tasks._write_round_events(admin, rows, post_event_ids)

    assert written == 3
    assert unresolved == 0
    assert post_event_ids == {("twitter_x", "a", "p1"): "db-0"}
    assert admin.log["updates"] == [({"target_event_id": "db-0"}, ["db-2"])]


def test_a_dm_neither_mints_a_parent_nor_claims_one():
    """`dm` is the value that was already in production while the allow-list was
    negative: its `target_id` is the message's own id, so registering it as a
    post put an id in the parent index that no reply can ever resolve to."""
    admin = _FakeAdmin()
    post_event_ids: dict[tuple[str, str, str], str] = {}

    written, unresolved = simulation_tasks._write_round_events(
        admin, [_row("dm", "dm1")], post_event_ids
    )

    assert written == 1
    assert unresolved == 0
    assert post_event_ids == {}


def test_a_reply_to_an_unregistered_ref_is_counted_not_absorbed():
    """A lookup miss and a legitimate absence must not be the same value."""
    admin = _FakeAdmin()
    post_event_ids: dict[tuple[str, str, str], str] = {}

    _written, unresolved = simulation_tasks._write_round_events(
        admin, [_row("react", "nothing-here")], post_event_ids
    )

    assert unresolved == 1


def test_a_decorated_ref_still_links_to_its_parent():
    """The 193-of-193 failure, at the runner boundary rather than the adapter's."""
    admin = _FakeAdmin()
    post_event_ids: dict[tuple[str, str, str], str] = {}

    simulation_tasks._write_round_events(
        admin, [_row("post", "p1"), _row("comment", "[p1]")], post_event_ids
    )

    assert admin.log["updates"] == [({"target_event_id": "db-0"}, ["db-1"])]


def test_the_runner_and_the_adapters_strip_the_same_decoration():
    """The strip set lived as a literal in two files and had already drifted by
    one character. One definition, or the failure returns silently."""
    from app.services.platforms.base_adapter import BasePlatformAdapter

    for raw in ("[a1b2c3]", "(a1b2c3)", "'a1b2c3',", "<a1b2c3>?", " a1b2c3 "):
        assert simulation_tasks._normalise_ref(raw) == BasePlatformAdapter.post_ref(raw)
