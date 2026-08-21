# PUBLIC INTERFACE
# ─────────────────────────────────────────────────────────
# WebsiteCapture                — the rendered evidence for one URL
# WebsiteCaptureError           — capture failure, founder-readable message
# capture_website(url, *, timeout_s=45) -> WebsiteCapture
# capture_html(html, *, timeout_s=45) -> WebsiteCapture
# ─────────────────────────────────────────────────────────
"""Fetch and render a founder-supplied URL into judgeable evidence (PRD V3 §4a).

The critics judge the *rendered* page, not its source: a full-page screenshot at
a desktop and a mobile viewport, the readable DOM text, and the meta/OG tags.
This module produces exactly that bundle and nothing else — no database rows,
no storage writes; snapshot lifecycle belongs to the worker and storage to
`store.py`, so a capture can be tested without either.

Two hard rules:

**SSRF is checked before any fetch, and again after redirects.** The server is
fetching an arbitrary URL a founder typed. `validate_external_url` (the same
guard `test_api_guards.py` pins) rejects loopback, RFC1918, link-local and the
cloud metadata range up front — and the post-redirect landing URL is validated
too, because a public hostname that 302s to 169.254.169.254 is the classic
bypass. The redirect target has necessarily been *fetched* by the browser by
then; the re-check guarantees its content never leaves this function.

**Playwright is imported lazily, inside the call.** The local dev venv and CI
have no browser runtime — only the Docker image does (see the Dockerfile) — so
this module must import cleanly everywhere, and tests mock the import boundary.

One soft rule: **the style census is best-effort.** Alongside the screenshots,
the desktop pass measures the page's computed styles — fonts, colors, spacing,
radii, shadows — into `style_census`, the numbers that let a later reviewer say
"your letter-spacing is X" instead of guessing. A page that defeats the census
(a hostile stylesheet, a mid-walk navigation) still captures; the census logs
its failure and ships empty, because the screenshots and text are the evidence
the product cannot do without and the census is the evidence it is better with.
"""
from __future__ import annotations

import asyncio
import math
import os
import re
from typing import Any

import structlog
from pydantic import BaseModel, Field

from app.core.security import validate_external_url

logger = structlog.get_logger()

DESKTOP_VIEWPORT = {"width": 1440, "height": 900}
MOBILE_VIEWPORT = {"width": 390, "height": 844}

# The address a string-rendered document reports as its `url` and `final_url`.
# Nothing was fetched, so no real URL exists; the constant keeps every reader
# (reports, storage paths, logs) agreeing on how that fact is spelled.
REVISION_URL = "about:revision"

# Full-page screenshots are evidence for vision critics, and an infinite-scroll
# page would otherwise produce an image no model accepts. The cap trades the
# tail of a very long page for a bounded payload; the cut is recorded in `meta`
# so a report never presents a cropped page as the whole page.
MAX_SCREENSHOT_HEIGHT_PX = 8_000

# DOM text rides inside prompts; one pathological page must not be able to blow
# a context window. Truncation is likewise noted in `meta`.
DOM_TEXT_MAX_CHARS = 100_000

# Scripts as module constants: each carries a distinctive marker string
# ("scrollHeight", "innerText", "querySelectorAll('meta')") that tests key on
# to fake `page.evaluate` without a browser.
_PAGE_HEIGHT_JS = (
    "() => Math.max("
    "document.body ? document.body.scrollHeight : 0, "
    "document.documentElement ? document.documentElement.scrollHeight : 0)"
)
_DOM_TEXT_JS = "() => document.body ? document.body.innerText : ''"
_META_TAGS_JS = """() => {
  const out = {};
  for (const el of document.querySelectorAll('meta')) {
    const key = (el.getAttribute('name') || el.getAttribute('property') || '').toLowerCase();
    const content = el.getAttribute('content');
    if (!key || content === null) continue;
    if (key === 'description' || key.startsWith('og:')) out[key] = content;
  }
  return out;
}"""

