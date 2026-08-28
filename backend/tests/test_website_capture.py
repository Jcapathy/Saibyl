"""Website capture and vision: the evidence pipeline can't lie about what it saw.

No live browser and no network anywhere in this file. Six claims:

**The module imports where Playwright is absent.** The dev venv and CI carry no
browser runtime — only the Docker image does — so `services/website/capture`
must import cleanly everywhere, and a real capture attempt without the runtime
must fail with install guidance, not an ImportError mid-request.

**The SSRF guard runs before any fetch, and again after every redirect.** The
server fetches URLs founders type. Every rejection in the first group arrives
as the guard's HTTPException *without any fake browser installed* — if capture
ever fetched (or imported Playwright) before validating, these tests would see
a WebsiteCaptureError instead. The redirect tests pin the classic bypass, a
public hostname that lands on a private address, and the two ways it was still
open: a host that redirects only on the *second* navigation (the mobile pass
had no check at all), and one that lands *late*, while the page is being read.

**A rendered revision is a capture too.** `capture_html` starts the same
Chromium, so it queues for the same slot and ends under the same deadline —
without that, every concurrent revision added an unbudgeted browser to a 2 GB
instance, and a launch that hung had no ceiling at all.

**The captured evidence is faithful, and it is kept apart from our notes about
it.** DOM text is capped and an endless page is clipped — a report must never
judge half a page as the whole page silently — with every cut recorded in
`notes`. Never in `meta`: that dict is the page's own tags, and the
credibility reviewer is handed it as what search results will show.

**The style census measures, and never endangers the capture.** The desktop
pass tallies computed styles into `style_census` — fonts, colors, spacing,
radii, shadows, structure — normalized, hex-converted and capped in Python so
the census is bounded and deterministic. A census that fails for any reason
ships empty; the screenshots and text are never hostage to it.

**`llm_vision` puts the images on the wire, or refuses.** litellm's message
conversion silently drops Anthropic-native image blocks, which is why
`llm_vision` speaks to the Anthropic SDK directly — so the payload it builds
is asserted block by block, an oversized image is rejected before any call,
and a non-Anthropic provider is a loud NotImplementedError rather than a
vision call that quietly saw nothing.
"""
from __future__ import annotations

import asyncio
import base64
import importlib
import socket
import sys
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.core import llm_client, security
from app.services.website import capture as capture_mod
from app.services.website.capture import (
    DOM_TEXT_MAX_CHARS,
    MAX_SCREENSHOT_HEIGHT_PX,
    WebsiteCapture,
    WebsiteCaptureError,
    capture_html,
    capture_website,
)

_PUBLIC_IP = "93.184.216.34"


# ---------------------------------------------------------------------------
# DNS and Playwright stand-ins
# ---------------------------------------------------------------------------

def _resolving(mapping: dict[str, str]):
    """A getaddrinfo that answers only from `mapping` — no resolver, no network."""

    def fake_getaddrinfo(host, *_args, **_kwargs):
        addr = mapping.get(host)
        if addr is None:
            raise socket.gaierror(f"unmapped host in test: {host}")
        return [(2, 1, 6, "", (addr, 0))]

    return fake_getaddrinfo


class _FakePlaywrightError(Exception):
    pass


class _FakePlaywrightTimeoutError(_FakePlaywrightError):
    pass


