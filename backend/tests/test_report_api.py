"""`POST /reports/generate` — the cheapest way to spend the most money.

Report generation is the most expensive main-model stage in the product
(`report_tasks`' own docstring: "roughly a fifth of a standard run's cost"),
and the route that starts it took no role gate, no bounds, and no failure
handler.

Three defects, and the same reason all three were invisible: this route spends
without ever touching the credit ledger, because the report is billed inside
the run's price. `test_role_gates`' scan only flags handlers whose own source
contains `deduct_credits(`, so it found nothing here.

* **Ungated.** A `viewer` — the account whose whole grant is to read — could
  drive the report writer against any run in its org, repeatedly. Pinned in
  `test_role_gates.SPENDING_ROUTES`.
* **Unbounded.** `max_sections` had no `ge`/`le` and `report_agent` uses
  `config.section_count` verbatim as the outline size, then `asyncio.gather`s
  one ReACT loop per section with no concurrency cap. `max_sections: 500`
  returned 200.
* **Silent.** This was the only `spawn` in the API with no `on_failure`, and
  `report_tasks` builds its `ReACTConfig` *before* `generate_report` inserts the
  `reports` row — so an out-of-enum `evidence_depth` raised with no row anywhere,
  the client polled `GET /reports/by-simulation/{id}` forever, and the API had
  already answered "started".
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.api import reports as reports_api
from app.core.auth import get_current_org

ORG = "11111111-1111-4111-8111-111111111111"
SIM = "22222222-2222-4222-8222-222222222222"
USER = "33333333-3333-4333-8333-333333333333"


class _Table:
    def __init__(self, name: str, store: dict, log: list):
        self._name, self._store, self._log = name, store, log
        self._op = "select"
        self._payload = None
        self._single = False

    def select(self, *_a, **_k):
        return self

    def insert(self, payload):
        self._op, self._payload = "insert", payload
        return self

    def update(self, payload):
        self._op, self._payload = "update", payload
        return self

    def eq(self, *_a):
        return self

    def in_(self, *_a):
        return self

    def order(self, *_a, **_k):
        return self

    def limit(self, *_a):
        return self

    def single(self):
        self._single = True
        return self

    def execute(self):
        if self._op in ("insert", "update"):
            self._log.append((self._name, self._op, self._payload))
            return SimpleNamespace(data=[self._payload])
        rows = self._store.get(self._name, [])
        return SimpleNamespace(data=(rows[0] if self._single else list(rows)))


class _Admin:
    def __init__(self, store: dict):
        self.store, self.writes = store, []

    def table(self, name: str):
        return _Table(name, self.store, self.writes)


@pytest.fixture
def owner(app):
    """A caller who may spend, so the gate is not what is under test here."""
    app.dependency_overrides[get_current_org] = lambda: {
        "org_id": ORG,
        "role": "owner",
        "user": {"id": USER},
        "org": {"plan": "growth"},
    }
    yield TestClient(app)
    app.dependency_overrides.pop(get_current_org, None)


@pytest.fixture
def spawned(monkeypatch):
    calls = []

    def _spawn(coro, name, *, on_failure=None):
        calls.append(SimpleNamespace(name=name, on_failure=on_failure))
        coro.close()
        return SimpleNamespace()

    monkeypatch.setattr(reports_api, "spawn", _spawn)
    return calls


# ── The caller does not choose how many Opus sections we write ──

def test_a_caller_chosen_section_count_is_bounded(owner, monkeypatch, spawned):
    """`max_sections: 500` returned 200 and became the outline size."""
    monkeypatch.setattr(
        reports_api, "get_supabase_admin", lambda: _Admin({"simulations": [{"id": SIM}]})
    )

    response = owner.post("/api/reports/generate", json={
        "simulation_id": SIM, "evidence_depth": "exhaustive", "max_sections": 500,
    })

    assert response.status_code == 422, response.text
    assert not spawned, "500 sections reached the worker"


def test_an_evidence_depth_the_worker_cannot_accept_is_refused_at_the_edge(
    owner, monkeypatch, spawned
):
    """The API said `str`, `ReACTConfig` says `Literal`, and the two disagreeing
    is what produced a report that never existed and never failed."""
    monkeypatch.setattr(
        reports_api, "get_supabase_admin", lambda: _Admin({"simulations": [{"id": SIM}]})
    )

    response = owner.post("/api/reports/generate", json={
        "simulation_id": SIM, "evidence_depth": "medium",
    })

    assert response.status_code == 422, response.text
    assert not spawned


def test_a_report_within_the_bounds_still_starts(owner, monkeypatch, spawned):
    """The bounds must refuse the abuse, not the feature."""
    monkeypatch.setattr(
        reports_api, "get_supabase_admin", lambda: _Admin({"simulations": [{"id": SIM}]})
    )

    response = owner.post("/api/reports/generate", json={
        "simulation_id": SIM, "evidence_depth": "deep", "max_sections": 4,
    })

    assert response.status_code == 200, response.text
    assert response.json() == {"status": "started"}
    assert len(spawned) == 1


# ── A failed report is not a spinner ─────────────────────

def test_the_spawn_carries_a_failure_handler(owner, monkeypatch, spawned):
    monkeypatch.setattr(
        reports_api, "get_supabase_admin", lambda: _Admin({"simulations": [{"id": SIM}]})
    )

    owner.post("/api/reports/generate", json={"simulation_id": SIM})

    assert spawned[0].on_failure is not None, (
        "the only spawn in the API with no on_failure; every other one passes a "
        "_mark_*_failed callback"
    )


def test_a_report_that_died_before_its_row_existed_still_gets_a_row(monkeypatch):
    """The exact failure case: nothing was ever inserted, so nothing to update.

    `run_generate_report` builds `ReACTConfig(evidence_depth=...)` before
    `generate_report` inserts the `reports` row at line 1257. A `ValidationError`
    there left no row at all, so `GET /reports/by-simulation/{id}` 404'd
    "No report found for this simulation" forever on an artifact the founder had
    already paid for the run to produce.
    """
    admin = _Admin({"reports": []})
    monkeypatch.setattr(reports_api, "get_supabase_admin", lambda: admin)

    reports_api._mark_report_failed(SIM, ORG)(ValueError("bad evidence_depth"))

    assert len(admin.writes) == 1
    table, op, payload = admin.writes[0]
    assert (table, op) == ("reports", "insert")
    assert payload["simulation_id"] == SIM
    assert payload["organization_id"] == ORG
    assert payload["status"] == "failed"
    assert "generate it again from the run" in payload["error_message"]


def test_a_report_that_died_mid_write_is_marked_rather_than_duplicated(monkeypatch):
    admin = _Admin({"reports": [{"id": "rep-1", "status": "generating"}]})
    monkeypatch.setattr(reports_api, "get_supabase_admin", lambda: admin)

    reports_api._mark_report_failed(SIM, ORG)(RuntimeError("supabase blip"))

    assert len(admin.writes) == 1
    table, op, payload = admin.writes[0]
    assert (table, op) == ("reports", "update")
    assert payload["status"] == "failed"


def test_a_failing_failure_handler_never_raises(monkeypatch):
    """It runs inside `spawn`'s own except block; raising there loses the log."""
    class _Broken:
        def table(self, _name):
            raise ConnectionError("supabase is gone")

    monkeypatch.setattr(reports_api, "get_supabase_admin", lambda: _Broken())

    reports_api._mark_report_failed(SIM, ORG)(ValueError("boom"))