# The style census samples computed styles across the page so a later reviewer
# argues from measured numbers, not vibes. The JS side only tallies raw values
# (value -> count); every cap, sort, hex conversion and the base-unit guess
# happen in `_normalize_census` below, in Python, where they are testable
# without a browser. All caps keep the census a bounded, deterministic dict.
_CENSUS_MAX_ELEMENTS = 800  # visible elements sampled; embedded in the JS below
_CENSUS_TOP_COLORS = 20  # text / background / border colors kept, each
_CENSUS_TOP_SPACING = 15  # margin/padding histogram entries kept
_CENSUS_TOP_SIZES = 15  # font-size histogram entries kept
_CENSUS_TOP_SHADOWS = 10  # box-shadow values kept
_CENSUS_TOP_COMMON = 10  # families, weights, line-heights, letter-spacings, radii

# Marker string for tests (the `getComputedStyle` call), same pattern as the
# meta/dom scripts above. Skips invisible elements, tallies computed styles,
# and counts structure document-wide; the sample cap keeps one pathological
# page from turning the census into a page crawl.
_STYLE_CENSUS_JS = ("""() => {
  const CAP = """ + str(_CENSUS_MAX_ELEMENTS) + """;
  const SKIP = new Set(['SCRIPT', 'STYLE', 'NOSCRIPT', 'TEMPLATE', 'META', 'LINK', 'HEAD', 'TITLE', 'BR', 'HR']);
  const tally = (map, key) => { if (key) map[key] = (map[key] || 0) + 1; };
  const out = {
    sampled: 0,
    font_families: {}, font_weights: {}, font_sizes: {},
    letter_spacing: { headings: {}, body: {} },
    line_heights: {},
    text_colors: {}, background_colors: {}, border_colors: {},
    border_radii: {}, box_shadows: {},
    spacing: {},
    structure: {
      headings: {
        h1: document.querySelectorAll('h1').length,
        h2: document.querySelectorAll('h2').length,
        h3: document.querySelectorAll('h3').length,
        h4: document.querySelectorAll('h4').length,
        h5: document.querySelectorAll('h5').length,
        h6: document.querySelectorAll('h6').length,
      },
      buttons: document.querySelectorAll('button, [role="button"], input[type="submit"], input[type="button"]').length,
      links: document.querySelectorAll('a[href]').length,
      images: document.querySelectorAll('img').length,
    },
  };
  const elements = document.body ? document.body.querySelectorAll('*') : [];
  for (const el of elements) {
    if (out.sampled >= CAP) break;
    if (SKIP.has(el.tagName)) continue;
    const rect = el.getBoundingClientRect();
    if (rect.width < 1 || rect.height < 1) continue;
    const cs = getComputedStyle(el);
    if (cs.display === 'none' || cs.visibility === 'hidden') continue;
    out.sampled += 1;
    tally(out.font_families, cs.fontFamily);
    tally(out.font_weights, cs.fontWeight);
    tally(out.font_sizes, cs.fontSize);
    const isHeading = /^H[1-6]$/.test(el.tagName);
    tally(isHeading ? out.letter_spacing.headings : out.letter_spacing.body, cs.letterSpacing);
    tally(out.line_heights, cs.lineHeight);
    tally(out.text_colors, cs.color);
    const bg = cs.backgroundColor;
    if (bg && bg !== 'rgba(0, 0, 0, 0)' && bg !== 'transparent') tally(out.background_colors, bg);
    if (cs.borderTopStyle !== 'none' && cs.borderTopWidth !== '0px') tally(out.border_colors, cs.borderTopColor);
    if (cs.borderRadius && cs.borderRadius !== '0px') tally(out.border_radii, cs.borderRadius);
    if (cs.boxShadow && cs.boxShadow !== 'none') tally(out.box_shadows, cs.boxShadow);
    const box = [cs.marginTop, cs.marginRight, cs.marginBottom, cs.marginLeft,
                 cs.paddingTop, cs.paddingRight, cs.paddingBottom, cs.paddingLeft];
    for (const v of box) { if (v && v !== '0px' && v !== 'auto') tally(out.spacing, v); }
  }
  return out;
}""")

# Chromium's net error codes, translated for the person who typed the URL. The
# raw form ("net::ERR_NAME_NOT_RESOLVED at https://…") reads as a stack trace
# to a founder; the report surfaces these messages verbatim.
_NET_ERROR_REASONS = {
    "ERR_NAME_NOT_RESOLVED": "the address could not be found — check the URL for typos",
    "ERR_CONNECTION_REFUSED": "the site refused the connection",
    "ERR_CONNECTION_TIMED_OUT": "the site took too long to respond",
    "ERR_CONNECTION_RESET": "the connection was interrupted by the site",
    "ERR_CERT_": "the site's security certificate failed validation",
    "ERR_SSL_": "a secure connection to the site could not be established",
    "ERR_TOO_MANY_REDIRECTS": "the site redirected in a loop and never settled on a page",
}


