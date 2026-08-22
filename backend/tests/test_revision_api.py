"""Page revisions (PRD_V3 §4d): create, charge, execute, read back, prove.

The contract under test:

- Unauthenticated requests never reach the database.
- A revision can only be ordered on a check the org owns (404) that has
  finished judging (409); one the balance cannot cover is a 402 with nothing
  created. Creating one deducts `website_revision_credits()` at create,
  records it on the row, and spawns the worker with an on_failure handler.
- The worker re-fetches the page the check judged (the honest current
  "before"), hands it with the stored critique, the gallery's design DNA, and
  the admired-site reference to the revision loop, stores the winning round's
  page and screenshots, and lands `complete` with the before/after scores,
  the after-critique, and the paste-ready fix prompts. The before-scores come
  from the snapshot's stored critique — the number the founder already read —
  not from the loop's own accounting. A failure lands as `failed` with a
  sentence a founder can read; never a spinner with no ending.
- The stored page and images stream back through org-scoped passthroughs with
  their real content types, and `which` must name a stored image.
- The admin gallery feed and detail carry the latest complete revision per
  check, so the cross-org feed reads before/after without a join.

The website services (`app.services.website.*`) are built in parallel and
mocked here at the import boundary: the worker and the passthrough routes
import them lazily, so these tests seed `sys.modules` with stand-ins and run
whether or not the real modules exist yet.
"""
from __future__ import annotations

import sys
import types
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.api import admin as admin_api
from app.api import website as website_api
from app.core.auth import get_current_org
from app.core.config import settings
from app.services.billing.agent_pricing import website_revision_credits
from app.services.website.claims import UnsupportedClaim
from app.workers import revision_tasks

ORG = "11111111-1111-1111-1111-111111111111"
OTHER_ORG = "22222222-2222-2222-2222-222222222222"
ADMIN_ORG = "99999999-9999-9999-9999-999999999999"
PROJECT = "33333333-3333-3333-3333-333333333333"
SNAP = "44444444-4444-4444-4444-444444444444"
SNAP_2 = "45454545-4545-4545-4545-454545454545"
REV = "77777777-7777-7777-7777-777777777777"
GALLERY = "66666666-6666-6666-6666-666666666666"
GALLERY_2 = "68686868-6868-6868-6868-686868686868"

URL = "https://acme.example/pricing"
REF_URL = "https://linear.example"


# ---------------------------------------------------------------------------
# A Supabase stand-in: filters, ordering, pagination, embeds
# ---------------------------------------------------------------------------

class _Query:
    def __init__(self, table: str, store: dict, calls: list):
        self._table = table
        self._store = store
        self._calls = calls
        self._filters: dict[str, object] = {}
        self._in: dict[str, tuple] = {}
        self._op: str | None = None
        self._payload = None
        self._columns: list[str] | None = None
        self._embeds: list[str] = []
        self._count = None
        self._order: tuple[str, bool] | None = None
        self._limit: int | None = None
        self._range: tuple[int, int] | None = None

    def select(self, *args, count=None, **_kwargs):
        self._op = "select"
        self._count = count
        joined = ", ".join(args) if args else "*"
        columns = [c.strip() for c in joined.split(",") if c.strip()]
        # `organizations(name)` — a PostgREST foreign-table embed.
        self._embeds = [c for c in columns if c.endswith(")")]
        plain = [c for c in columns if not c.endswith(")")]
        self._columns = None if ("*" in plain or not plain) else plain
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

    def in_(self, column: str, values):
        self._in[column] = tuple(values)
        return self

    def order(self, column: str, desc: bool = False):
        self._order = (column, desc)
        return self

    def limit(self, n: int):
        self._limit = n
        return self

    def range(self, start: int, end: int):
        self._range = (start, end)
        return self

    def _embed(self, row: dict, projected: dict) -> dict:
        for embed in self._embeds:
            fk_table = embed.split("(")[0]
            field = embed[embed.index("(") + 1 : -1]
            fk_column = f"{fk_table.rstrip('s')}_id"
            target = next(
                (
                    r
                    for r in self._store.get(fk_table, [])
                    if r.get("id") == row.get(fk_column)
                ),
                None,
            )
            projected[fk_table] = {field: target.get(field)} if target else None
        return projected

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
            and all(row.get(k) in v for k, v in self._in.items())
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
        if self._range is not None:
            start, end = self._range
            matched = matched[start : end + 1]
        elif self._limit is not None:
            matched = matched[: self._limit]
        out = []
        for row in matched:
            projected = (
                dict(row)
                if self._columns is None
                else {k: row.get(k) for k in self._columns}
            )
            out.append(self._embed(row, projected))
        return SimpleNamespace(data=out, count=total if self._count else None)


class _Admin:
    def __init__(self, store: dict | None = None):
        self.store = store or {}
        self.calls: list = []

    def table(self, name: str):
        return _Query(name, self.store, self.calls)


def _install(monkeypatch, store: dict | None = None) -> _Admin:
    admin = _Admin(store)
    monkeypatch.setattr(website_api, "get_supabase_admin", lambda: admin)
    monkeypatch.setattr(revision_tasks, "get_supabase_admin", lambda: admin)
    monkeypatch.setattr(admin_api, "get_supabase_admin", lambda: admin)
    return admin


# ---------------------------------------------------------------------------
# Website-service stand-ins at the import boundary
# ---------------------------------------------------------------------------

DOM_TEXT = "Acme helps teams ship faster. Start free, upgrade when it sticks. " * 30

REVISED_HTML = "<html><body><h1>Acme, for support teams</h1></body></html>"

# The check's stored verdict: this is the "before" the revision must beat.
CRITIQUE = {
    "overall_score": 62,
    "page_takeaway": "A tool for teams, but the page never says which teams.",
    "dimensions": [
        {
            "key": "hierarchy",
            "score": 55,
            "findings": ["The headline names no buyer."],
            "strengths": [],
        },
        {
            "key": "credibility",
            "score": 70,
            "findings": [],
            "strengths": ["Named customers with real logos."],
        },
    ],
}

