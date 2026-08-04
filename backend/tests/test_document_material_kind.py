"""A material kind must be correctable after upload, and only by a human.

`material_kind` was settable only as a query parameter at upload time, and
`documents` had no PATCH route. Two things followed, and both were live:

- Every document uploaded before the control existed carries NULL, and
  `gather_material` reads NULL as `own`. **Competitor grounding was unreachable
  for every one of those projects.** An adversarial archetype may name a rival
  only from a document marked `competitor` (PRD §4, DECISIONS_V2 §7), and no
  such document could be produced.
- A mislabelled file could only be fixed by deleting and re-uploading it.

The guardrail this route must not weaken: `material_kind` records a *human*
decision, and it is what licenses the model to name a competitor in copy a
founder may publish. Ingestion's own opinion lives in
`material_kind_suggested` / `material_kind_confidence` and must never be
promoted into it — at any confidence, by this route or any other.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest
import structlog
from fastapi import HTTPException

from app.api import documents as documents_api
from app.api.documents import DocumentUpdate, update_document
from app.core.auth import get_current_org

ORG = "11111111-1111-1111-1111-111111111111"
OTHER_ORG = "22222222-2222-2222-2222-222222222222"
PROJECT = "33333333-3333-3333-3333-333333333333"
DOC = "44444444-4444-4444-4444-444444444444"


# ---------------------------------------------------------------------------
# A Supabase stand-in that records what it was filtered on
# ---------------------------------------------------------------------------

class _Query:
    def __init__(self, rows: list[dict], calls: list):
        self._rows = rows
        self._calls = calls
        self._filters: dict[str, object] = {}
        self._op: str | None = None
        self._payload: dict | None = None

    def select(self, *_args, **_kwargs):
        self._op = "select"
        return self

    def update(self, payload: dict):
        self._op = "update"
        self._payload = payload
        return self

    def eq(self, column: str, value):
        self._filters[column] = value
        return self

    def execute(self):
        matched = [
            row
            for row in self._rows
            if all(row.get(k) == v for k, v in self._filters.items())
        ]
        self._calls.append((self._op, dict(self._filters), self._payload))
        if self._op == "update":
            for row in matched:
                row.update(self._payload or {})
        return SimpleNamespace(data=[dict(row) for row in matched])


class _Admin:
    def __init__(self, rows: list[dict]):
        self.rows = rows
        self.calls: list = []

    def table(self, _name: str):
        return _Query(self.rows, self.calls)


def _row(**overrides) -> dict:
    row = {
        "id": DOC,
        "organization_id": ORG,
        "project_id": PROJECT,
        "filename": "rival-pricing.pdf",
        "material_kind": None,
        "material_kind_suggested": None,
        "material_kind_confidence": None,
    }
    row.update(overrides)
    return row


def _install(monkeypatch, rows: list[dict]) -> _Admin:
    admin = _Admin(rows)
    monkeypatch.setattr(documents_api, "get_supabase_admin", lambda: admin)
    return admin


@pytest.fixture(autouse=True)
def capturable_logger(monkeypatch):
    """Make `capture_logs` able to see this module's logger, in any test order.

    `setup_logging()` configures a **new** processors list and `create_app()`
    calls it every time; `capture_logs` mutates whichever list is current *in
    place*. With `cache_logger_on_first_use=True`, a module logger first used
    before the last `create_app()` stays bound to the previous list — it still
    logs, and `capture_logs` still returns `[]`, which is a log assertion that
    passes for the wrong reason.
    """
    monkeypatch.setattr(documents_api, "log", structlog.get_logger(documents_api.__name__))


# ---------------------------------------------------------------------------
# The correction itself
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_a_null_document_can_be_promoted_to_competitor(monkeypatch):
    """The case that unblocks every project that predates the control."""
    admin = _install(monkeypatch, [_row()])

    result = await update_document(
        id=DOC,
        body=DocumentUpdate(material_kind="competitor"),
        auth={"org_id": ORG},
    )

    assert result["material_kind"] == "competitor"
    assert admin.rows[0]["material_kind"] == "competitor"


@pytest.mark.asyncio
async def test_a_mislabelled_document_can_be_demoted(monkeypatch):
    """Both directions matter: a wrongly-labelled competitor licenses a name."""
    admin = _install(monkeypatch, [_row(material_kind="competitor")])

    result = await update_document(
        id=DOC, body=DocumentUpdate(material_kind="own"), auth={"org_id": ORG}
    )

    assert result["material_kind"] == "own"
    assert admin.rows[0]["material_kind"] == "own"


@pytest.mark.asyncio
async def test_a_suggestion_is_never_promoted_into_the_label(monkeypatch):
    """DECISIONS_V2 §7, at the route that would be the easy place to break it.

    A high-confidence classifier suggestion sitting on the row must not change
    what an explicit request writes, and must not survive as a second value
    that later reads as a decision.
    """
    admin = _install(monkeypatch, [
        _row(material_kind_suggested="competitor", material_kind_confidence=0.99)
    ])

    result = await update_document(
        id=DOC, body=DocumentUpdate(material_kind="own"), auth={"org_id": ORG}
    )

    assert result["material_kind"] == "own"
    assert result["material_kind_suggested"] == "competitor"
    written = [payload for op, _f, payload in admin.calls if op == "update"]
    assert written == [{"material_kind": "own"}], written


@pytest.mark.asyncio
async def test_the_change_is_logged_with_both_values(monkeypatch):
    """A competitor label appearing must be reconstructible after the fact.

    `capture_logs`, not `caplog`: structlog is not bound to stdlib logging
    outside `create_app`, so a `caplog` assertion here would pass vacuously.
    """
    _install(monkeypatch, [_row(material_kind="own")])

    with structlog.testing.capture_logs() as logs:
        await update_document(
            id=DOC, body=DocumentUpdate(material_kind="competitor"), auth={"org_id": ORG}
        )

    entry = next(e for e in logs if e["event"] == "document_material_kind_updated")
    assert entry["material_kind_from"] == "own"
    assert entry["material_kind_to"] == "competitor"
    assert entry["document_id"] == DOC
    assert entry["organization_id"] == ORG


@pytest.mark.asyncio
async def test_a_null_previous_value_is_logged_as_own(monkeypatch):
    """NULL reads as `own` everywhere downstream, so it says `own` here too."""
    _install(monkeypatch, [_row(material_kind=None)])

    with structlog.testing.capture_logs() as logs:
        await update_document(
            id=DOC, body=DocumentUpdate(material_kind="market"), auth={"org_id": ORG}
        )

    entry = next(e for e in logs if e["event"] == "document_material_kind_updated")
    assert entry["material_kind_from"] == "own"


# ---------------------------------------------------------------------------
# Org scoping — getting this wrong is a cross-tenant write
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_another_orgs_document_is_a_404_and_is_not_written(monkeypatch):
    admin = _install(monkeypatch, [_row(organization_id=OTHER_ORG, material_kind="own")])

    with pytest.raises(HTTPException) as exc:
        await update_document(
            id=DOC, body=DocumentUpdate(material_kind="competitor"), auth={"org_id": ORG}
        )

    assert exc.value.status_code == 404
    assert admin.rows[0]["material_kind"] == "own", "a cross-tenant write happened"
    assert not [op for op, _f, _p in admin.calls if op == "update"]


@pytest.mark.asyncio
async def test_a_missing_document_is_a_404(monkeypatch):
    _install(monkeypatch, [])

    with pytest.raises(HTTPException) as exc:
        await update_document(
            id=DOC, body=DocumentUpdate(material_kind="own"), auth={"org_id": ORG}
        )

    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_both_the_read_and_the_write_are_org_scoped(monkeypatch):
    """The `eq` on the update is not redundant with the read.

    Every other route in this module scopes both, and dropping it here would
    leave a cross-tenant write one refactor away from being reintroduced.
    """
    admin = _install(monkeypatch, [_row()])

    await update_document(
        id=DOC, body=DocumentUpdate(material_kind="competitor"), auth={"org_id": ORG}
    )

    assert admin.calls, "no query was issued"
    for op, filters, _payload in admin.calls:
        assert filters.get("organization_id") == ORG, (op, filters)
        assert filters.get("id") == DOC, (op, filters)


# ---------------------------------------------------------------------------
# The route, as the app actually registers it
# ---------------------------------------------------------------------------

@pytest.fixture
def authed_client(app, monkeypatch):
    from fastapi.testclient import TestClient

    app.dependency_overrides[get_current_org] = lambda: {"org_id": ORG}
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.pop(get_current_org, None)


def test_the_route_is_registered_as_patch_on_the_document(authed_client, monkeypatch):
    _install(monkeypatch, [_row()])

    response = authed_client.patch(
        f"/api/documents/{DOC}", json={"material_kind": "competitor"}
    )

    assert response.status_code == 200, response.text
    assert response.json()["material_kind"] == "competitor"


@pytest.mark.parametrize("payload", [
    {"material_kind": "rival"},
    {"material_kind": "Competitor"},
    {"material_kind": None},
    {},
])
def test_anything_but_the_three_kinds_is_refused(authed_client, monkeypatch, payload):
    """Including an omitted field: a PATCH that changes nothing must not read
    as a confirmed decision."""
    admin = _install(monkeypatch, [_row()])

    response = authed_client.patch(f"/api/documents/{DOC}", json=payload)

    assert response.status_code == 422, response.text
    assert not [op for op, _f, _p in admin.calls if op == "update"]


def test_the_route_requires_an_organisation(app, monkeypatch):
    """No dependency override: unauthenticated must not reach the table."""
    from fastapi.testclient import TestClient

    admin = _install(monkeypatch, [_row()])
    response = TestClient(app).patch(
        f"/api/documents/{DOC}", json={"material_kind": "competitor"}
    )

    assert response.status_code in (401, 403), response.text
    assert not admin.calls
