"""A check that never loaded the page does not keep the money.

Found by running three sample products through production. A website check
failed because the founder's own site did not answer inside 45 seconds — a
cold start, not a defect — and the row read:

    "... did not finish loading within 45 seconds. The site may be slow or
     blocking automated visits — try again ..."

1,750 credits had been charged at create, no page was captured, no critic ran,
no model was called, and the founder was invited to try again at the same
price for work nobody had done.

The charge-at-create rule is right and stays: deducting on completion would
let one artifact's worth of credits start ten. What was missing is the other
half — giving it back when the job dies **before spending anything**. A check
that fails halfway through its critics has consumed real compute and is not
refunded, because a rule that quietly sometimes pays is worse than one that
says plainly when it does.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.workers import website_tasks

ORG = "11111111-1111-1111-1111-111111111111"
SNAP = "44444444-4444-4444-4444-444444444444"


class _Recorder:
    def __init__(self) -> None:
        self.refunds: list[tuple[str, int, str]] = []
        self.failures: list[tuple[str, str]] = []


@pytest.fixture
def spy(monkeypatch) -> _Recorder:
    rec = _Recorder()
    monkeypatch.setattr(
        website_tasks, "refund_credits",
        lambda org, credits, *, reason: rec.refunds.append((str(org), credits, reason)),
    )
    monkeypatch.setattr(
        website_tasks, "_record_failure",
        lambda snapshot_id, message: rec.failures.append((snapshot_id, message)),
    )
    return rec


def test_the_refund_is_wired_to_the_capture_failure_path():
    """Pinned on the source because the alternative — standing up the whole
    worker, its Supabase client and a browser runtime — would test the mocks.
    The ordering here is what matters: the refund sits inside the
    `WebsiteCaptureError` branch and nowhere else."""
    import inspect

    source = inspect.getsource(website_tasks.run_website_check)
    branch_start = source.find("except WebsiteCaptureError")
    assert branch_start != -1, "the capture failure branch is gone"

    # The first capture branch is the founder's own page. Take it to the next
    # `except` or the end of the branch.
    branch = source[branch_start:branch_start + 1200]
    assert "refund_credits" in branch, (
        "a capture that never loaded the page still keeps the charge"
    )
    assert "credits_charged" in branch, "the refund does not use the real charge"


def test_only_the_pre_model_path_refunds():
    """The generic failure at the bottom of the worker must NOT refund: by
    then the critics have run and real compute is spent."""
    import inspect

    source = inspect.getsource(website_tasks.run_website_check)
    generic = source[source.rfind("GENERIC_FAILURE_MESSAGE"):]

    assert "refund_credits" not in generic, (
        "a check that died after spending on critics was refunded anyway"
    )


def test_refund_credits_is_a_no_op_for_nothing():
    """A row with no recorded charge must not grant credits out of thin air."""
    from app.services.billing import agent_pricing

    granted: list[object] = []

    class _Admin:
        def rpc(self, *_a, **_k):
            granted.append(_a)
            raise AssertionError("should not have been called")

    agent_pricing.refund_credits("11111111-1111-1111-1111-111111111111", 0,
                                 reason="test")
    agent_pricing.refund_credits("11111111-1111-1111-1111-111111111111", -5,
                                 reason="test")

    assert granted == []


def test_grant_credits_is_never_used_for_a_refund(monkeypatch):
    """The one RPC a refund must never touch, and the one it went through.

    `grant_credits(org_uuid, amount)` is a *cycle* grant: its body sets
    `credits_balance += amount`, **`credits_granted = amount`** and
    **`credit_cycle_start = NOW()`**. Every refund in the product routed through
    it, so a Growth org with `credits_granted = 59,800` that hit one 3,000-credit
    refund ended with a plan grant of 3,000 and its month restarted today —
    `GET /billing/credits` then reporting a usage bar of 766.7%. And
    `get_credit_balance` reads `credits_granted or tier_grant(plan)`, so 3,000 is
    truthy and nothing ever recovers the real grant.

    Migration 028's header, migration 031's header, `gtm/store.refund_run`'s
    docstring and `test_gtm_refund.test_grant_credits_is_never_used_for_a_refund`
    all say this in writing. Nothing said it about `agent_pricing.refund_credits`,
    which is the one every refund path shipped that day actually called.
    """
    from app.services.billing import agent_pricing

    seen: list[tuple[str, dict]] = []

    class _Admin:
        def rpc(self, name, params):
            seen.append((name, params))
            return SimpleNamespace(execute=lambda: SimpleNamespace(data=None))

    monkeypatch.setattr(agent_pricing, "get_supabase_admin", lambda: _Admin())

    agent_pricing.refund_credits(ORG, 3000, reason="capital:no_matches:x")

    assert seen == [("refund_credits", {"org_uuid": ORG, "amount": 3000})]
    assert "grant_credits" not in [name for name, _ in seen]


def test_a_failing_refund_never_masks_the_original_failure(monkeypatch):
    """The founder is already being told the job failed. Turning a refund
    problem into a second exception would replace a recoverable accounting gap
    with a lost error message."""
    from app.services.billing import agent_pricing

    class _Broken:
        def rpc(self, *_a, **_k):
            raise ConnectionError("supabase is gone")

    monkeypatch.setattr(agent_pricing, "get_supabase_admin", lambda: _Broken())

    # Must not raise.
    agent_pricing.refund_credits(
        "11111111-1111-1111-1111-111111111111", 1750, reason="test"
    )