SCORES_AFTER = {"overall": 81, "dimensions": {"hierarchy": 78, "credibility": 84}}

CRITIQUE_AFTER = {
    "overall_score": 81,
    "page_takeaway": "A support-team tool that says so in the first line.",
    "dimensions": [
        {"key": "hierarchy", "score": 78, "findings": [], "strengths": []},
        {"key": "credibility", "score": 84, "findings": [], "strengths": []},
    ],
}

#: A badge the rewrite put on the page that the founder's page never carried.
#: The live case that made this necessary shipped SOC 2, ISO 27001 and PCI DSS
#: claims with no basis in the source (2026-08-22).
UNSUPPORTED_CLAIM = UnsupportedClaim(
    kind="certification",
    text="SOC 2",
    quote="soc 2 type ii report available under nda.",
)

FIX_PROMPTS = [
    {
        "title": "Name the buyer in the headline",
        "scope": "hero",
        "prompt": "In index.html, change the h1 to name support teams directly.",
    },
    {
        "title": "Put the customer logos above the fold",
        "scope": "credibility",
        "prompt": "Move the logo strip directly under the hero section.",
    },
]

ROUNDS = [
    {
        "round": 1,
        "overall_score": 68,
        "dimension_scores": {"hierarchy": 64, "credibility": 72},
    },
    {
        "round": 2,
        "overall_score": 81,
        "dimension_scores": {"hierarchy": 78, "credibility": 84},
    },
]


def _install_services(
    monkeypatch,
    *,
    capture_error: str | None = None,
    reference_error: str | None = None,
    blocked_reference: bool = False,
    revision_error: str | None = None,
    upload_error: Exception | None = None,
    stored: dict[str, bytes] | None = None,
):
    """Seed sys.modules with stand-ins for capture, revise, and store.

    The worker and the passthrough routes import them lazily, so entries
    seeded here are what they get — whether or not the real modules exist
    yet. `capture_error` fails the founder's own page; `reference_error`
    fails only the admired site; `blocked_reference` hands back a near-empty
    reference (a bot wall wearing a 200); `revision_error` raises the
    revision service's own founder-readable exception.
    """
    calls = SimpleNamespace(captures=[], revise=None, upload=None, reads=[])

    pkg = types.ModuleType("app.services.website")
    pkg.__path__ = []

    capture_mod = types.ModuleType("app.services.website.capture")

    class WebsiteCaptureError(Exception):
        pass

    main_capture = SimpleNamespace(
        url=URL,
        final_url="https://acme.example/pricing/",
        title="Acme — Pricing",
        dom_text=DOM_TEXT,
        meta={},
        screenshot_desktop=b"png-before-desktop",
        screenshot_mobile=b"png-before-mobile",
    )
    reference_capture = SimpleNamespace(
        url=REF_URL,
        final_url=REF_URL + "/",
        title="Linear — Home",
        dom_text=(
            "Just a moment..."
            if blocked_reference
            else "Purpose-built for product development. " * 20
        ),
        meta={},
        screenshot_desktop=b"png-reference-desktop",
        screenshot_mobile=b"png-reference-mobile",
    )

    async def capture_website(url, *, timeout_s=45):
        calls.captures.append(url)
        if url == REF_URL:
            if reference_error is not None:
                raise WebsiteCaptureError(reference_error)
            return reference_capture
        if capture_error is not None:
            raise WebsiteCaptureError(capture_error)
        return main_capture

    capture_mod.WebsiteCaptureError = WebsiteCaptureError
    capture_mod.capture_website = capture_website

    revise_mod = types.ModuleType("app.services.website.revise")

    class RevisionError(Exception):
        pass

    after_capture = SimpleNamespace(
        screenshot_desktop=b"png-after-desktop",
        screenshot_mobile=b"png-after-mobile",
    )
    result_obj = SimpleNamespace(
        html=REVISED_HTML,
        rounds=ROUNDS,
        best_round=2,
        # Deliberately different from the snapshot's stored critique: the row
        # must carry the number the founder already read, not this one.
        scores_before={"overall": 59, "dimensions": {"hierarchy": 51}},
        scores_after=SCORES_AFTER,
        critique_after=CRITIQUE_AFTER,
        capture_after=after_capture,
        fix_prompts=FIX_PROMPTS,
        # The real model, not another namespace: the worker serialises these
        # with `model_dump`, and a stub that merely holds the attribute would
        # let a shape change through unnoticed.
        unsupported_claims=[UNSUPPORTED_CLAIM],
    )

    async def generate_revision(
        capture,
        critique,
        dna,
        *,
        reference=None,
        max_rounds=3,
        target_overall=75,
        organization_id=None,
    ):
        calls.revise = SimpleNamespace(
            capture=capture,
            critique=critique,
            dna=dna,
            reference=reference,
            max_rounds=max_rounds,
            target_overall=target_overall,
            organization_id=organization_id,
        )
        if revision_error is not None:
            raise RevisionError(revision_error)
        return result_obj

    revise_mod.RevisionError = RevisionError
    revise_mod.generate_revision = generate_revision

    store_mod = types.ModuleType("app.services.website.store")
    stored_objects = stored or {}

    async def upload_revision(*, organization_id, revision_id, html, capture):
        calls.upload = SimpleNamespace(
            organization_id=organization_id,
            revision_id=revision_id,
            html=html,
            capture=capture,
        )
        if upload_error is not None:
            raise upload_error
        base = f"website/{organization_id}/revisions/{revision_id}"
        return {
            "html": f"{base}/revision.html",
            "desktop": f"{base}/desktop.png",
            "mobile": f"{base}/mobile.png",
        }

    async def read_stored(path):
        calls.reads.append(path)
        return stored_objects[path]

    store_mod.upload_revision = upload_revision
    store_mod.read_stored = read_stored

    monkeypatch.setitem(sys.modules, "app.services.website", pkg)
    monkeypatch.setitem(sys.modules, "app.services.website.capture", capture_mod)
    monkeypatch.setitem(sys.modules, "app.services.website.revise", revise_mod)
    monkeypatch.setitem(sys.modules, "app.services.website.store", store_mod)
    calls.page = main_capture
    calls.reference_page = reference_capture
    calls.after_capture = after_capture
    calls.result = result_obj
    return calls