class _FakePage:
    def __init__(self, spec: dict, viewport: dict, calls: list):
        self._spec = spec
        self._viewport = viewport
        self._calls = calls
        self.url: str | None = None

    async def goto(self, url, timeout=None, wait_until=None):
        self._calls.append(("goto", self._viewport["width"], url, timeout, wait_until))
        raises = self._spec.get("goto_raises")
        if raises is not None:
            raise raises
        # `final_urls` is consumed one per navigation, which is how a site that
        # redirects only on its SECOND request is written down — a request
        # counter, a cookie, an A/B split. The desktop and mobile passes are
        # two independent navigations, so they can land in different places.
        landings = self._spec.get("final_urls")
        if landings:
            self.url = landings.pop(0)
            return
        self.url = self._spec.get("final_url", url)

    async def set_content(self, html, timeout=None, wait_until=None):
        self._calls.append(("set_content", self._viewport["width"], html, timeout, wait_until))
        self.url = "about:blank"

    async def wait_for_load_state(self, state, timeout=None):
        """The settle after `domcontentloaded`.

        Modelled rather than left off the fake: without it the capture's
        `try/except` swallowed an AttributeError and every test passed while
        never exercising the settle at all. `settle_raises` lets a test say
        "this page's network never goes quiet", which is the normal case for a
        commercial page full of analytics.
        """
        self._calls.append(("settle", self._viewport["width"], state, timeout))
        raises = self._spec.get("settle_raises")
        if raises is not None:
            raise raises

    async def title(self):
        return self._spec.get("title", "")

    async def evaluate(self, script: str):
        # Keyed on marker substrings the module guarantees in its script constants.
        if "scrollTo" in script:
            # The lazy-content prime. It dwells for seconds between the
            # navigation and every read that produces the evidence, so a page
            # can land somewhere else while it runs — `navigates_during_prime`
            # is that redirect, arriving one moment late.
            landing = self._spec.get("navigates_during_prime")
            if landing:
                self.url = landing
            return self._spec.get("page_height", 900)
        if "getComputedStyle" in script:
            raises = self._spec.get("census_raises")
            if raises is not None:
                raise raises
            return self._spec.get("census_raw", {})
        if "querySelectorAll('meta')" in script:
            return dict(self._spec.get("meta", {}))
        if "innerText" in script:
            # `innerText` forces a full layout. On a long page and half a CPU
            # that measured over 45 seconds, so the module tries it briefly
            # and falls back. `innertext_raises` lets a test say "this page is
            # too heavy to lay out", which is the case that mattered.
            raises = self._spec.get("innertext_raises")
            if raises is not None:
                raise raises
            return self._spec.get("dom_text", "")
        if "createTreeWalker" in script:
            # The layout-free fallback: text nodes, minus script and style.
            return self._spec.get("dom_text_fallback", self._spec.get("dom_text", ""))
        if "scrollHeight" in script:
            return self._spec.get("page_height", 900)
        raise AssertionError(f"unexpected evaluate script: {script!r}")

    async def screenshot(self, **kwargs):
        self._calls.append(("screenshot", self._viewport["width"], kwargs))
        # Long enough for a second capture to be observed holding a browser at
        # the same time, when a test runs several at once.
        delay = self._spec.get("shot_delay")
        if delay:
            await asyncio.sleep(delay)
        return f"png-{self._viewport['width']}".encode()


class _FakeContext:
    def __init__(self, page: _FakePage, calls: list):
        self._page = page
        self._calls = calls
        self.closed = False
        # Recorded rather than ignored: the ceiling on Playwright's own
        # actions is what stops a screenshot of a very tall page running
        # unbounded after `goto` has already returned.
        self.default_timeout_ms: int | None = None

    def set_default_timeout(self, ms: int) -> None:
        self.default_timeout_ms = ms

    async def new_page(self):
        return self._page

    async def route(self, pattern, handler):
        self._calls.append(("route", pattern, handler))

    async def close(self):
        self.closed = True


class _FakeBrowser:
    def __init__(self, spec: dict, calls: list):
        self._spec = spec
        self._calls = calls
        self.closed = False
        # How many callers are holding a browser right now, and the most that
        # ever held one at once. A Chromium is the heaviest thing this service
        # starts, so "how many at once" is the number the instance lives or
        # dies by.
        self.live = 0
        self.peak = 0

    async def new_context(self, **kwargs):
        self._calls.append(("new_context", kwargs))
        return _FakeContext(
            _FakePage(self._spec, kwargs["viewport"], self._calls), self._calls
        )

    async def close(self):
        self.live = max(self.live - 1, 0)
        self.closed = True


class _FakeAsyncPlaywright:
    """What `async_playwright()` returns: an async context manager."""

    def __init__(self, browser: _FakeBrowser):
        self._browser = browser

    async def __aenter__(self):
        async def launch(**_kwargs):
            # `launch_hangs` is the production failure `timeout_s` never
            # covered: two checks sat at `capturing` for twelve minutes inside
            # a browser that never started.
            hangs = self._browser._spec.get("launch_hangs")
            if hangs:
                await asyncio.sleep(hangs)
            self._browser.live += 1
            self._browser.peak = max(self._browser.peak, self._browser.live)
            return self._browser

        return SimpleNamespace(chromium=SimpleNamespace(launch=launch))

    async def __aexit__(self, *_exc):
        return False


def _install_fake_playwright(monkeypatch, spec: dict) -> tuple[list, _FakeBrowser]:
    """Patch the lazy-import seam with a browserless Playwright stand-in."""
    calls: list = []
    browser = _FakeBrowser(spec, calls)
    module = SimpleNamespace(
        async_playwright=lambda: _FakeAsyncPlaywright(browser),
        Error=_FakePlaywrightError,
        TimeoutError=_FakePlaywrightTimeoutError,
    )
    monkeypatch.setattr(capture_mod, "_import_playwright", lambda: module)
    return calls, browser


def _block_playwright(monkeypatch):
    """Make `import playwright` fail even where someone installed it locally."""
    for name in [m for m in list(sys.modules) if m == "playwright" or m.startswith("playwright.")]:
        monkeypatch.delitem(sys.modules, name, raising=False)
    monkeypatch.setitem(sys.modules, "playwright", None)


