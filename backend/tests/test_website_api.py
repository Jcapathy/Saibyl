"""Website checks (PRD_V3 §4a–c): create, charge, execute, list.

The contract under test:

- Unauthenticated requests never reach the database.
- A workspace the org does not own is a 404 before anything is charged.
- A submission that is not a web address is refused with a plain sentence.
- A check the balance cannot cover is a 402 with nothing created.
- Creating a check deducts `website_check_credits()` at create, records it on
  the row, and spawns the worker with an on_failure handler.
- The worker captures the page, stores its screenshots, runs the critics,
  stores the page's text as a document with material_kind 'website_url', and
  lands `complete` with the critique and the document id on the row. A failure
  lands as `failed` with a sentence a founder can read — never a spinner with
  no ending.
- Reads are org-scoped, and the list never carries critique bodies.

The website services (`app.services.website.*`) are built in parallel and
mocked here at the import boundary: the worker imports them lazily, so these
tests seed `sys.modules` with stand-ins and run whether or not the real
modules exist yet. `documents.store_upload` is real code, faked by attribute.
"""
from __future__ import annotations

import sys
import types
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.api import documents as documents_api
from app.api import website as website_api
from app.core.auth import get_current_org
from app.services.billing.agent_pricing import website_check_credits
from app.workers import website_tasks

ORG = "11111111-1111-1111-1111-111111111111"
OTHER_ORG = "22222222-2222-2222-2222-222222222222"
PROJECT = "33333333-3333-3333-3333-333333333333"
SNAP = "44444444-4444-4444-4444-444444444444"
DOC = "55555555-5555-5555-5555-555555555555"

URL = "https://acme.example/pricing"


# ---------------------------------------------------------------------------
# A Supabase stand-in that honours column selection and records every call
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

    def in_(self, column: str, values):
        self._in[column] = tuple(values)
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
    monkeypatch.setattr(website_api, "get_supabase_admin", lambda: admin)
    monkeypatch.setattr(website_tasks, "get_supabase_admin", lambda: admin)
    return admin


def _capture_spawn(monkeypatch) -> list:
    spawned = []

    def _spawn(coro, name, *, on_failure=None):
        spawned.append(SimpleNamespace(name=name, on_failure=on_failure))
        coro.close()
        return SimpleNamespace()

    monkeypatch.setattr(website_api, "spawn", _spawn)
    return spawned


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


@pytest.fixture
def authed_client(app):
    from fastapi.testclient import TestClient

    app.dependency_overrides[get_current_org] = lambda: {"org_id": ORG}
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.pop(get_current_org, None)


def _owned_project() -> dict:
    return {"id": PROJECT, "organization_id": ORG}


# ---------------------------------------------------------------------------
# Pricing
# ---------------------------------------------------------------------------

def test_the_price_is_1750_credits():
    """The published price, pinned: $0.35 of COGS at the 80% margin."""
    assert website_check_credits() == 1_750


# ---------------------------------------------------------------------------
# Creating a check
# ---------------------------------------------------------------------------

def test_unauthenticated_is_refused_before_any_query(app, monkeypatch):
    from fastapi.testclient import TestClient

    admin = _install(monkeypatch)
    response = TestClient(app).post(
        "/api/website/check", json={"project_id": PROJECT, "url": URL}
    )

    assert response.status_code in (401, 403), response.text
    assert not admin.calls


def test_a_foreign_workspace_is_a_404_with_nothing_charged(
    authed_client, monkeypatch
):
    admin = _install(monkeypatch, {"projects": [
        {"id": PROJECT, "organization_id": OTHER_ORG}
    ]})
    spawned = _capture_spawn(monkeypatch)
    deductions = _fake_billing(monkeypatch)

    response = authed_client.post(
        "/api/website/check", json={"project_id": PROJECT, "url": URL}
    )

    assert response.status_code == 404, response.text
    assert not deductions
    assert not admin.store.get("website_snapshots")
    assert not spawned


def test_a_non_web_address_is_refused_with_a_sentence(authed_client, monkeypatch):
    admin = _install(monkeypatch, {"projects": [_owned_project()]})
    spawned = _capture_spawn(monkeypatch)
    deductions = _fake_billing(monkeypatch)

    response = authed_client.post(
        "/api/website/check",
        json={"project_id": PROJECT, "url": "ftp://acme.example/pricing"},
    )

    assert response.status_code == 400, response.text
    assert "http" in response.json()["detail"]
    assert not deductions
    assert not admin.store.get("website_snapshots")
    assert not spawned


