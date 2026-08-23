"""Who is allowed to write over a run's row, and when.

Three defects, one shape: a writer that names a row by id alone and assumes it
is still the row it last saw.

  - `_mark_simulation_failed` was a bare `.update(...).eq("id", ...)` — the only
    writer in this family without a compare-and-set, while
    `website_tasks._advance`, `revision_tasks._advance` and the reaper's own
    UPDATE all had one. `run_simulation` writes `complete`, publishes, and then
    calls `reconcile_run_cost`, which makes two unguarded network calls; a
    transient failure there propagated to `spawn` and rewrote a finished,
    reported, paid-for run to `failed`. `failed` is startable, so the founder
    re-ran it and paid twice for work already delivered.

  - The same handler overwrote `run_prepare_agents`'s one carefully written
    founder-readable sentence with the generic one, so the founder was told to
    retry the one thing a retry cannot fix.

  - `run_prepare_agents` asked "has this room already posted?" *94 lines after*
    it had regenerated the entire swarm — one `llm_fast` call per agent, up to
    1,000 at enterprise, on a route that deducts nothing.
"""
from __future__ import annotations

import inspect
from types import SimpleNamespace

import pytest

from app.api import simulations as sim_api
from app.workers import simulation_tasks

SIM = "22222222-2222-2222-2222-222222222222"
ORG = "11111111-1111-1111-1111-111111111111"


# ---------------------------------------------------------------------------
# A fake that honours `.in_()`, because the guard being tested *is* the filter.
# ---------------------------------------------------------------------------

class _Table:
    def __init__(self, store: dict, name: str, log: list):
        self._store, self._name, self._log = store, name, log
        self._filters: list[tuple] = []
        self._payload: dict | None = None
        self._op: str | None = None

    def select(self, *_a, **_k):
        self._op = "select"
        return self

    def update(self, payload):
        self._op, self._payload = "update", payload
        return self

    def eq(self, col, value):
        self._filters.append(("eq", col, value))
        return self

    def in_(self, col, values):
        self._filters.append(("in", col, list(values)))
        return self

    def limit(self, _n):
        return self

    def delete(self):
        self._op = "delete"
        return self

    def _matches(self, row) -> bool:
        for kind, col, value in self._filters:
            if kind == "eq" and str(row.get(col)) != str(value):
                return False
            if kind == "in" and row.get(col) not in value:
                return False
        return True

    def execute(self):
        rows = [r for r in self._store.get(self._name, []) if self._matches(r)]
        if self._op == "update":
            for row in rows:
                row.update(self._payload)
                self._log.append((self._name, row["id"], dict(self._payload)))
        if self._op == "delete":
            kept = [r for r in self._store.get(self._name, []) if not self._matches(r)]
            self._store[self._name] = kept
            for row in rows:
                self._log.append((self._name, row.get("id"), "delete"))
        return SimpleNamespace(data=rows)


class _Admin:
    def __init__(self, store: dict):
        self.store, self.writes = store, []

    def table(self, name):
        return _Table(self.store, name, self.writes)


@pytest.fixture
def world(monkeypatch):
    store: dict[str, list] = {}
    admin = _Admin(store)
    monkeypatch.setattr(sim_api, "get_supabase_admin", lambda: admin)
    return store, admin


# ---------------------------------------------------------------------------
# SIM-COMPLETE-CLOBBERED
# ---------------------------------------------------------------------------

def test_a_finished_run_is_not_rewritten_to_failed(world):
    """The failure verbatim: everything succeeded, then the tail raised.

    `run_simulation` has already written `complete`, published, and stored the
    analysis artifact and report. `reconcile_run_cost` then hits a transient
    PostgREST error, which reaches `spawn`'s `on_failure`.
    """
    store, admin = world
    store["simulations"] = [
        {"id": SIM, "status": "complete", "error_message": None}
    ]

    sim_api._mark_simulation_failed(SIM, "run_simulation")(
        ConnectionError("run_quotes select failed")
    )

    assert store["simulations"][0]["status"] == "complete", (
        "a run the founder paid for and that fully succeeded reads as failed"
    )
    assert store["simulations"][0]["error_message"] is None
    assert admin.writes == []