# ---------------------------------------------------------------------------
# Fixtures and row factories
# ---------------------------------------------------------------------------

@pytest.fixture
def authed_client(app):
    from fastapi.testclient import TestClient

    app.dependency_overrides[get_current_org] = lambda: {"org_id": ORG, "role": "owner"}
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.pop(get_current_org, None)


def _client_as(app, org_id: str, role: str):
    from fastapi.testclient import TestClient

    app.dependency_overrides[get_current_org] = lambda: {"org_id": org_id, "role": role}
    return TestClient(app)


@pytest.fixture
def clear_overrides(app):
    try:
        yield
    finally:
        app.dependency_overrides.pop(get_current_org, None)


def _fake_billing(monkeypatch, balance: int = 10_000) -> list:
    deductions = []
    monkeypatch.setattr(
        website_api, "get_credit_balance", lambda org_id: (balance, balance, "founder")
    )
    monkeypatch.setattr(
        website_api,
        "deduct_credits",
        lambda org_id, credits: deductions.append((str(org_id), credits)),
    )
    return deductions


def _capture_spawn(monkeypatch) -> list:
    spawned = []

    def _spawn(coro, name, *, on_failure=None):
        spawned.append(SimpleNamespace(name=name, on_failure=on_failure))
        coro.close()
        return SimpleNamespace()

    monkeypatch.setattr(website_api, "spawn", _spawn)
    return spawned


def _complete_snapshot(**overrides) -> dict:
    row = {
        "id": SNAP,
        "organization_id": ORG,
        "project_id": PROJECT,
        "url": URL,
        "reference_url": None,
        "reference_screenshot_path": None,
        "final_url": URL,
        "title": "Acme — Pricing",
        "status": "complete",
        "screenshot_desktop_path": f"website/{ORG}/{SNAP}/desktop.png",
        "screenshot_mobile_path": f"website/{ORG}/{SNAP}/mobile.png",
        "critique": CRITIQUE,
        "document_id": None,
        "dom_chars": 1_234,
        "credits_charged": 1_750,
        "error_message": None,
        "created_at": "2026-08-15T10:00:00+00:00",
        "completed_at": "2026-08-15T10:03:00+00:00",
    }
    row.update(overrides)
    return row


def _queued_revision(**overrides) -> dict:
    row = {
        "id": REV,
        "organization_id": ORG,
        "project_id": PROJECT,
        "snapshot_id": SNAP,
        "status": "queued",
        "rounds": 0,
        "best_round": None,
        "scores_before": {},
        "scores_after": {},
        "critique_after": None,
        "fix_prompts": [],
        "html_path": None,
        "screenshot_desktop_path": None,
        "screenshot_mobile_path": None,
        "credits_charged": 5_000,
        "error_message": None,
        "created_at": "2026-08-16T09:00:00+00:00",
        "completed_at": None,
    }
    row.update(overrides)
    return row


def _complete_revision(**overrides) -> dict:
    base = f"website/{ORG}/revisions/{REV}"
    fields = {
        "status": "complete",
        "rounds": 2,
        "best_round": 2,
        "scores_before": {
            "overall": 62,
            "dimensions": {"hierarchy": 55, "credibility": 70},
        },
        "scores_after": SCORES_AFTER,
        "critique_after": CRITIQUE_AFTER,
        "fix_prompts": FIX_PROMPTS,
        "html_path": f"{base}/revision.html",
        "screenshot_desktop_path": f"{base}/desktop.png",
        "screenshot_mobile_path": f"{base}/mobile.png",
        "completed_at": "2026-08-16T09:07:00+00:00",
    }
    fields.update(overrides)
    return _queued_revision(**fields)


# ---------------------------------------------------------------------------
# Pricing
# ---------------------------------------------------------------------------

def test_the_price_is_5000_credits():
    """The published price, pinned: $1.00 of COGS at the 80% margin."""
    assert website_revision_credits() == 5_000


# ---------------------------------------------------------------------------
# Creating a revision
# ---------------------------------------------------------------------------

def test_unauthenticated_is_refused_before_any_query(app, monkeypatch):
    from fastapi.testclient import TestClient

    admin = _install(monkeypatch)
    response = TestClient(app).post(
        "/api/website/revision", json={"snapshot_id": SNAP}
    )

    assert response.status_code in (401, 403), response.text
    assert not admin.calls


def test_a_foreign_check_is_a_404_with_nothing_charged(authed_client, monkeypatch):
    admin = _install(monkeypatch, {"website_snapshots": [
        _complete_snapshot(organization_id=OTHER_ORG)
    ]})
    spawned = _capture_spawn(monkeypatch)
    deductions = _fake_billing(monkeypatch)

    response = authed_client.post(
        "/api/website/revision", json={"snapshot_id": SNAP}
    )

    assert response.status_code == 404, response.text
    assert not deductions
    assert not admin.store.get("page_revisions")
    assert not spawned


def test_an_unfinished_check_is_a_409_with_a_sentence(authed_client, monkeypatch):
    admin = _install(monkeypatch, {"website_snapshots": [
        _complete_snapshot(status="judging", critique=None)
    ]})
    spawned = _capture_spawn(monkeypatch)
    deductions = _fake_billing(monkeypatch)

    response = authed_client.post(
        "/api/website/revision", json={"snapshot_id": SNAP}
    )

    assert response.status_code == 409, response.text
    assert "hasn't finished" in response.json()["detail"]
    assert not deductions
    assert not admin.store.get("page_revisions")
    assert not spawned