# ---------------------------------------------------------------------------
# Claim 1: importable, and clearly failing, without a browser runtime
# ---------------------------------------------------------------------------

def test_the_module_imports_where_playwright_is_absent(monkeypatch):
    _block_playwright(monkeypatch)
    monkeypatch.delitem(sys.modules, "app.services.website.capture", raising=False)
    module = importlib.import_module("app.services.website.capture")
    assert callable(module.capture_website)


async def test_a_capture_without_playwright_fails_with_install_guidance(monkeypatch):
    monkeypatch.setattr(
        security.socket, "getaddrinfo", _resolving({"acme.example": _PUBLIC_IP})
    )
    _block_playwright(monkeypatch)
    with pytest.raises(WebsiteCaptureError) as exc:
        await capture_website("https://acme.example/")
    assert "playwright install" in str(exc.value)


# ---------------------------------------------------------------------------
# Claim 2: the SSRF guard, before any fetch and after redirects
# ---------------------------------------------------------------------------
# None of these installs the fake browser: reaching the render path at all
# would surface as a WebsiteCaptureError, so the HTTPException below is also
# proof of ordering — validate first, fetch second.

async def test_a_loopback_literal_is_rejected():
    with pytest.raises(HTTPException) as exc:
        await capture_website("http://127.0.0.1/admin")
    assert exc.value.status_code == 400


async def test_a_private_ip_literal_is_rejected():
    with pytest.raises(HTTPException) as exc:
        await capture_website("http://10.0.0.5/")
    assert exc.value.status_code == 400


@pytest.mark.parametrize("url", ["file:///etc/passwd", "ftp://acme.example/x", "javascript:alert(1)"])
async def test_a_non_http_scheme_is_rejected(url):
    with pytest.raises(HTTPException) as exc:
        await capture_website(url)
    assert "http or https" in exc.value.detail


async def test_a_hostname_resolving_to_a_private_address_is_rejected(monkeypatch):
    monkeypatch.setattr(
        security.socket, "getaddrinfo", _resolving({"internal.corp": "192.168.1.10"})
    )
    with pytest.raises(HTTPException) as exc:
        await capture_website("https://internal.corp/")
    assert exc.value.status_code == 400


async def test_a_hostname_resolving_to_the_metadata_range_is_rejected(monkeypatch):
    monkeypatch.setattr(
        security.socket, "getaddrinfo", _resolving({"metadata.example": "169.254.169.254"})
    )
    with pytest.raises(HTTPException):
        await capture_website("https://metadata.example/")


async def test_a_redirect_landing_on_a_private_address_is_rejected(monkeypatch):
    """The founder's URL is public; the site 302s somewhere internal."""
    monkeypatch.setattr(
        security.socket,
        "getaddrinfo",
        _resolving({"good.example": _PUBLIC_IP, "internal.example": "10.0.0.5"}),
    )
    _install_fake_playwright(monkeypatch, {"final_url": "http://internal.example/"})
    with pytest.raises(HTTPException) as exc:
        await capture_website("https://good.example/")
    assert exc.value.status_code == 400


_METADATA = "http://169.254.169.254/latest/meta-data/iam/"


async def test_a_redirect_that_only_happens_on_the_second_navigation_is_rejected(monkeypatch):
    """The mobile pass is a second, independent navigation, and it had no
    check at all.

    A founder-supplied host that redirects only on its second request — a
    request counter, a cookie, an A/B split — got the metadata endpoint
    rendered into `screenshot_mobile`, which is stored by `upload_screenshots`
    and served back through `GET /website/check/{id}/image?which=mobile`. That
    is instance-credential exfiltration through a paid product feature, on a
    URL the founder chose, and the capture returned without raising.
    """
    monkeypatch.setattr(
        security.socket,
        "getaddrinfo",
        _resolving({"evil.example": _PUBLIC_IP, "169.254.169.254": "169.254.169.254"}),
    )
    _install_fake_playwright(monkeypatch, {
        # First navigation lands where it said it would; the second does not.
        "final_urls": ["https://evil.example/", _METADATA],
        "dom_text": "Nothing to see here.",
    })

    with pytest.raises(HTTPException) as exc:
        await capture_website("https://evil.example/")
    assert exc.value.status_code == 400