def test_an_unaffordable_check_is_a_402_with_nothing_created(
    authed_client, monkeypatch
):
    admin = _install(monkeypatch, {"projects": [_owned_project()]})
    spawned = _capture_spawn(monkeypatch)
    deductions = _fake_billing(monkeypatch, balance=100)

    response = authed_client.post(
        "/api/website/check", json={"project_id": PROJECT, "url": URL}
    )

    assert response.status_code == 402, response.text
    assert "Not enough credits" in response.json()["detail"]
    assert not deductions
    assert not admin.store.get("website_snapshots")
    assert not spawned


def test_a_check_is_created_charged_and_spawned(authed_client, monkeypatch):
    admin = _install(monkeypatch, {"projects": [_owned_project()]})
    spawned = _capture_spawn(monkeypatch)
    deductions = _fake_billing(monkeypatch, balance=10_000)

    response = authed_client.post(
        "/api/website/check", json={"project_id": PROJECT, "url": URL}
    )

    assert response.status_code == 200, response.text
    row = response.json()
    assert row["status"] == "queued"
    assert row["url"] == URL
    assert row["credits_charged"] == website_check_credits()
    assert "critique" not in row
    assert deductions == [(ORG, website_check_credits())]
    assert [s.name for s in spawned] == ["website_check"]
    assert spawned[0].on_failure is not None
    assert len(admin.store["website_snapshots"]) == 1


# ---------------------------------------------------------------------------
# Reading checks
# ---------------------------------------------------------------------------

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


def _stored_snapshot(**overrides) -> dict:
    row = {
        "id": SNAP,
        "organization_id": ORG,
        "project_id": PROJECT,
        "url": URL,
        "final_url": URL,
        "title": "Acme — Pricing",
        "status": "complete",
        "screenshot_desktop_path": f"{ORG}/{SNAP}/desktop.png",
        "screenshot_mobile_path": f"{ORG}/{SNAP}/mobile.png",
        "critique": CRITIQUE,
        "document_id": DOC,
        "dom_chars": 1_234,
        "credits_charged": 1_750,
        "error_message": None,
        "created_at": "2026-08-15T10:00:00+00:00",
        "completed_at": "2026-08-15T10:03:00+00:00",
    }
    row.update(overrides)
    return row


def test_get_by_id_is_org_scoped(authed_client, monkeypatch):
    _install(monkeypatch, {"website_snapshots": [
        _stored_snapshot(organization_id=OTHER_ORG)
    ]})

    response = authed_client.get(f"/api/website/check/{SNAP}")

    assert response.status_code == 404, response.text


def test_get_by_id_returns_the_critique_when_complete(authed_client, monkeypatch):
    _install(monkeypatch, {"website_snapshots": [_stored_snapshot()]})

    response = authed_client.get(f"/api/website/check/{SNAP}")

    assert response.status_code == 200, response.text
    row = response.json()
    assert row["critique"] == CRITIQUE
    assert row["document_id"] == DOC


def test_the_list_carries_the_score_but_not_the_critique(authed_client, monkeypatch):
    newer = _stored_snapshot(
        id=str(uuid4()),
        status="queued",
        critique=None,
        document_id=None,
        completed_at=None,
        created_at="2026-08-16T09:00:00+00:00",
    )
    _install(monkeypatch, {"website_snapshots": [
        _stored_snapshot(),
        newer,
        _stored_snapshot(id=str(uuid4()), organization_id=OTHER_ORG),
    ]})

    response = authed_client.get("/api/website/check")

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["total"] == 2, "another org's check leaked into the list"
    assert [item["id"] for item in body["items"]][0] == newer["id"], "not newest first"
    for item in body["items"]:
        assert "critique" not in item, "the list carried a critique body"
    scores = {item["id"]: item["overall_score"] for item in body["items"]}
    assert scores[SNAP] == 62
    assert scores[newer["id"]] is None


# ---------------------------------------------------------------------------
# The worker, with every website service mocked at the import boundary
# ---------------------------------------------------------------------------

DOM_TEXT = "Acme helps teams ship faster. Start free, upgrade when it sticks. " * 30