class WebsiteCaptureError(Exception):
    """A capture failure whose message a founder can read.

    The message is the product surface: no exception class names, no
    `net::ERR_*` codes, no stack traces. The original exception rides along as
    `__cause__` for logs.
    """


class WebsiteCapture(BaseModel):
    url: str
    final_url: str
    title: str | None
    dom_text: str
    meta: dict
    screenshot_desktop: bytes  # PNG
    screenshot_mobile: bytes  # PNG
    # Measured computed styles (see `_normalize_census` for the shape). Empty
    # when the census could not run — never a reason the capture itself fails.
    style_census: dict = Field(default_factory=dict)


def _import_playwright() -> Any:
    """The lazy-import seam. Tests monkeypatch this to inject a fake runtime.

    Returns the `playwright.async_api` module. Raising here (rather than at
    module import) is what lets every environment without a browser — local
    venvs, CI — import the app while still failing a real capture clearly.
    """
    try:
        from playwright import async_api
    except ImportError as exc:
        raise WebsiteCaptureError(
            "Website capture needs the Playwright browser runtime, which is not "
            "installed in this environment. It ships in the backend Docker image; "
            "for local use run: pip install playwright && playwright install chromium"
        ) from exc
    return async_api


async def capture_website(url: str, *, timeout_s: int = 45) -> WebsiteCapture:
    """Render `url` at desktop and mobile viewports and return the evidence.

    Raises HTTPException(400) when the URL (or its redirect target) fails the
    SSRF guard, and WebsiteCaptureError for everything the browser could not
    do — with the reason in founder-readable language.
    """
    validate_external_url(url)
    return await _bounded(_capture_website(url, timeout_s=timeout_s), url, timeout_s)


# How many captures may hold a browser at once, per process.
#
# **One, because the box is 512 MB.** `render.yaml` puts saibyl-backend on the
# `starter` plan; a headless Chromium wants 300–500 MB on its own. Two do not
# fit, and the failure is not a slow capture — it is the whole service being
# killed and restarted. Measured twice: three sample products reaching their
# website checks together produced hung captures on the first run and
# `502 Bad Gateway` across every endpoint on the second, taking down runs and
# billing calls that had nothing to do with the browser.
#
# So the cost of the wrong number here is not paid by the founder whose check
# is slow. It is paid by every other founder on the platform.
#
# Tunable by env because the right value is a property of the instance rather
# than of this code: on a plan with room for two browsers, set
# WEBSITE_CAPTURE_CONCURRENCY=2 and the queue halves.
MAX_CONCURRENT_CAPTURES = max(
    1, int(os.environ.get("WEBSITE_CAPTURE_CONCURRENCY", "1") or 1)
)

# How Chromium is started inside a container, and the reason the flagship
# module never worked on a real website.
#
# The launch took no arguments at all. Docker gives a container **64 MB of
# /dev/shm**, and Chromium uses shared memory for rendering — so a light page
# renders fine and a heavy commercial one exhausts it and hangs. That is
# exactly the shape of the production record: every successful check in this
# database was one small Vercel page, and every attempt at stripe.com or
# simplepractice.com — the kind of site a founder actually submits — failed or
# hung, on every try, for four days.
#
# `--disable-dev-shm-usage` moves that allocation to /tmp, which is disk-backed
# and not capped at 64 MB. It is the standard fix for Playwright in Docker and
# it is the one that matters here; the rest trim memory and start-up work that
# a headless screenshot pass has no use for.
_LAUNCH_ARGS = [
    "--disable-dev-shm-usage",
    "--no-sandbox",                     # already unprivileged in the container
    "--disable-gpu",
    "--disable-extensions",
    "--disable-background-networking",
    "--disable-backgrounding-occluded-windows",
    "--disable-renderer-backgrounding",
    "--mute-audio",
]

_capture_slots: asyncio.Semaphore | None = None


