"""The room re-runs against the revised page (PRD_V3 §4d, the prove leg).

The contract under test:

- Unauthenticated requests never reach the database.
- Eligibility encodes the inoculation machinery's real preconditions: the
  newest finished run that has both a saved audience to copy and measured
  objections to line up. Anything less is ineligible, with a founder
  sentence saying why.
- A revision another org owns, or one that has not finished building, is
  refused with a sentence before anything launches.
- The launch composes ONE asset from the revised page — tags stripped,
  scripts and styles dropped, entities unescaped, capped — files it under
  the parent run's most load-bearing objection, and hands it to
  `create_resimulation` unchanged. Nothing about cloning is reimplemented.
- Charging follows the inoculation path exactly: creating the re-run is
  free here, and the run is priced and charged at the ordinary simulation
  start route the response points at. This router deducts nothing.
- Every founder-facing sentence avoids the report's banned vocabulary.

`page_revisions` and the storage read helper are built in parallel (C-2);
both are faked here at their seams — the table through the Supabase
stand-in, `read_stored` as an attribute the real store module does not
carry yet.
"""
from __future__ import annotations

from types import SimpleNamespace
from uuid import uuid4

import pytest

import app.services.intelligence.inoculation as inoculation_service
from app.api import website_room as website_room_api
from app.core.auth import get_current_org
from app.services.website import room_run
from app.services.website import store as website_store
from tests.test_report_vocabulary import JARGON, _pattern

ORG = "11111111-1111-1111-1111-111111111111"
OTHER_ORG = "22222222-2222-2222-2222-222222222222"
PROJECT = "33333333-3333-3333-3333-333333333333"
SNAP = "44444444-4444-4444-4444-444444444444"
REV = "55555555-5555-5555-5555-555555555555"
SIM = "66666666-6666-6666-6666-666666666666"
CHILD = "77777777-7777-7777-7777-777777777777"
USER = "88888888-8888-8888-8888-888888888888"

URL = "https://acme.example/pricing"
HTML_PATH = f"website/{ORG}/{SNAP}/revision.html"

# A page with everything the stripper must survive: markup, a script, a
# style block, a comment, an entity, and far more copy than the cap admits.
REVISION_HTML = (
    "<!doctype html><html><head><title>ignored</title>"
    "<style>.hero{color:red}</style>"
    "<script>console.log('tracking beacon')</script>"
    "</head><body><!-- build 42 -->"
    "<h1>Ship the answer, <em>not</em> the homework</h1>"
    "<p>Acme &amp; Co checks every claim before your buyer does.</p>"
    "<p>" + "Working sentence. " * 2000 + "</p>"
    "</body></html>"
)


# ---------------------------------------------------------------------------
# A Supabase stand-in that honours column selection and records every call
# ---------------------------------------------------------------------------

class _Query:
    def __init__(self, table: str, store: dict, calls: list):
        self._table = table
        self._store = store
        self._calls = calls
        self._filters: dict[str, object] = {}
        self._op: str | None = None
        self._payload = None
        self._columns: list[str] | None = None
        self._order: tuple[str, bool] | None = None
        self._limit: int | None = None

    def select(self, *args, **_kwargs):
        self._op = "select"
        joined = ", ".join(args) if args else "*"
        if joined.strip() != "*":
            self._columns = [c.strip() for c in joined.split(",") if c.strip()]
        return self

    def insert(self, payload):
        self._op = "insert"
        self._payload = payload
        return self

    def eq(self, column: str, value):
        self._filters[column] = value
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
        ]
        if self._order:
            column, desc = self._order
            matched = sorted(
                matched, key=lambda r: str(r.get(column) or ""), reverse=desc
            )
        if self._limit is not None:
            matched = matched[: self._limit]
        if self._columns is not None:
            matched = [{k: row.get(k) for k in self._columns} for row in matched]
        else:
            matched = [dict(row) for row in matched]
        return SimpleNamespace(data=matched, count=None)


class _Admin:
    def __init__(self, store: dict | None = None):
        self.store = store or {}
        self.calls: list = []

    def table(self, name: str):
        return _Query(name, self.store, self.calls)


def _install(monkeypatch, store: dict | None = None) -> _Admin:
    admin = _Admin(store)
    monkeypatch.setattr(website_room_api, "get_supabase_admin", lambda: admin)
    monkeypatch.setattr(room_run, "get_supabase_admin", lambda: admin)
    return admin