async def test_a_page_that_navigates_while_it_is_being_read_is_rejected(monkeypatch):
    """The re-check was defeated by a redirect that lands one moment late.

    `final_url` was snapshotted before the page was read, so a navigation that
    happens during the lazy-content prime — which dwells for seconds, by
    design — left `final_url` equal to the URL the founder typed. The
    `final_url != url` guard was then False and the SSRF check never ran at
    all, while `dom_text` (the report body) and the screenshots came from
    wherever the page had gone.
    """
    monkeypatch.setattr(
        security.socket,
        "getaddrinfo",
        _resolving({"evil.example": _PUBLIC_IP, "169.254.169.254": "169.254.169.254"}),
    )
    _install_fake_playwright(monkeypatch, {
        "navigates_during_prime": _METADATA,
        "dom_text": "AccessKeyId: ASIA... SecretAccessKey: wJalrXUtn...",
    })

    with pytest.raises(HTTPException) as exc:
        await capture_website("https://evil.example/")
    assert exc.value.status_code == 400


# ---------------------------------------------------------------------------
# Claim 3: the captured evidence is faithful
# ---------------------------------------------------------------------------

async def test_a_page_too_heavy_to_lay_out_still_yields_its_text(monkeypatch):
    """`innerText` is what a person sees, and it forces a full layout to know
    what is visible. On a long marketing page and half a CPU that measured
    over 45 seconds and failed a capture that had already navigated and
    screenshotted fine. The fallback walks text nodes and needs no layout."""
    monkeypatch.setattr(
        security.socket, "getaddrinfo", _resolving({"acme.example": _PUBLIC_IP})
    )
    _calls, _browser = _install_fake_playwright(monkeypatch, {
        "innertext_raises": TimeoutError("layout never finished"),
        "dom_text_fallback": "Prior authorization, answered.",
        "page_height": 900,
    })

    result = await capture_website("https://acme.example/", timeout_s=45)

    assert result.dom_text == "Prior authorization, answered."


async def test_the_good_read_is_preferred_when_it_is_affordable(monkeypatch):
    """The fallback is cheaper and worse — it cannot tell hidden text from
    visible. It must not be used when `innerText` answers."""
    monkeypatch.setattr(
        security.socket, "getaddrinfo", _resolving({"acme.example": _PUBLIC_IP})
    )
    _calls, _browser = _install_fake_playwright(monkeypatch, {
        "dom_text": "What a person sees.",
        "dom_text_fallback": "every text node, hidden ones too",
        "page_height": 900,
    })

    result = await capture_website("https://acme.example/", timeout_s=45)

    assert result.dom_text == "What a person sees."


async def test_navigation_does_not_wait_for_every_tracker_to_finish(monkeypatch):
    """`load` waits for every subresource — analytics beacons, chat widgets,
    lazily-loaded video. On a real commercial marketing page those keep the
    load event pending long after the page is visually done, which is how
    simplepractice.com and stripe.com exhausted a 45-second budget while
    example.com completed in 94 seconds end to end."""
    monkeypatch.setattr(
        security.socket, "getaddrinfo", _resolving({"acme.example": _PUBLIC_IP})
    )
    calls, _browser = _install_fake_playwright(monkeypatch, {"page_height": 900})

    await capture_website("https://acme.example/", timeout_s=45)

    gotos = [c for c in calls if c[0] == "goto"]
    assert gotos, "the page was never navigated"
    for call in gotos:
        assert call[4] == "domcontentloaded", (
            f"navigation waited on {call[4]!r}, which a page full of trackers "
            f"may never reach"
        )
    assert [c for c in calls if c[0] == "settle"], (
        "nothing waited for the page to settle, so a screenshot could be taken "
        "before the hero image painted"
    )


async def test_a_page_whose_network_never_goes_quiet_is_still_captured(monkeypatch):
    """The settle is a courtesy, not a requirement. A page whose analytics
    chatter forever is shot as it stands."""
    monkeypatch.setattr(
        security.socket, "getaddrinfo", _resolving({"acme.example": _PUBLIC_IP})
    )
    _calls, _browser = _install_fake_playwright(monkeypatch, {
        "dom_text": "Welcome to Acme.",
        "page_height": 900,
        "settle_raises": TimeoutError("networkidle never reached"),
    })

    result = await capture_website("https://acme.example/", timeout_s=45)

    assert result.dom_text == "Welcome to Acme."
    assert result.screenshot_desktop


async def test_a_capture_returns_the_rendered_evidence(monkeypatch):
    monkeypatch.setattr(
        security.socket, "getaddrinfo", _resolving({"acme.example": _PUBLIC_IP})
    )
    calls, browser = _install_fake_playwright(monkeypatch, {
        "title": "Acme — Ship faster",
        "meta": {"description": "Acme ships things.", "og:title": "Acme"},
        "dom_text": "Welcome to Acme.",
        "page_height": 1200,
    })

    result = await capture_website("https://acme.example/", timeout_s=45)

    assert isinstance(result, WebsiteCapture)
    assert result.url == result.final_url == "https://acme.example/"
    assert result.title == "Acme — Ship faster"
    assert result.dom_text == "Welcome to Acme."
    assert result.meta["description"] == "Acme ships things."
    assert result.meta["og:title"] == "Acme"

    # One pass per viewport, in order, each with the caller's timeout in ms.
    goto_calls = [c for c in calls if c[0] == "goto"]
    assert [c[1] for c in goto_calls] == [1440, 390]
    assert all(c[3] == 45_000 for c in goto_calls)

    # Each viewport photographed full-page (the page fits under the cap) and
    # each screenshot is the one its own context produced.
    assert result.screenshot_desktop == b"png-1440"
    assert result.screenshot_mobile == b"png-390"
    shot_calls = [c for c in calls if c[0] == "screenshot"]
    assert all(c[2].get("full_page") is True for c in shot_calls)

    context_calls = [c for c in calls if c[0] == "new_context"]
    assert context_calls[1][1].get("is_mobile") is True
    assert browser.closed


