"""IP clearance (PRD_V3 §11): create, charge, execute, list.

The contract under test:

- Unauthenticated requests never reach the database.
- No USPTO key configured is a 503 before anything is created or charged.
- QUICK is free, spawns the worker, and is capped per org per day.
- STANDARD charges `clearance_credits('STANDARD')` at create and records it
  on the row.
- Reads are org-scoped, and the list never carries artifact or report bodies.
- The worker persists artifact + findings + `complete`, and a failure lands as
  `failed` with the reason on the row — never a spinner with no ending.

The clearance services (`app.services.clearance.*`) are built in parallel and
mocked here at the import boundary: the worker imports them lazily, so these
tests seed `sys.modules` with stand-ins and run whether or not the real
modules exist yet.
"""
from __future__ import annotations

import sys
import types
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.api import clearance as clearance_api
from app.core.auth import get_current_org
from app.services.billing.agent_pricing import clearance_credits
from app.workers import clearance_tasks

ORG = "11111111-1111-1111-1111-111111111111"
OTHER_ORG = "22222222-2222-2222-2222-222222222222"
RUN = "44444444-4444-4444-4444-444444444444"


# ---------------------------------------------------------------------------
# A Supabase stand-in that honours column selection and records every call
# ---------------------------------------------------------------------------

class _Query:
    def __init__(self, table: str, store: dict, calls: list):
        self._table = table
        self._store = store
        self._calls = calls
        self._filters: dict[str, object] = {}
        self._gte: dict[str, str] = {}
        self._op: str | None = None
        self._payload = None
        self._columns: list[str] | None = None
        self._count = None
        self._order: tuple[str, bool] | None = None
        self._limit: int | None = None

    def select(self, *args, count=None, **_kwargs):
        self._op = "select"
        self._count = count
        joined = ", ".join(args) if args else "*"
        if joined.strip() != "*":
            self._columns = [c.strip() for c in joined.split(",") if c.strip()]
        return self

    def insert(self, payload):
        self._op = "insert"
        self._payload = payload
        return self

    def update(self, payload):
        self._op = "update"
        self._payload = payload
        return self

    def eq(self, column: str, value):
        self._filters[column] = value
        return self

    def gte(self, column: str, value):
        self._gte[column] = value
        return self

    def order(self, column: str, desc: bool = False):
        self._order = (column, desc)
        return self

    def limit(self, n: int):
        self._limit = n
        return self

    def execute(self):
        rows = self._store.setdefault(self._table, [])
        self._calls.append((self._table, self._op, dict(self._filters), self._payload))

        if self._op == "insert":
            payloads = (
                self._payload if isinstance(self._payload, list) else [self._payload]
            )
            inserted = []
            for payload in payloads:
                row = {"id": str(uuid4()), **payload}
                rows.append(row)
                inserted.append(dict(row))
            return SimpleNamespace(data=inserted, count=None)

        matched = [
            row
            for row in rows
            if all(row.get(k) == v for k, v in self._filters.items())
            and all(str(row.get(k) or "") >= v for k, v in self._gte.items())
        ]

        if self._op == "update":
            for row in matched:
                row.update(self._payload or {})
            return SimpleNamespace(data=[dict(r) for r in matched], count=None)

        if self._order:
            column, desc = self._order
            matched = sorted(
                matched, key=lambda r: str(r.get(column) or ""), reverse=desc
            )
        total = len(matched)
        if self._limit is not None:
            matched = matched[: self._limit]
        if self._columns is not None:
            matched = [{k: row.get(k) for k in self._columns} for row in matched]
        else:
            matched = [dict(row) for row in matched]
        return SimpleNamespace(data=matched, count=total if self._count else None)


class _Admin:
    def __init__(self, store: dict | None = None):
        self.store = store or {}
        self.calls: list = []

    def table(self, name: str):
        return _Query(name, self.store, self.calls)


def _install(monkeypatch, store: dict | None = None) -> _Admin:
    admin = _Admin(store)
    monkeypatch.setattr(clearance_api, "get_supabase_admin", lambda: admin)
    monkeypatch.setattr(clearance_tasks, "get_supabase_admin", lambda: admin)
    return admin