def _record_deductions(monkeypatch) -> list:
    """The whole billing surface. The inoculation path charges the re-run at
    the simulation start route, so a deduction from anywhere in this flow is
    a double charge."""
    from app.services.billing import agent_pricing

    deductions = []
    monkeypatch.setattr(
        agent_pricing,
        "deduct_credits",
        lambda org_id, credits: deductions.append((str(org_id), credits)),
    )
    return deductions


def _fake_read_stored(monkeypatch, content: str = REVISION_HTML) -> list:
    """The C-2 storage-read contract: `read_stored(path) -> bytes`."""
    reads = []

    def read_stored(path):
        reads.append(path)
        return content.encode("utf-8")

    monkeypatch.setattr(website_store, "read_stored", read_stored, raising=False)
    return reads


def _fake_resimulation(monkeypatch) -> list:
    calls = []

    def create_resimulation(simulation_id, org_id, asset_ids, created_by=None, name=None):
        calls.append(SimpleNamespace(
            simulation_id=simulation_id,
            org_id=org_id,
            asset_ids=list(asset_ids),
            created_by=created_by,
            name=name,
        ))
        return {"id": CHILD, "status": "ready", "parent_simulation_id": simulation_id}

    monkeypatch.setattr(inoculation_service, "create_resimulation", create_resimulation)
    return calls


@pytest.fixture
def authed_client(app):
    from fastapi.testclient import TestClient

    app.dependency_overrides[get_current_org] = lambda: {
        "org_id": ORG,
        "user": {"id": USER},
    }
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.pop(get_current_org, None)


# ---------------------------------------------------------------------------
# Fixture rows
# ---------------------------------------------------------------------------

def _sim(**overrides) -> dict:
    row = {
        "id": SIM,
        "organization_id": ORG,
        "project_id": PROJECT,
        "name": "First room",
        "status": "complete",
        "created_at": "2026-08-01T10:00:00+00:00",
    }
    row.update(overrides)
    return row


def _agent(simulation_id: str = SIM) -> dict:
    return {"id": str(uuid4()), "simulation_id": simulation_id}


def _objection(simulation_id: str = SIM, key: str = "no-price-anchor",
               label: str = "The page never says what it costs",
               score: float = 0.9) -> dict:
    return {
        "simulation_id": simulation_id,
        "objection_key": key,
        "label": label,
        "load_bearing_score": score,
    }


def _repeatable_store(**sim_overrides) -> dict:
    """One finished run with a saved audience and measured objections."""
    sim = _sim(**sim_overrides)
    return {
        "simulations": [sim],
        "simulation_agents": [_agent(sim["id"])],
        "canonical_objections": [
            _objection(sim["id"], score=0.9),
            _objection(sim["id"], key="setup-looks-heavy",
                       label="Setup looks heavy", score=0.4),
        ],
        "inoculation_assets": [],
    }


def _revision(**overrides) -> dict:
    # `html_path` is the column migration 037 actually declares and the one
    # `revision_tasks.py` writes. This fixture said `revision_html` — PRD_V3
    # §4d's name — which is why every test passed while the live gate refused
    # every finished revision: the fixture and the code shared one invented
    # key, and neither matched the schema. Fixed 2026-08-17; the pin below
    # keeps the fixture honest.
    row = {
        "id": REV,
        "snapshot_id": SNAP,
        "html_path": HTML_PATH,
        "rounds": 2,
        "scores_before": {"overall": 58},
        "scores_after": {"overall": 81},
        "created_at": "2026-08-15T10:00:00+00:00",
    }
    row.update(overrides)
    return row


def _snapshot(**overrides) -> dict:
    row = {
        "id": SNAP,
        "organization_id": ORG,
        "project_id": PROJECT,
        "url": URL,
        "status": "complete",
    }
    row.update(overrides)
    return row


# ---------------------------------------------------------------------------
# HTML → text: a "less than" is copy, not a tag
# ---------------------------------------------------------------------------