def _install_services(
    monkeypatch,
    *,
    capture_error: str | Exception | None = None,
    upload_error: Exception | None = None,
    critic_error: str | Exception | None = None,
):
    """Seed sys.modules with website-service stand-ins.

    The worker imports the services inside `run_website_check`, so entries
    seeded here are what it gets — whether or not the real modules exist yet.
    `capture_error` / `critic_error` as a string raise the service's own
    founder-readable exception with that message; as an exception instance
    they raise it as-is, which is how the generic path is exercised.
    """
    calls = SimpleNamespace(capture=None, upload=None, critics=None)

    pkg = types.ModuleType("app.services.website")
    pkg.__path__ = []

    capture_mod = types.ModuleType("app.services.website.capture")

    class WebsiteCaptureError(Exception):
        pass

    capture_obj = SimpleNamespace(
        url=URL,
        final_url="https://acme.example/pricing/",
        title="Acme — Pricing",
        dom_text=DOM_TEXT,
        meta={"description": "Acme ships your team's work faster."},
        screenshot_desktop=b"png-desktop",
        screenshot_mobile=b"png-mobile",
    )

    async def capture_website(url, *, timeout_s=45):
        calls.capture = (url, timeout_s)
        if isinstance(capture_error, BaseException):
            raise capture_error
        if capture_error is not None:
            raise WebsiteCaptureError(capture_error)
        return capture_obj

    capture_mod.WebsiteCaptureError = WebsiteCaptureError
    capture_mod.capture_website = capture_website

    store_mod = types.ModuleType("app.services.website.store")

    async def upload_screenshots(*, organization_id, snapshot_id, capture):
        calls.upload = SimpleNamespace(
            organization_id=organization_id,
            snapshot_id=snapshot_id,
            capture=capture,
        )
        if upload_error is not None:
            raise upload_error
        return {
            "desktop": f"{organization_id}/{snapshot_id}/desktop.png",
            "mobile": f"{organization_id}/{snapshot_id}/mobile.png",
        }

    store_mod.upload_screenshots = upload_screenshots

    critics_mod = types.ModuleType("app.services.website.critics")

    class CriticError(Exception):
        pass

    critique_obj = SimpleNamespace(model_dump=lambda: CRITIQUE)

    async def run_critic_gauntlet(capture, *, reference=None, organization_id=None):
        calls.critics = SimpleNamespace(
            capture=capture, reference=reference, organization_id=organization_id
        )
        if isinstance(critic_error, BaseException):
            raise critic_error
        if critic_error is not None:
            raise CriticError(critic_error)
        return critique_obj

    critics_mod.CriticError = CriticError
    critics_mod.run_critic_gauntlet = run_critic_gauntlet

    monkeypatch.setitem(sys.modules, "app.services.website", pkg)
    monkeypatch.setitem(sys.modules, "app.services.website.capture", capture_mod)
    monkeypatch.setitem(sys.modules, "app.services.website.store", store_mod)
    monkeypatch.setitem(sys.modules, "app.services.website.critics", critics_mod)
    calls.page = capture_obj
    return calls


def _capture_store_upload(monkeypatch) -> list:
    """Fake `documents.store_upload`, recording what the worker composed.

    The worker imports it lazily from `app.api.documents`, so patching the
    attribute on that module is the whole seam — the real ingestion path never
    runs here.
    """
    stored = []

    async def fake_store_upload(
        *, project_id, org_id, file, material_kind="own", source_url=None, title=None
    ):
        content = await file.read()
        stored.append(SimpleNamespace(
            project_id=project_id,
            org_id=org_id,
            filename=file.filename,
            content=content.decode("utf-8"),
            material_kind=material_kind,
            source_url=source_url,
            title=title,
        ))
        return {"id": DOC}

    monkeypatch.setattr(documents_api, "store_upload", fake_store_upload)
    return stored


def _queued_snapshot(**overrides) -> dict:
    return _stored_snapshot(
        status="queued",
        final_url=None,
        title=None,
        screenshot_desktop_path=None,
        screenshot_mobile_path=None,
        critique=None,
        document_id=None,
        dom_chars=None,
        completed_at=None,
        **overrides,
    )


