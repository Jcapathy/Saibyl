"""The design gallery and the admired-site reference (PRD_V3 §4).

The contract under test:

- A founder may name a site they admire. The worker captures it too, stores
  its desktop screenshot beside the snapshot's own pair, and hands it to the
  critics as the reference. That capture failing fails the run — with a
  sentence that says which address defeated the check.
- Every completed check distils the page's design into a `design_gallery` row:
  the DNA fields, the capture's style census, the critique's overall score,
  the stored screenshot paths. The distillation failing never fails the run —
  the critique is the paid deliverable; the gallery is the byproduct.
- POST /check accepts `reference_url` with the same shape guard as `url`, and
  the org's own reads carry `reference_url` plus the gallery row's id.
- /api/admin is the platform owner's cross-org feed. It answers only when
  ADMIN_ORGANIZATION_ID names the caller's org and the caller is an owner or
  admin of it; every other caller gets a 404 — never a 403, because a hidden
  surface must not confirm itself by refusing.

The website services are built in parallel and mocked at the import boundary,
exactly as `test_website_api.py` does: the worker imports them lazily, so
these tests seed `sys.modules` with stand-ins.
"""
from __future__ import annotations

import sys
import types
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.api import admin as admin_api
from app.api import documents as documents_api
from app.api import website as website_api
from app.core.auth import get_current_org
from app.core.config import settings
from app.workers import website_tasks

ORG = "11111111-1111-1111-1111-111111111111"
OTHER_ORG = "22222222-2222-2222-2222-222222222222"
ADMIN_ORG = "99999999-9999-9999-9999-999999999999"
PROJECT = "33333333-3333-3333-3333-333333333333"
SNAP = "44444444-4444-4444-4444-444444444444"
DOC = "55555555-5555-5555-5555-555555555555"
GALLERY = "66666666-6666-6666-6666-666666666666"

URL = "https://acme.example/pricing"
REF_URL = "https://linear.example"


# ---------------------------------------------------------------------------
# A Supabase stand-in: filters, ordering, pagination, embeds, and storage
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


class _Bucket:
    def __init__(self, name: str, uploads: list):
        self._name = name
        self._uploads = uploads

    def upload(self, path, content, options=None):
        self._uploads.append(
            SimpleNamespace(
                bucket=self._name, path=path, content=content, options=options
            )
        )


class _Storage:
    def __init__(self, uploads: list):
        self._uploads = uploads

    def from_(self, name: str):
        return _Bucket(name, self._uploads)


class _Admin:
    def __init__(self, store: dict | None = None):
        self.store = store or {}
        self.calls: list = []
        self.uploads: list = []
        self.storage = _Storage(self.uploads)

    def table(self, name: str):
        return _Query(name, self.store, self.calls)


def _install(monkeypatch, store: dict | None = None) -> _Admin:
    admin = _Admin(store)
    monkeypatch.setattr(website_api, "get_supabase_admin", lambda: admin)
    monkeypatch.setattr(website_tasks, "get_supabase_admin", lambda: admin)
    monkeypatch.setattr(admin_api, "get_supabase_admin", lambda: admin)
    return admin


# ---------------------------------------------------------------------------
# Website-service stand-ins at the import boundary
# ---------------------------------------------------------------------------

DOM_TEXT = "Acme helps teams ship faster. Start free, upgrade when it sticks. " * 30

CENSUS = {"fonts": ["Inter"], "colors": ["#111111", "#fafafa"], "buttons": 4}

TOKENS = {"color_primary": "#5B5BD6", "font_heading": "Inter"}

# Six dimensions, per the widened critic panel.
CRITIQUE = {
    "overall_score": 62,
    "page_takeaway": "A tool for teams, but the page never says which teams.",
    "dimensions": [
        {"key": key, "score": 62, "findings": [], "strengths": []}
        for key in (
            "hierarchy",
            "credibility",
            "copy",
            "mobile",
            "accessibility",
            "reference_alignment",
        )
    ],
}