def test_a_literal_angle_bracket_in_the_copy_is_not_read_as_a_tag():
    """The same defect `style_guide.visible_copy` carried, in the other strip.

    `<[^>]+>` treats any literal "<" as a tag opening and deletes everything up
    to the next ">" — so "Setup takes <5 minutes" plus a "Learn more >" further
    down deleted every sentence between them. A browser renders both as copy
    (HTML only starts a tag when a name follows the "<"), so the room would
    have been shown a page the founder's visitors never see, and this text is a
    stored artifact the before/after cites.
    """
    html = (
        "<!doctype html><html><body>"
        "<h1>Acme Payroll</h1>"
        "<p>Setup takes <5 minutes and churn is <1%.</p>"
        "<p>Plans start at $29 per month.</p>"
        "<a href='/docs'>Read the docs ></a>"
        "</body></html>"
    )

    body = room_run.page_text(html)

    assert "Setup takes <5 minutes" in body
    assert "$29 per month" in body, "the founder's own price was deleted as markup"
    assert "Read the docs >" in body
    assert "href" not in body, "real markup must still go"


def test_well_formed_markup_is_still_stripped_from_the_room_copy():
    """The widening may not cost the strip the asset depends on."""
    body = room_run.page_text(REVISION_HTML)

    assert "console.log" not in body
    assert "color:red" not in body
    assert "build 42" not in body
    assert "<em>" not in body and "<h1>" not in body
    assert room_run.page_title(REVISION_HTML) == "Ship the answer, not the homework"


# ---------------------------------------------------------------------------
# Eligibility encodes the machinery's real preconditions
# ---------------------------------------------------------------------------

def test_eligibility_takes_the_newest_run_the_machinery_can_repeat(monkeypatch):
    """Complete, has agents to copy, has objections to line up — all three."""
    repeatable = _sim(id=str(uuid4()), created_at="2026-08-01T10:00:00+00:00")
    no_objections = _sim(id=str(uuid4()), created_at="2026-08-12T10:00:00+00:00")
    no_agents = _sim(id=str(uuid4()), created_at="2026-08-14T10:00:00+00:00")
    still_running = _sim(
        id=str(uuid4()), status="running", created_at="2026-08-15T10:00:00+00:00"
    )
    _install(monkeypatch, {
        "simulations": [repeatable, no_objections, no_agents, still_running],
        "simulation_agents": [_agent(repeatable["id"]), _agent(no_objections["id"])],
        "canonical_objections": [_objection(repeatable["id"])],
    })

    found = room_run.eligible_simulation(PROJECT, ORG)

    assert found is not None
    assert found["id"] == repeatable["id"], (
        "a run the machinery cannot repeat was preferred over one it can"
    )


def test_no_finished_run_is_ineligible_with_the_first_sentence(monkeypatch):
    _install(monkeypatch, {
        "simulations": [_sim(status="running")],
        "simulation_agents": [_agent()],
        "canonical_objections": [_objection()],
    })

    assert room_run.eligible_simulation(PROJECT, ORG) is None
    assert room_run.ineligibility_reason(PROJECT, ORG) == room_run.NO_FINISHED_RUN_REASON


def test_a_finished_run_with_nothing_to_line_up_reads_the_second_sentence(monkeypatch):
    _install(monkeypatch, {
        "simulations": [_sim()],
        "simulation_agents": [_agent()],
        "canonical_objections": [],
    })

    assert room_run.eligible_simulation(PROJECT, ORG) is None
    assert room_run.ineligibility_reason(PROJECT, ORG) == room_run.NOT_REPEATABLE_REASON


# ---------------------------------------------------------------------------
# The launch composes the page as one asset and reuses the machinery
# ---------------------------------------------------------------------------