def test_an_unaffordable_revision_is_a_402_with_nothing_created(
    authed_client, monkeypatch
):
    admin = _install(monkeypatch, {"website_snapshots": [_complete_snapshot()]})
    spawned = _capture_spawn(monkeypatch)
    deductions = _fake_billing(monkeypatch, balance=100)

    response = authed_client.post(
        "/api/website/revision", json={"snapshot_id": SNAP}
    )

    assert response.status_code == 402, response.text
    assert "Not enough credits" in response.json()["detail"]
    assert not deductions
    assert not admin.store.get("page_revisions")
    assert not spawned


def test_a_revision_is_created_charged_and_spawned(authed_client, monkeypatch):
    admin = _install(monkeypatch, {"website_snapshots": [_complete_snapshot()]})
    spawned = _capture_spawn(monkeypatch)
    deductions = _fake_billing(monkeypatch, balance=10_000)

    response = authed_client.post(
        "/api/website/revision", json={"snapshot_id": SNAP}
    )

    assert response.status_code == 200, response.text
    row = response.json()
    assert row["status"] == "queued"
    assert row["snapshot_id"] == SNAP
    assert row["project_id"] == PROJECT, "the check's workspace must ride along"
    assert row["credits_charged"] == website_revision_credits()
    for heavy in ("scores_before", "scores_after", "critique_after", "fix_prompts"):
        assert heavy not in row, f"the create response carried {heavy}"
    assert deductions == [(ORG, website_revision_credits())]
    assert [s.name for s in spawned] == ["page_revision"]
    assert spawned[0].on_failure is not None
    assert len(admin.store["page_revisions"]) == 1


# ---------------------------------------------------------------------------
# The worker, with every website service mocked at the import boundary
# ---------------------------------------------------------------------------

async def test_the_worker_revises_uploads_and_completes(monkeypatch):
    admin = _install(monkeypatch, {
        "website_snapshots": [_complete_snapshot()],
        "page_revisions": [_queued_revision()],
        "design_gallery": [{
            "id": GALLERY,
            "organization_id": ORG,
            "snapshot_id": SNAP,
            "design_md": "# Design DNA\n",
        }],
    })
    calls = _install_services(monkeypatch)

    await revision_tasks.run_page_revision(REV, ORG)

    row = admin.store["page_revisions"][0]
    assert row["status"] == "complete", row.get("error_message")
    assert row["rounds"] == 2
    assert row["best_round"] == 2
    # The before comes from the check's stored critique — overall plus each
    # dimension — not from the revision loop's own scores_before.
    assert row["scores_before"] == {
        "overall": 62,
        "dimensions": {"hierarchy": 55, "credibility": 70},
    }
    assert row["scores_after"] == SCORES_AFTER
    assert row["critique_after"] == CRITIQUE_AFTER
    assert row["fix_prompts"] == FIX_PROMPTS
    # What the new page claims that the founder's page never claimed, stored as
    # plain rows so the bundle and the UI can both read it. Serialised here
    # rather than passed through, because a model object would not survive the
    # round trip to Postgres.
    assert row["unsupported_claims"] == [
        {
            "kind": "certification",
            "text": "SOC 2",
            "quote": "soc 2 type ii report available under nda.",
        }
    ]
    base = f"website/{ORG}/revisions/{REV}"
    assert row["html_path"] == f"{base}/revision.html"
    assert row["screenshot_desktop_path"] == f"{base}/desktop.png"
    assert row["screenshot_mobile_path"] == f"{base}/mobile.png"
    assert row["completed_at"]

    # The loop was driven from the row, not from re-derived inputs: the
    # re-fetched page, the stored critique, the gallery's DNA, no reference.
    assert calls.captures == [URL]
    assert calls.revise.capture is calls.page
    assert calls.revise.critique == CRITIQUE
    assert calls.revise.dna is not None
    assert calls.revise.dna["id"] == GALLERY
    assert calls.revise.reference is None
    assert calls.revise.organization_id == ORG

    # What was stored is the winning round's page and its own re-render.
    assert calls.upload.organization_id == ORG
    assert calls.upload.revision_id == REV
    assert calls.upload.html == REVISED_HTML
    assert calls.upload.capture is calls.after_capture


async def test_a_missing_gallery_row_means_dna_is_none_not_a_failure(monkeypatch):
    admin = _install(monkeypatch, {
        "website_snapshots": [_complete_snapshot()],
        "page_revisions": [_queued_revision()],
    })
    calls = _install_services(monkeypatch)

    await revision_tasks.run_page_revision(REV, ORG)

    row = admin.store["page_revisions"][0]
    assert row["status"] == "complete", row.get("error_message")
    assert calls.revise.dna is None


async def test_the_admired_site_rides_the_revision_too(monkeypatch):
    admin = _install(monkeypatch, {
        "website_snapshots": [_complete_snapshot(reference_url=REF_URL)],
        "page_revisions": [_queued_revision()],
    })
    calls = _install_services(monkeypatch)

    await revision_tasks.run_page_revision(REV, ORG)

    row = admin.store["page_revisions"][0]
    assert row["status"] == "complete", row.get("error_message")
    assert calls.captures == [URL, REF_URL], "both addresses must be captured, in order"
    assert calls.revise.reference is calls.reference_page


async def test_a_blocked_reference_fails_the_revision_like_the_check(monkeypatch):
    """The bot-wall floor from the check applies verbatim to the revision."""
    admin = _install(monkeypatch, {
        "website_snapshots": [_complete_snapshot(reference_url=REF_URL)],
        "page_revisions": [_queued_revision()],
    })
    calls = _install_services(monkeypatch, blocked_reference=True)

    await revision_tasks.run_page_revision(REV, ORG)

    row = admin.store["page_revisions"][0]
    assert row["status"] == "failed", "the row would spin forever"
    assert row["error_message"].startswith("We couldn't read the site you admire — ")
    assert "blocked automated readers" in row["error_message"]
    assert calls.revise is None, "the loop ran against a CAPTCHA reference"


