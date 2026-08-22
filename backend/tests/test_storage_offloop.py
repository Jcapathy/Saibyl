"""Storage never blocks the event loop.

**This is the bug that made the Website Gauntlet look like a memory problem,
and it is worth stating exactly.**

`get_supabase_admin()` returns `supabase._sync.client.Client` — a synchronous
client. `store.py` called `bucket.upload(...)` and `bucket.download(...)`
directly inside `async def`. A multi-megabyte screenshot upload therefore held
the event loop for its entire duration, and while it was held:

- no other request was served, so Render's health check timed out and the
  platform answered **502 on every endpoint** — which read like the box
  running out of memory;
- **no asyncio timer could fire**, which is why the capture deadlines never
  went off and a check sat at `capturing` for fifteen minutes with a
  150-second ceiling on it;
- one founder's upload stalled everybody's requests.

It also matches the production record exactly: every check that ever completed
was a light page with a small screenshot, and every heavy commercial page —
taller page, bigger PNG — stalled.

The tests below assert the property rather than the implementation: while a
storage call is in flight, the loop must still be running other work.
"""
from __future__ import annotations

import asyncio
import time

import pytest

from app.services.website import store


class _SlowBucket:
    """A bucket whose calls block the calling thread, like the real one."""

    def __init__(self, seconds: float = 0.4):
        self.seconds = seconds
        self.uploads: list[str] = []

    def upload(self, path, _data, _opts=None):
        time.sleep(self.seconds)      # blocking, exactly like the real client
        self.uploads.append(path)
        return {"path": path}

    def download(self, path):
        time.sleep(self.seconds)
        return b"bytes"


@pytest.mark.asyncio
async def test_a_blocking_storage_call_leaves_the_loop_free():
    """The property that was violated. If the loop is blocked, the ticker
    below cannot advance while the upload is in flight."""
    bucket = _SlowBucket(0.4)
    ticks = 0

    async def _ticker():
        nonlocal ticks
        while True:
            await asyncio.sleep(0.02)
            ticks += 1

    beat = asyncio.create_task(_ticker())
    try:
        await store.run_off_loop(bucket.upload, "a.png", b"x", what="a screenshot")
    finally:
        beat.cancel()

    assert ticks >= 5, (
        f"the loop advanced only {ticks} times during a 0.4s storage call — "
        f"it was blocked, which is the whole defect"
    )


@pytest.mark.asyncio
async def test_an_asyncio_timeout_can_still_fire_during_storage():
    """The second-order consequence, pinned directly. A blocked loop cannot
    run its own timers, which is why the capture deadlines never fired."""
    bucket = _SlowBucket(0.5)
    fired = False

    async def _alarm():
        nonlocal fired
        await asyncio.sleep(0.1)
        fired = True

    alarm = asyncio.create_task(_alarm())
    await store.run_off_loop(bucket.upload, "a.png", b"x", what="a screenshot")
    await alarm

    assert fired, "a timer scheduled during a storage call never ran"


@pytest.mark.asyncio
async def test_a_storage_call_that_overruns_ends_with_a_sentence(monkeypatch):
    monkeypatch.setattr(store, "_STORAGE_TIMEOUT_S", 0.05)
    bucket = _SlowBucket(2.0)

    with pytest.raises(store.StorageTimeoutError) as exc:
        await store.run_off_loop(bucket.upload, "a.png", b"x", what="the desktop screenshot")

    assert "the desktop screenshot" in str(exc.value)
    assert "Traceback" not in str(exc.value)


@pytest.mark.asyncio
async def test_both_screenshots_are_uploaded_and_their_paths_returned(monkeypatch):
    bucket = _SlowBucket(0.0)
    monkeypatch.setattr(
        store, "get_supabase_admin",
        lambda: type("A", (), {"storage": type("S", (), {
            "from_": staticmethod(lambda _b: bucket)
        })()})(),
    )

    capture = type("C", (), {
        "screenshot_desktop": b"desktop-png",
        "screenshot_mobile": b"mobile-png",
    })()

    paths = await store.upload_screenshots(
        organization_id="org", snapshot_id="snap", capture=capture
    )

    assert paths == {
        "desktop": "website/org/snap/desktop.png",
        "mobile": "website/org/snap/mobile.png",
    }
    assert bucket.uploads == [paths["desktop"], paths["mobile"]]


def test_no_storage_call_is_made_directly_on_the_loop():
    """A future edit that adds a sixth call must route it through
    `run_off_loop` too. Pinned on the source because the alternative —
    noticing a stalled production service — is how this one was found."""
    import inspect

    source = inspect.getsource(store)
    body = source[source.find("async def upload_screenshots"):]

    for call in ("bucket.upload(", "bucket.download("):
        for line in body.splitlines():
            stripped = line.strip()
            if stripped.startswith(call):
                raise AssertionError(
                    f"{stripped!r} runs on the event loop; pass it to "
                    f"`run_off_loop` instead"
                )