@pytest.mark.parametrize("terminal", ["complete", "completed", "stopped"])
def test_no_terminal_status_is_rewritten(world, terminal):
    """`completed` and `complete` both exist in this column; `stopped` is the
    founder's own instruction and must not be reported as a failure."""
    store, _admin = world
    store["simulations"] = [{"id": SIM, "status": terminal}]

    sim_api._mark_simulation_failed(SIM, "run_simulation")(RuntimeError("boom"))

    assert store["simulations"][0]["status"] == terminal


def test_a_run_that_really_died_in_flight_is_still_closed(world):
    """The handler's actual job, unchanged."""
    store, _admin = world
    store["simulations"] = [{"id": SIM, "status": "running"}]

    sim_api._mark_simulation_failed(SIM, "run_simulation")(RuntimeError("boom"))

    row = store["simulations"][0]
    assert row["status"] == "failed"
    assert "stopped before it finished" in row["error_message"]


def test_a_better_sentence_already_on_the_row_survives(world):
    """`run_prepare_agents` writes one the founder can act on. This handler used
    to replace it with "This run stopped before it finished", which for the
    already-posted case invites exactly the retry that cannot work."""
    store, _admin = world
    store["simulations"] = [{
        "id": SIM,
        "status": "failed",
        "error_message": simulation_tasks.ROOM_ALREADY_RAN_MESSAGE,
    }]

    sim_api._mark_simulation_failed(SIM, "prepare_agents")(
        ValueError(simulation_tasks.ROOM_ALREADY_RAN_MESSAGE)
    )

    assert (
        store["simulations"][0]["error_message"]
        == simulation_tasks.ROOM_ALREADY_RAN_MESSAGE
    )


def test_the_guard_set_matches_the_reaper_s_own():
    """Two things decide "still in flight" and they must agree, or one of them
    closes a row the other thinks is finished."""
    from app.services.maintenance import reaper

    rule = next(r for r in reaper.STUCK if r.table == "simulations")

    assert set(sim_api.UNFINISHED_STATUSES) == set(rule.states)


# ---------------------------------------------------------------------------
# The twin: every other `on_failure` handler was the same unguarded write
# ---------------------------------------------------------------------------

# `app.api.reports` is skipped by the two scans below because that module was
# being edited by another change in the same release, and its
# `_mark_report_failed` has a separate defect of its own: the lookup it guards
# on filters `('pending', 'queued', 'generating')` — a set that includes a
# status the reaper's `reports` rule does not watch, and one the worker has
# already moved past by the time this handler runs.
#
# **Delete this line once `reports.py` lands, and the scans cover it unchanged.**
_OTHER_AGENTS_FILES = {"reports"}


def test_no_failure_handler_writes_over_a_row_it_no_longer_owns():
    """The rule, over every `_mark_*_failed` in the app.

    `_mark_simulation_failed` was the one the finding names, but it was not the
    only bare `.update(...).eq("id", ...)`: all six were, and only one of them
    happened to have a reachable path to a completed row. "Harder to reach" is
    not a guard, and the round this ships in exists because a correct fix was
    applied to one of two places three times running.

    Derived from the module source rather than listed, so the seventh handler
    somebody writes fails here.
    """
    import pathlib
    import re

    api_dir = pathlib.Path(sim_api.__file__).parent
    offenders: list[str] = []
    for path in sorted(api_dir.glob("*.py")):
        if path.stem in _OTHER_AGENTS_FILES:
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        for match in re.finditer(r"def _mark[_a-z]*\(", text):
            # The closure body: up to the `return _mark` that ends the factory.
            end = text.find("return _mark", match.start())
            body = text[match.start(): end if end != -1 else len(text)]
            if '"status": "failed"' not in body:
                continue
            if not re.search(r'\.(?:in_|eq)\(\s*"status"', body):
                offenders.append(f"{path.name}:{text[:match.start()].count(chr(10)) + 1}")

    assert not offenders, (
        "failure handlers that overwrite a row without checking it is still in "
        f"flight: {offenders}"
    )


