"""The analysis artifact can be recomposed without paying for the run again.

The artifact is derived data, composed once when a run finishes; a copy or
vocabulary fix shipped later reaches nothing already composed (PRD_V3 §8.2).
`POST /api/simulations/{id}/analysis/rebuild` recomposes it from the stored
measurements. The contract under test:

- Ownership first: a run the organisation does not own is a 404 and the
  builder is never invoked — a rebuild writes to the artifact table, so
  getting this wrong is a cross-tenant write.
- A successful call hands `build_simulation_analysis` exactly the run and the
  organisation from the request, nothing remembered or guessed.
- No organisation, no route: unauthenticated is refused before any query.
"""
from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from app.api import analysis as analysis_api
from app.core.auth import get_current_org

ORG = "11111111-1111-1111-1111-111111111111"
OTHER_ORG = "22222222-2222-2222-2222-222222222222"
SIM = "55555555-5555-5555-5555-555555555555"


# ---------------------------------------------------------------------------
# A Supabase stand-in that filters like `_owned_simulation` queries
# ---------------------------------------------------------------------------

class _Query:
    def __init__(self, rows: list[dict], calls: list):
        self._rows = rows
        self._calls = calls
        self._filters: dict[str, object] = {}

    def select(self, *_args, **_kwargs):
        return self

    def eq(self, column: str, value):
        self._filters[column] = value
        return self

    def limit(self, _n: int):
        return self

    def execute(self):
        self._calls.append(dict(self._filters))
        matched = [
            row
            for row in self._rows
            if all(row.get(k) == v for k, v in self._filters.items())
        ]
        return SimpleNamespace(data=[dict(row) for row in matched])


class _Admin:
    def __init__(self, rows: list[dict]):
        self.rows = rows
        self.calls: list = []

    def table(self, _name: str):
        return _Query(self.rows, self.calls)


def _sim_row(**overrides) -> dict:
    row = {
        "id": SIM,
        "name": "Launch reaction",
        "status": "completed",
        "organization_id": ORG,
    }
    row.update(overrides)
    return row


def _install(monkeypatch, rows: list[dict]) -> _Admin:
    admin = _Admin(rows)
    monkeypatch.setattr(analysis_api, "get_supabase_admin", lambda: admin)
    return admin


class _Builder:
    """Stands in for `build_simulation_analysis`, recording what it was asked."""

    def __init__(self):
        self.calls: list[tuple[str, str]] = []

    async def __call__(self, simulation_id: str, organization_id: str):
        self.calls.append((simulation_id, organization_id))
        return SimpleNamespace(
            schema_version=4,
            generated_at=datetime.now(UTC),
            objections=[object()] * 3,
            flashpoints=[object()],
            sentiment_timeline=[object()] * 5,
            quality=SimpleNamespace(confidence="moderate"),
        )


def _install_builder(monkeypatch) -> _Builder:
    builder = _Builder()
    monkeypatch.setattr(analysis_api, "build_simulation_analysis", builder)
    return builder


@pytest.fixture
def authed_client(app):
    from fastapi.testclient import TestClient

    app.dependency_overrides[get_current_org] = lambda: {"org_id": ORG}
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.pop(get_current_org, None)


# ---------------------------------------------------------------------------
# Ownership — getting this wrong is a cross-tenant write
# ---------------------------------------------------------------------------

def test_another_orgs_run_is_a_404_and_never_rebuilt(authed_client, monkeypatch):
    _install(monkeypatch, [_sim_row(organization_id=OTHER_ORG)])
    builder = _install_builder(monkeypatch)

    response = authed_client.post(f"/api/simulations/{SIM}/analysis/rebuild")

    assert response.status_code == 404, response.text
    assert builder.calls == [], "the artifact was rebuilt for a foreign org"


def test_a_missing_run_is_a_404(authed_client, monkeypatch):
    _install(monkeypatch, [])
    builder = _install_builder(monkeypatch)

    response = authed_client.post(f"/api/simulations/{SIM}/analysis/rebuild")

    assert response.status_code == 404, response.text
    assert builder.calls == []


# ---------------------------------------------------------------------------
# The rebuild itself
# ---------------------------------------------------------------------------

def test_a_rebuild_invokes_the_builder_with_the_requests_run_and_org(
    authed_client, monkeypatch
):
    _install(monkeypatch, [_sim_row()])
    builder = _install_builder(monkeypatch)

    response = authed_client.post(f"/api/simulations/{SIM}/analysis/rebuild")

    assert response.status_code == 200, response.text
    assert builder.calls == [(SIM, ORG)]

    body = response.json()
    assert body["simulation_id"] == SIM
    assert body["build_status"] == "complete"
    assert body["schema_version"] == 4
    assert body["objections"] == 3
    assert body["flashpoints"] == 1
    assert body["rounds"] == 5
    assert body["confidence"] == "moderate"


# ---------------------------------------------------------------------------
# The route, as the app actually registers it
# ---------------------------------------------------------------------------

def test_the_route_requires_an_organisation(app, monkeypatch):
    """No dependency override: unauthenticated must not reach the table."""
    from fastapi.testclient import TestClient

    admin = _install(monkeypatch, [_sim_row()])
    builder = _install_builder(monkeypatch)

    response = TestClient(app).post(f"/api/simulations/{SIM}/analysis/rebuild")

    assert response.status_code in (401, 403), response.text
    assert admin.calls == []
    assert builder.calls == []