async def test_dom_text_is_capped_with_a_note_of_its_own(monkeypatch):
    monkeypatch.setattr(
        security.socket, "getaddrinfo", _resolving({"acme.example": _PUBLIC_IP})
    )
    original_chars = DOM_TEXT_MAX_CHARS + 5_000
    _install_fake_playwright(monkeypatch, {"dom_text": "x" * original_chars})

    result = await capture_website("https://acme.example/")

    assert len(result.dom_text) == DOM_TEXT_MAX_CHARS
    note = result.notes["dom_text_truncated"]
    assert str(DOM_TEXT_MAX_CHARS) in note
    assert str(original_chars) in note


async def test_an_endless_page_is_clipped_not_shot_in_full(monkeypatch):
    monkeypatch.setattr(
        security.socket, "getaddrinfo", _resolving({"acme.example": _PUBLIC_IP})
    )
    calls, _browser = _install_fake_playwright(monkeypatch, {"page_height": 25_000})

    result = await capture_website("https://acme.example/")

    shot_calls = [c for c in calls if c[0] == "screenshot"]
    for _, width, kwargs in shot_calls:
        assert "full_page" not in kwargs
        assert kwargs["clip"] == {
            "x": 0,
            "y": 0,
            "width": width,
            "height": MAX_SCREENSHOT_HEIGHT_PX,
        }
    assert "screenshot_desktop_truncated" in result.notes
    assert "screenshot_mobile_truncated" in result.notes


async def test_what_the_capture_had_to_cut_is_never_filed_as_one_of_the_pages_tags(
    monkeypatch,
):
    """`meta` is what the page ships; `notes` is what we did to it.

    Mixed into one dict, the caps reached the credibility reviewer under a
    heading that calls the block "PAGE TAGS (what search results and link
    previews will show)", with an instruction to quote any drift between them
    and the page. A page taller than 8,000px at 1440 wide — which a long
    marketing page routinely is — therefore had its trust dimension scored
    partly against two strings that are not tags and do not exist on the
    founder's site. The founder pays for that critique.
    """
    monkeypatch.setattr(
        security.socket, "getaddrinfo", _resolving({"acme.example": _PUBLIC_IP})
    )
    _install_fake_playwright(monkeypatch, {
        "meta": {"description": "Acme ships things.", "og:title": "Acme"},
        "dom_text": "x" * (DOM_TEXT_MAX_CHARS + 1),
        "page_height": 25_000,
    })

    result = await capture_website("https://acme.example/")

    assert result.meta == {"description": "Acme ships things.", "og:title": "Acme"}
    assert not any("truncated" in key for key in result.meta)
    # And the record itself is kept, so no report can present a cropped page as
    # the whole page.
    assert set(result.notes) == {
        "dom_text_truncated",
        "screenshot_desktop_truncated",
        "screenshot_mobile_truncated",
    }


async def test_a_navigation_failure_reads_like_a_sentence_not_a_trace(monkeypatch):
    monkeypatch.setattr(
        security.socket, "getaddrinfo", _resolving({"nope.example": _PUBLIC_IP})
    )
    _install_fake_playwright(monkeypatch, {
        "goto_raises": _FakePlaywrightError(
            "net::ERR_NAME_NOT_RESOLVED at https://nope.example/\n    at Frame.goto (...)"
        ),
    })
    with pytest.raises(WebsiteCaptureError) as exc:
        await capture_website("https://nope.example/")
    message = str(exc.value)
    assert "could not be found" in message
    assert "net::" not in message
    assert "Frame.goto" not in message


async def test_a_timeout_names_the_budget_it_exhausted(monkeypatch):
    monkeypatch.setattr(
        security.socket, "getaddrinfo", _resolving({"slow.example": _PUBLIC_IP})
    )
    _install_fake_playwright(monkeypatch, {
        "goto_raises": _FakePlaywrightTimeoutError("Timeout 30000ms exceeded."),
    })
    with pytest.raises(WebsiteCaptureError) as exc:
        await capture_website("https://slow.example/", timeout_s=30)
    assert "30 seconds" in str(exc.value)


