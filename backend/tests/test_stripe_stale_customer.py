"""A `stripe_customer_id` from another Stripe account must not block a purchase.

**This defect reached production and cost a real payment attempt**, on
2026-08-27, the day Saibyl first took money.

The founder's org held `cus_V9cLNGxXbbzvOo`, minted while the backend pointed at
a Stripe *sandbox*. When the keys moved to the live account, both checkout paths
kept handing that id to Stripe, because each created a customer only
`if not customer_id` — a stored id was assumed to be a valid one. Stripe
answered `resource_missing`, the request raised, and the founder saw "network
error" in the browser with **no `credit_topups` row** and nothing anywhere to
explain it. The insert is the last step in the function, so its absence is what
located the failure.

There was no way out of it: every retry re-sent the same dead id. Clearing the
column by hand was the only fix, and a paying customer cannot do that.

A customer id is only meaningful for the Stripe account that issued it, and the
account can change beneath us — sandbox to live, a key rotation, a restored
backup. What is pinned here is that a stored id is treated as a hint rather than
a fact: when Stripe says it does not exist, the id is replaced and the checkout
retried once, so the founder sees a Checkout page instead of an error.
"""
from __future__ import annotations

from types import SimpleNamespace
from uuid import uuid4

import pytest
import stripe

from app.services.billing import stripe_service

ORG_ID = uuid4()
STALE = "cus_from_the_sandbox"
FRESH = "cus_minted_on_the_live_account"


def _missing_customer_error() -> stripe.error.InvalidRequestError:
    """Exactly what Stripe returned in production."""
    return stripe.error.InvalidRequestError(
        f"No such customer: '{STALE}'", "customer", code="resource_missing"
    )


class _FakeQuery:
    def __init__(self, table: str, state: SimpleNamespace):
        self._table = table
        self._state = state
        self._payload: dict | None = None
        self._op = "select"

    def select(self, *_a, **_k):
        self._op = "select"
        return self

    def update(self, payload: dict):
        self._op = "update"
        self._payload = payload
        return self

    def insert(self, payload: dict):
        self._op = "insert"
        self._payload = payload
        return self

    def eq(self, *_a, **_k):
        return self

    def single(self):
        return self

    def execute(self):
        if self._op == "update" and self._table == "organizations":
            self._state.org.update(self._payload or {})
            self._state.org_writes.append(dict(self._payload or {}))
        elif self._op == "insert" and self._table == "credit_topups":
            self._state.topup_rows.append(dict(self._payload or {}))
        return SimpleNamespace(data=self._state.org)


class _FakeAdmin:
    def __init__(self, state: SimpleNamespace):
        self._state = state

    def table(self, name: str) -> _FakeQuery:
        return _FakeQuery(name, self._state)


@pytest.fixture
def stripe_env(monkeypatch):
    """Wire a fake Supabase and a scriptable Stripe."""
    state = SimpleNamespace(
        org={"id": str(ORG_ID), "name": "Jesse Crawford", "stripe_customer_id": STALE},
        org_writes=[],
        topup_rows=[],
        customers_created=[],
        session_attempts=[],
        # Customer ids Stripe will reject when Checkout is handed them.
        reject=set(),
    )

    monkeypatch.setattr(stripe_service, "get_supabase_admin", lambda: _FakeAdmin(state))

    def _customer_create(**kwargs):
        state.customers_created.append(kwargs)
        return SimpleNamespace(id=FRESH)

    def _session_create(**kwargs):
        customer = kwargs.get("customer")
        state.session_attempts.append(customer)
        if customer in state.reject:
            raise _missing_customer_error()
        return SimpleNamespace(id="cs_live_x", url="https://checkout.stripe.com/x")

    monkeypatch.setattr(stripe.Customer, "create", staticmethod(_customer_create))
    monkeypatch.setattr(
        stripe.checkout.Session, "create", staticmethod(_session_create)
    )
    return state


# ── The production failure, and that it now recovers ─────────────────────────