async def test_launch_composes_the_asset_and_hands_it_to_the_machinery(monkeypatch):
    admin = _install(monkeypatch, _repeatable_store())
    reads = _fake_read_stored(monkeypatch)
    resim = _fake_resimulation(monkeypatch)

    result = await room_run.launch_room_run(
        revision_row=_revision(),
        snapshot_row=_snapshot(),
        organization_id=ORG,
        created_by=USER,
    )

    # The revision HTML came from storage through the C-2 read contract.
    assert reads == [HTML_PATH]

    # One asset, composed from the page, filed under the top objection.
    assets = admin.store["inoculation_assets"]
    assert len(assets) == 1
    asset = assets[0]
    assert asset["simulation_id"] == SIM
    assert asset["organization_id"] == ORG
    assert asset["objection_key"] == "no-price-anchor", (
        "not filed under the most load-bearing objection"
    )
    assert asset["asset_type"] == "disclosure", (
        "must be a kind the inoculation_assets CHECK constraint accepts"
    )
    assert asset["status"] == "draft"
    assert asset["created_by"] == USER
    assert asset["title"] == "Ship the answer, not the homework"
    assert asset["hypothesis"], "an unstated hypothesis is retroactively correct"

    body = asset["body"]
    assert "<" not in body, "markup survived the strip"
    assert "console.log" not in body, "script content leaked into the copy"
    assert "color:red" not in body, "style content leaked into the copy"
    assert "build 42" not in body, "a comment leaked into the copy"
    assert "Acme & Co checks every claim" in body, "entities were not unescaped"
    assert "Working sentence." in body
    assert len(body) == room_run.PAGE_TEXT_CAP, "the body was not capped"

    # The existing machinery was called, not reimplemented.
    assert len(resim) == 1
    call = resim[0]
    assert call.simulation_id == SIM
    assert call.org_id == ORG
    assert call.asset_ids == [asset["id"]]
    assert call.created_by == USER
    assert call.name == "First room — the new page"

    # What a caller needs to poll the existing surfaces.
    assert result["simulation_id"] == CHILD
    assert result["parent_simulation_id"] == SIM
    assert result["asset_id"] == asset["id"]
    assert result["status"] == "ready"
    assert result["start"] == f"/api/simulations/{CHILD}/start"
    assert result["result"] == f"/api/inoculation/{CHILD}/result"


async def test_launch_uses_worker_passed_text_without_touching_storage(monkeypatch):
    admin = _install(monkeypatch, _repeatable_store())
    reads = _fake_read_stored(monkeypatch)
    _fake_resimulation(monkeypatch)

    await room_run.launch_room_run(
        revision_row=_revision(
            html_path=None,
            revision_text="<h1>New</h1><p>Copy a buyer can act on.</p>",
        ),
        snapshot_row=_snapshot(),
        organization_id=ORG,
    )

    assert reads == [], "storage was read although the worker passed the text"
    asset = admin.store["inoculation_assets"][0]
    assert asset["title"] == "New"
    assert "Copy a buyer can act on." in asset["body"]


async def test_launch_refuses_a_page_with_no_readable_text(monkeypatch):
    admin = _install(monkeypatch, _repeatable_store())
    resim = _fake_resimulation(monkeypatch)

    with pytest.raises(ValueError, match="no readable text"):
        await room_run.launch_room_run(
            revision_row=_revision(
                html_path=None,
                revision_text="<script>x()</script><style>a{}</style>",
            ),
            snapshot_row=_snapshot(),
            organization_id=ORG,
        )

    assert not admin.store["inoculation_assets"], "an empty asset was stored"
    assert not resim, "a re-run launched with nothing to show"


async def test_launch_rechecks_eligibility_and_refuses(monkeypatch):
    admin = _install(monkeypatch, {
        "simulations": [_sim(status="running")],
        "simulation_agents": [],
        "canonical_objections": [],
        "inoculation_assets": [],
    })
    resim = _fake_resimulation(monkeypatch)

    with pytest.raises(ValueError) as excinfo:
        await room_run.launch_room_run(
            revision_row=_revision(),
            snapshot_row=_snapshot(),
            organization_id=ORG,
        )

    assert str(excinfo.value) == room_run.NO_FINISHED_RUN_REASON
    assert not admin.store["inoculation_assets"]
    assert not resim


# ---------------------------------------------------------------------------
# The routes
# ---------------------------------------------------------------------------

def test_unauthenticated_never_reaches_the_database(app, monkeypatch):
    from fastapi.testclient import TestClient

    admin = _install(monkeypatch)
    client = TestClient(app)

    eligibility = client.get(f"/api/website-room/eligibility?project_id={PROJECT}")
    run = client.post("/api/website-room/run", json={"revision_id": REV})

    assert eligibility.status_code in (401, 403), eligibility.text
    assert run.status_code in (401, 403), run.text
    assert not admin.calls


