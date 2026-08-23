"""No route checked `role` before spending credits or destroying data.

`get_current_org` has always returned `role`. Until now the only readers were
three routes in `organizations.py` and two in `billing.py`. Every other route
took the auth dict and never looked.

**What it cost.** A `viewer` — an account whose entire name is the promise made
to whoever assigned it — could order a 5,000-credit page revision, a
3,000-credit family-office shortlist, a 6,000-credit clearance search, start a
full simulation, or call `POST /api/gtm/purge` and delete every candidate and
contact the organisation had ever paid to discover. None of it was recoverable
and none of it required anything but a login.

**Two gates, because there are two acts.** Spending is owner/admin/member: a
member is the ordinary invited teammate, `InviteMemberBody` offers no other
working role, and a member who cannot spend cannot use the product. Destruction
is owner/admin: the asymmetry is recoverability — a mistaken 3,000 credits buys
something and can be topped up, a mistaken `DELETE /simulations/{id}` cascades
through reports, sections, events and agents and undoes nothing. The full
argument is in `core/auth.py`; this file is where it is enforced.

The last block is the one that matters over time. Spot-checking today's routes
proves nothing about the route somebody adds next month, so it walks every
registered route and fails on any ungated `DELETE`, and on any handler that
reaches `deduct_credits` without a gate above it.
"""
from __future__ import annotations

import inspect

import pytest
from fastapi.routing import APIRoute

from app.core.auth import (
    DESTRUCTIVE_ROLES,
    SPENDING_ROLES,
    get_current_org,
    require_can_destroy,
    require_can_spend,
)

ORG = "11111111-1111-1111-1111-111111111111"
USER = "33333333-3333-3333-3333-333333333333"


def _client_as(app, role: str | None):
    """A caller carrying `role`, or carrying none at all when `role` is None."""
    from fastapi.testclient import TestClient

    auth: dict = {"org_id": ORG, "user": {"id": USER}, "org": {"plan": "growth"}}
    if role is not None:
        auth["role"] = role
    app.dependency_overrides[get_current_org] = lambda: auth
    return TestClient(app)


@pytest.fixture(autouse=True)
def _clear_overrides(app):
    yield
    app.dependency_overrides.pop(get_current_org, None)


# Every route that spends the balance, with a body good enough to get past
# parsing. None of these should reach a handler under a refusing role, so the
# bodies never have to be realistic — only well-formed.
SPENDING_ROUTES = [
    ("POST", "/api/simulations/11111111-1111-1111-1111-111111111111/start", {}),
    # Five routes that spend without ever touching the credit ledger, which is
    # why the `deduct_credits(` scan at the bottom of this file could not see
    # them and why they shipped ungated.
    #
    # `/prepare` makes one `llm_fast` call per agent, up to 1,000 at
    # enterprise. `/reports/generate` drives the most expensive main-model stage
    # in the product — a fifth of a standard run's cost — and is billed inside
    # the run's price, so it charges nothing at the route. Each interview is two
    # calls on Saibyl's account and the batch takes up to 1,000 agent ids.
    ("POST", "/api/simulations/11111111-1111-1111-1111-111111111111/prepare", {}),
    ("POST", "/api/reports/generate", {"simulation_id": ORG}),
    (
        "POST", "/api/simulations/11111111-1111-1111-1111-111111111111/interview",
        {"prompt": "hi", "agent_id": "a-1"},
    ),
    (
        "POST",
        "/api/simulations/11111111-1111-1111-1111-111111111111/interview/batch",
        {"prompt": "hi", "agent_ids": ["a-1"]},
    ),
    (
        "POST",
        "/api/simulations/11111111-1111-1111-1111-111111111111/interview/by-persona",
        {"prompt": "hi", "persona_type": "IT director"},
    ),
    ("POST", "/api/clearance", {"item": "Saibyl", "tier": "COMPREHENSIVE"}),
    ("POST", "/api/website/check", {"project_id": ORG, "url": "https://acme.example"}),
    ("POST", "/api/website/revision", {"snapshot_id": ORG}),
    ("POST", "/api/capital/shortlist", {"project_id": ORG}),
    ("POST", "/api/answer-pack", {"simulation_id": ORG}),
    ("POST", "/api/messaging-doc", {"simulation_id": ORG}),
    ("POST", "/api/outbound", {"simulation_id": ORG}),
    ("POST", "/api/icp/synthesize", {"project_id": ORG}),
    ("POST", "/api/inoculation/11111111-1111-1111-1111-111111111111/assets", {}),
    ("POST", "/api/gtm/discover", {"icp_profile_id": ORG}),
    ("POST", "/api/billing/topup", {"amount_cents": 1000}),
    ("POST", "/api/billing/flash-report", {"report_type": "flash"}),
]