def _configure_key(monkeypatch, key: str = "test-odp-key") -> None:
    monkeypatch.setattr(
        clearance_api, "settings", SimpleNamespace(uspto_odp_api_key=key)
    )


def _capture_spawn(monkeypatch) -> list:
    spawned = []

    def _spawn(coro, name, *, on_failure=None):
        spawned.append(SimpleNamespace(name=name, on_failure=on_failure))
        coro.close()
        return SimpleNamespace()

    monkeypatch.setattr(clearance_api, "spawn", _spawn)
    return spawned


def _fake_billing(monkeypatch, balance: int = 10_000) -> list:
    deductions = []
    monkeypatch.setattr(
        clearance_api, "get_credit_balance", lambda org_id: (balance, balance, "founder")
    )
    monkeypatch.setattr(
        clearance_api,
        "deduct_credits",
        lambda org_id, credits: deductions.append((str(org_id), credits)),
    )
    return deductions


@pytest.fixture
def authed_client(app):
    from fastapi.testclient import TestClient

    app.dependency_overrides[get_current_org] = lambda: {"org_id": ORG}
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.pop(get_current_org, None)


# ---------------------------------------------------------------------------
# Pricing
# ---------------------------------------------------------------------------

def test_the_tier_prices_are_0_2000_6000():
    """The published prices, pinned. QUICK free; the rest at the 80% margin."""
    assert clearance_credits("QUICK") == 0
    assert clearance_credits("STANDARD") == 2_000
    assert clearance_credits("COMPREHENSIVE") == 6_000


def test_an_unknown_tier_is_refused_not_priced_at_zero():
    with pytest.raises(ValueError):
        clearance_credits("PREMIUM")


# ---------------------------------------------------------------------------
# Creating a run
# ---------------------------------------------------------------------------

def test_unauthenticated_is_refused_before_any_query(app, monkeypatch):
    from fastapi.testclient import TestClient

    admin = _install(monkeypatch)
    response = TestClient(app).post("/api/clearance", json={"item": "Saibyl"})

    assert response.status_code in (401, 403), response.text
    assert not admin.calls


def test_a_missing_key_is_a_503_before_anything_is_created(
    authed_client, monkeypatch
):
    """No run row, no charge, no query — the guard fires before all of them."""
    admin = _install(monkeypatch)
    _configure_key(monkeypatch, key="")
    spawned = _capture_spawn(monkeypatch)
    deductions = _fake_billing(monkeypatch)

    response = authed_client.post(
        "/api/clearance", json={"item": "Saibyl", "tier": "STANDARD"}
    )

    assert response.status_code == 503, response.text
    assert "isn't configured yet" in response.json()["detail"]
    assert not admin.calls, "the guard let a query through"
    assert not admin.store.get("clearance_runs")
    assert not spawned
    assert not deductions


def test_a_quick_run_is_created_free_and_spawned(authed_client, monkeypatch):
    admin = _install(monkeypatch)
    _configure_key(monkeypatch)
    spawned = _capture_spawn(monkeypatch)
    deductions = _fake_billing(monkeypatch)

    response = authed_client.post(
        "/api/clearance",
        json={"item": "Saibyl", "type_hint": "name", "competitors": ["Acme"]},
    )

    assert response.status_code == 200, response.text
    run = response.json()
    assert run["tier"] == "QUICK"
    assert run["status"] == "queued"
    assert run["credits_charged"] == 0
    assert run["search_date"], "a run must be date-stamped at creation"
    assert not deductions, "a free run moved the balance"
    assert [s.name for s in spawned] == ["clearance_run"]
    assert spawned[0].on_failure is not None
    assert len(admin.store["clearance_runs"]) == 1