# ---------------------------------------------------------------------------
# capture_html starts a browser too, so it queues and it ends
#
# `generate_revision` calls it up to three times per revision, and every
# revision is its own task in the API process, beside the browsers
# `capture_website` is allowed. Bypassing the slot and the deadline is not a
# slow revision — it is the whole service killed, which this module's own
# comments describe as 502 across every endpoint, paid for by every other
# founder on the platform.
# ---------------------------------------------------------------------------

_REVISION_HTML = "<html><head><title>Rewritten</title></head><body><main>Hi</main></body></html>"


async def test_a_rendered_revision_holds_a_browser_slot_like_any_other_capture(monkeypatch):
    capture_mod._capture_slots = None  # a fresh semaphore on this loop
    try:
        _calls, browser = _install_fake_playwright(monkeypatch, {
            "dom_text": "Hi",
            "shot_delay": 0.05,
        })

        await asyncio.gather(*[capture_html(_REVISION_HTML) for _ in range(6)])

        assert browser.peak <= capture_mod.MAX_CONCURRENT_CAPTURES, (
            f"{browser.peak} browsers ran at once against a cap of "
            f"{capture_mod.MAX_CONCURRENT_CAPTURES}"
        )
    finally:
        capture_mod._capture_slots = None


async def test_a_revision_render_whose_browser_never_starts_is_cut_off(monkeypatch):
    """The exact production hang, on the path that had no ceiling: a launch
    that never returns parks a `page_revisions` row at `generating` forever,
    with no founder-readable error — the twelve-minute-spinner symptom the
    deadline was built to end."""
    capture_mod._capture_slots = None
    try:
        monkeypatch.setattr(capture_mod, "_overall_deadline", lambda _t: 0.05)
        _install_fake_playwright(monkeypatch, {"launch_hangs": 3600})

        with pytest.raises(WebsiteCaptureError) as exc:
            await capture_html(_REVISION_HTML)

        message = str(exc.value)
        assert "could not finish reading" in message
        assert "the rewritten page" in message, (
            "a founder cannot read 'about:revision' as the name of anything"
        )
    finally:
        capture_mod._capture_slots = None


# ---------------------------------------------------------------------------
# Claim 4: the style census measures, and never endangers the capture
# ---------------------------------------------------------------------------

#: What the census script would tally on a small page: raw {value: count}
#: maps, exactly the shape `_normalize_census` receives from the browser.
_RAW_CENSUS = {
    "sampled": 42,
    "font_families": {'"Space Grotesk", sans-serif': 30, "Arial, sans-serif": 12},
    "font_weights": {"400": 28, "700": 14},
    "font_sizes": {"16px": 25, "48px": 4},
    "letter_spacing": {"headings": {"-0.02em": 4}, "body": {"normal": 38}},
    "line_heights": {"24px": 30},
    "text_colors": {"rgb(16, 20, 24)": 40, "rgba(16, 20, 24, 0.5)": 2},
    "background_colors": {"rgb(245, 242, 236)": 6},
    "border_colors": {"rgb(220, 220, 220)": 3},
    "border_radii": {"8px": 9},
    "box_shadows": {"rgba(0, 0, 0, 0.08) 0px 1px 2px 0px": 5},
    "spacing": {"24px": 40, "16px": 30, "8px": 22, "32px": 10, "40px": 5},
    "structure": {"headings": {"h1": 1, "h2": 4}, "buttons": 3, "links": 12, "images": 6},
}


def test_the_census_script_carries_its_marker_and_the_sample_cap():
    """The constant exists, is fake-able by its marker, and embeds the cap."""
    assert "getComputedStyle" in capture_mod._STYLE_CENSUS_JS
    assert str(capture_mod._CENSUS_MAX_ELEMENTS) in capture_mod._STYLE_CENSUS_JS


