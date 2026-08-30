# PUBLIC INTERFACE
# ─────────────────────────────────────────────────────────
# read_machine_signals(raw_html, rendered_headline, rendered_text, ...)
# AI_CRAWLERS
#
# The judgment over these signals is `found.py`, kept separate so this module
# imports nothing from `critics` — `capture` calls it at module scope, and
# `critics` imports `capture`.
# ─────────────────────────────────────────────────────────
"""What a machine sees when it reads this page, as opposed to what a person does.

**Why this exists.** Every other reader in the gauntlet judges the page a human
gets: a rendered screenshot, or the text after JavaScript has run. That is half
the audience. The other half is a crawler — GPTBot, ClaudeBot, PerplexityBot,
Google-Extended — deciding whether this product can be described, quoted or
recommended when somebody asks a model what to use.

**The two halves pull against each other, and that is the point of measuring
both.** The techniques that make a page beautiful — imagery, inline SVG, canvas,
text set inside graphics, content assembled by JavaScript — are the same
techniques that make it unreadable to a crawler. Measured 2026-08-30:
linear.app scores 100 on the visual standard and ships **zero** structured data;
vercel.com renders **866 characters** of text behind a rich visual page. Neither
is a bad site. Both are half-legible to the machines their buyers now ask.

**Nothing here is a threshold, and that is deliberate.** Every signal below is
either a count reported as evidence or a structural yes/no. The one question
that would ordinarily want a threshold — *"is enough of this page visible
without JavaScript"* — is answered structurally instead, by asking whether the
page's own headline appears in the HTML a crawler receives. A ratio would have
needed a number nobody measured; the headline test needs none.

**No model call and no cost.** Like `measured` and `standard`, this is
arithmetic over evidence the capture already holds, so it is reproducible across
runs and free to re-run.

**A note on vocabulary.** The founder-facing strings here never say *the*
word for the `rel` value this module reads — a founder should not have to learn
it. It is "the page's declared web address" in prose and a regex in code.
"""
from __future__ import annotations

import re

#: The crawlers worth naming, and what each one decides.
#:
#: The distinction that matters, from `docs/SEO_AEO.md`: a *training* crawler
#: and an *answering* crawler are different jobs, and blocking the wrong one
#: deletes the product from the surface its buyers use. These are the ones that
#: fetch a page in order to answer a question about it.
AI_CRAWLERS: tuple[str, ...] = (
    "GPTBot",
    "OAI-SearchBot",
    "ChatGPT-User",
    "ClaudeBot",
    "Claude-User",
    "PerplexityBot",
    "Google-Extended",
    "CCBot",
)

_SCRIPTISH = re.compile(r"(?is)<(script|style|noscript|template)[^>]*>.*?</\1>")
_TAG = re.compile(r"<[^>]+>")
_WS = re.compile(r"\s+")

_JSONLD = re.compile(
    r'(?is)<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>'
)
_LD_TYPE = re.compile(r'"@type"\s*:\s*"([^"]+)"')
_H1 = re.compile(r"(?is)<h1[^>]*>(.*?)</h1>")
_IMG = re.compile(r"(?i)<img\b[^>]*>")
_HAS_ALT = re.compile(r"(?i)\balt\s*=")
_DECLARED_ADDRESS = re.compile(r'(?i)<link[^>]+rel=["\']?canonical')
_DESCRIPTION = re.compile(r'(?i)<meta[^>]+name=["\']?description')

#: How much of the headline must survive for it to count as present. Not a
#: judgment call: it is the number of characters of the *page's own* first
#: heading that must appear verbatim in the crawler's HTML. Short enough that a
#: headline broken across tags still matches, long enough that it cannot match
#: by accident.
_HEADLINE_PROBE_CHARS = 24

#: Caps, so the signals stay a bounded dict like the style census.
_MAX_TYPES = 12
_MAX_BLOCKED = 12


def _visible_text(html: str) -> str:
    """Roughly what a crawler reads: tags gone, scripts and styles gone."""
    return _WS.sub(" ", _TAG.sub(" ", _SCRIPTISH.sub(" ", html or ""))).strip()


def _first_heading(html: str) -> str | None:
    match = _H1.search(html or "")
    if not match:
        return None
    text = _WS.sub(" ", _TAG.sub(" ", match.group(1))).strip()
    return text or None


def _headline_reaches_the_crawler(raw_html: str, rendered_headline: str) -> bool | None:
    """Does the page's own first heading appear in the HTML a crawler receives?

    `None` when the question cannot be asked — a page with no `<h1>` at all is
    a different finding, made by `standard`, and answering `False` here would
    report the same defect twice under two names.

    The comparison is on the *rendered* headline, because that is the one the
    founder believes their page has. A prerendered or server-rendered page
    carries it in both; a client-rendered one carries it only after JavaScript,
    which most answering crawlers do not run.

    Matching is done on the raw HTML rather than on its visible text, because a
    headline is routinely split across tags — `<h1>Ship <em>faster</em></h1>` —
    and the probe would then fail on a page that carries the words perfectly
    well. Stripping tags from the raw HTML first is what makes that safe.
    """
    if not rendered_headline:
        return None
    probe = _WS.sub(" ", rendered_headline).strip()[:_HEADLINE_PROBE_CHARS].strip()
    if not probe:
        return None
    haystack = _WS.sub(" ", _TAG.sub(" ", _SCRIPTISH.sub(" ", raw_html or ""))).casefold()
    return probe.casefold() in haystack