async def test_a_reference_capture_failure_names_the_admired_site(monkeypatch):
    message = "We couldn't reach that page — it took longer than 45 seconds to answer."
    admin = _install(monkeypatch, {
        "website_snapshots": [_complete_snapshot(reference_url=REF_URL)],
        "page_revisions": [_queued_revision()],
    })
    calls = _install_services(monkeypatch, reference_error=message)

    await revision_tasks.run_page_revision(REV, ORG)

    row = admin.store["page_revisions"][0]
    assert row["status"] == "failed"
    assert row["error_message"] == (
        "We couldn't read the site you admire — " + message
    )
    assert calls.revise is None


async def test_an_original_refetch_failure_lands_the_capture_sentence(monkeypatch):
    message = "We couldn't reach that page — it took longer than 45 seconds to answer."
    admin = _install(monkeypatch, {
        "website_snapshots": [_complete_snapshot()],
        "page_revisions": [_queued_revision()],
    })
    calls = _install_services(monkeypatch, capture_error=message)

    await revision_tasks.run_page_revision(REV, ORG)

    row = admin.store["page_revisions"][0]
    assert row["status"] == "failed", "the row would spin forever"
    assert row["error_message"] == message
    assert "WebsiteCaptureError" not in row["error_message"]
    assert calls.revise is None, "the loop ran without its page"
    assert row["html_path"] is None


async def test_a_revision_error_lands_its_message_on_the_row(monkeypatch):
    message = "The revised page never cleared the bar. Try again in a few minutes."
    admin = _install(monkeypatch, {
        "website_snapshots": [_complete_snapshot()],
        "page_revisions": [_queued_revision()],
    })
    calls = _install_services(monkeypatch, revision_error=message)

    await revision_tasks.run_page_revision(REV, ORG)

    row = admin.store["page_revisions"][0]
    assert row["status"] == "failed"
    assert row["error_message"] == message
    assert "RevisionError" not in row["error_message"]
    assert calls.upload is None, "a failed loop stored a page anyway"


async def test_an_unfinished_snapshot_fails_with_a_sentence(monkeypatch):
    admin = _install(monkeypatch, {
        "website_snapshots": [_complete_snapshot(status="judging", critique=None)],
        "page_revisions": [_queued_revision()],
    })
    calls = _install_services(monkeypatch)

    await revision_tasks.run_page_revision(REV, ORG)

    row = admin.store["page_revisions"][0]
    assert row["status"] == "failed"
    assert row["error_message"] == revision_tasks.UNFINISHED_CHECK_MESSAGE
    assert calls.captures == [], "an unfinished check's page was fetched"


async def test_an_unexpected_failure_is_generic_on_the_row_and_full_in_the_logs(
    monkeypatch,
):
    admin = _install(monkeypatch, {
        "website_snapshots": [_complete_snapshot()],
        "page_revisions": [_queued_revision()],
    })
    _install_services(monkeypatch, upload_error=RuntimeError("bucket ACL denied"))

    await revision_tasks.run_page_revision(REV, ORG)

    row = admin.store["page_revisions"][0]
    assert row["status"] == "failed"
    assert row["error_message"] == revision_tasks.GENERIC_FAILURE_MESSAGE
    assert "RuntimeError" not in row["error_message"]
    assert "ACL" not in row["error_message"]


async def test_the_worker_never_runs_another_orgs_row(monkeypatch):
    """Org id comes from the authenticated route; the worker re-checks it."""
    admin = _install(monkeypatch, {
        "website_snapshots": [_complete_snapshot()],
        "page_revisions": [_queued_revision(organization_id=OTHER_ORG)],
    })
    calls = _install_services(monkeypatch)

    await revision_tasks.run_page_revision(REV, ORG)

    row = admin.store["page_revisions"][0]
    assert row["status"] in ("queued", "failed")
    assert row["html_path"] is None, "a cross-tenant revision executed"
    assert calls.captures == [], "another org's page was fetched"


# ---------------------------------------------------------------------------
# Reading revisions
# ---------------------------------------------------------------------------

def test_get_by_id_is_org_scoped(authed_client, monkeypatch):
    _install(monkeypatch, {"page_revisions": [
        _complete_revision(organization_id=OTHER_ORG)
    ]})

    response = authed_client.get(f"/api/website/revision/{REV}")

    assert response.status_code == 404, response.text


def test_get_by_id_carries_the_verdict_and_the_fix_prompts(authed_client, monkeypatch):
    _install(monkeypatch, {"page_revisions": [_complete_revision()]})

    response = authed_client.get(f"/api/website/revision/{REV}")

    assert response.status_code == 200, response.text
    row = response.json()
    assert row["critique_after"] == CRITIQUE_AFTER
    assert row["fix_prompts"] == FIX_PROMPTS
    assert row["scores_before"]["overall"] == 62
    assert row["scores_after"]["overall"] == 81


def test_the_list_lifts_the_overalls_and_drops_the_bodies(authed_client, monkeypatch):
    newer = _queued_revision(
        id=str(uuid4()), created_at="2026-08-16T11:00:00+00:00"
    )
    _install(monkeypatch, {"page_revisions": [
        _complete_revision(),
        newer,
        _complete_revision(id=str(uuid4()), organization_id=OTHER_ORG),
    ]})

    response = authed_client.get(f"/api/website/revision?snapshot_id={SNAP}")

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["total"] == 2, "another org's revision leaked into the list"
    assert body["items"][0]["id"] == newer["id"], "not newest first"
    for item in body["items"]:
        for heavy in ("scores_before", "scores_after", "critique_after", "fix_prompts"):
            assert heavy not in item, f"the list carried {heavy} bodies"
    by_id = {item["id"]: item for item in body["items"]}
    assert by_id[REV]["overall_before"] == 62
    assert by_id[REV]["overall_after"] == 81
    assert by_id[newer["id"]]["overall_after"] is None