def _install_services(
    monkeypatch,
    *,
    reference_error: str | None = None,
    dna_error: Exception | None = None,
):
    """Seed sys.modules with stand-ins for capture, store, critics, and DNA.

    `reference_error` makes only the admired site's capture fail, with the
    capture service's own founder-readable sentence. `dna_error` makes the DNA
    extraction blow up, which the worker must survive.
    """
    calls = SimpleNamespace(captures=[], upload=None, critics=None, dna=None)

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
        meta={"description": "Acme ships your team's work faster."},
        screenshot_desktop=b"png-desktop",
        screenshot_mobile=b"png-mobile",
        style_census=CENSUS,
    )
    reference_capture = SimpleNamespace(
        url=REF_URL,
        final_url=REF_URL + "/",
        title="Linear — Home",
        # Long enough to clear the worker's blocked-reference floor (a tiny
        # dom_text now reads as a bot wall, per the live linear.app gate).
        dom_text="Purpose-built for product development. " * 20,
        meta={},
        screenshot_desktop=b"png-reference-desktop",
        screenshot_mobile=b"png-reference-mobile",
        style_census={"fonts": ["Inter Display"]},
    )

    async def capture_website(url, *, timeout_s=45):
        calls.captures.append(url)
        if url == REF_URL:
            if reference_error is not None:
                raise WebsiteCaptureError(reference_error)
            return reference_capture
        return main_capture

    capture_mod.WebsiteCaptureError = WebsiteCaptureError
    capture_mod.capture_website = capture_website

    store_mod = types.ModuleType("app.services.website.store")

    async def upload_screenshots(*, organization_id, snapshot_id, capture):
        calls.upload = SimpleNamespace(
            organization_id=organization_id,
            snapshot_id=snapshot_id,
            capture=capture,
        )
        return {
            "desktop": f"website/{organization_id}/{snapshot_id}/desktop.png",
            "mobile": f"website/{organization_id}/{snapshot_id}/mobile.png",
        }

    async def run_off_loop(fn, *args, what: str):
        """The real module runs blocking Supabase storage calls on a thread,
        because the client is synchronous and a multi-megabyte upload on the
        event loop stalls the whole service. The stand-in keeps the signature
        so the worker's reference-screenshot upload takes the same path it
        takes in production."""
        return fn(*args)

    store_mod.upload_screenshots = upload_screenshots
    store_mod.run_off_loop = run_off_loop

    critics_mod = types.ModuleType("app.services.website.critics")

    class CriticError(Exception):
        pass

    critique_obj = SimpleNamespace(model_dump=lambda: CRITIQUE)

    async def run_critic_gauntlet(capture, *, reference=None, organization_id=None):
        calls.critics = SimpleNamespace(
            capture=capture, reference=reference, organization_id=organization_id
        )
        return critique_obj

    critics_mod.CriticError = CriticError
    critics_mod.run_critic_gauntlet = run_critic_gauntlet

    dna_mod = types.ModuleType("app.services.website.design_dna")

    dna_obj = SimpleNamespace(
        characterization="Confident developer-tool minimalism",
        summary="Dark, dense, and typographic, with one violet accent.",
        tokens=SimpleNamespace(model_dump=lambda: TOKENS),
        dos=["Keep the single accent color"],
        donts=["No gradients"],
        style_tags=["minimal", "dark", "typographic"],
        maturity_level=5,
        maturity_rationale="A deliberate palette and a consistent spacing scale.",
        design_md="# Design DNA\n\nConfident developer-tool minimalism.\n",
    )

    async def extract_design_dna(capture, *, organization_id=None):
        calls.dna = SimpleNamespace(capture=capture, organization_id=organization_id)
        if dna_error is not None:
            raise dna_error
        return dna_obj

    dna_mod.extract_design_dna = extract_design_dna

    monkeypatch.setitem(sys.modules, "app.services.website", pkg)
    monkeypatch.setitem(sys.modules, "app.services.website.capture", capture_mod)
    monkeypatch.setitem(sys.modules, "app.services.website.store", store_mod)
    monkeypatch.setitem(sys.modules, "app.services.website.critics", critics_mod)
    monkeypatch.setitem(sys.modules, "app.services.website.design_dna", dna_mod)
    calls.page = main_capture
    calls.reference_page = reference_capture
    calls.dna_obj = dna_obj
    return calls


def _capture_store_upload(monkeypatch) -> list:
    stored = []

    async def fake_store_upload(
        *, project_id, org_id, file, material_kind="own", source_url=None, title=None
    ):
        stored.append(SimpleNamespace(project_id=project_id, org_id=org_id))
        return {"id": DOC}

    monkeypatch.setattr(documents_api, "store_upload", fake_store_upload)
    return stored


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