async def test_the_census_is_wired_into_the_desktop_pass_and_normalized(monkeypatch):
    monkeypatch.setattr(
        security.socket, "getaddrinfo", _resolving({"acme.example": _PUBLIC_IP})
    )
    _install_fake_playwright(monkeypatch, {"census_raw": dict(_RAW_CENSUS)})

    result = await capture_website("https://acme.example/")
    census = result.style_census

    assert census["sampled_elements"] == 42
    assert census["fonts"]["families"][0] == {
        "stack": '"Space Grotesk", sans-serif',
        "family": "Space Grotesk",
        "count": 30,
    }
    assert census["fonts"]["weights"][0] == {"value": "400", "count": 28}
    assert census["fonts"]["sizes"][0] == {"value": "16px", "count": 25}

    # Colors arrive as rgb()/rgba() and leave as hex — alpha kept as hex8.
    assert census["color"]["text"][0] == {"value": "#101418", "count": 40}
    assert census["color"]["text"][1]["value"] == "#10141880"
    assert census["color"]["background"][0]["value"] == "#f5f2ec"
    assert census["color"]["border"][0]["value"] == "#dcdcdc"

    assert census["text"]["letter_spacing"]["headings"][0]["value"] == "-0.02em"
    assert census["text"]["letter_spacing"]["body"][0]["value"] == "normal"
    assert census["shape"]["border_radius"][0] == {"value": "8px", "count": 9}
    assert census["shape"]["box_shadow"][0]["count"] == 5

    # The grid guess is Python arithmetic over the top values: gcd(24,16,8,32,40).
    assert census["spacing"]["values"][0] == {"value": "24px", "count": 40}
    assert census["spacing"]["base_unit_px"] == 8

    assert census["structure"] == {
        "headings": {"h1": 1, "h2": 4},
        "buttons": 3,
        "links": 12,
        "images": 6,
        # Added 2026-08-25 with the counted dimension. A raw census that never
        # reported it normalizes to 0 rather than to a missing key, so a reader
        # doing arithmetic on it cannot trip over None — and `measured` is
        # careful to treat an absent `labels` block, not a zero here, as the
        # signal that this capture predates the check.
        "sections": 0,
    }

    # The two blocks the counted dimension reads. A raw census without them
    # normalizes to an empty tally and an empty list, never to None.
    assert census["labels"] == {"total": 0, "above_heading": 0}
    assert census["actions"] == []


async def test_a_census_failure_never_fails_the_capture(monkeypatch):
    monkeypatch.setattr(
        security.socket, "getaddrinfo", _resolving({"acme.example": _PUBLIC_IP})
    )
    _install_fake_playwright(monkeypatch, {
        "title": "Acme — Ship faster",
        "dom_text": "Welcome to Acme.",
        "census_raises": _FakePlaywrightError("Execution context was destroyed"),
    })

    result = await capture_website("https://acme.example/")

    assert result.style_census == {}
    assert result.title == "Acme — Ship faster"
    assert result.dom_text == "Welcome to Acme."


def test_census_caps_hold_on_a_pathologically_styled_page():
    """A page with hundreds of one-off values still yields a bounded census."""
    raw = {
        "sampled": 800,
        "font_families": {f"Font{i:02d}, serif": i + 1 for i in range(15)},
        "font_weights": {str(100 * (i + 1)): i + 1 for i in range(9)},
        "font_sizes": {f"{i}px": i + 1 for i in range(10, 40)},
        "letter_spacing": {"body": {f"{i / 100}em": i + 1 for i in range(20)}},
        "line_heights": {f"{i}px": i + 1 for i in range(10, 40)},
        "text_colors": {f"rgb({i}, 0, 0)": i + 1 for i in range(30)},
        "background_colors": {f"rgb(0, {i}, 0)": i + 1 for i in range(25)},
        "border_colors": {f"rgb(0, 0, {i})": i + 1 for i in range(25)},
        "border_radii": {f"{i}px": i + 1 for i in range(20)},
        "box_shadows": {f"0 0 {i}px red": i + 1 for i in range(25)},
        "spacing": {f"{i}px": i + 1 for i in range(1, 41)},
        "structure": {"headings": {"h1": 1}, "buttons": 2, "links": 3, "images": 4},
    }

    census = capture_mod._normalize_census(raw)

    assert len(census["fonts"]["families"]) == 10
    assert len(census["fonts"]["sizes"]) == 15
    assert len(census["text"]["letter_spacing"]["body"]) == 10
    assert len(census["text"]["line_heights"]) == 10
    assert len(census["color"]["text"]) == 20
    assert len(census["color"]["background"]) == 20
    assert len(census["color"]["border"]) == 20
    assert len(census["shape"]["border_radius"]) == 10
    assert len(census["shape"]["box_shadow"]) == 10
    assert len(census["spacing"]["values"]) == 15

    # Most-used first, and no grid pretended into consecutive-integer chaos.
    assert census["spacing"]["values"][0]["value"] == "40px"
    assert census["spacing"]["base_unit_px"] is None


def test_an_empty_or_malformed_census_normalizes_to_nothing():
    assert capture_mod._normalize_census({}) == {}
    assert capture_mod._normalize_census(None) == {}
    assert capture_mod._normalize_census("nonsense") == {}
    assert capture_mod._normalize_census(["rgb(0, 0, 0)"]) == {}