def test_a_standard_run_deducts_and_records_its_price(authed_client, monkeypatch):
    admin = _install(monkeypatch)
    _configure_key(monkeypatch)
    spawned = _capture_spawn(monkeypatch)
    deductions = _fake_billing(monkeypatch, balance=10_000)

    response = authed_client.post(
        "/api/clearance", json={"item": "A synthetic market engine", "tier": "STANDARD"}
    )

    assert response.status_code == 200, response.text
    expected = clearance_credits("STANDARD")
    assert deductions == [(ORG, expected)]
    assert response.json()["credits_charged"] == expected
    assert admin.store["clearance_runs"][0]["credits_charged"] == expected
    assert [s.name for s in spawned] == ["clearance_run"]


def test_an_unaffordable_run_is_a_402_with_nothing_created(
    authed_client, monkeypatch
):
    admin = _install(monkeypatch)
    _configure_key(monkeypatch)
    spawned = _capture_spawn(monkeypatch)
    deductions = _fake_billing(monkeypatch, balance=100)

    response = authed_client.post(
        "/api/clearance", json={"item": "Saibyl", "tier": "COMPREHENSIVE"}
    )

    assert response.status_code == 402, response.text
    assert not deductions
    assert not admin.store.get("clearance_runs")
    assert not spawned


def test_the_sixth_quick_run_of_the_day_is_a_429(authed_client, monkeypatch):
    admin = _install(monkeypatch)
    _configure_key(monkeypatch)
    spawned = _capture_spawn(monkeypatch)
    _fake_billing(monkeypatch)

    for n in range(5):
        response = authed_client.post("/api/clearance", json={"item": f"Name {n}"})
        assert response.status_code == 200, response.text

    response = authed_client.post("/api/clearance", json={"item": "Name 5"})

    assert response.status_code == 429, response.text
    assert "free checks" in response.json()["detail"]
    assert len(admin.store["clearance_runs"]) == 5
    assert len(spawned) == 5


def test_a_blank_item_is_refused(authed_client, monkeypatch):
    admin = _install(monkeypatch)
    _configure_key(monkeypatch)

    response = authed_client.post("/api/clearance", json={"item": "   "})

    assert response.status_code == 422, response.text
    assert not admin.calls


# ---------------------------------------------------------------------------
# Reading runs
# ---------------------------------------------------------------------------

def _stored_run(**overrides) -> dict:
    row = {
        "id": RUN,
        "organization_id": ORG,
        "project_id": None,
        "item": "Saibyl",
        "type_hint": "name",
        "field": None,
        "competitors": [],
        "tier": "STANDARD",
        "status": "complete",
        "credits_charged": 2_000,
        "search_date": "2026-08-15",
        "created_at": "2026-08-15T10:00:00+00:00",
        "completed_at": "2026-08-15T10:05:00+00:00",
        "artifact": {"patents": {"overall_risk": "YELLOW"}},
        "report_markdown": "# Clearance report",
        "error_message": None,
    }
    row.update(overrides)
    return row


def test_get_by_id_is_org_scoped(authed_client, monkeypatch):
    _install(monkeypatch, {"clearance_runs": [
        _stored_run(organization_id=OTHER_ORG)
    ]})
    _configure_key(monkeypatch)

    response = authed_client.get(f"/api/clearance/{RUN}")

    assert response.status_code == 404, response.text


def test_get_by_id_returns_artifact_and_report_when_complete(
    authed_client, monkeypatch
):
    _install(monkeypatch, {"clearance_runs": [_stored_run()]})
    _configure_key(monkeypatch)

    response = authed_client.get(f"/api/clearance/{RUN}")

    assert response.status_code == 200, response.text
    run = response.json()
    assert run["artifact"] == {"patents": {"overall_risk": "YELLOW"}}
    assert run["report_markdown"] == "# Clearance report"


def test_the_list_carries_the_risk_but_not_the_bodies(authed_client, monkeypatch):
    newer = _stored_run(
        id=str(uuid4()),
        status="queued",
        artifact=None,
        report_markdown=None,
        created_at="2026-08-16T09:00:00+00:00",
    )
    _install(monkeypatch, {"clearance_runs": [
        _stored_run(),
        newer,
        _stored_run(id=str(uuid4()), organization_id=OTHER_ORG),
    ]})
    _configure_key(monkeypatch)

    response = authed_client.get("/api/clearance")

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["total"] == 2, "another org's run leaked into the list"
    assert [item["id"] for item in body["items"]][0] == newer["id"], "not newest first"
    for item in body["items"]:
        assert "artifact" not in item, "the list carried an artifact body"
        assert "report_markdown" not in item, "the list carried a report body"
    risks = {item["id"]: item["risk"] for item in body["items"]}
    assert risks[RUN] == "YELLOW"
    assert risks[newer["id"]] is None


