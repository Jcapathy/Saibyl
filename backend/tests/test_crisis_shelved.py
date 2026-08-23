"""Crisis is shelved, not deleted (PRD_V3 §7).

`CRISIS_ENABLED` (default false) is the only thing standing between the
shelved surface and the public API. The contract under test:

- Off, a Crisis-configured run is a 404 — not a 403, because a hidden surface
  that answers "forbidden" has confirmed it exists — and the request touches
  the database not at all.
- The request-body type still accepts the value. Were it removed from the
  Literal, validation would answer 422 before the guard could fire, and the
  code would have been deleted rather than shelved.
- On, the guard steps aside and the request proceeds to the ordinary checks.
- Founder and Marketing runs never see the guard.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.api import simulations as simulations_api
from app.core.auth import get_current_org
from app.core.config import settings

ORG = "11111111-1111-1111-1111-111111111111"
PROJECT = "33333333-3333-3333-3333-333333333333"

CRISIS_DETAIL = "Not available."


class _Admin:
    """Just enough Supabase to prove whether the route touched the database.

    Every query resolves to "no rows", so any request that gets past the
    crisis guard lands on the project-ownership 404 — whose detail differs
    from the guard's, which is how the tests tell the two apart.
    """

    def __init__(self):
        self.queries = 0

    def table(self, _name: str):
        self.queries += 1
        return self

    def select(self, *_args, **_kwargs):
        return self

    def eq(self, *_args):
        return self

    def single(self):
        return self

    # What `core.database.maybe_one` calls. The real `.single()` raises on zero
    # rows; `.maybe_single()` is the one that answers with nothing.
    def maybe_single(self):
        return self

    def execute(self):
        return SimpleNamespace(data=None)


def _install(monkeypatch) -> _Admin:
    admin = _Admin()
    monkeypatch.setattr(simulations_api, "get_supabase_admin", lambda: admin)
    return admin


def _body(lens: str | None) -> dict:
    body = {
        "name": "Launch reaction",
        "prediction_goal": "How does the market react to the launch?",
        "project_id": PROJECT,
        "platforms": ["twitter_x"],
    }
    if lens is not None:
        body["lens"] = lens
    return body


@pytest.fixture
def authed_client(app):
    from fastapi.testclient import TestClient

    app.dependency_overrides[get_current_org] = lambda: {"org_id": ORG}
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.pop(get_current_org, None)


def test_a_crisis_run_is_a_404_by_default(authed_client, monkeypatch):
    """404 with the flag's detail, and the database was never asked anything."""
    admin = _install(monkeypatch)

    response = authed_client.post("/api/simulations", json=_body("crisis"))

    assert response.status_code == 404, response.text
    assert response.json()["detail"] == CRISIS_DETAIL
    assert admin.queries == 0, "a hidden surface ran a query before refusing"


def test_the_flag_lets_a_crisis_request_past_the_guard(authed_client, monkeypatch):
    """With CRISIS_ENABLED the request reaches the ordinary checks.

    It still fails here — the stand-in database has no project — but it fails
    *there*, with that 404's detail, which is the proof the crisis guard did
    not fire.
    """
    monkeypatch.setattr(settings, "crisis_enabled", True)
    admin = _install(monkeypatch)

    response = authed_client.post("/api/simulations", json=_body("crisis"))

    assert response.json()["detail"] != CRISIS_DETAIL, response.text
    assert admin.queries > 0, "the request never reached the project lookup"


@pytest.mark.parametrize("lens", ["founder", "marketing", None])
def test_other_runs_never_see_the_guard(authed_client, monkeypatch, lens):
    """The flag gates Crisis alone; everything else proceeds as before."""
    admin = _install(monkeypatch)

    response = authed_client.post("/api/simulations", json=_body(lens))

    assert response.json()["detail"] != CRISIS_DETAIL, response.text
    assert admin.queries > 0, "the request never reached the project lookup"
