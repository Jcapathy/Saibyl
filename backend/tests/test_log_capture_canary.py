"""A canary for the test suite's own honesty.

Roughly thirty assertions across this suite are of the form "the failure was
logged". Each is the guard on a defect whose whole signature was that it
*failed silently* — the margin gate passing on no data, a stop signal lost to a
Redis error, a swarm shipped smaller than the one quoted. If `capture_logs`
returns an empty list, every one of those assertions passes for the wrong
reason and the suite reports success while checking nothing.

That is not hypothetical here. It depends on test order: `create_app()` calls
`setup_logging()`, which installs a new processors list, while module loggers
cache their bound logger on first use. A module logger bound before the last
`create_app()` keeps logging to the old list, and `capture_logs` — which swaps
processors on the *current* list, in place — sees nothing.

So these tests do not check application behaviour. They check that the
instrument the other tests rely on is still plugged in. If this file fails,
treat every `capture_logs` assertion in the suite as unverified until it is
fixed.
"""
from __future__ import annotations

import structlog
from structlog.testing import capture_logs

from app.main import create_app


def test_capture_logs_sees_a_module_logger():
    """The baseline: capture works at all."""
    from app.services.billing import usage_ledger

    with capture_logs() as logs:
        usage_ledger.logger.info("canary_event", detail="baseline")

    assert any(entry["event"] == "canary_event" for entry in logs), (
        "capture_logs saw nothing at all — every log assertion in this suite "
        "is passing vacuously"
    )


def test_capture_logs_still_works_after_the_app_is_built():
    """The ordering hazard, reproduced deliberately.

    `create_app()` reconfigures structlog. A suite that builds the app in one
    test and asserts on logs in another runs exactly this sequence, which is
    why the failure appeared only with certain files in the run.
    """
    from app.services.billing import usage_ledger

    create_app()

    with capture_logs() as logs:
        usage_ledger.logger.info("canary_event_after_app", detail="post-create_app")

    assert any(entry["event"] == "canary_event_after_app" for entry in logs), (
        "capture_logs went blind after create_app() — the conftest fixture "
        "that resets cached logger proxies is not doing its job"
    )


def test_capture_logs_survives_repeated_app_construction():
    """Several tests build the app; each rebuild installs a new list."""
    from app.workers import analysis_tasks

    for _ in range(3):
        create_app()

    with capture_logs() as logs:
        analysis_tasks.logger.warning("canary_event_repeated", attempt=3)

    assert any(entry["event"] == "canary_event_repeated" for entry in logs)


def test_the_residual_hazard_is_still_only_within_a_single_test():
    """Documents the limit of the conftest fixture, so nobody assumes more.

    The fixture rebinds `app.*` module loggers before **each** test, which is
    what makes cross-test order irrelevant — the case that silently emptied
    real assertions. It cannot help a logger that is bound and then orphaned
    *inside one test*, because the reconfiguration happens after the fixture
    has already run.

    So this sequence — bind, rebuild the app, then capture — is still blind,
    and a test that needs to assert on logs after building the app must
    capture with a logger obtained after the last `create_app()`.

    If this test ever starts failing, structlog's caching behaviour changed:
    re-check whether the conftest fixture is still needed at all, rather than
    deleting this test.
    """
    proxy = structlog.get_logger("app.canary.bound_early")
    proxy.info("warm_the_cache")

    create_app()

    with capture_logs() as logs:
        proxy.info("canary_event_bound_early")

    assert not any(entry["event"] == "canary_event_bound_early" for entry in logs), (
        "the within-test hazard appears to be gone — structlog's behaviour "
        "changed, so revisit whether the conftest rebinding fixture is needed"
    )

    # And the documented remedy works: re-obtain after the reconfiguration.
    fresh = structlog.get_logger("app.canary.bound_early")
    with capture_logs() as logs:
        fresh.info("canary_event_rebound")

    assert any(entry["event"] == "canary_event_rebound" for entry in logs)