# ---------------------------------------------------------------------------
# The worker, with every clearance service mocked at the import boundary
# ---------------------------------------------------------------------------

# Keys follow the ip-clearance-search output contract exactly ("trademark"
# singular, "pending_landscape") — the worker flattens the real artifact, so a
# fixture with invented keys would validate a reader of keys that never exist.
ARTIFACT = {
    "schema_version": 1,
    "trademark": {
        "conflicts": [{
            "serial_or_reg": "97123456",
            "mark": "SAIBYL",
            "owner": "Acme Corp",
            "status": "LIVE",
            "risk": "red",
            "dates": {"filed": "2021-03-01"},
        }],
    },
    "patents": {
        "overall_risk": "YELLOW",
        "closest_art": [{
            "number": "US-11222333-B2",
            "title": "Synthetic audience engine",
            "assignee": "Example Inc",
            "status": "granted",
            "risk": "YELLOW",
            "claim_requirements": "Claim 1 requires a physical sensor array.",
            "differences": "The submitted idea has no sensor array.",
            "dates": {"granted": "2023-06-10"},
        }],
    },
    "pending_landscape": {
        "notable_pending": [{
            "app": "18/123456",
            "title": "Audience prediction method",
            "assignee": "Example Inc",
            "status": "pending",
        }],
    },
}

REPORT = "# Clearance report\n\nNot legal advice."


def _install_services(monkeypatch, *, artifact=ARTIFACT, tracks_error=None):
    """Seed sys.modules with clearance-service stand-ins.

    The worker imports the services inside `run_clearance`, so entries seeded
    here are what it gets — whether or not the real modules exist yet.
    """
    calls = SimpleNamespace(plan=None, tracks=None, artifact=None, composed=None)

    pkg = types.ModuleType("app.services.clearance")
    pkg.__path__ = []

    uspto = types.ModuleType("app.services.clearance.uspto_client")

    class ClearanceConfigError(Exception):
        pass

    class UsptoClient:
        odp_available = True

    uspto.UsptoClient = UsptoClient
    uspto.ClearanceConfigError = ClearanceConfigError

    query_plan = types.ModuleType("app.services.clearance.query_plan")
    plan_obj = SimpleNamespace(assumptions=["treated as a product name"])

    async def build_query_plan(item, type_hint, field, competitors, *, organization_id=None):
        calls.plan = (item, type_hint, field, competitors, organization_id)
        return plan_obj

    query_plan.build_query_plan = build_query_plan

    tracks = types.ModuleType("app.services.clearance.tracks")
    result_obj = SimpleNamespace(kind="clearance-result")

    async def run_clearance_tracks(
        client, plan, item, tier, competitors, search_date=None, *, organization_id=None
    ):
        calls.tracks = SimpleNamespace(
            client=client, plan=plan, item=item, tier=tier,
            competitors=competitors, search_date=search_date,
            organization_id=organization_id,
        )
        if tracks_error is not None:
            raise tracks_error
        return result_obj

    tracks.run_clearance_tracks = run_clearance_tracks

    artifact_mod = types.ModuleType("app.services.clearance.artifact")

    def build_artifact(item, tier, search_date, assumptions, result):
        calls.artifact = (item, tier, search_date, assumptions, result)
        return artifact

    def compose_report_markdown(art, *, examiner_notes=None):
        calls.composed = art
        return REPORT

    artifact_mod.build_artifact = build_artifact
    artifact_mod.compose_report_markdown = compose_report_markdown

    monkeypatch.setitem(sys.modules, "app.services.clearance", pkg)
    monkeypatch.setitem(sys.modules, "app.services.clearance.uspto_client", uspto)
    monkeypatch.setitem(sys.modules, "app.services.clearance.query_plan", query_plan)
    monkeypatch.setitem(sys.modules, "app.services.clearance.tracks", tracks)
    monkeypatch.setitem(sys.modules, "app.services.clearance.artifact", artifact_mod)
    return calls