def _slots() -> asyncio.Semaphore:
    """Created lazily: a Semaphore binds to the running loop, and this module
    is imported at startup before there is one."""
    global _capture_slots
    if _capture_slots is None:
        _capture_slots = asyncio.Semaphore(MAX_CONCURRENT_CAPTURES)
    return _capture_slots


def _overall_deadline(timeout_s: int) -> int:
    """The whole capture's ceiling: two renders, plus room to launch and close.

    `timeout_s` bounds `page.goto`. It does not bound
    `chromium.launch()` — and that is where two production checks hung
    indefinitely, sitting at `capturing` with no screenshots and no error
    while a founder watched a spinner. Three checks had been started within
    four minutes of each other on one instance; the third failed honestly at
    its `goto` timeout and the two that were still launching never returned.
    """
    return timeout_s * 2 + 60


async def _bounded(coro, subject: str, timeout_s: int) -> WebsiteCapture:
    """Run a capture under a hard ceiling, so no step can hang unbounded.

    The deadline starts when the browser slot is acquired, not when the
    request arrived: time spent waiting for another capture to finish is not
    this page's fault and must not be charged against its budget.
    """
    try:
        async with _slots():
            return await asyncio.wait_for(coro, timeout=_overall_deadline(timeout_s))
    except TimeoutError as exc:
        raise WebsiteCaptureError(
            f"We could not finish reading {subject} within "
            f"{_overall_deadline(timeout_s)} seconds. This is usually a very "
            "heavy page or a browser that would not start — try again in a "
            "moment."
        ) from exc


async def _capture_website(url: str, *, timeout_s: int) -> WebsiteCapture:
    pw = _import_playwright()

    try:
        async with pw.async_playwright() as playwright:
            browser = await playwright.chromium.launch(headless=True, args=_LAUNCH_ARGS)
            try:
                desktop = await _render(browser, DESKTOP_VIEWPORT, timeout_s, mobile=False, url=url)

                # Redirects re-open the SSRF question: the guard above cleared
                # the URL the founder typed, not the one the site landed on.
                final_url = str(desktop["final_url"] or url)
                if final_url != url:
                    validate_external_url(final_url)

                mobile = await _render(browser, MOBILE_VIEWPORT, timeout_s, mobile=True, url=url)
            finally:
                await browser.close()
    except pw.TimeoutError as exc:
        raise WebsiteCaptureError(
            f"{url} did not finish loading within {timeout_s} seconds. The site may "
            "be slow or blocking automated visits — try again, or confirm the page "
            "loads in a normal browser."
        ) from exc
    except pw.Error as exc:
        raise WebsiteCaptureError(f"We couldn't load {url}: {_failure_reason(exc)}") from exc

    return _assemble(url=url, final_url=final_url, desktop=desktop, mobile=mobile)


async def capture_html(html: str, *, timeout_s: int = 45) -> WebsiteCapture:
    """Render a provided HTML string through the same pipeline as a URL capture.

    Same evidence bundle — desktop and mobile full-page screenshots, DOM text,
    meta tags, style census — but the document is set directly on the page
    rather than fetched, so there is no URL to SSRF-check and nothing to
    redirect. `url` and `final_url` are both `REVISION_URL`, the honest
    spelling of "this page never had an address".

    The rendered document is still denied the network entirely — see
    `_abort_external_request` for why.
    """
    pw = _import_playwright()

    try:
        async with pw.async_playwright() as playwright:
            browser = await playwright.chromium.launch(headless=True, args=_LAUNCH_ARGS)
            try:
                desktop = await _render(
                    browser, DESKTOP_VIEWPORT, timeout_s, mobile=False, html=html
                )
                mobile = await _render(browser, MOBILE_VIEWPORT, timeout_s, mobile=True, html=html)
            finally:
                await browser.close()
    except pw.TimeoutError as exc:
        raise WebsiteCaptureError(
            f"The page did not finish rendering within {timeout_s} seconds — its "
            "markup may be too heavy for a browser to lay out. Generate it again."
        ) from exc
    except pw.Error as exc:
        raise WebsiteCaptureError(
            f"The page could not be rendered: {_failure_reason(exc)}"
        ) from exc

    return _assemble(url=REVISION_URL, final_url=REVISION_URL, desktop=desktop, mobile=mobile)