async def test_the_worker_captures_judges_stores_and_completes(monkeypatch):
    admin = _install(monkeypatch, {"website_snapshots": [_queued_snapshot()]})
    calls = _install_services(monkeypatch)
    stored = _capture_store_upload(monkeypatch)

    await website_tasks.run_website_check(SNAP, ORG)

    row = admin.store["website_snapshots"][0]
    assert row["status"] == "complete", row.get("error_message")
    assert row["critique"] == CRITIQUE
    assert row["document_id"] == DOC
    assert row["completed_at"]
    assert row["final_url"] == calls.page.final_url
    assert row["title"] == "Acme — Pricing"
    assert row["dom_chars"] == len(DOM_TEXT)
    assert row["screenshot_desktop_path"] == f"{ORG}/{SNAP}/desktop.png"
    assert row["screenshot_mobile_path"] == f"{ORG}/{SNAP}/mobile.png"

    # The services were driven from the row, not from re-derived inputs.
    assert calls.capture[0] == URL
    assert calls.upload.organization_id == ORG
    assert calls.upload.snapshot_id == SNAP
    assert calls.upload.capture is calls.page
    assert calls.critics.capture is calls.page
    assert calls.critics.organization_id == ORG

    # The page joined the founder's material through the real intake path.
    assert len(stored) == 1
    doc = stored[0]
    assert doc.material_kind == "website_url"
    assert doc.filename == "website.md"
    assert doc.project_id == PROJECT
    assert doc.org_id == ORG
    assert doc.source_url == calls.page.final_url
    assert "# Acme — Pricing" in doc.content
    assert "Acme ships your team's work faster." in doc.content
    assert "Acme helps teams ship faster." in doc.content


async def test_a_capture_failure_lands_its_message_on_the_row(monkeypatch):
    message = "We couldn't reach that page — it took longer than 45 seconds to answer."
    admin = _install(monkeypatch, {"website_snapshots": [_queued_snapshot()]})
    _install_services(monkeypatch, capture_error=message)
    stored = _capture_store_upload(monkeypatch)

    await website_tasks.run_website_check(SNAP, ORG)

    row = admin.store["website_snapshots"][0]
    assert row["status"] == "failed", "the row would spin forever"
    assert row["error_message"] == message
    assert "WebsiteCaptureError" not in row["error_message"]
    assert row["critique"] is None
    assert row["document_id"] is None
    assert row["screenshot_desktop_path"] is None
    assert not stored


async def test_a_critic_failure_lands_its_message_on_the_row(monkeypatch):
    message = "The critics couldn't finish judging this page. Try again in a few minutes."
    admin = _install(monkeypatch, {"website_snapshots": [_queued_snapshot()]})
    _install_services(monkeypatch, critic_error=message)
    stored = _capture_store_upload(monkeypatch)

    await website_tasks.run_website_check(SNAP, ORG)

    row = admin.store["website_snapshots"][0]
    assert row["status"] == "failed"
    assert row["error_message"] == message
    assert "CriticError" not in row["error_message"]
    # The capture had already landed before the critics failed.
    assert row["screenshot_desktop_path"] == f"{ORG}/{SNAP}/desktop.png"
    assert row["critique"] is None
    assert not stored


async def test_an_unexpected_failure_is_generic_on_the_row_and_full_in_the_logs(
    monkeypatch,
):
    admin = _install(monkeypatch, {"website_snapshots": [_queued_snapshot()]})
    _install_services(monkeypatch, upload_error=RuntimeError("bucket ACL denied"))
    stored = _capture_store_upload(monkeypatch)

    await website_tasks.run_website_check(SNAP, ORG)

    row = admin.store["website_snapshots"][0]
    assert row["status"] == "failed"
    assert row["error_message"] == website_tasks.GENERIC_FAILURE_MESSAGE
    assert "RuntimeError" not in row["error_message"]
    assert "ACL" not in row["error_message"]
    assert not stored


async def test_the_worker_never_runs_another_orgs_row(monkeypatch):
    """Org id comes from the authenticated route; the worker re-checks it."""
    admin = _install(monkeypatch, {"website_snapshots": [
        _queued_snapshot(organization_id=OTHER_ORG)
    ]})
    calls = _install_services(monkeypatch)
    stored = _capture_store_upload(monkeypatch)

    await website_tasks.run_website_check(SNAP, ORG)

    row = admin.store["website_snapshots"][0]
    assert row["status"] in ("queued", "failed")
    assert row["critique"] is None, "a cross-tenant check executed"
    assert row["document_id"] is None
    assert calls.capture is None, "another org's page was fetched"
    assert not stored