def _queued_snapshot(**overrides) -> dict:
    row = {
        "id": SNAP,
        "organization_id": ORG,
        "project_id": PROJECT,
        "url": URL,
        "reference_url": None,
        "reference_screenshot_path": None,
        "final_url": None,
        "title": None,
        "status": "queued",
        "screenshot_desktop_path": None,
        "screenshot_mobile_path": None,
        "critique": None,
        "document_id": None,
        "dom_chars": None,
        "credits_charged": 1_750,
        "error_message": None,
        "created_at": "2026-08-15T10:00:00+00:00",
        "completed_at": None,
    }
    row.update(overrides)
    return row


def _gallery_row(**overrides) -> dict:
    row = {
        "id": GALLERY,
        "organization_id": ORG,
        "project_id": PROJECT,
        "snapshot_id": SNAP,
        "url": URL,
        "characterization": "Confident developer-tool minimalism",
        "summary": "Dark, dense, and typographic, with one violet accent.",
        "style_tags": ["minimal", "dark"],
        "maturity_level": 5,
        "maturity_rationale": "A deliberate palette and a consistent spacing scale.",
        "tokens": TOKENS,
        "census": CENSUS,
        "design_md": "# Design DNA\n\nConfident developer-tool minimalism.\n",
        "overall_score": 62,
        "screenshot_desktop_path": f"website/{ORG}/{SNAP}/desktop.png",
        "screenshot_mobile_path": f"website/{ORG}/{SNAP}/mobile.png",
        "reference_url": None,
        "created_at": "2026-08-15T10:05:00+00:00",
    }
    row.update(overrides)
    return row


# ---------------------------------------------------------------------------
# The worker: the admired site rides the run
# ---------------------------------------------------------------------------

async def test_the_worker_captures_the_admired_site_and_hands_it_to_the_critics(
    monkeypatch,
):
    admin = _install(monkeypatch, {"website_snapshots": [
        _queued_snapshot(reference_url=REF_URL)
    ]})
    calls = _install_services(monkeypatch)
    _capture_store_upload(monkeypatch)

    await website_tasks.run_website_check(SNAP, ORG)

    row = admin.store["website_snapshots"][0]
    assert row["status"] == "complete", row.get("error_message")
    assert calls.captures == [URL, REF_URL], "both addresses must be captured, in order"
    assert calls.critics.capture is calls.page
    assert calls.critics.reference is calls.reference_page

    # The admired site's desktop frame landed beside the snapshot's own pair.
    expected_path = f"website/{ORG}/{SNAP}/reference-desktop.png"
    assert row["reference_screenshot_path"] == expected_path
    assert len(admin.uploads) == 1
    upload = admin.uploads[0]
    assert upload.bucket == "project-media"
    assert upload.path == expected_path
    assert upload.content == b"png-reference-desktop"
    assert upload.options == {"content-type": "image/png"}

    # The gallery row remembers which site was admired.
    assert admin.store["design_gallery"][0]["reference_url"] == REF_URL


async def test_a_reference_capture_failure_fails_the_run_with_a_founder_sentence(
    monkeypatch,
):
    message = "We couldn't reach that page — it took longer than 45 seconds to answer."
    admin = _install(monkeypatch, {"website_snapshots": [
        _queued_snapshot(reference_url=REF_URL)
    ]})
    calls = _install_services(monkeypatch, reference_error=message)
    stored = _capture_store_upload(monkeypatch)

    await website_tasks.run_website_check(SNAP, ORG)

    row = admin.store["website_snapshots"][0]
    assert row["status"] == "failed", "the row would spin forever"
    assert row["error_message"] == (
        "We couldn't read the site you admire — " + message
    )
    assert "WebsiteCaptureError" not in row["error_message"]
    # The run stopped before anything else happened.
    assert calls.upload is None, "the founder's screenshots were stored anyway"
    assert calls.critics is None, "the critics ran without their reference"
    assert not admin.uploads
    assert not admin.store.get("design_gallery")
    assert not stored


# ---------------------------------------------------------------------------
# The worker: every completed check leaves a gallery row
# ---------------------------------------------------------------------------

