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

That promise holds only if the re-check sees **every** landing URL and sees it
**late**, and for a while it did neither. The desktop and mobile passes are two
independent navigations, so a host that redirects on the second request only
was checked on the first and rendered on the second; and each pass read its
`final_url` before the page was read, so a navigation landing during the
seconds-long lazy-content prime left `final_url` equal to the URL the founder
typed and skipped the check entirely, while the text and screenshots came from
wherever the page had gone. Both passes are validated now, each from a
`final_url` read after its own last read.

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
from urllib.parse import urljoin, urlsplit

import structlog
from pydantic import BaseModel, Field

from app.core.security import validate_external_url
from app.services.website.machine import read_machine_signals

logger = structlog.get_logger()

DESKTOP_VIEWPORT = {"width": 1440, "height": 900}
MOBILE_VIEWPORT = {"width": 390, "height": 844}

# The address a string-rendered document reports as its `url` and `final_url`.
# Nothing was fetched, so no real URL exists; the constant keeps every reader
# (reports, storage paths, logs) agreeing on how that fact is spelled.
REVISION_URL = "about:revision"

# Full-page screenshots are evidence for vision critics, and an infinite-scroll
# page would otherwise produce an image no model accepts. The cap trades the
# tail of a very long page for a bounded payload; the cut is recorded in
# `notes` so a report never presents a cropped page as the whole page.
MAX_SCREENSHOT_HEIGHT_PX = 8_000

# DOM text rides inside prompts; one pathological page must not be able to blow
# a context window. Truncation is likewise noted in `notes`.
DOM_TEXT_MAX_CHARS = 100_000

# How long to let the network go quiet after the document is parsed, before
# measuring and shooting the page. Long enough for hero images and webfonts,
# short enough that a page whose analytics never stop chattering is captured
# rather than waited on.
_SETTLE_MS = 8_000

# How long the lazy-content pass may take before the capture moves on without
# it. Bounded and optional: a page that will not scroll is still captured.
_PRIME_TIMEOUT_S = 20

# How far down the page that pass will walk. An infinite-scroll page must not
# be able to hold a capture open, and the screenshot is capped at 8,000px
# anyway — reading text well past the image the critics judge buys nothing.
_PRIME_MAX_PX = 30_000

# The census's own ceiling, shorter than the required steps'.
#
# It is the most expensive thing in a capture by a wide margin: for every
# sampled element it reads `getBoundingClientRect` and `getComputedStyle`, and
# each pair forces the browser to recompute layout. Hundreds of those on a
# heavy page, on half a CPU, is the slowest step there is — and it is the one
# the product can most afford to lose, because the screenshots and the text
# are what the critics actually judge.
_CENSUS_TIMEOUT_S = 20

# How long a capture will queue for the single browser slot before giving up.
#
# Long enough that an ordinary founder waiting behind one other check still
# gets served; short enough that a wedged capture cannot silently swallow
# every check that follows it. Roughly one full capture's worth of patience.
_QUEUE_WAIT_S = 330

# Scripts as module constants: each carries a distinctive marker string
# ("scrollHeight", "innerText", "querySelectorAll('meta')") that tests key on
# to fake `page.evaluate` without a browser.
#: Walk the page top to bottom, then back, so anything lazy-loaded is in the
#: DOM before the text is read.
#:
#: This is the difference between reading a page and reading its hero. Measured
#: on 2026-08-23 across three fresh captures: duolingo.com 2,320 characters,
#: gumroad.com 4,050, supabase.com 7,905 — and the placeholder count in each
#: delivered revision tracked it inversely, 10 / 7 / 3, as did the score damage,
#: -13 / -1 / 0. Duolingo's homepage plainly states its user count and app-store
#: rating; we never saw them, called them unsupported, and told the founder to
#: fill in facts their own page already displays.
#:
#: The full-page screenshot scrolls too, which is why the *images* were always
#: complete — but it runs after this point, so the text had already been read
#: from an unscrolled page. Ordering was the whole bug.
#: The cap is baked in rather than passed as an argument, so the script keeps
#: the single-parameter `page.evaluate(script)` shape every other script here
#: uses — which is what the browserless test doubles key on.
_PRIME_LAZY_JS = """async () => {
  const maxPx = __MAX_PX__;
  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
  const height = () => Math.max(
    document.body ? document.body.scrollHeight : 0,
    document.documentElement ? document.documentElement.scrollHeight : 0
  );
  const step = Math.max(400, Math.floor(window.innerHeight * 0.85));
  let y = 0;
  let guard = 0;
  while (y < Math.min(height(), maxPx) && guard < 80) {
    window.scrollTo(0, y);
    await sleep(110);
    y += step;
    guard += 1;
  }
  window.scrollTo(0, 0);
  await sleep(250);
  return height();
}""".replace("__MAX_PX__", str(_PRIME_MAX_PX))

_PAGE_HEIGHT_JS = (
    "() => Math.max("
    "document.body ? document.body.scrollHeight : 0, "
    "document.documentElement ? document.documentElement.scrollHeight : 0)"
)
_DOM_TEXT_JS = "() => document.body ? document.body.innerText : ''"

