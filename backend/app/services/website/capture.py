# PUBLIC INTERFACE
# ─────────────────────────────────────────────────────────
# WebsiteCapture                — the rendered evidence for one URL
# WebsiteCaptureError           — capture failure, founder-readable message
# capture_website(url, *, timeout_s=45) -> WebsiteCapture
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
"""
from __future__ import annotations

from typing import Any

import structlog
from pydantic import BaseModel

from app.core.security import validate_external_url

logger = structlog.get_logger()

DESKTOP_VIEWPORT = {"width": 1440, "height": 900}
MOBILE_VIEWPORT = {"width": 390, "height": 844}

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
    pw = _import_playwright()

    try:
        async with pw.async_playwright() as playwright:
            browser = await playwright.chromium.launch(headless=True)
            try:
                desktop = await _render(browser, url, DESKTOP_VIEWPORT, timeout_s, mobile=False)

                # Redirects re-open the SSRF question: the guard above cleared
                # the URL the founder typed, not the one the site landed on.
                final_url = str(desktop["final_url"] or url)
                if final_url != url:
                    validate_external_url(final_url)

                mobile = await _render(browser, url, MOBILE_VIEWPORT, timeout_s, mobile=True)
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
    )


async def _render(
    browser: Any,
    url: str,
    viewport: dict[str, int],
    timeout_s: int,
    *,
    mobile: bool,
) -> dict[str, Any]:
    """One viewport's pass: navigate, extract (desktop only), screenshot."""
    context_kwargs: dict[str, Any] = {"viewport": viewport}
    if mobile:
        context_kwargs["is_mobile"] = True
    context = await browser.new_context(**context_kwargs)
    try:
        page = await context.new_page()
        await page.goto(url, timeout=timeout_s * 1000, wait_until="load")

        result: dict[str, Any] = {"final_url": page.url}
        if not mobile:
            # Text and tags are viewport-independent; extracting once keeps the
            # mobile pass to what only it can provide — the mobile rendering.
            result["title"] = (await page.title()) or None
            result["meta"] = await page.evaluate(_META_TAGS_JS)
            result["dom_text"] = await page.evaluate(_DOM_TEXT_JS)

        result["screenshot"], result["screenshot_truncated"] = await _screenshot(page, viewport)
        return result
    finally:
        await context.close()


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


def _failure_reason(exc: Exception) -> str:
    """The first line of a Playwright error, in founder language where known."""
    message = str(exc).split("\n", 1)[0]
    for code, reason in _NET_ERROR_REASONS.items():
        if code in message:
            return reason
    return message or "the browser could not open the page"