# ---------------------------------------------------------------------------
# Passthroughs: the stored page and images, with their real content types
# ---------------------------------------------------------------------------

def _stored_objects() -> dict[str, bytes]:
    rev_base = f"website/{ORG}/revisions/{REV}"
    snap_base = f"website/{ORG}/{SNAP}"
    return {
        f"{rev_base}/revision.html": REVISED_HTML.encode("utf-8"),
        f"{rev_base}/desktop.png": b"png-after-desktop",
        f"{rev_base}/mobile.png": b"png-after-mobile",
        f"{snap_base}/desktop.png": b"png-before-desktop",
        f"{snap_base}/mobile.png": b"png-before-mobile",
        f"{snap_base}/reference-desktop.png": b"png-reference-desktop",
    }


def test_the_html_passthrough_requires_auth(app, monkeypatch):
    from fastapi.testclient import TestClient

    admin = _install(monkeypatch, {"page_revisions": [_complete_revision()]})
    _install_services(monkeypatch, stored=_stored_objects())

    response = TestClient(app).get(f"/api/website/revision/{REV}/html")

    assert response.status_code in (401, 403), response.text
    assert not admin.calls


def test_the_html_passthrough_streams_the_stored_page(authed_client, monkeypatch):
    _install(monkeypatch, {"page_revisions": [_complete_revision()]})
    calls = _install_services(monkeypatch, stored=_stored_objects())

    response = authed_client.get(f"/api/website/revision/{REV}/html")

    assert response.status_code == 200, response.text
    assert response.headers["content-type"].startswith("text/html")
    assert response.text == REVISED_HTML
    assert calls.reads == [f"website/{ORG}/revisions/{REV}/revision.html"]


def test_the_html_passthrough_is_org_scoped(authed_client, monkeypatch):
    _install(monkeypatch, {"page_revisions": [
        _complete_revision(organization_id=OTHER_ORG)
    ]})
    _install_services(monkeypatch, stored=_stored_objects())

    response = authed_client.get(f"/api/website/revision/{REV}/html")

    assert response.status_code == 404, response.text


def test_an_unfinished_revisions_page_is_a_409(authed_client, monkeypatch):
    _install(monkeypatch, {"page_revisions": [_queued_revision()]})
    calls = _install_services(monkeypatch, stored=_stored_objects())

    response = authed_client.get(f"/api/website/revision/{REV}/html")

    assert response.status_code == 409, response.text
    assert "isn't finished" in response.json()["detail"]
    assert calls.reads == []


# ---------------------------------------------------------------------------
# The takeaway bundle: the page and the rules that came with it
# ---------------------------------------------------------------------------

BUNDLE_HTML = (
    "<html><head><style>body{font-family:Manrope,sans-serif;color:#14294a;"
    "background:#f8fbff}.cta{background:#286cf0;border-radius:10px;"
    "box-shadow:0 1px 2px rgba(20,41,74,.08)}.note{color:#286cf0;"
    "border-radius:10px;background:#f8fbff}</style></head><body>"
    "<h1>Prior authorization, answered before the patient leaves</h1>"
    "<p>Acme works inside your EHR so clinical staff stop faxing health "
    "plans. Built for hospital revenue teams and their patient care "
    "coordinators.</p></body></html>"
)


def _bundle_store(**snapshot_overrides) -> dict:
    return {
        "page_revisions": [_complete_revision()],
        "website_snapshots": [_complete_snapshot(**snapshot_overrides)],
        "design_gallery": [{
            "id": GALLERY,
            "organization_id": ORG,
            "snapshot_id": SNAP,
            "url": URL,
            "characterization": "A default Bootstrap theme with the buttons recoloured.",
            "summary": "Stock components, no type scale, three competing blues.",
        }],
    }


def _bundle_stored() -> dict[str, bytes]:
    stored = _stored_objects()
    stored[f"website/{ORG}/revisions/{REV}/revision.html"] = BUNDLE_HTML.encode()
    return stored


def _open_bundle(response) -> dict[str, str]:
    import io
    import zipfile

    with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
        return {
            name: archive.read(name).decode("utf-8")
            for name in archive.namelist()
        }


def test_the_bundle_requires_auth(app, monkeypatch):
    from fastapi.testclient import TestClient

    admin = _install(monkeypatch, _bundle_store())
    _install_services(monkeypatch, stored=_bundle_stored())

    response = TestClient(app).get(f"/api/website/revision/{REV}/bundle")

    assert response.status_code in (401, 403), response.text
    assert not admin.calls


def test_the_bundle_carries_the_page_and_its_guide(authed_client, monkeypatch):
    """The founder's request: the new page, downloadable, with the branding
    guide beside it so it survives the next person who edits it."""
    _install(monkeypatch, _bundle_store())
    _install_services(monkeypatch, stored=_bundle_stored())

    response = authed_client.get(f"/api/website/revision/{REV}/bundle")

    assert response.status_code == 200, response.text
    assert response.headers["content-type"] == "application/zip"
    files = _open_bundle(response)
    assert set(files) == {"index.html", "STYLE_GUIDE.md"}
    assert files["index.html"] == BUNDLE_HTML


def test_the_guide_describes_the_page_it_ships_with(authed_client, monkeypatch):
    """Derived, not written alongside: every value in the guide must be one
    the delivered file actually contains, or the two drift apart the first
    time the page is regenerated."""
    _install(monkeypatch, _bundle_store())
    _install_services(monkeypatch, stored=_bundle_stored())

    guide = _open_bundle(
        authed_client.get(f"/api/website/revision/{REV}/bundle")
    )["STYLE_GUIDE.md"]

    # Colours and faces read out of the file.
    assert "#286cf0" in guide and "#f8fbff" in guide
    assert "Manrope" in guide
    assert "10px" in guide  # the radius the page uses
    # A colour used once is detail, not a token.
    assert "#14294a" not in guide

    # The category the copy establishes, argued rather than decorated.
    assert "Health and clinical software" in guide
    assert "compliance" in guide.lower() or "audit" in guide.lower()

    # The measured verdict and where the design came from.
    assert "81" in guide
    assert "Bootstrap theme" in guide

    assert "Saido Labs LLC" in guide


