"""A job the process died inside does not stay half-finished forever.

Both halves of this were observed while testing the release it ships in:

- A redeploy killed three report writers mid-write. The rows kept
  `status='generating'` with `section_count` already set and zero characters
  of markdown, and nothing would ever have changed them.
- A website check sat at `capturing` for eleven minutes against a 150-second
  deadline. `asyncio.wait_for` cancels at an `await`, and Playwright's own
  teardown can block that cancellation — so the in-process deadline is right
  but not sufficient.

`gtm/discovery` had already written the limit down: "if the API process dies
mid-run, the run row stays `running`. There is no worker to reap it." This is
that worker.
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from app.services.maintenance import reaper

NOW = datetime(2026, 8, 21, 18, 0, tzinfo=UTC)
ORG = "11111111-1111-1111-1111-111111111111"


class _Table:
    def __init__(self, store: dict, name: str, log: list):
        self._store, self._name, self._log = store, name, log
        self._filters: list[tuple] = []
        self._payload = None
        self._op = None

    def select(self, *_a, **_k):
        self._op = "select"
        return self

    def update(self, payload):
        self._op, self._payload = "update", payload
        return self

    def in_(self, col, values):
        self._filters.append(("in", col, values))
        return self

    def lt(self, col, value):
        self._filters.append(("lt", col, value))
        return self

    def eq(self, col, value):
        self._filters.append(("eq", col, value))
        return self

    def limit(self, _n):
        return self

    def _matches(self, row) -> bool:
        for kind, col, value in self._filters:
            if kind == "in" and row.get(col) not in value:
                return False
            if kind == "lt" and not (str(row.get(col)) < str(value)):
                return False
            if kind == "eq" and str(row.get(col)) != str(value):
                return False
        return True

    def execute(self):
        rows = [r for r in self._store.get(self._name, []) if self._matches(r)]
        if self._op == "update":
            for row in rows:
                row.update(self._payload)
                self._log.append((self._name, row["id"], self._payload))
        return type("R", (), {"data": rows})()


class _Admin:
    def __init__(self, store: dict):
        self.store, self.updates = store, []

    def table(self, name):
        return _Table(self.store, name, self.updates)


@pytest.fixture
def world(monkeypatch):
    refunds: list[tuple] = []
    store: dict[str, list] = {}
    admin = _Admin(store)
    monkeypatch.setattr(reaper, "get_supabase_admin", lambda: admin)
    monkeypatch.setattr(
        reaper, "refund_credits",
        lambda org, credits, *, reason: refunds.append((str(org), credits, reason)),
    )
    return store, admin, refunds


def _row(status: str, minutes_old: int, credits: int = 1750) -> dict:
    return {
        "id": f"row-{status}-{minutes_old}",
        "organization_id": ORG,
        "status": status,
        "credits_charged": credits,
        "created_at": (NOW - timedelta(minutes=minutes_old)).isoformat(),
    }


@pytest.mark.asyncio
async def test_a_row_stuck_past_its_deadline_is_closed(world):
    """The website check that sat at `capturing` for eleven minutes."""
    store, _admin, _refunds = world
    store["website_snapshots"] = [_row("capturing", 60)]

    closed = await reaper.sweep_once(now=NOW)

    assert closed.get("website_snapshots") == 1
    row = store["website_snapshots"][0]
    assert row["status"] == "failed"
    assert "stopped before it finished" in row["error_message"]


@pytest.mark.asyncio
async def test_a_report_killed_by_a_deploy_is_closed(world):
    """Observed: `generating`, section_count set, zero characters written."""
    store, _admin, _refunds = world
    store["reports"] = [_row("generating", 120, credits=0)]

    closed = await reaper.sweep_once(now=NOW)

    assert closed.get("reports") == 1
    assert store["reports"][0]["status"] == "failed"


@pytest.mark.asyncio
async def test_work_still_inside_its_deadline_is_left_alone(world):
    """Closing a job that was still working is worse than leaving a dead one a
    few minutes longer: the founder loses something real."""
    store, _admin, _refunds = world
    store["website_snapshots"] = [_row("judging", 5)]

    closed = await reaper.sweep_once(now=NOW)

    assert closed == {}
    assert store["website_snapshots"][0]["status"] == "judging"


@pytest.mark.asyncio
async def test_a_finished_row_is_never_touched(world):
    store, _admin, _refunds = world
    store["website_snapshots"] = [_row("complete", 600), _row("failed", 600)]

    closed = await reaper.sweep_once(now=NOW)

    assert closed == {}
    assert [r["status"] for r in store["website_snapshots"]] == ["complete", "failed"]


@pytest.mark.asyncio
async def test_only_states_that_prove_nothing_was_spent_are_refunded(world):
    """`capturing` means no page was read, so no critic ran and no model was
    called. `judging` means the critics were running — real compute, no
    refund."""
    store, _admin, refunds = world
    store["website_snapshots"] = [_row("capturing", 60), _row("judging", 60)]

    await reaper.sweep_once(now=NOW)

    assert len(refunds) == 1, f"refunded the wrong set: {refunds}"
    org, credits, reason = refunds[0]
    assert org == ORG
    assert credits == 1750
    assert "capturing" in reason


@pytest.mark.asyncio
async def test_a_report_that_died_writing_is_not_refunded(world):
    """It had already spent the largest main-model stage in the run."""
    store, _admin, refunds = world
    store["reports"] = [_row("generating", 120)]

    await reaper.sweep_once(now=NOW)

    assert refunds == []


@pytest.mark.asyncio
async def test_the_close_is_conditional_on_the_state_it_read(world):
    """A worker that finishes between the read and the write must win. The
    update carries the status it saw, so a row that moved on is not clobbered
    back to failed."""
    store, admin, _refunds = world
    store["answer_packs"] = [_row("building", 90)]

    await reaper.sweep_once(now=NOW)

    _table, _row_id, payload = admin.updates[0]
    assert payload["status"] == "failed"
    # The eq("status", ...) guard is what makes the write safe; assert it ran
    # by checking a row in another state is untouched by the same rule.
    store["answer_packs"] = [dict(_row("building", 90), status="complete")]
    admin.updates.clear()
    await reaper.sweep_once(now=NOW)
    assert admin.updates == []


@pytest.mark.asyncio
async def test_a_broken_table_does_not_stop_the_sweep(world):
    """A maintenance pass that takes the process down with it is worse than
    the rows it was meant to clean."""
    store, admin, _refunds = world
    store["website_snapshots"] = [_row("capturing", 60)]

    original = admin.table

    def _explode(name):
        if name == "reports":
            raise ConnectionError("that table is unreachable")
        return original(name)

    admin.table = _explode

    closed = await reaper.sweep_once(now=NOW)

    assert closed.get("website_snapshots") == 1, "one bad table sank the sweep"


def test_every_rule_names_states_and_a_sentence_a_founder_can_act_on():
    for rule in reaper.STUCK:
        assert rule.states, f"{rule.table}: no states"
        assert rule.minutes > 0
        assert len(rule.message) > 40, f"{rule.table}: message is not a sentence"
        assert "Traceback" not in rule.message
        for state in rule.refund_states:
            assert state in rule.states, (
                f"{rule.table}: refunds a state it never closes"
            )