def test_eligibility_for_a_foreign_workspace_is_a_404(authed_client, monkeypatch):
    _install(monkeypatch, {"projects": [
        {"id": PROJECT, "organization_id": OTHER_ORG}
    ]})

    response = authed_client.get(
        f"/api/website-room/eligibility?project_id={PROJECT}"
    )

    assert response.status_code == 404, response.text
    assert "workspace" in response.json()["detail"]


def test_eligibility_names_the_run_the_room_will_repeat(authed_client, monkeypatch):
    _install(monkeypatch, {"projects": [{"id": PROJECT, "organization_id": ORG}]})
    monkeypatch.setattr(room_run, "eligible_simulation", lambda p, o: {"id": SIM})

    response = authed_client.get(
        f"/api/website-room/eligibility?project_id={PROJECT}"
    )

    assert response.status_code == 200, response.text
    assert response.json() == {"eligible": True, "simulation_id": SIM}


def test_eligibility_says_why_when_the_room_cannot_rerun(authed_client, monkeypatch):
    _install(monkeypatch, {"projects": [{"id": PROJECT, "organization_id": ORG}]})
    monkeypatch.setattr(room_run, "eligible_simulation", lambda p, o: None)
    monkeypatch.setattr(
        room_run, "ineligibility_reason",
        lambda p, o: room_run.NOT_REPEATABLE_REASON,
    )

    response = authed_client.get(
        f"/api/website-room/eligibility?project_id={PROJECT}"
    )

    assert response.status_code == 200, response.text
    assert response.json() == {
        "eligible": False,
        "reason": room_run.NOT_REPEATABLE_REASON,
    }


def _fake_launch(monkeypatch, *, error: Exception | None = None) -> list:
    calls = []

    async def launch_room_run(*, revision_row, snapshot_row, organization_id,
                              created_by=None):
        calls.append(SimpleNamespace(
            revision_row=revision_row,
            snapshot_row=snapshot_row,
            organization_id=organization_id,
            created_by=created_by,
        ))
        if error is not None:
            raise error
        return {
            "simulation_id": CHILD,
            "parent_simulation_id": SIM,
            "asset_id": str(uuid4()),
            "revision_id": revision_row.get("id"),
            "status": "ready",
            "start": f"/api/simulations/{CHILD}/start",
            "watch": f"/api/simulations/{CHILD}/status",
            "result": f"/api/inoculation/{CHILD}/result",
        }

    monkeypatch.setattr(room_run, "launch_room_run", launch_room_run)
    return calls


def test_running_a_foreign_revision_is_a_404(authed_client, monkeypatch):
    _install(monkeypatch, {
        "page_revisions": [_revision()],
        "website_snapshots": [_snapshot(organization_id=OTHER_ORG)],
    })
    launches = _fake_launch(monkeypatch)
    deductions = _record_deductions(monkeypatch)

    response = authed_client.post(
        "/api/website-room/run", json={"revision_id": REV}
    )

    assert response.status_code == 404, response.text
    assert "revised page" in response.json()["detail"]
    assert not launches, "a cross-tenant revision launched a run"
    assert not deductions


@pytest.mark.parametrize("revision", [
    _revision(status="revising"),
    _revision(html_path=None),
], ids=["status-says-so", "no-stored-copy"])
def test_an_unfinished_revision_is_refused(authed_client, monkeypatch, revision):
    _install(monkeypatch, {
        "page_revisions": [revision],
        "website_snapshots": [_snapshot()],
    })
    launches = _fake_launch(monkeypatch)

    response = authed_client.post(
        "/api/website-room/run", json={"revision_id": REV}
    )

    assert response.status_code == 409, response.text
    assert "hasn't finished building" in response.json()["detail"]
    assert not launches


def test_an_ineligible_workspace_reads_the_reason_sentence(authed_client, monkeypatch):
    _install(monkeypatch, {
        "page_revisions": [_revision()],
        "website_snapshots": [_snapshot()],
    })
    _fake_launch(monkeypatch, error=ValueError(room_run.NO_FINISHED_RUN_REASON))
    deductions = _record_deductions(monkeypatch)

    response = authed_client.post(
        "/api/website-room/run", json={"revision_id": REV}
    )

    assert response.status_code == 409, response.text
    assert response.json()["detail"] == room_run.NO_FINISHED_RUN_REASON
    assert not deductions