def test_every_guarded_handler_names_the_states_its_reaper_rule_watches():
    """A guard listing the wrong states is worse than none: the row never gets
    its sentence and the founder watches a spinner forever.

    Anchored to `reaper.STUCK`, which `test_every_non_terminal_status_a_worker_
    writes_is_reapable` already pins against the workers themselves — so the
    lists here cannot drift from what the workers actually write.
    """
    import pathlib
    import re

    from app.services.maintenance import reaper

    watched = {rule.table: set(rule.states) for rule in reaper.STUCK}
    api_dir = pathlib.Path(sim_api.__file__).parent

    checked = 0
    for path in sorted(api_dir.glob("*.py")):
        if path.stem in _OTHER_AGENTS_FILES:
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        for match in re.finditer(r"def _mark[_a-z]*\(", text):
            end = text.find("return _mark", match.start())
            body = text[match.start(): end if end != -1 else len(text)]
            table_match = re.search(r'\.table\(\s*"(\w+)"\s*\)', body)
            states_match = re.search(
                r'\.in_\(\s*"status",\s*(?:list\()?\[?([^\])]*)', body
            )
            if not table_match or not states_match:
                continue
            table = table_match.group(1)
            if table not in watched:
                continue
            named = set(re.findall(r'"(\w+)"', states_match.group(1)))
            if not named:
                # Written as a module constant; resolve it from the module.
                const = re.search(r'list\((\w+)\)', body)
                if const:
                    module = __import__(
                        f"app.api.{path.stem}", fromlist=["x"]
                    )
                    named = set(getattr(module, const.group(1)))
            assert named == watched[table], (
                f"{path.name}: guards {sorted(named)} but the reaper closes "
                f"{sorted(watched[table])} — a row in the difference never gets "
                f"its failure sentence"
            )
            checked += 1

    assert checked >= 5, f"the scan found only {checked} guarded handlers"


# ---------------------------------------------------------------------------
# R2-06: the guard must come before the spend
# ---------------------------------------------------------------------------

def test_prepare_checks_for_events_before_it_generates_the_swarm():
    """The one-query guard sat 94 lines downstream of `asyncio.gather`.

    `PREPARABLE_STATUSES` includes `failed` and the frontend's `IDLE_STATUSES`
    includes `failed`, so "Start the run →" renders on a run that died
    mid-execution — which has events. Every click regenerated the whole swarm
    and then refused.
    """
    source = inspect.getsource(simulation_tasks.run_prepare_agents)

    first_guard = source.find("_agents_with_events(")
    spend = source.find("asyncio.gather(")

    assert first_guard != -1, "the already-posted guard is gone"
    assert spend != -1, "the agent-generation gather is gone"
    assert first_guard < spend, (
        "the room-already-posted check still runs after the swarm has been "
        "regenerated, so a refused preparation costs a full swarm of model calls"
    )


def test_the_guard_still_stands_in_front_of_the_delete():
    """Both copies are load-bearing: the early one saves the money, the late one
    guards the DELETE against the window in between."""
    source = inspect.getsource(simulation_tasks.run_prepare_agents)

    assert source.count("_agents_with_events(") == 2
    delete = source.find('table("simulation_agents").delete()')
    assert delete != -1
    assert source.rfind("_agents_with_events(") < delete


def test_every_way_preparation_can_end_leaves_a_sentence():
    """`_mark_simulation_failed` no longer writes over this worker's own close,
    so a bare `{"status": "failed"}` here would leave the founder with a status
    word and nothing else."""
    source = inspect.getsource(simulation_tasks.run_prepare_agents)

    assert '{"status": "failed"}' not in source, (
        "a preparation failure closes the row with no sentence on it"
    )
    # Every close goes through the one guarded helper: the two already-posted
    # guards plus the four ways the audience can produce nobody.
    assert source.count("_fail_preparation(") == 6

    for message in (
        simulation_tasks.ROOM_ALREADY_RAN_MESSAGE,
        simulation_tasks.NO_PACKS_MESSAGE,
        simulation_tasks.NO_VALID_PACKS_MESSAGE,
        simulation_tasks.NO_AGENTS_MESSAGE,
        simulation_tasks.GENERATION_FAILED_MESSAGE,
    ):
        assert len(message) > 40
        assert "Traceback" not in message