def _queued_run(**overrides) -> dict:
    return _stored_run(
        status="queued",
        artifact=None,
        report_markdown=None,
        completed_at=None,
        field="productivity software",
        competitors=["Acme Corp"],
        search_date="2026-08-16",
        **overrides,
    )


async def test_the_worker_persists_artifact_findings_and_complete(monkeypatch):
    admin = _install(monkeypatch, {"clearance_runs": [_queued_run()]})
    calls = _install_services(monkeypatch)

    await clearance_tasks.run_clearance(RUN, ORG)

    run = admin.store["clearance_runs"][0]
    assert run["status"] == "complete", run.get("error_message")
    assert run["artifact"] == ARTIFACT
    assert run["report_markdown"] == REPORT
    assert run["completed_at"]

    # The services were driven from the row, not from re-derived inputs.
    assert calls.plan == (
        "Saibyl", "name", "productivity software", ["Acme Corp"], ORG
    )
    assert calls.tracks.tier == "STANDARD"
    assert calls.tracks.organization_id == ORG
    assert calls.tracks.search_date == "2026-08-16"
    art_item, art_tier, art_date, art_assumptions, art_result = calls.artifact
    assert (art_item, art_tier, art_date) == ("Saibyl", "STANDARD", "2026-08-16")
    assert art_assumptions == ["treated as a product name"]
    assert art_result.kind == "clearance-result"
    assert calls.composed == ARTIFACT, "the report was not composed from the artifact"

    findings = admin.store["clearance_findings"]
    assert len(findings) == 3
    by_kind = {f["kind"]: f for f in findings}
    assert set(by_kind) == {"trademark", "patent", "pending"}
    for f in findings:
        assert f["run_id"] == RUN
        assert f["organization_id"] == ORG

    assert by_kind["trademark"]["reference_number"] == "97123456"
    assert by_kind["trademark"]["title"] == "SAIBYL"
    assert by_kind["trademark"]["owner"] == "Acme Corp"
    assert by_kind["trademark"]["risk"] == "RED", "risk casing must be normalised"

    assert by_kind["patent"]["reference_number"] == "US-11222333-B2"
    assert by_kind["patent"]["owner"] == "Example Inc"
    assert by_kind["patent"]["risk"] == "YELLOW"
    assert by_kind["patent"]["claim_requirements"] == (
        "Claim 1 requires a physical sensor array."
    )

    assert by_kind["pending"]["reference_number"] == "18/123456"
    assert by_kind["pending"]["owner"] == "Example Inc"
    assert by_kind["pending"]["risk"] is None
    assert by_kind["pending"]["raw"] == (
        ARTIFACT["pending_landscape"]["notable_pending"][0]
    )


async def test_a_worker_failure_lands_on_the_row(monkeypatch):
    admin = _install(monkeypatch, {"clearance_runs": [_queued_run()]})
    _install_services(
        monkeypatch, tracks_error=RuntimeError("USPTO answered 500")
    )

    await clearance_tasks.run_clearance(RUN, ORG)

    run = admin.store["clearance_runs"][0]
    assert run["status"] == "failed"
    assert "RuntimeError" in run["error_message"]
    assert "USPTO answered 500" in run["error_message"]
    assert not admin.store.get("clearance_findings")
    assert not run.get("artifact")


async def test_the_worker_never_runs_another_orgs_row(monkeypatch):
    """Org id comes from the authenticated route; the worker re-checks it."""
    admin = _install(monkeypatch, {"clearance_runs": [
        _queued_run(organization_id=OTHER_ORG)
    ]})
    _install_services(monkeypatch)

    await clearance_tasks.run_clearance(RUN, ORG)

    run = admin.store["clearance_runs"][0]
    assert run["status"] in ("queued", "failed")
    assert run.get("artifact") is None, "a cross-tenant run executed"