async def _abort_external_request(route: Any) -> None:
    """Deny the network to a string-rendered document.

    A document that arrives as a string was written, not fetched — for page
    revisions, written by a model — so any network request it makes is a
    liability rather than a dependency: a beacon that reports where the page
    is being judged, or a reference to a dead CDN that stalls the render until
    the timeout. Everything except a data: URI (which never leaves the page)
    is aborted; the self-contained contract says the page must render from
    what it carries, and this is that contract enforced.
    """
    if str(route.request.url).startswith("data:"):
        await route.continue_()
        return
    await route.abort()


async def _render(
    browser: Any,
    viewport: dict[str, int],
    timeout_s: int,
    *,
    mobile: bool,
    url: str | None = None,
    html: str | None = None,
) -> dict[str, Any]:
    """One viewport's pass: open the page, extract (desktop only), screenshot.

    Exactly one of `url` (navigate to it) and `html` (set it as the document,
    with all outbound requests aborted) is given; everything downstream of the
    open — text, tags, census, screenshot — is the same pipeline either way.
    """
    context_kwargs: dict[str, Any] = {"viewport": viewport}
    if mobile:
        context_kwargs["is_mobile"] = True
    context = await browser.new_context(**context_kwargs)
    # Everything after the navigation used to be unbounded, and that is where
    # captures actually hung: `page.evaluate` has no default timeout in
    # Playwright, and the style census walks computed styles across the whole
    # DOM. Two heavy commercial pages sat at `capturing` for fifteen minutes
    # each with their `goto` long since returned. This covers the Playwright
    # actions; `_step` below covers the evaluates, which ignore it.
    context.set_default_timeout(timeout_s * 1000)
    try:
        page = await context.new_page()
        if html is not None:
            await context.route("**/*", _abort_external_request)
            await page.set_content(html, timeout=timeout_s * 1000, wait_until="load")
        else:
            await page.goto(url, timeout=timeout_s * 1000, wait_until="load")

        result: dict[str, Any] = {"final_url": page.url}
        if not mobile:
            # Text and tags are viewport-independent; extracting once keeps the
            # mobile pass to what only it can provide — the mobile rendering.
            # Extras: the product is better with them and does not need them,
            # so an overrun costs the field rather than the capture.
            result["title"] = await _optional(page.title(), timeout_s, "title")
            result["meta"] = await _optional(
                page.evaluate(_META_TAGS_JS), timeout_s, "meta"
            ) or {}
            # Best-effort by contract — this module's own docstring says a page
            # that defeats the census still captures, because the screenshots
            # and the text are the evidence the product cannot do without.
            # Until now "defeats" did not include "takes forever".
            result["style_census"] = await _optional(
                _style_census(page, url or REVISION_URL), timeout_s, "style_census"
            ) or {}

            # Evidence. A capture without the page's text is not a capture,
            # and returning an empty string would send the critics a blank
            # page to judge.
            result["dom_text"] = await _required(
                page.evaluate(_DOM_TEXT_JS), timeout_s, "the page's text", url
            )

        result["screenshot"], result["screenshot_truncated"] = await _required(
            _screenshot(page, viewport), timeout_s, "a screenshot", url
        )
        return result
    finally:
        await context.close()


async def _optional(awaitable: Any, timeout_s: int, what: str) -> Any:
    """A step whose failure costs a field, not the capture."""
    try:
        return await asyncio.wait_for(awaitable, timeout=timeout_s)
    except TimeoutError:
        logger.warning("website_capture_step_timeout", step=what, seconds=timeout_s)
    except Exception as exc:  # noqa: BLE001
        logger.warning("website_capture_step_failed", step=what, error=str(exc)[:200])
    return None


async def _required(awaitable: Any, timeout_s: int, what: str, url: str | None) -> Any:
    """A step the capture has no meaning without.

    Bounded like the others, but its overrun ends the capture with a sentence
    rather than degrading quietly — a page that came back with no text is not
    a cheaper capture, it is a wrong one.
    """
    try:
        return await asyncio.wait_for(awaitable, timeout=timeout_s)
    except TimeoutError as exc:
        raise WebsiteCaptureError(
            f"We loaded {url or 'the page'} but could not read {what} from it "
            f"within {timeout_s} seconds. This usually means a very heavy "
            "page — try again, or try a lighter page on the same site."
        ) from exc


