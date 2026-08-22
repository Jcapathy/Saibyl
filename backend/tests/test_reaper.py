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

from app.core.messages import looks_like_a_traceback
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


@pytest.mark.asyncio
async def test_a_table_without_a_credits_column_is_still_swept(world):
    """Found in production, and hidden by this module's own error handling.

    The select named `credits_charged`, which `reports` does not have.
    PostgREST rejected it, the handler logged it, and that table was skipped
    on every sweep forever — three orphaned reports sat at `generating` while
    the website rows beside them were being closed correctly. The read now
    takes `*`, so a rule cannot be disabled by a column that varies between
    tables.
    """
    store, _admin, refunds = world
    row = _row("generating", 120)
    del row["credits_charged"]          # exactly what a `reports` row looks like
    store["reports"] = [row]

    closed = await reaper.sweep_once(now=NOW)

    assert closed.get("reports") == 1, "a table without credits_charged was skipped"
    assert store["reports"][0]["status"] == "failed"
    assert refunds == []


@pytest.mark.asyncio
async def test_a_refundable_row_missing_its_charge_refunds_nothing_rather_than_crashing(
    world,
):
    store, _admin, refunds = world
    row = _row("capturing", 60)
    del row["credits_charged"]
    store["website_snapshots"] = [row]

    await reaper.sweep_once(now=NOW)

    assert refunds == [(ORG, 0, "reaper:website_snapshots:capturing")]


@pytest.mark.asyncio
async def test_a_reaped_report_now_says_why(world):
    """`reports` was the one table with nowhere to put the sentence.

    It had no `error_message` column, so the rule carried a `writes_message=
    False` flag and a founder whose report died saw the word "failed" and
    nothing else. That was not rare: two of three reports generated on
    2026-08-22 failed, and all three the day before. The column was added the
    same day and the flag deleted, so this is the assertion that the sentence
    actually lands.
    """
    store, admin, _refunds = world
    store["reports"] = [_row("generating", 120)]

    closed = await reaper.sweep_once(now=NOW)

    assert closed.get("reports") == 1
    _table, _row_id, payload = admin.updates[0]
    assert payload["status"] == "failed"
    assert "generate it again from the run" in payload["error_message"]


def test_every_non_terminal_status_a_worker_writes_is_reapable():
    """A rule that watches a status nothing writes protects nothing.

    `page_revisions` shipped exactly that: the worker has always written
    `generating`, the rule has always watched `running`, and nothing writes
    `running`. A wedged revision therefore sat at `generating` forever — no
    failure sentence, no refund of the 5,000 credits it cost, and a spinner the
    founder could not clear. The most expensive artifact in the product was the
    one the reaper could not see, and it read as covered because a rule with
    its table name was sitting right there.

    Read out of the worker sources rather than listed here, so a worker that
    invents a new in-flight status fails this instead of going quiet.
    """
    import pathlib
    import re

    workers = pathlib.Path(reaper.__file__).parents[2] / "workers"
    #: States a row may legitimately sit in forever. `ready` means the agents
    #: are built and the run is waiting on the founder to start it; `stopped`
    #: means they stopped it on purpose. Neither has a process that owes it an
    #: ending, which is the only thing the reaper exists to supply.
    resting = {
        "complete", "completed", "failed", "cancelled", "canceled",
        "ready", "stopped",
    }
    watched = {rule.table: set(rule.states) for rule in reaper.STUCK}

    missing: list[str] = []
    for source in workers.glob("*.py"):
        text = source.read_text(encoding="utf-8", errors="replace")
        for table, status in re.findall(
            r'table\(\s*"(\w+)"\s*\)\s*\.update\(\s*\{\s*"status"\s*:\s*"(\w+)"',
            text,
        ):
            if table not in watched or status in resting:
                continue
            if status not in watched[table]:
                missing.append(f"{source.name}: {table}.status={status!r}")

    assert not missing, (
        "a worker parks rows in a status no reaper rule watches, so they can "
        f"never be closed: {missing}"
    )


def test_every_rule_tells_the_founder_something_they_can_act_on():
    """No rule may close a row silently.

    The point of the reaper is that a dead row stops lying about being alive —
    but a row that says "failed" and nothing else has only traded one useless
    state for another. Each sentence has to name what survived and what to do.
    """
    for rule in reaper.STUCK:
        assert rule.message.strip(), f"{rule.table} closes rows with no reason"
        assert rule.message.strip().endswith("."), (
            f"{rule.table}'s reason is not a sentence"
        )
        assert not looks_like_a_traceback(rule.message), (
            f"{rule.table} shows a founder machine output"
        )


@pytest.mark.asyncio
async def test_a_run_stuck_analyzing_is_closed_too(world):
    """The omission that proved the point. The first version of the rule list
    covered every artifact built *from* a run and not the run itself — which
    is the one `gtm/discovery`'s docstring actually names. A Ledgerline run
    sat at `analyzing` for twenty-seven minutes while its neighbours were
    being closed correctly."""
    store, _admin, _refunds = world
    row = _row("analyzing", 200)
    del row["credits_charged"]          # simulations has no such column
    store["simulations"] = [row]

    closed = await reaper.sweep_once(now=NOW)

    assert closed.get("simulations") == 1
    assert store["simulations"][0]["status"] == "failed"


@pytest.mark.asyncio
async def test_a_prepared_run_waiting_for_the_founder_is_never_reaped(world):
    """`ready` is a resting state, not a half-finished one: a prepared run
    waits there until someone presses start. Reaping it would destroy work
    nobody had abandoned — which is why the states are listed rather than
    inferred as "anything not terminal"."""
    store, _admin, _refunds = world
    store["simulations"] = [_row("ready", 10_000)]

    closed = await reaper.sweep_once(now=NOW)

    assert closed == {}
    assert store["simulations"][0]["status"] == "ready"


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