def test_the_run_launches_and_this_route_charges_nothing(authed_client, monkeypatch):
    """The charge lives where the machinery put it — the simulation start
    route the response points at — so this route deducting anything would
    price the same run twice."""
    revision = _revision()
    revision.pop("status", None)  # the PRD shape has no status column
    _install(monkeypatch, {
        "page_revisions": [revision],
        "website_snapshots": [_snapshot()],
    })
    launches = _fake_launch(monkeypatch)
    deductions = _record_deductions(monkeypatch)

    response = authed_client.post(
        "/api/website-room/run", json={"revision_id": REV}
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["simulation_id"] == CHILD
    assert body["parent_simulation_id"] == SIM
    assert body["status"] == "ready"
    assert body["start"] == f"/api/simulations/{CHILD}/start"
    assert body["result"] == f"/api/inoculation/{CHILD}/result"

    assert len(launches) == 1
    call = launches[0]
    assert call.revision_row["id"] == REV
    assert call.snapshot_row["id"] == SNAP
    assert call.organization_id == ORG
    assert call.created_by == USER

    assert deductions == [], "this route charged; the start route already does"


# ---------------------------------------------------------------------------
# The vocabulary rule, applied to what a founder reads on this surface
# ---------------------------------------------------------------------------

def test_founder_sentences_carry_no_report_jargon(authed_client, monkeypatch):
    """The stored constants and the live refusals, scanned against the same
    banned list the report is held to."""
    sentences = [
        room_run.NO_FINISHED_RUN_REASON,
        room_run.NOT_REPEATABLE_REASON,
        room_run.NO_READABLE_TEXT_ERROR,
        room_run.NO_STORED_COPY_ERROR,
    ]

    _install(monkeypatch, {
        "projects": [{"id": PROJECT, "organization_id": OTHER_ORG}],
        "page_revisions": [_revision(status="revising")],
        "website_snapshots": [_snapshot()],
    })
    sentences.append(
        authed_client.get(
            f"/api/website-room/eligibility?project_id={PROJECT}"
        ).json()["detail"]
    )
    sentences.append(
        authed_client.post(
            "/api/website-room/run", json={"revision_id": REV}
        ).json()["detail"]
    )
    sentences.append(
        authed_client.post(
            "/api/website-room/run", json={"revision_id": str(uuid4())}
        ).json()["detail"]
    )

    for sentence in sentences:
        hits = [word for word in JARGON if _pattern(word).search(sentence)]
        assert not hits, f"banned word(s) {hits} in: {sentence!r}"


# ---------------------------------------------------------------------------
# The seam this file's own docstring warns about
# ---------------------------------------------------------------------------

def test_the_revision_fixture_uses_columns_migration_037_declares():
    """The fixture must be shaped like the table, not like the PRD.

    This file fakes `page_revisions` "at its seam" because the table was built
    in parallel. That is exactly how the prove leg shipped broken: the gate
    read `revision_html` / `revision_text`, this fixture supplied
    `revision_html`, every test passed — and **no production row has ever
    carried either key.** Migration 037 declares `html_path` and
    `revision_tasks.py` writes it, so a green suite was asserting a column
    that does not exist.

    The fixture is therefore pinned to the migration text. If the schema
    moves this fails and the fixture is corrected with it; a fixture is only
    evidence while it matches the table it stands in for.
    """
    from pathlib import Path

    migration = (
        Path(__file__).resolve().parents[1]
        / "scripts" / "migrations" / "037_page_revisions.sql"
    ).read_text(encoding="utf-8")

    for column in _revision():
        assert column in migration, (
            f"the fixture supplies {column!r}, which 037 never declares — "
            "the fixture is inventing a column the code will then read"
        )


def test_a_finished_revision_is_launchable_from_the_column_that_exists():
    """`html_path` alone must satisfy the completion gate.

    The regression test for the prove leg. A row exactly as the worker writes
    it — storage ref in `html_path`, nothing inline — is a finished revision.
    Before the fix this returned False for every revision ever built and the
    founder was told the page "hasn't finished building yet".
    """
    assert website_room_api._revision_is_complete(
        {"html_path": HTML_PATH, "status": "complete"}
    )
    assert website_room_api._revision_is_complete({"html_path": HTML_PATH})
    # Still refused when there is genuinely no copy to show.
    assert not website_room_api._revision_is_complete({"html_path": None})
    assert not website_room_api._revision_is_complete({})