def _assemble(*, url: str, final_url: str, desktop: dict, mobile: dict) -> WebsiteCapture:
    """The two viewport passes as one WebsiteCapture, every cap noted in meta."""
    meta = dict(desktop["meta"] or {})
    dom_text = str(desktop["dom_text"] or "")
    if len(dom_text) > DOM_TEXT_MAX_CHARS:
        meta["dom_text_truncated"] = (
            f"dom_text capped at {DOM_TEXT_MAX_CHARS} characters; "
            f"the page had {len(dom_text)}"
        )
        dom_text = dom_text[:DOM_TEXT_MAX_CHARS]
    if desktop["screenshot_truncated"]:
        meta["screenshot_desktop_truncated"] = (
            f"desktop screenshot capped at {MAX_SCREENSHOT_HEIGHT_PX}px of page height"
        )
    if mobile["screenshot_truncated"]:
        meta["screenshot_mobile_truncated"] = (
            f"mobile screenshot capped at {MAX_SCREENSHOT_HEIGHT_PX}px of page height"
        )

    logger.info(
        "website_captured",
        url=url,
        final_url=final_url,
        dom_chars=len(dom_text),
        desktop_bytes=len(desktop["screenshot"]),
        mobile_bytes=len(mobile["screenshot"]),
    )
    return WebsiteCapture(
        url=url,
        final_url=final_url,
        title=desktop["title"],
        dom_text=dom_text,
        meta=meta,
        screenshot_desktop=desktop["screenshot"],
        screenshot_mobile=mobile["screenshot"],
        style_census=desktop.get("style_census") or {},
    )


async def _screenshot(page: Any, viewport: dict[str, int]) -> tuple[bytes, bool]:
    """Full-page PNG, clipped at MAX_SCREENSHOT_HEIGHT_PX for endless pages."""
    height = int(await page.evaluate(_PAGE_HEIGHT_JS) or 0)
    if height > MAX_SCREENSHOT_HEIGHT_PX:
        shot = await page.screenshot(
            type="png",
            clip={
                "x": 0,
                "y": 0,
                "width": viewport["width"],
                "height": MAX_SCREENSHOT_HEIGHT_PX,
            },
        )
        return shot, True
    return await page.screenshot(type="png", full_page=True), False


async def _style_census(page: Any, url: str) -> dict:
    """Measure the page's computed styles — best-effort by contract.

    Whatever goes wrong here (a script error, a navigation mid-walk, a fake
    page in tests that never learned the census) is logged and answered with
    an empty census. The capture's hard evidence — screenshots, text, tags —
    must never be hostage to the soft evidence.
    """
    try:
        return _normalize_census(await page.evaluate(_STYLE_CENSUS_JS))
    except Exception as exc:
        logger.warning("style_census_failed", url=url, error=f"{type(exc).__name__}: {exc}")
        return {}


def _normalize_census(raw: object) -> dict:
    """Order, cap and annotate the tallies the census script measured.

    Pure and deterministic: same raw tallies in, same census out. Every list
    is sorted by count (desc), then value (asc) for stable ties, and capped by
    the `_CENSUS_TOP_*` constants; colors are normalized to hex; the spacing
    base unit is guessed here — GCD of the most-used pixel values — because
    arithmetic belongs in Python, not in a page-evaluated script.
    """
    if not isinstance(raw, dict) or not raw:
        return {}
    letter = raw.get("letter_spacing")
    if not isinstance(letter, dict):
        letter = {}
    spacing_rows = _top(raw.get("spacing"), _CENSUS_TOP_SPACING)
    return {
        "sampled_elements": _as_count(raw.get("sampled")),
        "fonts": {
            "families": _font_families(raw.get("font_families")),
            "weights": _top(raw.get("font_weights"), _CENSUS_TOP_COMMON),
            "sizes": _top(raw.get("font_sizes"), _CENSUS_TOP_SIZES),
        },
        "text": {
            "letter_spacing": {
                "headings": _top(letter.get("headings"), _CENSUS_TOP_COMMON),
                "body": _top(letter.get("body"), _CENSUS_TOP_COMMON),
            },
            "line_heights": _top(raw.get("line_heights"), _CENSUS_TOP_COMMON),
        },
        "color": {
            "text": _hex_rows(_top(raw.get("text_colors"), _CENSUS_TOP_COLORS)),
            "background": _hex_rows(_top(raw.get("background_colors"), _CENSUS_TOP_COLORS)),
            "border": _hex_rows(_top(raw.get("border_colors"), _CENSUS_TOP_COLORS)),
        },
        "shape": {
            "border_radius": _top(raw.get("border_radii"), _CENSUS_TOP_COMMON),
            "box_shadow": _top(raw.get("box_shadows"), _CENSUS_TOP_SHADOWS),
        },
        "spacing": {
            "values": spacing_rows,
            "base_unit_px": _base_unit_guess(spacing_rows),
        },
        "structure": _structure(raw.get("structure")),
    }


