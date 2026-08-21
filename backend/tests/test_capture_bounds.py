"""A capture always ends, and never starves the box it runs on.

Two production checks sat at `capturing` for more than twelve minutes with no
screenshots and no error, while a founder watched a spinner. `timeout_s`
bounds `page.goto`; it does not bound `chromium.launch()`. Three checks had
begun within four minutes of each other on one Render instance, and the two
that were still trying to start a browser never returned. The third failed
honestly at its own `goto` timeout, which is what made the other two legible
as stuck rather than merely slow.

Two fixes, and they answer different questions:

- The **deadline** makes the failure honest. Whatever hangs — launch, a
  screenshot, the style census — the capture ends and says so.
- The **semaphore** stops it happening. A Chromium instance is the heaviest
  thing this service starts, and the memory is what ran out.
"""
from __future__ import annotations

import asyncio

import pytest

from app.services.website import capture as cap


def test_the_deadline_covers_more_than_one_navigation():
    """A capture renders desktop AND mobile, each bounded by `timeout_s`, then
    launches and closes a browser around them. A ceiling at `timeout_s` would
    cut off captures that were working."""
    assert cap._overall_deadline(45) > 45 * 2, (
        "the ceiling is tighter than the two renders it must contain"
    )


@pytest.mark.asyncio
async def test_a_capture_that_hangs_is_cut_off_and_explains_itself(monkeypatch):
    """The production symptom, reproduced: something inside never returns.

    The real ceiling is a minute-plus, so it is shortened here rather than
    waited out — a test that sleeps for the production timeout tests the clock.
    """
    monkeypatch.setattr(cap, "_overall_deadline", lambda _t: 0.05)

    async def _never_returns():
        await asyncio.sleep(3600)

    with pytest.raises(cap.WebsiteCaptureError) as exc:
        await cap._bounded(_never_returns(), "https://slow.example", timeout_s=45)

    assert "could not finish reading" in str(exc.value)
    assert "https://slow.example" in str(exc.value)


@pytest.mark.asyncio
async def test_a_capture_inside_the_deadline_passes_its_result_through():
    async def _fast():
        return "captured"

    assert await cap._bounded(_fast(), "https://ok.example", 45) == "captured"


def test_the_default_fits_the_instance_the_service_actually_runs_on():
    """`render.yaml` puts saibyl-backend on the `starter` plan: 512 MB. A
    headless Chromium wants 300-500 MB on its own, so two do not fit — and the
    failure is not a slow capture, it is the whole service being killed. Two
    sample runs proved it: hung captures the first time, `502 Bad Gateway`
    across every endpoint the second, taking down runs and billing calls that
    had nothing to do with the browser."""
    assert cap.MAX_CONCURRENT_CAPTURES == 1, (
        "more than one browser at a time does not fit in 512 MB; raise this "
        "only alongside the Render plan"
    )


@pytest.mark.asyncio
async def test_no_more_browsers_run_at_once_than_the_box_can_hold():
    """The contention that caused the hang. Without a cap, every concurrent
    check starts its own Chromium."""
    cap._capture_slots = None  # a fresh semaphore on this loop
    live = 0
    peak = 0

    async def _work():
        nonlocal live, peak
        live += 1
        peak = max(peak, live)
        await asyncio.sleep(0.05)
        live -= 1
        return "done"

    await asyncio.gather(*[
        cap._bounded(_work(), "https://x.example", 45) for _ in range(6)
    ])

    assert peak <= cap.MAX_CONCURRENT_CAPTURES, (
        f"{peak} browsers would have run at once against a cap of "
        f"{cap.MAX_CONCURRENT_CAPTURES}"
    )
    cap._capture_slots = None


@pytest.mark.asyncio
async def test_waiting_for_a_slot_is_not_charged_against_the_pages_budget():
    """A founder whose capture queued behind another must not have that wait
    counted as their own page being slow."""
    cap._capture_slots = None
    order: list[str] = []

    async def _slow():
        order.append("slow-start")
        await asyncio.sleep(0.15)
        order.append("slow-end")
        return "slow"

    async def _quick():
        order.append("quick")
        return "quick"

    # Fill both slots with slow work, then queue a quick one behind them.
    results = await asyncio.gather(
        cap._bounded(_slow(), "a", 1),
        cap._bounded(_slow(), "b", 1),
        cap._bounded(_quick(), "c", 1),
    )

    assert results == ["slow", "slow", "quick"], (
        "a queued capture failed on a deadline that was running while it waited"
    )
    cap._capture_slots = None


# ---------------------------------------------------------------------------
# The steps AFTER the navigation — where captures actually hung
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_a_slow_optional_step_costs_a_field_not_the_capture():
    """The style census is best-effort by this module's own contract. Until
    now "a page that defeats the census" did not include "takes forever"."""
    async def _forever():
        await asyncio.sleep(3600)

    assert await cap._optional(_forever(), 0, "style_census") is None


@pytest.mark.asyncio
async def test_an_optional_step_that_raises_is_also_survivable():
    async def _boom():
        raise RuntimeError("the page fought back")

    assert await cap._optional(_boom(), 5, "meta") is None


@pytest.mark.asyncio
async def test_a_slow_required_step_ends_the_capture_with_a_sentence():
    """A page that came back with no text is not a cheaper capture, it is a
    wrong one — the critics would be handed a blank page to judge."""
    async def _forever():
        await asyncio.sleep(3600)

    with pytest.raises(cap.WebsiteCaptureError) as exc:
        await cap._required(_forever(), 0, "the page's text", "https://heavy.example")

    message = str(exc.value)
    assert "could not read the page's text" in message
    assert "https://heavy.example" in message
    assert "Traceback" not in message


@pytest.mark.asyncio
async def test_steps_inside_their_budget_pass_their_value_through():
    async def _ok():
        return {"font-family": "Inter"}

    assert await cap._optional(_ok(), 5, "census") == {"font-family": "Inter"}
    assert await cap._required(_ok(), 5, "text", "u") == {"font-family": "Inter"}