DESTRUCTIVE_ROUTES = [
    ("POST", "/api/gtm/purge", {"confirm": True}),
    ("DELETE", "/api/simulations/11111111-1111-1111-1111-111111111111", None),
    ("DELETE", "/api/reports/11111111-1111-1111-1111-111111111111", None),
    ("DELETE", "/api/documents/11111111-1111-1111-1111-111111111111", None),
    ("DELETE", "/api/projects/11111111-1111-1111-1111-111111111111", None),
    ("DELETE", "/api/packs/11111111-1111-1111-1111-111111111111", None),
    ("DELETE", "/api/icp/11111111-1111-1111-1111-111111111111", None),
    ("DELETE", "/api/gtm/candidates/11111111-1111-1111-1111-111111111111", None),
    ("DELETE", "/api/inoculation/assets/11111111-1111-1111-1111-111111111111", None),
]


def _call(client, method: str, path: str, body):
    if method == "DELETE":
        return client.delete(path)
    return client.post(path, json=body if body is not None else {})


# ---------------------------------------------------------------------------
# A viewer does neither. That is what the word means.
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(("method", "path", "body"), SPENDING_ROUTES)
def test_a_viewer_cannot_spend_the_organisations_credits(app, method, path, body):
    """The defect: 5,000 credits, 3,000 credits, a full run — on a read-only
    account, with nothing between the request and the charge."""
    response = _call(_client_as(app, "viewer"), method, path, body)

    assert response.status_code == 403, f"{method} {path}: {response.text}"
    assert "view-only" in response.json()["detail"]


@pytest.mark.parametrize(("method", "path", "body"), DESTRUCTIVE_ROUTES)
def test_a_viewer_cannot_destroy_what_the_organisation_paid_for(
    app, method, path, body
):
    """`POST /gtm/purge` is the worst of these: org-wide, irreversible, and its
    only guard was `confirm=true` in a body the caller writes."""
    response = _call(_client_as(app, "viewer"), method, path, body)

    assert response.status_code == 403, f"{method} {path}: {response.text}"
    assert "owner or admin" in response.json()["detail"]


# ---------------------------------------------------------------------------
# A member works. A member does not delete.
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(("method", "path", "body"), DESTRUCTIVE_ROUTES)
def test_a_member_cannot_destroy(app, method, path, body):
    """The judgement call, pinned.

    A member may spend because spending is using the product and the balance
    can be topped up. A member may not delete because nothing puts a deleted
    run back — the money and the artifact go together and neither returns.
    """
    response = _call(_client_as(app, "member"), method, path, body)

    assert response.status_code == 403, f"{method} {path}: {response.text}"


# Admission is asserted at the gate rather than through the route. Past the
# gate a handler reaches real storage, so driving it through the app would
# assert about network reachability instead of about the policy — and the
# refusal tests above already prove which gate each route is wired to.

@pytest.mark.parametrize("role", ["owner", "admin", "member"])
async def test_a_member_is_not_locked_out_of_the_product(role):
    """The other half of that call, and the reason spending is not owner/admin.

    `InviteMemberBody` offers exactly `member` and `viewer`, and `member` is the
    default. A member who cannot spend cannot run a simulation, order a check,
    or build a pack — which is the whole product — and every invitation becomes
    decorative.
    """
    auth = {"org_id": ORG, "role": role, "user": {"id": USER}}

    assert await require_can_spend(auth) is auth


@pytest.mark.parametrize("role", ["owner", "admin"])
async def test_an_owner_or_admin_may_destroy(role):
    auth = {"org_id": ORG, "role": role, "user": {"id": USER}}

    assert await require_can_destroy(auth) is auth


# ---------------------------------------------------------------------------
# Default-deny
# ---------------------------------------------------------------------------

def test_the_roles_are_an_allowlist_not_a_viewer_denylist():
    """`organization_members.role` is a bare TEXT column with no CHECK
    constraint, so an unrecognised string is storable. A denylist would wave
    it through; an allowlist refuses it."""
    assert SPENDING_ROLES == ("owner", "admin", "member")
    assert DESTRUCTIVE_ROLES == ("owner", "admin")


def test_a_role_nobody_recognises_is_refused(app):
    response = _call(_client_as(app, "billing-contact"), "POST", "/api/clearance",
                     {"item": "Saibyl"})
    assert response.status_code == 403, response.text


def test_an_auth_dict_with_no_role_is_refused_not_crashed_on(app):
    """403, not 500.

    A caller that assembled an auth dict without a role has proved nothing
    about its permissions, so the honest answer is a refusal — and `auth["role"]`
    would have made "we cannot tell" read as our fault. This is also the shape
    every pre-existing test fixture had, which is why two of them had to be
    changed deliberately when the gates landed.
    """
    response = _call(_client_as(app, None), "POST", "/api/clearance", {"item": "S"})

    assert response.status_code == 403, response.text