def test_the_guide_reads_the_copy_not_the_markup(authed_client, monkeypatch):
    """A page whose CSS is full of category words but whose copy says nothing
    must not be handed a category. Class names are not an argument."""
    markup_only = (
        "<html><head><style>.patient-card{color:#286cf0}.clinical-grid{}"
        ".health-hero{}.hospital-nav{}.ehr-panel{color:#286cf0}</style></head>"
        "<body><h1>We make software.</h1></body></html>"
    )
    stored = _stored_objects()
    stored[f"website/{ORG}/revisions/{REV}/revision.html"] = markup_only.encode()
    _install(monkeypatch, _bundle_store())
    _install_services(monkeypatch, stored=stored)

    guide = _open_bundle(
        authed_client.get(f"/api/website/revision/{REV}/bundle")
    )["STYLE_GUIDE.md"]

    assert "Health and clinical software" not in guide
    assert "General" in guide


def test_the_bundle_is_named_for_the_founders_own_domain(authed_client, monkeypatch):
    _install(monkeypatch, _bundle_store())
    _install_services(monkeypatch, stored=_bundle_stored())

    response = authed_client.get(f"/api/website/revision/{REV}/bundle")

    assert (
        response.headers["content-disposition"]
        == 'attachment; filename="acme.example-redesign.zip"'
    )


def test_a_hostile_url_cannot_break_out_of_the_download_header(
    authed_client, monkeypatch
):
    """The filename lands in a response header. A quote or a newline there is
    a response-splitting bug, not a cosmetic one — and the URL is founder
    input."""
    _install(monkeypatch, _bundle_store(url='https://ac"me\r\nX-Evil: 1.example/'))
    _install_services(monkeypatch, stored=_bundle_stored())

    disposition = authed_client.get(
        f"/api/website/revision/{REV}/bundle"
    ).headers["content-disposition"]

    assert '"' not in disposition.removeprefix('attachment; filename="').rstrip('"')
    assert "\r" not in disposition and "\n" not in disposition
    assert "X-Evil" not in disposition


def test_the_bundle_is_org_scoped(authed_client, monkeypatch):
    store = _bundle_store()
    store["page_revisions"] = [_complete_revision(organization_id=OTHER_ORG)]
    _install(monkeypatch, store)
    _install_services(monkeypatch, stored=_bundle_stored())

    response = authed_client.get(f"/api/website/revision/{REV}/bundle")

    assert response.status_code == 404, response.text


def test_an_unfinished_revision_has_nothing_to_bundle(authed_client, monkeypatch):
    store = _bundle_store()
    store["page_revisions"] = [_queued_revision()]
    _install(monkeypatch, store)
    calls = _install_services(monkeypatch, stored=_bundle_stored())

    response = authed_client.get(f"/api/website/revision/{REV}/bundle")

    assert response.status_code == 409, response.text
    assert "isn't finished" in response.json()["detail"]
    assert calls.reads == []


def test_a_missing_gallery_row_costs_a_section_not_the_download(
    authed_client, monkeypatch
):
    """The gallery row is a byproduct whose failure is only ever a log line,
    so a revision can legitimately exist without one."""
    store = _bundle_store()
    store["design_gallery"] = []
    _install(monkeypatch, store)
    _install_services(monkeypatch, stored=_bundle_stored())

    response = authed_client.get(f"/api/website/revision/{REV}/bundle")

    assert response.status_code == 200, response.text
    guide = _open_bundle(response)["STYLE_GUIDE.md"]
    assert "Where this came from" not in guide
    assert "Health and clinical software" in guide, "the rest of the guide survived"


def test_another_orgs_gallery_row_never_reaches_the_guide(authed_client, monkeypatch):
    store = _bundle_store()
    store["design_gallery"][0]["organization_id"] = OTHER_ORG
    store["design_gallery"][0]["characterization"] = "Leaked characterization."
    _install(monkeypatch, store)
    _install_services(monkeypatch, stored=_bundle_stored())

    guide = _open_bundle(
        authed_client.get(f"/api/website/revision/{REV}/bundle")
    )["STYLE_GUIDE.md"]

    assert "Leaked" not in guide


def test_the_bundle_charges_nothing(authed_client, monkeypatch):
    """Both files are already-produced artifacts. A founder who paid for the
    revision pays nothing to take it away."""
    _install(monkeypatch, _bundle_store())
    _install_services(monkeypatch, stored=_bundle_stored())
    deductions = _fake_billing(monkeypatch)

    assert (
        authed_client.get(f"/api/website/revision/{REV}/bundle").status_code == 200
    )
    assert deductions == []


def test_a_screenshot_request_must_name_a_stored_image(authed_client, monkeypatch):
    _install(monkeypatch, {
        "page_revisions": [_complete_revision()],
        "website_snapshots": [_complete_snapshot()],
    })
    calls = _install_services(monkeypatch, stored=_stored_objects())

    for_revision = authed_client.get(
        f"/api/website/revision/{REV}/screenshot?which=sideways"
    )
    assert for_revision.status_code == 400, for_revision.text
    detail = for_revision.json()["detail"]
    assert "after_desktop" in detail and "after_mobile" in detail

    for_check = authed_client.get(
        f"/api/website/check/{SNAP}/screenshot?which=after_desktop"
    )
    assert for_check.status_code == 400, for_check.text
    detail = for_check.json()["detail"]
    assert "desktop" in detail and "reference" in detail

    assert calls.reads == [], "an unnamed image was read from storage anyway"