async def test_a_completed_check_leaves_a_design_gallery_row(monkeypatch):
    admin = _install(monkeypatch, {"website_snapshots": [_queued_snapshot()]})
    calls = _install_services(monkeypatch)
    _capture_store_upload(monkeypatch)

    await website_tasks.run_website_check(SNAP, ORG)

    snapshot = admin.store["website_snapshots"][0]
    assert snapshot["status"] == "complete", snapshot.get("error_message")
    # No admired site named — the critics judge without a reference.
    assert calls.critics.reference is None

    # The DNA was extracted from the page the critics judged, on the org's tab.
    assert calls.dna.capture is calls.page
    assert calls.dna.organization_id == ORG

    rows = admin.store.get("design_gallery") or []
    assert len(rows) == 1, "the check completed without leaving its gallery row"
    row = rows[0]
    assert row["organization_id"] == ORG
    assert row["project_id"] == PROJECT
    assert row["snapshot_id"] == SNAP
    assert row["url"] == calls.page.final_url
    assert row["characterization"] == calls.dna_obj.characterization
    assert row["summary"] == calls.dna_obj.summary
    assert row["style_tags"] == calls.dna_obj.style_tags
    assert row["maturity_level"] == 5
    assert row["maturity_rationale"] == calls.dna_obj.maturity_rationale
    assert row["tokens"] == TOKENS
    assert row["census"] == CENSUS, "the capture's style census must ride along"
    assert row["design_md"] == calls.dna_obj.design_md
    assert row["overall_score"] == CRITIQUE["overall_score"]
    assert row["screenshot_desktop_path"] == f"website/{ORG}/{SNAP}/desktop.png"
    assert row["screenshot_mobile_path"] == f"website/{ORG}/{SNAP}/mobile.png"
    assert row["reference_url"] is None
    assert row["created_at"]


async def test_a_dna_failure_never_fails_the_founders_check(monkeypatch):
    admin = _install(monkeypatch, {"website_snapshots": [_queued_snapshot()]})
    _install_services(monkeypatch, dna_error=RuntimeError("model refused"))
    stored = _capture_store_upload(monkeypatch)

    await website_tasks.run_website_check(SNAP, ORG)

    row = admin.store["website_snapshots"][0]
    assert row["status"] == "complete", (
        "the paid critique failed because its byproduct did"
    )
    assert row["critique"] == CRITIQUE
    assert row["document_id"] == DOC
    assert row["error_message"] is None
    assert not admin.store.get("design_gallery")
    assert len(stored) == 1, "the page document must still be stored"


# ---------------------------------------------------------------------------
# POST /check: the admired site is accepted, guarded, and stored
# ---------------------------------------------------------------------------

def test_post_check_accepts_and_stores_the_admired_site(authed_client, monkeypatch):
    admin = _install(monkeypatch, {"projects": [
        {"id": PROJECT, "organization_id": ORG}
    ]})
    spawned = _capture_spawn(monkeypatch)
    _fake_billing(monkeypatch)

    response = authed_client.post(
        "/api/website/check",
        json={"project_id": PROJECT, "url": URL, "reference_url": REF_URL},
    )

    assert response.status_code == 200, response.text
    assert response.json()["reference_url"] == REF_URL
    assert admin.store["website_snapshots"][0]["reference_url"] == REF_URL
    assert [s.name for s in spawned] == ["website_check"]


def test_post_check_refuses_a_reference_that_is_not_a_web_address(
    authed_client, monkeypatch
):
    admin = _install(monkeypatch, {"projects": [
        {"id": PROJECT, "organization_id": ORG}
    ]})
    spawned = _capture_spawn(monkeypatch)
    deductions = _fake_billing(monkeypatch)

    response = authed_client.post(
        "/api/website/check",
        json={
            "project_id": PROJECT,
            "url": URL,
            "reference_url": "ftp://linear.example",
        },
    )

    assert response.status_code == 400, response.text
    detail = response.json()["detail"]
    assert "http" in detail
    assert "admire" in detail, "the sentence must say which address is wrong"
    assert not deductions
    assert not admin.store.get("website_snapshots")
    assert not spawned


def test_a_checks_reads_carry_its_gallery_id_and_reference(authed_client, monkeypatch):
    _install(monkeypatch, {
        "website_snapshots": [_queued_snapshot(
            status="complete", reference_url=REF_URL, critique=CRITIQUE
        )],
        "design_gallery": [_gallery_row(reference_url=REF_URL)],
    })

    detail = authed_client.get(f"/api/website/check/{SNAP}")
    assert detail.status_code == 200, detail.text
    assert detail.json()["design_gallery_id"] == GALLERY
    assert detail.json()["reference_url"] == REF_URL

    listing = authed_client.get("/api/website/check")
    assert listing.status_code == 200, listing.text
    item = listing.json()["items"][0]
    assert item["design_gallery_id"] == GALLERY
    assert item["reference_url"] == REF_URL
    assert "critique" not in item