def test_a_refusal_is_logged(app):
    """A gate that refuses silently cannot tell you it is being probed."""
    from structlog.testing import capture_logs

    with capture_logs() as logs:
        _call(_client_as(app, "viewer"), "POST", "/api/gtm/purge", {"confirm": True})

    refusals = [e for e in logs if e["event"] == "role_refused"]
    assert refusals, "the refusal never reached the log"
    assert refusals[0]["act"] == "destroy"
    assert refusals[0]["role"] == "viewer"
    assert refusals[0]["org_id"] == ORG


# ---------------------------------------------------------------------------
# The invariant — the only part of this file that protects the next route
# ---------------------------------------------------------------------------

def _gates(route: APIRoute) -> set:
    """Every dependency callable in this route's chain."""
    found: set = set()

    def walk(dependant) -> None:
        if dependant.call is not None:
            found.add(dependant.call)
        for sub in dependant.dependencies:
            walk(sub)

    for dep in route.dependant.dependencies:
        walk(dep)
    return found


def _is_gated(route: APIRoute, gate) -> bool:
    """Gated by the shared dependency, or by an equivalent check in the handler.

    `organizations.py` and `billing.py` predate the dependencies and check
    `auth["role"]` inline against the same `("owner", "admin")` pair. Those
    checks are correct; rewriting working code to satisfy a test would be the
    test choosing the shape of the codebase. So both forms count, and the
    invariant is "this route consults the role", not "this route imports my
    helper".
    """
    if gate in _gates(route):
        return True
    try:
        source = inspect.getsource(route.endpoint)
    except (OSError, TypeError):
        return False
    return 'auth["role"]' in source or "require_platform_admin" in source


def _routes():
    from app.main import create_app

    return [r for r in create_app().routes if isinstance(r, APIRoute)]


def test_every_delete_route_in_the_app_is_role_gated():
    """The rule that catches the next one somebody writes.

    A DELETE that any authenticated account can call is the defect this file
    exists for, and there were eight of them. Scanning every registered router
    means the ninth fails here rather than in production.
    """
    ungated = [
        f"{sorted(r.methods - {'HEAD', 'OPTIONS'})[0]} {r.path}"
        for r in _routes()
        if "DELETE" in r.methods and not _is_gated(r, require_can_destroy)
    ]

    assert not ungated, f"DELETE routes anyone can call: {ungated}"


def test_no_handler_reaches_deduct_credits_without_a_spending_gate():
    """Static, so it does not depend on somebody remembering to add a case.

    Reads each route handler's own source. The four routes whose spend happens
    one call deeper are named below, because source scanning stops at the
    handler body and a check that quietly covers less than it claims is worse
    than no check.
    """
    ungated = []
    for route in _routes():
        try:
            source = inspect.getsource(route.endpoint)
        except (OSError, TypeError):
            continue
        if "deduct_credits(" not in source:
            continue
        if not _is_gated(route, require_can_spend):
            ungated.append(f"{sorted(route.methods)[0]} {route.path}")

    assert not ungated, f"routes that spend with no role check: {ungated}"


@pytest.mark.parametrize("path", [
    # `run_discovery` deducts; the handler only calls it.
    "/api/gtm/discover",
    # Stripe Checkout sessions — money leaves the org's card, not its balance,
    # so `deduct_credits` never appears in these.
    "/api/billing/topup",
    "/api/billing/flash-report",
    # Charged by `reconcile_run_cost` at the tail of the spawned worker.
    "/api/simulations/{id}/start",
    # These five spend model calls on Saibyl's account and never reach the
    # credit ledger at all — the report is billed inside the run's price, and
    # preparation and interviews are not metered anywhere. A source scan for
    # `deduct_credits(` will never find them, so they are listed by hand.
    "/api/simulations/{id}/prepare",
    "/api/reports/generate",
    "/api/simulations/{id}/interview",
    "/api/simulations/{id}/interview/batch",
    "/api/simulations/{id}/interview/by-persona",
])
def test_the_routes_whose_spend_is_one_call_deeper_are_gated_too(path):
    """The hand-maintained tail of the scan above, listed rather than inferred."""
    matches = [
        r for r in _routes() if r.path == path and "POST" in r.methods
    ]
    assert matches, f"{path} is no longer a POST route — update this list"
    assert _is_gated(matches[0], require_can_spend), f"{path} is ungated"


def test_the_gates_are_distinguishable_in_a_traceback():
    """Three identical `_dependency` closures in a stack trace help nobody."""
    assert require_can_spend.__name__ == "require_can_spend"
    assert require_can_destroy.__name__ == "require_can_destroy"