# The same text, without forcing the browser to lay the page out.
#
# `innerText` is the better read — it is what a person sees, in reading order,
# with hidden elements dropped. It is also **expensive**: the browser must
# compute layout for the whole document to know what is visible. On half a CPU
# with a long marketing page that measured over 45 seconds and failed the
# capture, on a page that had already navigated and screenshotted fine.
#
# `textContent` needs no layout at all, but on `body` it would sweep up the
# contents of every `<script>` and `<style>` — handing the critics a page of
# JavaScript source and calling it copy. So this walks text nodes and skips
# those, which keeps the cheapness and most of the quality.
#
# Used only as a fallback: quality first, and this when quality costs too much.
_DOM_TEXT_FALLBACK_JS = """() => {
  const SKIP = new Set(['SCRIPT', 'STYLE', 'NOSCRIPT', 'TEMPLATE', 'HEAD']);
  const walker = document.createTreeWalker(
    document.body || document.documentElement,
    NodeFilter.SHOW_TEXT,
    { acceptNode: (node) =>
        SKIP.has(node.parentNode && node.parentNode.nodeName)
          ? NodeFilter.FILTER_REJECT
          : NodeFilter.FILTER_ACCEPT }
  );
  const parts = [];
  let node;
  while ((node = walker.nextNode())) {
    const text = (node.nodeValue || '').trim();
    if (text) parts.push(text);
  }
  return parts.join('\\n');
}"""

# How long the good read gets before falling back to the cheap one.
_DOM_TEXT_TIMEOUT_S = 20
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

#: What moves on the page, and whether it stops when the reader asks.
#:
#: **Motion was entirely invisible to this product until 2026-08-30.** Nothing
#: in the census recorded it, no reviewer asked about it, and the two
#: screenshots are still images — so a vision model could not see it either.
#: Saibyl's own design law makes motion mandatory and says collapsing it under
#: `prefers-reduced-motion: reduce` "is not optional", and none of that had
#: ever been checked on a founder's page.
#:
#: Counted rather than judged: a running animation and a non-zero transition
#: are facts about computed style, not opinions.
#:
#: Marker: `animationName` — the browserless test doubles key on it.
_MOTION_JS = """() => {
  const SKIP = new Set(['SCRIPT', 'STYLE', 'NOSCRIPT', 'TEMPLATE', 'META', 'LINK', 'HEAD', 'TITLE']);
  const out = { animated: 0, transitioned: 0, names: {} };
  // A duration shorter than one frame cannot be seen as movement.
  //
  // **Not a judgment call — a property of displays.** At 60Hz a frame is
  // 16.7ms, so an animation shorter than that renders as a jump between two
  // states with nothing in between. The universal reduced-motion recipe sets
  // `animation-duration: .01ms !important` rather than `none`, precisely so
  // `animationend` still fires and scripts waiting on it do not hang. Reading
  // any duration above zero as motion therefore reports every page that
  // correctly honours the preference as ignoring it — measured 2026-08-30 on
  // saibyl.com, whose own reduced-motion block is exactly that recipe.
  const FRAME_S = 1 / 60;
  const seconds = (v) => {
    return (v || '').split(',').some((part) => {
      const n = parseFloat(part);
      if (!Number.isFinite(n)) return false;
      const secs = /ms\\s*$/.test(part.trim()) ? n / 1000 : n;
      return secs >= FRAME_S;
    });
  };
  let n = 0;
  const elements = document.body ? document.body.querySelectorAll('*') : [];
  for (const el of elements) {
    if (n >= 800) break;
    if (SKIP.has(el.tagName)) continue;
    const rect = el.getBoundingClientRect();
    if (rect.width < 1 || rect.height < 1) continue;
    const cs = getComputedStyle(el);
    if (cs.display === 'none' || cs.visibility === 'hidden') continue;
    n += 1;
    const name = cs.animationName;
    if (name && name !== 'none' && seconds(cs.animationDuration)) {
      out.animated += 1;
      for (const one of name.split(',')) {
        const key = one.trim();
        if (key && key !== 'none') out.names[key] = (out.names[key] || 0) + 1;
      }
    }
    if (seconds(cs.transitionDuration)) out.transitioned += 1;
  }
  return out;
}"""

#: The page's own first heading, as a person sees it. One line, read from the
#: rendered DOM, so it can be compared against the HTML a crawler receives.
#: Marker: `querySelector` — the browserless test doubles key on it.
_HEADLINE_JS = """() => {
  const h = document.querySelector('h1');
  if (!h) return '';
  return ((h.innerText || h.textContent || '').trim()).slice(0, 200);
}"""

#: `robots.txt` and `llms.txt` are small files at fixed paths. A short budget:
#: they are worth having and never worth waiting on, and a site that does not
#: serve them is the common case rather than a failure.
_SIDECAR_TIMEOUT_S = 8

#: Past this, the file is not a `robots.txt` any reader should be arguing from.
#: Google stops parsing at 500 KiB; this is well under that and well over any
#: real file.
_ROBOTS_MAX_CHARS = 100_000


async def _fetch_text(context: Any, url: str, path: str) -> str:
    """One small sidecar file, through the browser's own network stack."""
    target = urljoin(url, path)
    response = await context.request.get(target, timeout=_SIDECAR_TIMEOUT_S * 1000)
    if response.status != 200:
        return ""
    body = await response.text()
    return (body or "")[:_ROBOTS_MAX_CHARS]


async def _probe_exists(context: Any, url: str, path: str) -> bool:
    """Whether a sidecar file is actually served.

    Status alone is not enough. A single-page app with a catch-all rewrite
    answers 200 for every path with its own HTML shell, so `llms.txt` would
    read as present on every SPA on the web. A real one is served as text and
    is not an HTML document.
    """
    target = urljoin(url, path)
    response = await context.request.get(target, timeout=_SIDECAR_TIMEOUT_S * 1000)
    if response.status != 200:
        return False
    content_type = (response.headers or {}).get("content-type", "").casefold()
    if "html" in content_type:
        return False
    body = (await response.text() or "").lstrip()
    return bool(body) and not body[:200].casefold().startswith(("<!doctype", "<html"))


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