# ---------------------------------------------------------------------------
# /api/admin: hidden unless configured, and only for the platform owner's org
# ---------------------------------------------------------------------------

def _admin_seed() -> dict:
    return {
        "organizations": [
            {"id": ORG, "name": "Acme"},
            {"id": OTHER_ORG, "name": "Zed Labs"},
            {"id": ADMIN_ORG, "name": "Saibyl"},
        ],
        "design_gallery": [
            _gallery_row(),
            _gallery_row(
                id=str(uuid4()),
                organization_id=OTHER_ORG,
                snapshot_id=str(uuid4()),
                url="https://zed.example",
                created_at="2026-08-16T09:00:00+00:00",
            ),
        ],
    }


def test_admin_routes_answer_404_when_no_admin_org_is_configured(
    app, clear_overrides, monkeypatch
):
    monkeypatch.setattr(settings, "admin_organization_id", "")
    admin = _install(monkeypatch, _admin_seed())
    client = _client_as(app, ADMIN_ORG, "owner")

    assert client.get("/api/admin/design-gallery").status_code == 404
    assert client.get(f"/api/admin/design-gallery/{GALLERY}").status_code == 404
    assert not admin.calls, "a hidden route touched the database"


def test_admin_routes_answer_404_for_any_other_org(app, clear_overrides, monkeypatch):
    monkeypatch.setattr(settings, "admin_organization_id", ADMIN_ORG)
    admin = _install(monkeypatch, _admin_seed())
    client = _client_as(app, ORG, "owner")

    response = client.get("/api/admin/design-gallery")

    assert response.status_code == 404, response.text
    assert not admin.calls


def test_admin_routes_answer_404_for_a_plain_member_of_the_admin_org(
    app, clear_overrides, monkeypatch
):
    monkeypatch.setattr(settings, "admin_organization_id", ADMIN_ORG)
    admin = _install(monkeypatch, _admin_seed())
    client = _client_as(app, ADMIN_ORG, "member")

    response = client.get("/api/admin/design-gallery")

    assert response.status_code == 404, response.text
    assert not admin.calls


def test_the_admin_feed_spans_orgs_newest_first_without_the_bodies(
    app, clear_overrides, monkeypatch
):
    monkeypatch.setattr(settings, "admin_organization_id", ADMIN_ORG)
    _install(monkeypatch, _admin_seed())
    client = _client_as(app, ADMIN_ORG, "owner")

    response = client.get("/api/admin/design-gallery")

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["total"] == 2
    assert body["limit"] == 50
    assert body["offset"] == 0
    assert len(body["items"]) == 2

    orgs = {item["organization_id"] for item in body["items"]}
    assert orgs == {ORG, OTHER_ORG}, "the feed must cross tenant lines"
    assert body["items"][0]["url"] == "https://zed.example", "not newest first"

    names = {item["organization_id"]: item["organization_name"]
             for item in body["items"]}
    assert names == {ORG: "Acme", OTHER_ORG: "Zed Labs"}

    for item in body["items"]:
        for heavy in ("design_md", "census", "tokens"):
            assert heavy not in item, f"the feed carried {heavy} bodies"
        assert item["characterization"]
        assert item["maturity_level"] == 5
        assert item["overall_score"] == 62
        assert item["screenshot_desktop_path"]
        assert item["created_at"]


def test_the_admin_detail_carries_the_full_record(app, clear_overrides, monkeypatch):
    monkeypatch.setattr(settings, "admin_organization_id", ADMIN_ORG)
    _install(monkeypatch, _admin_seed())
    client = _client_as(app, ADMIN_ORG, "owner")

    response = client.get(f"/api/admin/design-gallery/{GALLERY}")

    assert response.status_code == 200, response.text
    row = response.json()
    assert row["id"] == GALLERY
    assert row["organization_name"] == "Acme"
    assert row["design_md"].startswith("# Design DNA")
    assert row["census"] == CENSUS
    assert row["tokens"] == TOKENS
    assert row["maturity_rationale"]


def test_the_admin_detail_misses_with_a_plain_sentence(
    app, clear_overrides, monkeypatch
):
    monkeypatch.setattr(settings, "admin_organization_id", ADMIN_ORG)
    _install(monkeypatch, _admin_seed())
    client = _client_as(app, ADMIN_ORG, "owner")

    response = client.get(f"/api/admin/design-gallery/{uuid4()}")

    assert response.status_code == 404, response.text
    assert response.json()["detail"] == "We couldn't find that gallery entry."