def _as_count(value: object) -> int:
    try:
        return max(int(value), 0)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 0


def _top(tally: object, limit: int) -> list[dict]:
    """A raw `{value: count}` tally as `[{value, count}]`, sorted and capped."""
    if not isinstance(tally, dict):
        return []
    rows = []
    for value, count in tally.items():
        n = _as_count(count)
        if n > 0:
            rows.append((str(value), n))
    rows.sort(key=lambda pair: (-pair[1], pair[0]))
    return [{"value": value, "count": n} for value, n in rows[:limit]]


def _font_families(tally: object) -> list[dict]:
    """Font stacks with counts, the first family split out for easy naming.

    The split-out key is `family` — the name downstream readers (the critics'
    census digest, the design-DNA prompt) reach for first.
    """
    return [
        {"stack": row["value"], "family": _first_family(row["value"]), "count": row["count"]}
        for row in _top(tally, _CENSUS_TOP_COMMON)
    ]


def _first_family(stack: str) -> str:
    return stack.split(",", 1)[0].strip().strip("'\"")


_RGB_RE = re.compile(r"rgba?\(([^)]*)\)")


def _hex_rows(rows: list[dict]) -> list[dict]:
    return [{"value": _css_color_to_hex(row["value"]), "count": row["count"]} for row in rows]


def _css_color_to_hex(value: str) -> str:
    """`rgb(…)`/`rgba(…)` as `#rrggbb` (or `#rrggbbaa`); anything else as-is."""
    match = _RGB_RE.fullmatch(value.strip())
    if not match:
        return value
    parts = match.group(1).replace("/", " ").replace(",", " ").split()
    if len(parts) not in (3, 4):
        return value
    try:
        r, g, b = (round(float(part)) for part in parts[:3])
        alpha = float(parts[3]) if len(parts) == 4 else 1.0
    except ValueError:
        return value
    if not all(0 <= c <= 255 for c in (r, g, b)) or not 0.0 <= alpha <= 1.0:
        return value
    out = f"#{r:02x}{g:02x}{b:02x}"
    if alpha < 1.0:
        out += f"{round(alpha * 255):02x}"
    return out


def _base_unit_guess(spacing_rows: list[dict]) -> int | None:
    """The GCD of the most-used spacing values, in px — the grid, if one exists.

    Hairlines (0/1px) are ignored so a border-heavy page cannot flatten the
    guess to 1, and a GCD under 2 is reported as no grid at all rather than a
    meaningless "1px system".
    """
    values = []
    for row in spacing_rows[:8]:
        px = _px_int(str(row["value"]))
        if px is not None and px >= 2:
            values.append(px)
    if not values:
        return None
    unit = values[0]
    for value in values[1:]:
        unit = math.gcd(unit, value)
    return unit if unit >= 2 else None


def _px_int(value: str) -> int | None:
    if not value.endswith("px"):
        return None
    try:
        return round(float(value[:-2]))
    except ValueError:
        return None


def _structure(raw: object) -> dict:
    if not isinstance(raw, dict):
        return {}
    headings = raw.get("headings")
    out: dict[str, Any] = {
        "headings": (
            {str(level): _as_count(count) for level, count in headings.items()}
            if isinstance(headings, dict)
            else {}
        )
    }
    for key in ("buttons", "links", "images"):
        out[key] = _as_count(raw.get(key))
    return out


def _failure_reason(exc: Exception) -> str:
    """The first line of a Playwright error, in founder language where known."""
    message = str(exc).split("\n", 1)[0]
    for code, reason in _NET_ERROR_REASONS.items():
        if code in message:
            return reason
    return message or "the browser could not open the page"