def test_css_colors_normalize_to_hex_only_where_parseable():
    assert capture_mod._css_color_to_hex("rgb(255, 255, 255)") == "#ffffff"
    assert capture_mod._css_color_to_hex("rgb(16, 20, 24)") == "#101418"
    assert capture_mod._css_color_to_hex("rgba(0, 0, 0, 0.5)") == "#00000080"
    assert capture_mod._css_color_to_hex("rgb(0 128 255 / 0.25)") == "#0080ff40"
    # Anything the parser does not understand passes through untouched.
    assert capture_mod._css_color_to_hex("color(display-p3 1 0 0)") == "color(display-p3 1 0 0)"
    assert capture_mod._css_color_to_hex("rgb(300, 0, 0)") == "rgb(300, 0, 0)"


# ---------------------------------------------------------------------------
# Claim 5: llm_vision puts the images on the wire, or refuses
# ---------------------------------------------------------------------------

def _fake_anthropic(monkeypatch) -> list[dict]:
    """Replace the SDK client; return the list of messages.create payloads."""
    created: list[dict] = []

    class _Messages:
        async def create(self, **kwargs):
            created.append(kwargs)
            return SimpleNamespace(
                content=[SimpleNamespace(type="text", text="a verdict")],
                usage=SimpleNamespace(
                    input_tokens=321,
                    output_tokens=45,
                    cache_read_input_tokens=0,
                    cache_creation_input_tokens=0,
                ),
            )

    class _Client:
        def __init__(self, api_key=None):
            self.api_key = api_key
            self.messages = _Messages()

    monkeypatch.setattr(llm_client, "AsyncAnthropic", _Client)
    return created


async def test_llm_vision_builds_anthropic_image_blocks_ahead_of_the_text(monkeypatch):
    created = _fake_anthropic(monkeypatch)

    out = await llm_client.llm_vision(
        "What is weak about this page?",
        [b"desktop-png", b"mobile-png"],
        media_type="image/png",
        system="You are a critic.",
    )

    assert out == "a verdict"
    call = created[0]
    content = call["messages"][0]["content"]
    assert [block["type"] for block in content] == ["image", "image", "text"]
    assert content[0]["source"] == {
        "type": "base64",
        "media_type": "image/png",
        "data": base64.b64encode(b"desktop-png").decode(),
    }
    assert content[1]["source"]["data"] == base64.b64encode(b"mobile-png").decode()
    assert content[2]["text"] == "What is weak about this page?"
    assert call["system"] == "You are a critic."

    # **Inverted on 2026-08-28, and this is now the assertion that matters.**
    # It used to read `call["temperature"] == 0.3`. `temperature`, `top_p` and
    # `top_k` are rejected with a 400 on Opus 4.7 and later, so sending one does
    # not degrade the call — it kills every LLM request in the product. This
    # fails if anybody adds a sampling parameter back.
    for banned in ("temperature", "top_p", "top_k"):
        assert banned not in call, (
            f"{banned} is rejected with a 400 on Opus 4.7+; sending it breaks "
            "every LLM call, not just this one"
        )

    # Raised from 4096 with the move to Opus 5: thinking is on by default there
    # and `max_tokens` caps thinking PLUS the answer, so the old ceiling could
    # truncate a response that used to fit.
    assert call["max_tokens"] == llm_client._OPUS_MAX_TOKENS == 8192


async def test_llm_vision_records_usage_through_the_same_ledger(monkeypatch):
    _fake_anthropic(monkeypatch)
    recorded: list[dict] = []
    monkeypatch.setattr(llm_client, "record_llm_call", lambda **kw: recorded.append(kw))

    await llm_client.llm_vision("look", [b"img"])

    assert recorded[0]["input_tokens"] == 321
    assert recorded[0]["output_tokens"] == 45
    # Provider-prefixed like every litellm call site; model_pricing strips it.
    assert recorded[0]["model"].startswith("anthropic/")


async def test_llm_vision_rejects_an_oversized_image_before_calling_the_model(monkeypatch):
    created = _fake_anthropic(monkeypatch)
    too_big = b"\x00" * 3_400_000  # ~4.53M chars as base64, over the 4.5M cap

    with pytest.raises(ValueError) as exc:
        await llm_client.llm_vision("look", [too_big])

    assert "resize" in str(exc.value)
    assert created == []


async def test_llm_vision_refuses_non_anthropic_providers_loudly(monkeypatch):
    """The payload is Anthropic wire format; other providers would ignore the
    images and return a fluent answer about a page they never saw."""
    created = _fake_anthropic(monkeypatch)
    monkeypatch.setattr(llm_client.settings, "llm_provider", "openai")

    with pytest.raises(NotImplementedError) as exc:
        await llm_client.llm_vision("look", [b"img"])

    assert "openai" in str(exc.value)
    assert created == []


async def test_llm_vision_requires_at_least_one_image(monkeypatch):
    created = _fake_anthropic(monkeypatch)
    with pytest.raises(ValueError):
        await llm_client.llm_vision("look", [])
    assert created == []