def _structured_data(raw_html: str) -> dict:
    blocks = _JSONLD.findall(raw_html or "")
    types: list[str] = []
    for block in blocks:
        for found in _LD_TYPE.findall(block):
            if found not in types:
                types.append(found)
    return {"blocks": len(blocks), "types": sorted(types)[:_MAX_TYPES]}


def _images(raw_html: str) -> tuple[int, int]:
    tags = _IMG.findall(raw_html or "")
    without = [tag for tag in tags if not _HAS_ALT.search(tag)]
    return len(tags), len(without)


def _blocked_crawlers(robots_txt: str) -> list[str]:
    """Which answering crawlers this site tells to go away.

    Parsed per group, because `robots.txt` is grouped: a `Disallow: /` only
    applies to the user-agents named immediately above it. A naive substring
    search reports a site as blocking GPTBot when the disallow belonged to an
    unrelated agent three groups down.
    """
    if not robots_txt:
        return []

    # One group is: one or more consecutive `User-agent` lines, then its rules.
    # A rule line ends the agent list, so the *next* `User-agent` starts a new
    # group. Tracking that is the whole job — without it the agents of every
    # group pile up and one `Disallow: /` anywhere in the file appears to bind
    # to all of them.
    groups: list[tuple[list[str], list[tuple[str, str]]]] = []
    agents: list[str] = []
    rules: list[tuple[str, str]] = []
    reading_agents = False

    for line in robots_txt.splitlines():
        stripped = line.split("#", 1)[0].strip()
        if not stripped or ":" not in stripped:
            continue
        field, _, value = stripped.partition(":")
        field = field.strip().casefold()
        value = value.strip()
        if field == "user-agent":
            if not reading_agents and agents:
                groups.append((agents, rules))
                agents, rules = [], []
            agents.append(value.casefold())
            reading_agents = True
        elif field in ("allow", "disallow"):
            reading_agents = False
            rules.append((field, value))
    if agents:
        groups.append((agents, rules))

    blocked: list[str] = []
    for group_agents, group_rules in groups:
        # `Disallow: /` shuts the whole site. An `Allow: /` in the same group
        # contradicts it, and the tie goes to allow — the same way Google
        # resolves two rules of equal length. Reporting a block on an
        # ambiguous group would be the alarming reading of a file that does
        # not clearly say it.
        shuts = any(f == "disallow" and v == "/" for f, v in group_rules)
        opens = any(f == "allow" and v == "/" for f, v in group_rules)
        if not shuts or opens:
            continue
        for crawler in AI_CRAWLERS:
            if (crawler.casefold() in group_agents or "*" in group_agents) and (
                crawler not in blocked
            ):
                blocked.append(crawler)
    return blocked[:_MAX_BLOCKED]


def read_machine_signals(
    *,
    raw_html: str,
    rendered_headline: str = "",
    rendered_text: str = "",
    robots_txt: str = "",
    llms_txt_found: bool | None = None,
) -> dict:
    """The bounded, deterministic dict a machine-readability reader argues from.

    `raw_html` is the document the server sent, before any script ran — the
    bytes an answering crawler actually receives. `rendered_headline` and
    `rendered_text` are what a person ends up looking at.

    The headline arrives as a string rather than the rendered document because
    that document runs to hundreds of kilobytes on a real commercial page, and
    the only thing this module needs from it is one line.

    Every value is a count or a yes/no. Nothing here decides whether a page is
    good; that is the reader's job, and keeping the split means a later
    disagreement about the rules does not require re-capturing anything.
    """
    raw_html = raw_html or ""
    crawler_text = _visible_text(raw_html)
    total_images, without_alt = _images(raw_html)
    signals: dict = {
        "crawler_text_chars": len(crawler_text),
        "rendered_text_chars": len(rendered_text or ""),
        "headline_reaches_the_crawler": _headline_reaches_the_crawler(
            raw_html, rendered_headline or ""
        ),
        "h1_in_raw_html": len(_H1.findall(raw_html)),
        "structured_data": _structured_data(raw_html),
        "has_description": bool(_DESCRIPTION.search(raw_html)),
        "has_declared_address": bool(_DECLARED_ADDRESS.search(raw_html)),
        "images_in_raw_html": total_images,
        "images_without_alt": without_alt,
        "answering_crawlers_blocked": _blocked_crawlers(robots_txt),
    }
    # `None` where the fetch could not be made, so a reader can abstain rather
    # than report a missing file that nobody looked for. Same rule the census
    # follows: a zero meaning "we did not look" is this codebase's most-repeated
    # defect, and a False meaning it is the same bug wearing a different type.
    signals["has_llms_txt"] = llms_txt_found
    return signals