#: The smallest rendered dimension at which a visual element counts as imagery
#: rather than an icon, for `structure.visual_media`.
#:
#: **Measured, not chosen.** On 2026-08-30 the visible media on six real pages
#: was bucketed by minimum rendered dimension:
#:
#: | page | img | svg | other | >= 64px |
#: |---|---|---|---|---|
#: | anthropic.com | 0 | 16 | — | **1** |
#: | saibyl.com | 1 | 0 | — | **1** |
#: | stripe.com | 24 | 174 | 2 canvas | **23** |
#: | linear.app | 34 | 191 | 10 css-bg | **14** |
#: | vercel.com | 5 | 23 | 1 canvas | **6** |
#: | news.ycombinator.com | 1 | 0 | 30 css-bg | **0** |
#:
#: 64 is the lowest threshold at which every designed page scores at least one
#: and news.ycombinator.com — which genuinely is all text — scores none. Below
#: it the count fills with iconography: stripe.com ships 174 visible `<svg>`
#: and exactly 2 of them are 64px or larger.
_CENSUS_MEDIA_MIN_PX = 64

# Marker string for tests (the `getComputedStyle` call), same pattern as the
# meta/dom scripts above. Skips invisible elements, tallies computed styles,
# and counts structure document-wide; the sample cap keeps one pathological
# page from turning the census into a page crawl.
_STYLE_CENSUS_JS = ("""() => {
  const CAP = """ + str(_CENSUS_MAX_ELEMENTS) + """;
  const MEDIA_MIN_PX = """ + str(_CENSUS_MEDIA_MIN_PX) + """;
  const SKIP = new Set(['SCRIPT', 'STYLE', 'NOSCRIPT', 'TEMPLATE', 'META', 'LINK', 'HEAD', 'TITLE', 'BR', 'HR']);
  const tally = (map, key) => { if (key) map[key] = (map[key] || 0) + 1; };
  // A box that says it is standing in for a picture is not a picture.
  //
  // The revision loop is *told* to draw one where an image belongs — "draw a
  // CSS or inline-SVG placeholder and label it visibly as a placeholder" — so
  // without this the loop clears the imagery requirement by drawing a labelled
  // rectangle. Measured 2026-08-30: a page whose only graphic was a box
  // reading "[PLACEHOLDER: product screenshot]" scored 100 on `standard`, and
  // 73 with the box deleted. A 27-point gain for a gesture is the
  // deletion-gaming defect wearing the opposite costume.
  //
  // Self-declaration is the whole signal, and it is a fair one: our own
  // rewrites must label these, and a founder's hand-built page that says
  // "placeholder" on a live graphic is telling the truth about it too.
  const _declaresItselfAPlaceholder = (el) => {
    const label = (el.getAttribute && (el.getAttribute('aria-label') || el.getAttribute('alt'))) || '';
    const text = (el.textContent || '').slice(0, 300);
    return /placeholder|\\[owner:/i.test(label + ' ' + text);
  };
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
      sections: document.querySelectorAll('section, [role="region"]').length,
      // Imagery the reader can actually see, however the page draws it.
      // `images` above is the literal <img> count and stays that way, because a
      // field named `images` that quietly meant something else is the defect
      // this pair was split to avoid. A page can be fully illustrated with
      // inline SVG, a canvas, a video or a CSS background and still ship zero
      // <img> elements — anthropic.com does exactly that — so a rule that asks
      // "does this page show anything" must read this one. Filled by the walk
      // below, which already holds the rect and the computed style.
      visual_media: 0,
    },
    // Small, wide-tracked, upper-case text: the signature of a section label.
    // `above_heading` is the subset sitting immediately before a heading, which
    // is the pattern worth counting — a page that puts one of these over every
    // section has a rhythm a reader recognises without being able to name.
    labels: { total: 0, above_heading: 0 },
    // What the page's actions say, and where they go. Collected so a reader can
    // be told when one destination wears several different labels, which is a
    // fact about the page rather than an inference about intent.
    actions: [],
  };
  const ACTION_CAP = 40;
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

    // All three of the following reuse `cs` and the rect already read above, so
    // they add no layout work to the most expensive step in a capture.

    // Visible imagery, at or above the measured icon/image boundary. `tagName`
    // is upper-cased first: SVG elements are foreign elements and report their
    // tag in the authored lower case, so a bare === 'SVG' silently never fires.
    // Only the <svg> root matches — its <path>/<g> children report their own
    // tags — so one graphic is counted once.
    if (Math.min(rect.width, rect.height) >= MEDIA_MIN_PX && !_declaresItselfAPlaceholder(el)) {
      const mediaTag = el.tagName.toUpperCase();
      const bgImage = cs.backgroundImage;
      // A gradient is also a backgroundImage and is not imagery, so the url()
      // test is what separates a picture from a painted panel.
      const painted = bgImage && bgImage !== 'none' && bgImage.indexOf('url(') !== -1;
      if (mediaTag === 'IMG' || mediaTag === 'SVG' || mediaTag === 'VIDEO'
          || mediaTag === 'CANVAS' || painted) {
        out.structure.visual_media += 1;
      }
    }

    // A section label: small, tracked wide, upper-case, short, and a leaf so a
    // wrapper cannot be counted as its own label.
    const px = parseFloat(cs.fontSize) || 0;
    const track = parseFloat(cs.letterSpacing) || 0;
    if (!isHeading && px > 0 && px <= 14 && track / px >= 0.05 && el.children.length === 0) {
      const text = (el.textContent || '').trim();
      if (text && text.length <= 48 &&
          (cs.textTransform === 'uppercase' || text === text.toUpperCase())) {
        out.labels.total += 1;
        let next = el.nextElementSibling;
        if (!next && el.parentElement) next = el.parentElement.nextElementSibling;
        if (next && /^H[1-6]$/.test(next.tagName)) out.labels.above_heading += 1;
      }
    }

    // An action: a button, or an anchor painted like one. A page's body links
    // are not calls to action and would drown the signal, so an anchor counts
    // only when it carries a background or a border of its own.
    if (out.actions.length < ACTION_CAP) {
      const tag = el.tagName;
      // A gradient counts as paint, and leaving it out was a real defect.
      //
      // `bg` is `backgroundColor`; a gradient sets `background-image` and
      // leaves the colour transparent, so a button painted the way most design
      // systems paint their primary action was invisible here — no background,
      // no border, therefore "not an action". Saibyl's own design law
      // specifies exactly that button: a 135deg gradient, "never a flat fill".
      // Found 2026-08-30 when a page built by the graphics kit, carrying two
      // gradient CTAs, was told it had "no button, and no action with a
      // destination, anywhere on the page".
      const bgImg = cs.backgroundImage;
      const painted = (bg && bg !== 'rgba(0, 0, 0, 0)' && bg !== 'transparent')
        || (bgImg && bgImg !== 'none' && bgImg.indexOf('gradient') !== -1)
        || (cs.borderTopStyle !== 'none' && cs.borderTopWidth !== '0px');
      const isAction = tag === 'BUTTON'
        || el.getAttribute('role') === 'button'
        || (tag === 'INPUT' && /^(submit|button)$/i.test(el.type || ''))
        || (tag === 'A' && el.getAttribute('href') && painted);
      if (isAction) {
        const label = ((el.innerText || el.value || '').trim()).replace(/\\s+/g, ' ');
        if (label && label.length <= 60) {
          let where = null;
          if (tag === 'A') {
            // The query is dropped, and that part is deliberate: a full URL can
            // carry a token or an email, and `_census_text` renders this whole
            // dict into a reviewer prompt verbatim.
            //
            // The host and the fragment are kept, and dropping them was a bug.
            // `where` is the grouping key behind "one destination wearing
            // several labels", so anything it discards makes unrelated links
            // look like the same door. On path alone, anthropic.com collapsed
            // seven origins — status., trust., platform., support., academy.,
            // www. — into a single bucket keyed "/", and its two WCAG skip
            // links landed there too, so the page was told to rename actions
            // that already had nothing to do with each other.
            //
            // Same-origin links stay bare paths, both because that is what a
            // founder reads in the finding and because it is the shape the
            // stored censuses already carry.
            try {
              const u = new URL(el.getAttribute('href'), location.href);
              // A fragment is an anchor name — "#pricing", "#main". One
              // carrying key=value pairs is an OAuth implicit-flow payload
              // rather than a place on the page, and falls under the same
              // rule as the query.
              const frag = u.hash.indexOf('=') === -1 ? u.hash : '';
              const host = u.origin === location.origin ? '' : u.origin;
              where = host + u.pathname + frag;
            }
            catch (e) { where = null; }
          }
          out.actions.push({ label: label, where: where });
        }
      }
    }
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
    #: The page's OWN tags — `description` and `og:*`, exactly as the document
    #: ships them. Nothing this module knows about itself belongs here: the
    #: credibility critic is handed this dict under the heading "PAGE TAGS
    #: (what search results and link previews will show)" and asked to quote
    #: any drift between them and the page. A capture's bookkeeping in that
    #: block is a fact about our pipeline presented as a fact about the
    #: founder's site, and the founder pays for the critique that results.
    meta: dict
    #: What this capture had to cut, in our own words rather than the page's.
    #: Read by anything that must not present a cropped page as the whole page;
    #: never shown to a reviewer as the page's content.
    notes: dict = Field(default_factory=dict)
    screenshot_desktop: bytes  # PNG
    screenshot_mobile: bytes  # PNG
    # Measured computed styles (see `_normalize_census` for the shape). Empty
    # when the census could not run — never a reason the capture itself fails.
    style_census: dict = Field(default_factory=dict)
    #: What a machine reading this page can get from it, as opposed to a person
    #: looking at it — see `machine.read_machine_signals` for the shape. Empty
    #: on a pasted-HTML capture, which has no server response, no address to
    #: resolve a sidecar file against, and therefore nothing honest to say.
    machine: dict = Field(default_factory=dict)
    #: What moves, and whether it stops under `prefers-reduced-motion` — see
    #: `_motion`. Empty when the reading could not be taken; a still page
    #: reports zeroes with `respects_reduced_motion: None`, because it has no
    #: motion to honour rather than a preference it ignored.
    motion: dict = Field(default_factory=dict)


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
# **Two, since the instance moved to Standard (1 vCPU, 2 GB) on 2026-08-22.**
# A headless Chromium wants 300–500 MB, so two fit in 2 GB with room for the
# API beside them; on the old 512 MB `starter` plan they did not, and the
# failure was not a slow capture but the whole service being killed —
# `502 Bad Gateway` across every endpoint, taking down runs and billing calls
# that had nothing to do with a browser.
#
# The cost of the wrong number here is not paid by the founder whose check is
# slow. It is paid by every other founder on the platform. So it is raised
# only against measurement: on the new plan a capture of stripe.com takes
# about 11 seconds and simplepractice.com about 21, where both previously
# never finished at all.
#
# Still env-tunable, because the right value is a property of the instance
# rather than of this code.
MAX_CONCURRENT_CAPTURES = max(
    1, int(os.environ.get("WEBSITE_CAPTURE_CONCURRENCY", "2") or 2)
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


# The whole capture's ceiling, in seconds.
#
# **Measured, not guessed — the first value here was a guess and it was too
# tight.** A capture is two full renders, and each one is: navigate, settle,
# read the title, the meta tags and the page's text, take the style census,
# and screenshot up to 8,000px of page. On half a CPU, a heavy commercial
# marketing site does not fit that into two and a half minutes;
# simplepractice.com reached this ceiling with every individual step inside
# its own budget.
#
# Five minutes is a long time to wait, and it is the honest cost of judging a
# real website on a small instance. The founder is told what is happening and
# the work is already asynchronous. Tunable because the right number is a
# property of the CPU underneath: on a faster plan, lower it.
WEBSITE_CAPTURE_DEADLINE_S = max(
    60, int(os.environ.get("WEBSITE_CAPTURE_DEADLINE_S", "300") or 300)
)


def _overall_deadline(timeout_s: int) -> int:
    """The whole capture's ceiling.

    `timeout_s` bounds one `page.goto`. It bounds neither
    `chromium.launch()` — where two production checks hung indefinitely — nor
    the sum of every step across both viewports, which is what this covers.
    """
    return max(WEBSITE_CAPTURE_DEADLINE_S, timeout_s * 2 + 60)


#: How long a *revision* render waits for the browser slot.
#:
#: Longer than a check's, because the two are not in the same position. A check
#: that gives up has cost the founder nothing they cannot retry for the same
#: price. A revision render is round one of an artifact that already charged
#: 5,000 credits and already spent a 32,000-token generation call — giving up
#: there throws that away and returns "the checker is busy", which is a
#: sentence about our capacity, not about their page.
#:
#: It cannot wait forever: `page_revisions` is reaped at 80 minutes and three
#: rounds must fit inside that.
_REVISION_QUEUE_WAIT_S = 600


async def _bounded(
    coro, subject: str, timeout_s: int, queue_wait_s: int | None = None
) -> WebsiteCapture:
    """Run a capture under a hard ceiling, so no step can hang unbounded.

    The deadline starts when the browser slot is acquired, not when the
    request arrived: time spent waiting for another capture to finish is not
    this page's fault and must not be charged against its budget.

    **The wait for the slot is bounded too, and that omission was a real
    defect of its own.** There is one slot. `asyncio.wait_for` cancels a task
    and then *awaits* its cancellation, so a browser call wedged somewhere
    that never processes cancellation leaves the deadline itself waiting — and
    the `async with` below never exits, so the slot is never returned. Every
    later capture then blocked on `acquire()`, which sits OUTSIDE the deadline
    and therefore had no ceiling at all.

    One wedged page could take the whole Website Gauntlet down until the next
    deploy, and the symptom — every check sitting at `capturing` — looked
    exactly like the wedge repeating. Bounding the queue wait makes the
    difference visible: "this page is too heavy" and "the checker is busy" are
    now different sentences.
    """
    # Resolved here, not in the signature. A default argument is bound once at
    # import, so `queue_wait_s: int = _QUEUE_WAIT_S` would have frozen the value
    # and made every runtime override of the module constant a no-op — silently,
    # including the one the wedged-capture test uses to keep itself fast.
    if queue_wait_s is None:
        queue_wait_s = _QUEUE_WAIT_S

    slots = _slots()
    try:
        await asyncio.wait_for(slots.acquire(), timeout=queue_wait_s)
    except TimeoutError as exc:
        # The capture coroutine was built by the caller and will never run.
        # Closing it is not tidiness: an un-awaited coroutine raises a
        # RuntimeWarning at collection and holds its frame until then.
        coro.close()
        raise WebsiteCaptureError(
            "Website checks are busy right now — another page is still being "
            "read. Try again in a few minutes."
        ) from exc

    try:
        return await asyncio.wait_for(coro, timeout=_overall_deadline(timeout_s))
    except TimeoutError as exc:
        raise WebsiteCaptureError(
            f"We could not finish reading {subject} within "
            f"{_overall_deadline(timeout_s)} seconds. This is usually a very "
            "heavy page or a browser that would not start — try again in a "
            "moment."
        ) from exc
    finally:
        slots.release()


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

                # **The mobile pass is a second, independent navigation, and it
                # gets the same check.** It had none: a founder-supplied host
                # that redirects only on the second request — a counter, a
                # cookie, an A/B split — rendered wherever it landed into
                # `screenshot_mobile`, which `upload_screenshots` stores and
                # `GET /website/check/{id}/image?which=mobile` serves back. The
                # docstring's promise that the re-check "guarantees its content
                # never leaves this function" was true of half the capture.
                mobile_final = str(mobile["final_url"] or url)
                if mobile_final != url:
                    validate_external_url(mobile_final)
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

    The rendered document is still denied the network, bar the one Google
    Fonts link the generation prompt permits it — see
    `_abort_external_request` for why, and for why that exception exists.

    **It starts a browser, so it queues for a slot and runs under the deadline
    like every other capture.** It did neither, and both omissions were paid
    for by other founders: `generate_revision` calls this up to three times per
    revision, each revision is its own task, and every one of them was adding
    an unbudgeted 300–500 MB Chromium beside the two `capture_website` is
    allowed — on the instance whose failure mode is not a slow capture but
    `502` across every endpoint. A launch that hangs was unbounded too, which
    parks a revision at `generating` forever with no founder-readable error.
    """
    return await _bounded(
        _capture_html(html, timeout_s=timeout_s),
        "the rewritten page",
        timeout_s,
        # A revision waits longer for the slot than a check does: it has
        # already been charged for and already spent a generation call, so
        # losing the queue to a free-standing check throws real money away.
        queue_wait_s=_REVISION_QUEUE_WAIT_S,
    )


async def _capture_html(html: str, *, timeout_s: int) -> WebsiteCapture:
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


#: The only remote hosts a string-rendered document may reach: the Google
#: Fonts stylesheet endpoint and the file host it points at.
#:
#: `revise._HARD_REQUIREMENTS` tells the generator "system-font stacks, or at
#: most one Google Fonts <link> and nothing else remote" — and the two sides of
#: that contract have to agree. They did not: a revision that took the
#: permitted option rendered in Times/Arial for both screenshots, so the design
#: reviewer's very first signal ("if the primary typeface is a browser default
#: or system stack … major at the least, critical if the whole page is set in
#: it") fired on a page that specifies Inter, while the style census — read
#: from the declared stack — reported Inter in the same prompt. The grounding
#: line and the picture disagreed. Worse, those same bytes become
#: `capture_after`, which `upload_revision` serves as the founder's before/after
#: "after" image: a picture of a page their own browser does not render.
#:
#: This is an allowlist of two hosts, not a relaxation of the rule. Everything
#: else — beacons, dead CDNs, external script and image references — is still
#: aborted, and the host is compared against the parsed hostname so
#: `fonts.googleapis.com.example.invalid` is not one of them.
_FONT_HOSTS = frozenset({"fonts.googleapis.com", "fonts.gstatic.com"})


def _is_permitted_font_request(url: str) -> bool:
    """Whether a request is for the one remote thing the contract permits."""
    try:
        parts = urlsplit(url)
    except ValueError:
        return False
    if parts.scheme not in ("http", "https"):
        return False
    return (parts.hostname or "").lower() in _FONT_HOSTS


async def _abort_external_request(route: Any) -> None:
    """Deny the network to a string-rendered document, bar its fonts.

    A document that arrives as a string was written, not fetched — for page
    revisions, written by a model — so any network request it makes is a
    liability rather than a dependency: a beacon that reports where the page
    is being judged, or a reference to a dead CDN that stalls the render until
    the timeout. Everything except a data: URI (which never leaves the page)
    and the two Google Fonts hosts the generation prompt explicitly permits
    (`_FONT_HOSTS`) is aborted; the self-contained contract says the page must
    render from what it carries and the one typeface it is allowed to ask for,
    and this is that contract enforced.
    """
    url = str(route.request.url)
    if url.startswith("data:") or _is_permitted_font_request(url):
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
    # The pre-script document, filled in by the navigation below. Stays empty
    # for a pasted-HTML capture, which never made a request and so has no
    # server response to read — the machine-readability signals are absent for
    # those rather than guessed at.
    raw_html = ""
    try:
        page = await context.new_page()
        if html is not None:
            await context.route("**/*", _abort_external_request)
            await page.set_content(html, timeout=timeout_s * 1000, wait_until="load")
        else:
            # `domcontentloaded`, then settle — not `load`.
            #
            # `load` waits for **every** subresource, and on a real commercial
            # marketing page that includes analytics beacons, chat widgets,
            # lazily-loaded video and third-party pixels. Those keep the load
            # event pending long after the page is visually finished, which is
            # why simplepractice.com and stripe.com exhausted a 45-second
            # navigation budget while example.com completed in 94 seconds
            # end to end.
            #
            # The screenshot still wants images painted, so the settle below
            # waits for the network to go quiet — but only briefly, and its
            # expiry is not an error. A page whose trackers never go idle is
            # normal, and shooting it as it stands is the right answer.
            response = await page.goto(
                url, timeout=timeout_s * 1000, wait_until="domcontentloaded"
            )
            # The document as the server sent it, before a single script ran.
            #
            # This is what an answering crawler receives — GPTBot and
            # ClaudeBot do not execute JavaScript — and it is free here: the
            # bytes are already in the navigation response, so reading them
            # costs no second request and no extra load on the founder's site.
            # Fetching the URL again with an HTTP client would have been a
            # different request, possibly served differently, and twice the
            # traffic for a page we were already holding.
            if response is not None:
                raw_html = await _optional(response.text(), timeout_s, "raw_html") or ""
            try:
                await page.wait_for_load_state("networkidle", timeout=_SETTLE_MS)
            except Exception:  # noqa: BLE001 - never going idle is not a failure
                logger.info("website_capture_settle_skipped", url=url)

        result: dict[str, Any] = {"raw_html": raw_html}
        if not mobile:
            # **The evidence first, the extras after.** Text and tags are
            # viewport-independent; extracting once keeps the mobile pass to
            # what only it can provide — the mobile rendering.
            #
            # The order here is load-bearing and was wrong. The census ran
            # first and the page's text second, so a heavy page spent its
            # budget on an *optional* measurement and then failed on the
            # *required* one — observed on simplepractice.com, which navigated
            # fine and then died reading its own text.
            # Lazy content first, because everything below reads the DOM and
            # a page that has not been scrolled has not finished building
            # itself. Optional and bounded: a page that refuses to scroll is
            # captured as it stands, which is what the old behaviour did for
            # every page.
            await _optional(
                page.evaluate(_PRIME_LAZY_JS), _PRIME_TIMEOUT_S, "lazy_content"
            )

            result["title"] = await _optional(page.title(), timeout_s, "title")
            result["meta"] = await _optional(
                page.evaluate(_META_TAGS_JS), timeout_s, "meta"
            ) or {}

            # Evidence. A capture without the page's text is not a capture,
            # and returning an empty string would send the critics a blank
            # page to judge — so this is the one read with a second attempt
            # rather than a failure.
            #
            # `innerText` is what a person sees and is worth trying first. It
            # forces a full layout, which on a long page and half a CPU has
            # measured over 45 seconds; the fallback walks text nodes instead
            # and needs no layout at all.
            text = await _optional(
                page.evaluate(_DOM_TEXT_JS), _DOM_TEXT_TIMEOUT_S, "dom_text"
            )
            if not text:
                logger.info("website_capture_text_fallback", url=url)
                text = await _required(
                    page.evaluate(_DOM_TEXT_FALLBACK_JS),
                    timeout_s,
                    "the page's text",
                    url,
                )
            result["dom_text"] = text

            # One line, not the whole rendered document. The machine-readability
            # reader compares the headline a person sees against the HTML a
            # crawler receives, and `page.content()` would move hundreds of
            # kilobytes to answer a question about one heading.
            result["rendered_headline"] = await _optional(
                page.evaluate(_HEADLINE_JS), timeout_s, "rendered_headline"
            ) or ""

            # `robots.txt` decides whether any of the rest matters: a site that
            # disallows the answering crawlers cannot be cited however well it
            # is written. Fetched through the browser's own context so it uses
            # the same network stack, cookies and proxy as the navigation, and
            # optional in the strict sense — a site with no robots.txt is
            # normal, and a fetch that fails must never fail a capture.
            if url:
                result["robots_txt"] = await _optional(
                    _fetch_text(context, url, "/robots.txt"), _SIDECAR_TIMEOUT_S, "robots_txt"
                ) or ""
                result["llms_txt_found"] = await _optional(
                    _probe_exists(context, url, "/llms.txt"), _SIDECAR_TIMEOUT_S, "llms_txt"
                )

            # Best-effort by contract — this module's own docstring says a page
            # that defeats the census still captures, because the screenshots
            # and the text are the evidence the product cannot do without.
            # Until now "defeats" did not include "takes forever".
            #
            # It gets a **shorter** budget than the required steps, because it
            # is the most expensive thing here by a wide margin: it reads
            # `getBoundingClientRect` and `getComputedStyle` for hundreds of
            # elements, and each pair forces the browser to recompute layout.
            # On a small instance that is the single slowest step in a capture,
            # and it is the one the product can most afford to lose.
            result["style_census"] = await _optional(
                _style_census(page, url or REVISION_URL),
                _CENSUS_TIMEOUT_S,
                "style_census",
            ) or {}

        result["screenshot"], result["screenshot_truncated"] = await _required(
            _screenshot(page, viewport), timeout_s, "a screenshot", url
        )

        # Motion, and only after the screenshot.
        #
        # The second reading emulates `prefers-reduced-motion: reduce`, which
        # re-evaluates the page's media queries in place — no reload, no second
        # navigation, and nothing the founder's server sees. Doing it before
        # the screenshot would photograph the reduced page and quietly change
        # what six vision reviewers judge.
        #
        # **The comparison is the whole test, and it needs no threshold.** A
        # page that honours the preference moves less under it; a page that
        # ignores the preference is bit-for-bit identical. "Did anything
        # change at all" is a structural question, and the alternative — some
        # percentage of animations that ought to stop — would have been a
        # number nobody measured.
        if not mobile:
            normal = await _optional(page.evaluate(_MOTION_JS), timeout_s, "motion")
            reduced = None
            if normal:
                # Optional in the strict sense this module means it: a runtime
                # that cannot emulate the preference costs the *comparison*,
                # never the capture. `_motion` then reports the motion it did
                # see with `respects_reduced_motion: None`, which the rule
                # abstains on rather than reading as a failure.
                try:
                    await page.emulate_media(reduced_motion="reduce")
                    reduced = await _optional(
                        page.evaluate(_MOTION_JS), timeout_s, "motion_reduced"
                    )
                except Exception as exc:  # noqa: BLE001
                    logger.info(
                        "website_capture_reduced_motion_skipped",
                        error=f"{type(exc).__name__}: {exc}",
                    )
                finally:
                    # Restore, so nothing downstream inherits the emulation.
                    try:
                        await page.emulate_media(reduced_motion="no-preference")
                    except Exception:  # noqa: BLE001
                        pass
            result["motion"] = _motion(normal, reduced)

        # **Read last, not first — where the bytes came from, not where the
        # navigation first settled.** Snapshotted before the reads, a
        # `final_url` names a page the evidence did not come from, and the
        # caller's `final_url != url` re-check is then False: a redirect that
        # lands one moment late is never validated at all. Today's lazy-content
        # prime made that window deterministic and seconds wide, and everything
        # after it — the title, the tags, `dom_text` (which IS the report body)
        # and the screenshot — is read from wherever the page went.
        result["final_url"] = page.url
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
    """The two viewport passes as one WebsiteCapture, every cap noted.

    **The caps are recorded in `notes`, never in `meta`.** They were written
    into the same dict as the page's `description` and `og:*` tags, and the
    credibility critic renders that dict whole under "PAGE TAGS (what search
    results and link previews will show)". A page taller than 8,000px — which
    a long marketing page routinely is, and the lazy-content prime makes taller
    still — handed the reviewer `screenshot_desktop_truncated: desktop
    screenshot capped at 8000px of page height` as one of the founder's own
    tags, and asked it to judge the drift. The founder pays for that critique.
    """
    meta = dict(desktop["meta"] or {})
    notes: dict[str, str] = {}
    dom_text = str(desktop["dom_text"] or "")
    if len(dom_text) > DOM_TEXT_MAX_CHARS:
        notes["dom_text_truncated"] = (
            f"dom_text capped at {DOM_TEXT_MAX_CHARS} characters; "
            f"the page had {len(dom_text)}"
        )
        dom_text = dom_text[:DOM_TEXT_MAX_CHARS]
    if desktop["screenshot_truncated"]:
        notes["screenshot_desktop_truncated"] = (
            f"desktop screenshot capped at {MAX_SCREENSHOT_HEIGHT_PX}px of page height"
        )
    if mobile["screenshot_truncated"]:
        notes["screenshot_mobile_truncated"] = (
            f"mobile screenshot capped at {MAX_SCREENSHOT_HEIGHT_PX}px of page height"
        )

    logger.info(
        "website_captured",
        url=url,
        final_url=final_url,
        dom_chars=len(dom_text),
        desktop_bytes=len(desktop["screenshot"]),
        mobile_bytes=len(mobile["screenshot"]),
        truncations=sorted(notes),
    )
    return WebsiteCapture(
        url=url,
        final_url=final_url,
        title=desktop["title"],
        dom_text=dom_text,
        meta=meta,
        notes=notes,
        screenshot_desktop=desktop["screenshot"],
        screenshot_mobile=mobile["screenshot"],
        style_census=desktop.get("style_census") or {},
        # Derived here and the raw HTML dropped. The document a crawler
        # receives runs to hundreds of kilobytes on a real page, and every
        # question worth asking of it is answered by a bounded dict — the same
        # bargain `style_census` makes with the computed styles.
        motion=desktop.get("motion") or {},
        machine=read_machine_signals(
            raw_html=str(desktop.get("raw_html") or ""),
            rendered_headline=str(desktop.get("rendered_headline") or ""),
            rendered_text=dom_text,
            robots_txt=str(desktop.get("robots_txt") or ""),
            llms_txt_found=desktop.get("llms_txt_found"),
        ),
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
        "labels": _labels(raw.get("labels")),
        "actions": _actions(raw.get("actions")),
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
    for key in ("buttons", "links", "images", "sections", "visual_media"):
        out[key] = _as_count(raw.get(key))
    return out


# How many action labels the census keeps. Matches `ACTION_CAP` in the script;
# a page with more actions than this has a different problem.
_CENSUS_ACTION_CAP = 40


#: Animation names kept as evidence. Enough to quote, bounded like every other
#: census list.
_CENSUS_TOP_ANIMATIONS = 8


def _motion(normal: object, reduced: object) -> dict:
    """What moves, and whether it stops when the reader asks it to.

    `respects_reduced_motion` is `None` — not `False` — when the second reading
    could not be taken, or when there was no motion to reduce in the first
    place. A still page has not failed to honour the preference; it has nothing
    to honour, and reporting that as a defect would tell every deliberately
    static page to fix something it does not have. The rule that reads this
    abstains on `None`, exactly as the taste rules abstain on an unreadable
    census.
    """
    if not isinstance(normal, dict):
        return {}
    animated = _as_count(normal.get("animated"))
    transitioned = _as_count(normal.get("transitioned"))
    moving = animated + transitioned

    respects: bool | None = None
    if moving and isinstance(reduced, dict):
        still_moving = _as_count(reduced.get("animated")) + _as_count(
            reduced.get("transitioned")
        )
        # Any reduction at all counts. The preference asks for less motion, not
        # for none — a colour fade is not what it is about — so a page that
        # gives up nothing is the one ignoring it.
        respects = still_moving < moving

    return {
        "animated_elements": animated,
        "transitioned_elements": transitioned,
        "animations": _top(normal.get("names"), _CENSUS_TOP_ANIMATIONS),
        "respects_reduced_motion": respects,
    }


def _labels(raw: object) -> dict:
    """The section-label tally, or zeroes. Never None, so readers can do maths."""
    if not isinstance(raw, dict):
        return {"total": 0, "above_heading": 0}
    return {
        "total": _as_count(raw.get("total")),
        "above_heading": _as_count(raw.get("above_heading")),
    }


def _actions(raw: object) -> list[dict]:
    """Action labels and their destinations, trimmed, capped and deduplicated.

    Deduplicated on the exact (label, destination) pair rather than on the label
    alone: the same words pointing at two different places is an ordinary page,
    and two different labels pointing at one place is the thing worth reporting.
    Collapsing either would delete the signal.
    """
    if not isinstance(raw, list):
        return []
    seen: set[tuple[str, str | None]] = set()
    rows: list[dict] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        label = str(item.get("label") or "").strip()
        if not label:
            continue
        where_raw = item.get("where")
        where = str(where_raw).strip() if isinstance(where_raw, str) and where_raw.strip() else None
        key = (label, where)
        if key in seen:
            continue
        seen.add(key)
        rows.append({"label": label[:60], "where": where})
        if len(rows) >= _CENSUS_ACTION_CAP:
            break
    return rows


def _failure_reason(exc: Exception) -> str:
    """The first line of a Playwright error, in founder language where known."""
    message = str(exc).split("\n", 1)[0]
    for code, reason in _NET_ERROR_REASONS.items():
        if code in message:
            return reason
    return message or "the browser could not open the page"