# ── One report at a time per run ──


def test_a_second_report_is_refused_while_one_is_generating(
    owner, monkeypatch, spawned
):
    """The role gate stops a viewer starting these. It does nothing about the
    same member starting twenty.

    Nothing on this route calls `deduct_credits` — the report is billed inside
    the run's price — so a loop here drives unbounded Opus sections against
    Saibyl's own account with no ledger entry anywhere to notice it.
    """
    admin = _Admin({
        "simulations": [{"id": SIM}],
        "reports": [{"id": "rep-1", "status": "generating"}],
    })
    monkeypatch.setattr(reports_api, "get_supabase_admin", lambda: admin)

    response = owner.post("/api/reports/generate", json={"simulation_id": SIM})

    assert response.status_code == 409
    assert "already being generated" in response.json()["detail"]
    assert spawned == [], "a second report writer was started"


def test_regenerating_a_finished_report_is_allowed(owner, monkeypatch, spawned):
    """`complete` and `failed` are deliberately not blocked — regenerating a
    finished or broken write-up is a thing a founder legitimately wants."""
    admin = _Admin({
        "simulations": [{"id": SIM}],
        "reports": [],  # the in_() filter matches nothing
    })
    monkeypatch.setattr(reports_api, "get_supabase_admin", lambda: admin)

    response = owner.post("/api/reports/generate", json={"simulation_id": SIM})

    assert response.status_code == 200
    assert len(spawned) == 1