def test_the_after_images_stream_as_png(authed_client, monkeypatch):
    _install(monkeypatch, {"page_revisions": [_complete_revision()]})
    _install_services(monkeypatch, stored=_stored_objects())

    desktop = authed_client.get(
        f"/api/website/revision/{REV}/screenshot?which=after_desktop"
    )
    assert desktop.status_code == 200, desktop.text
    assert desktop.headers["content-type"] == "image/png"
    assert desktop.content == b"png-after-desktop"

    mobile = authed_client.get(
        f"/api/website/revision/{REV}/screenshot?which=after_mobile"
    )
    assert mobile.status_code == 200, mobile.text
    assert mobile.content == b"png-after-mobile"


def test_the_before_images_stream_from_the_check(authed_client, monkeypatch):
    _install(monkeypatch, {"website_snapshots": [_complete_snapshot(
        reference_screenshot_path=f"website/{ORG}/{SNAP}/reference-desktop.png"
    )]})
    _install_services(monkeypatch, stored=_stored_objects())

    desktop = authed_client.get(
        f"/api/website/check/{SNAP}/screenshot?which=desktop"
    )
    assert desktop.status_code == 200, desktop.text
    assert desktop.headers["content-type"] == "image/png"
    assert desktop.content == b"png-before-desktop"

    reference = authed_client.get(
        f"/api/website/check/{SNAP}/screenshot?which=reference"
    )
    assert reference.status_code == 200, reference.text
    assert reference.content == b"png-reference-desktop"


def test_an_image_that_was_never_stored_is_a_404(authed_client, monkeypatch):
    """No admired site was named, so there is no reference frame to serve."""
    _install(monkeypatch, {"website_snapshots": [_complete_snapshot()]})
    calls = _install_services(monkeypatch, stored=_stored_objects())

    response = authed_client.get(
        f"/api/website/check/{SNAP}/screenshot?which=reference"
    )

    assert response.status_code == 404, response.text
    assert calls.reads == []


# ---------------------------------------------------------------------------
# /api/admin: the gallery feed becomes before/after-ready
# ---------------------------------------------------------------------------

def _admin_seed() -> dict:
    return {
        "organizations": [
            {"id": ORG, "name": "Acme"},
            {"id": OTHER_ORG, "name": "Zed Labs"},
            {"id": ADMIN_ORG, "name": "Saibyl"},
        ],
        "design_gallery": [
            {
                "id": GALLERY,
                "organization_id": ORG,
                "snapshot_id": SNAP,
                "url": URL,
                "characterization": "Confident developer-tool minimalism",
                "style_tags": ["minimal"],
                "maturity_level": 5,
                "overall_score": 62,
                "screenshot_desktop_path": f"website/{ORG}/{SNAP}/desktop.png",
                "screenshot_mobile_path": f"website/{ORG}/{SNAP}/mobile.png",
                "reference_url": None,
                "created_at": "2026-08-15T10:05:00+00:00",
            },
            {
                "id": GALLERY_2,
                "organization_id": OTHER_ORG,
                "snapshot_id": SNAP_2,
                "url": "https://zed.example",
                "characterization": "Bootstrap defaults",
                "style_tags": [],
                "maturity_level": 2,
                "overall_score": 41,
                "screenshot_desktop_path": f"website/{OTHER_ORG}/{SNAP_2}/desktop.png",
                "screenshot_mobile_path": f"website/{OTHER_ORG}/{SNAP_2}/mobile.png",
                "reference_url": None,
                "created_at": "2026-08-16T09:00:00+00:00",
            },
        ],
        "page_revisions": [
            # An older complete revision, a newer complete one, and a failed
            # one newer still: the feed must carry the newest *complete* one.
            _complete_revision(
                id=str(uuid4()),
                scores_after={"overall": 71},
                created_at="2026-08-16T08:00:00+00:00",
            ),
            _complete_revision(created_at="2026-08-16T09:30:00+00:00"),
            _queued_revision(
                id=str(uuid4()),
                status="failed",
                error_message="Something went wrong.",
                created_at="2026-08-16T10:00:00+00:00",
            ),
        ],
    }


def test_the_admin_feed_carries_the_latest_complete_revision(
    app, clear_overrides, monkeypatch
):
    monkeypatch.setattr(settings, "admin_organization_id", ADMIN_ORG)
    _install(monkeypatch, _admin_seed())
    client = _client_as(app, ADMIN_ORG, "owner")

    response = client.get("/api/admin/design-gallery")

    assert response.status_code == 200, response.text
    items = {item["id"]: item for item in response.json()["items"]}
    assert len(items) == 2

    revised = items[GALLERY]["revision"]
    assert revised is not None, "the feed missed a check with a complete revision"
    assert revised["id"] == REV, "not the latest complete revision"
    assert revised["overall_after"] == 81
    assert revised["screenshot_desktop_path"] == (
        f"website/{ORG}/revisions/{REV}/desktop.png"
    )
    assert set(revised) == {"id", "overall_after", "screenshot_desktop_path"}

    assert items[GALLERY_2]["revision"] is None, (
        "a check with no revision claimed one"
    )


def test_the_admin_detail_carries_the_revision_when_one_exists(
    app, clear_overrides, monkeypatch
):
    monkeypatch.setattr(settings, "admin_organization_id", ADMIN_ORG)
    _install(monkeypatch, _admin_seed())
    client = _client_as(app, ADMIN_ORG, "owner")

    with_revision = client.get(f"/api/admin/design-gallery/{GALLERY}")
    assert with_revision.status_code == 200, with_revision.text
    revised = with_revision.json()["revision"]
    assert revised is not None
    assert revised["id"] == REV
    assert revised["overall_after"] == 81

    without = client.get(f"/api/admin/design-gallery/{GALLERY_2}")
    assert without.status_code == 200, without.text
    assert without.json()["revision"] is None