def test_the_reconciliation_cannot_report_itself_as_a_run_failure():
    """`reconcile_run_cost` sat bare between two try/excepts, and it is not a
    local computation — it selects `run_quotes` over the network and can call
    `admin.rpc('deduct_credits', ...)`."""
    lines = inspect.getsource(simulation_tasks.run_simulation).splitlines()
    at = next(
        i for i, ln in enumerate(lines)
        if "reconcile_run_cost(simulation_id, org_id)" in ln
    )
    previous = next(
        lines[i] for i in range(at - 1, -1, -1) if lines[i].strip()
    )

    assert previous.strip() == "try:", (
        f"reconcile_run_cost can still propagate out of a completed run; the "
        f"line above it is {previous.strip()!r}"
    )


# ---------------------------------------------------------------------------
# DELETE-PARENT-ORPHANS-RESIM
# ---------------------------------------------------------------------------

PARENT = "33333333-3333-3333-3333-333333333333"
CHILD = "44444444-4444-4444-4444-444444444444"


@pytest.mark.asyncio
async def test_deleting_a_parent_run_is_refused_while_it_has_re_simulations(world):
    """Two foreign keys made routine tidying destructive (021_inoculation_loop):

        inoculation_results.parent_simulation_id  ON DELETE CASCADE
        simulations.parent_simulation_id          ON DELETE SET NULL

    So deleting a completed parent cascaded away the before/after the founder
    paid for — after which `GET /api/inoculation/{child}/result` answers "This
    run is not a re-simulation" for an artifact that exists nowhere else — and
    nulled the child's link. The response was a bare `{"status": "deleted"}`
    with no warning, while the two sibling delete routes written for exactly
    this problem (`icp.py`, `packs.py`) both report what they broke.
    """
    from fastapi import HTTPException

    store, admin = world
    store["simulations"] = [
        {"id": PARENT, "status": "complete", "organization_id": ORG,
         "parent_simulation_id": None, "name": "Ledgerline"},
        {"id": CHILD, "status": "complete", "organization_id": ORG,
         "parent_simulation_id": PARENT, "name": "Ledgerline — the new page"},
    ]

    with pytest.raises(HTTPException) as caught:
        await sim_api.delete_simulation(PARENT, {"org_id": ORG, "role": "owner"})

    assert caught.value.status_code == 409
    # Named, not merely refused: the founder has a step they can take.
    assert "Ledgerline — the new page" in caught.value.detail
    # And nothing was destroyed on the way to the refusal.
    assert admin.writes == []
    assert len(store["simulations"]) == 2


@pytest.mark.asyncio
async def test_an_ordinary_run_still_deletes(world):
    """The guard is narrow: only a run something else was measured against."""
    store, _admin = world
    store["simulations"] = [
        {"id": SIM, "status": "complete", "organization_id": ORG,
         "parent_simulation_id": None, "name": "A one-off"},
    ]

    result = await sim_api.delete_simulation(SIM, {"org_id": ORG, "role": "owner"})

    assert result == {"status": "deleted", "id": SIM}


def test_a_re_simulation_is_priced_from_its_own_state_not_a_nullable_link():
    """`simulations.parent_simulation_id` is ON DELETE SET NULL, so deleting a
    parent rewrote the child's price: 2,681 credits with `reuse_agents=True`
    against 2,996 without — 315 credits for an `agent_generation` stage that
    provably never runs, because the child's agents are copied rows.

    `inoculation_asset_ids` is the child's own column and survives the parent.
    """
    source = inspect.getsource(sim_api.start_simulation)
    line = next(
        ln for ln in source.splitlines() if ln.strip().startswith("reuse_agents =")
    )

    assert "inoculation_asset_ids" in source
    # Either fact is enough; neither alone may be the whole derivation.
    assert "or bool(" in line or "inoculation_asset_ids" in line, line

    # And the arithmetic the finding measured, so the claim is not just a shape.
    from app.services.billing.agent_pricing import estimate_simulation_cost

    reused = estimate_simulation_cost(
        100, 5, 2, 1, inoculation_assets=2, reuse_agents=True
    ).credits
    generated = estimate_simulation_cost(
        100, 5, 2, 1, inoculation_assets=2, reuse_agents=False
    ).credits

    assert (reused, generated) == (2681, 2996), (reused, generated)
    assert generated - reused == 315, (
        "an orphaned re-simulation is charged for an agent_generation stage it "
        "provably never performs"
    )