@pytest.mark.asyncio
async def test_a_customer_from_another_account_does_not_block_a_top_up(stripe_env):
    """The founder's exact case: sandbox customer, live keys."""
    stripe_env.reject = {STALE}

    url = await stripe_service.create_topup_checkout(ORG_ID, 1_000)

    assert url == "https://checkout.stripe.com/x", "the founder got an error, not Checkout"
    assert stripe_env.session_attempts == [STALE, FRESH], (
        f"expected one retry with a fresh customer, got {stripe_env.session_attempts}"
    )
    assert len(stripe_env.customers_created) == 1


@pytest.mark.asyncio
async def test_the_replacement_customer_is_persisted(stripe_env):
    """Otherwise the next purchase re-sends the dead id and fails identically."""
    stripe_env.reject = {STALE}

    await stripe_service.create_topup_checkout(ORG_ID, 1_000)

    assert stripe_env.org["stripe_customer_id"] == FRESH
    assert {"stripe_customer_id": FRESH} in stripe_env.org_writes


@pytest.mark.asyncio
async def test_the_topup_row_is_still_written_after_a_recovery(stripe_env):
    """The row the webhook claims. Its absence is how this bug was found."""
    stripe_env.reject = {STALE}

    await stripe_service.create_topup_checkout(ORG_ID, 1_000)

    assert len(stripe_env.topup_rows) == 1
    row = stripe_env.topup_rows[0]
    assert row["status"] == "pending"
    assert row["amount_cents"] == 1_000


# ── The happy paths are unchanged ────────────────────────────────────────────

@pytest.mark.asyncio
async def test_a_valid_stored_customer_is_used_as_is(stripe_env):
    """No validating round trip on every purchase — that was the design choice."""
    stripe_env.reject = set()

    await stripe_service.create_topup_checkout(ORG_ID, 1_000)

    assert stripe_env.session_attempts == [STALE]
    assert stripe_env.customers_created == [], "minted a customer for no reason"


@pytest.mark.asyncio
async def test_an_org_with_no_customer_gets_one(stripe_env):
    stripe_env.org["stripe_customer_id"] = None
    stripe_env.reject = set()

    await stripe_service.create_topup_checkout(ORG_ID, 1_000)

    assert stripe_env.session_attempts == [FRESH]
    assert len(stripe_env.customers_created) == 1


# ── What must NOT be swallowed ───────────────────────────────────────────────

@pytest.mark.asyncio
async def test_an_unrelated_stripe_error_still_raises(stripe_env):
    """A bad price is not a stale customer, and hiding it would be worse."""
    def _boom(**_kwargs):
        raise stripe.error.InvalidRequestError(
            "No such price: 'price_nope'", "price", code="resource_missing"
        )

    stripe.checkout.Session.create = staticmethod(_boom)

    with pytest.raises(stripe.error.InvalidRequestError):
        await stripe_service.create_topup_checkout(ORG_ID, 1_000)

    assert stripe_env.customers_created == [], "re-minted a customer over a price error"


@pytest.mark.asyncio
async def test_the_retry_happens_exactly_once(stripe_env):
    """If the fresh customer is also rejected, that is not a stale id."""
    stripe_env.reject = {STALE, FRESH}

    with pytest.raises(stripe.error.InvalidRequestError):
        await stripe_service.create_topup_checkout(ORG_ID, 1_000)

    assert stripe_env.session_attempts == [STALE, FRESH], "retried more than once"


# ── The same hole existed on the other checkout path ─────────────────────────

@pytest.mark.asyncio
async def test_the_flash_report_path_recovers_too(stripe_env):
    """`create_flash_report_checkout` had the identical `if not customer_id`."""
    stripe_env.reject = {STALE}

    url = await stripe_service.create_flash_report_checkout(ORG_ID, "quick_read")

    assert url == "https://checkout.stripe.com/x"
    assert stripe_env.session_attempts == [STALE, FRESH]


def test_only_a_missing_customer_triggers_the_retry():
    """The predicate, directly — it decides whether an error is swallowed."""
    assert stripe_service._is_missing_customer(_missing_customer_error())

    assert not stripe_service._is_missing_customer(
        stripe.error.InvalidRequestError("No such price", "price", code="resource_missing")
    )
    assert not stripe_service._is_missing_customer(
        stripe.error.InvalidRequestError("Bad customer", "customer", code="parameter_invalid")
    )
    assert not stripe_service._is_missing_customer(ValueError("unrelated"))
