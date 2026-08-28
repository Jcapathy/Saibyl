# PUBLIC INTERFACE
# ─────────────────────────────────────────────────────────
# measure_page(capture) -> CriticDimension
# MEASURED_KEY, MEASURED_LABEL
# EM_DASHES_PER_1K_LIMIT, RADIUS_SCALE_LIMIT, FONT_FAMILY_LIMIT,
# TEXT_COLOR_LIMIT, SHADOW_LIMIT
# ─────────────────────────────────────────────────────────
"""Defects a page can be *counted* to have, rather than judged to have.

**Why this sits next to six vision reviewers.** The gauntlet's six critics are
model calls: they read a screenshot and return an opinion. An opinion is the
right instrument for "does this hierarchy work" and the wrong one for "how many
different corner radii are on this page", which is arithmetic. Arithmetic run by
a vision model can be wrong, cannot be reproduced, and costs money every time it
is asked.

Everything here is computed from what the capture already measured —
`dom_text` and `style_census` — with no model call, no network and no
randomness. The same capture produces the same findings forever.

**It is also the part of a website check nobody can call a mirror.** The
objection that has dominated every dogfood run of this product is that synthetic
feedback may not correlate with real buyers. That is a fair challenge to a
reaction and an irrelevant one to a count: a page either has one `<h1>` or it
does not, and no belief about synthetic audiences changes the number. This is
the website check's equivalent of the prior-art search — the half that is true
whether or not the founder trusts the room.

**Thresholds are constants on purpose.** Every limit below is a judgment rather
than a law of design, and each is a module constant with its reasoning beside it
so a later reader can disagree with the number instead of reverse-engineering it
out of a conditional.

**Grouped by what is provable, never by what is inferred.** The action check
groups by where an action *goes*, not by what it appears to mean: two buttons
pointing at the same path with different words are demonstrably one ask, and
anything softer than that would be this module guessing at intent, which is what
the six reviewers are for.

**The action check is silent on pasted HTML, and that is not a clean pass.**
`capture_html` sets the document directly, so the page's address is
`about:blank` and `new URL('/signup', location.href)` throws for every relative
link. Destinations come back null, nothing groups, and no finding is produced no
matter how many differently-worded buttons point at one place. A URL capture is
unaffected. Found on the first run of the sample pages, where a page with two
labels on one destination reported nothing. Fixing it means giving the census a
base to resolve against; until then a review of pasted HTML is missing this
check rather than passing it.

**What this module deliberately does NOT check.** These are worth counting and
cannot be counted from what the capture returns, and estimating them would throw
away the only property that makes a measured check worth having:

  · **Whether one layout repeats down the page.** There is no honest DOM
    signature for "this section looks like the last one".
  · **Whether navigation wraps to a second line at desktop.** The census
    records no per-element geometry, only computed styles.

Both are named here rather than approximated.
"""
from __future__ import annotations

import re

from app.services.website.critics import CriticDimension, CriticFinding

MEASURED_KEY = "measured"

# Founder-facing. Not "static analysis" and not "automated checks": the founder
# bought a read of their page, and this is the half of it that is counted.
MEASURED_LABEL = "counted"


# ── Thresholds, each a judgment written down so it can be argued with ────────

# Em-dashes per 1,000 words of visible text.
#
# The em-dash is not a defect. Reaching for one in most sentences is a texture,
# and it is the texture a language model falls into when it is trying to sound
# considered, which makes a page dense with them read as machine-written to
# exactly the readers who care. This is not a corpus statistic and is not
# presented as one: it is set so ordinary editorial use passes and
# once-a-sentence use does not.
EM_DASHES_PER_1K_LIMIT = 6

# Distinct corner radii, ignoring square corners.
#
# A design system picks a radius scale — a couple of values applied by element
# size. Four is generous. Past that the page is not using a scale, it is using
# whatever each component shipped with, which a reader perceives as "slightly
# off" without being able to name it.
RADIUS_SCALE_LIMIT = 4

# Distinct font families actually rendered.
#
# A display face, a text face and at most a mono is three, and it is a
# deliberate pairing. A fourth is nearly always an embed, a widget, or a
# fallback firing that nobody intended.
FONT_FAMILY_LIMIT = 3

# Distinct text colours.
#
# Ink, a muted grey, a link colour, an inverted colour for dark panels and a
# state colour or two covers a real system. More than that is drift.
TEXT_COLOR_LIMIT = 6

# Distinct box-shadows.
#
# Shadow encodes how far off the page a surface sits, and elevation has levels.
# Four levels is already a lot of depth for a marketing page.
SHADOW_LIMIT = 4

# How many sections may carry a small upper-case label above their heading,
# as a share of the sections on the page.
#
# One of these is a device: it tells the reader what kind of thing is coming.
# One above every section is a rhythm, and it is the rhythm of a template — the
# reader stops reading them and the page loses the device entirely. A third of
# the sections is enough to use it where it earns its place.
LABELLED_SECTION_SHARE = 1 / 3

# Subtracted from 100 to score the dimension.
_SEVERITY_COST = {"critical": 25, "major": 12, "minor": 5}

_EM_DASH = "—"
_WORD = re.compile(r"[^\s]+")

# `_top()` in `capture` caps every histogram at ten rows, so a page with forty
# radii and a page with exactly ten are indistinguishable here. A count that
# lands on the cap is reported as "at least N" — the alternative is a report
# stating a number the capture never established.
_CENSUS_ROW_CAP = 10

# Below this there is not enough copy for density to mean anything.
_MIN_WORDS_FOR_DENSITY = 120


def _rows(census: dict, *path: str) -> list[dict]:
    """A census list at `path`, or empty. Never raises on a partial census."""
    node: object = census
    for key in path:
        if not isinstance(node, dict):
            return []
        node = node.get(key)
    return node if isinstance(node, list) else []


def _distinct(
    rows: list[dict], *, ignore: set[str] | None = None
) -> tuple[int, bool, list[str]]:
    """(count, whether the census cap was hit, the values themselves).

    **Deduplicated, and that is not redundant.** Most census histograms are
    already keyed by value, so this is a no-op on them. Font families are not:
    `_font_families` splits a family name out of each font *stack*, and a page
    that declares `Manrope, sans-serif` in one place and `Manrope, system-ui` in
    another yields two rows naming one typeface.

    Counting rows instead of values reported Saibyl's own landing page as using
    "7 distinct font families: Manrope, DM Mono, Manrope, DM Mono, Playfair
    Display, Playfair Display, Manrope" — three faces, listed seven times, on a
    page whose pairing is deliberate and correct. Found by the first live
    capture; no synthetic fixture had a repeated value in it.
    """
    seen: set[str] = set()
    values: list[str] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        value = str(row.get("value", "")).strip()
        if not value or (ignore and value in ignore) or value in seen:
            continue
        seen.add(value)
        values.append(value)
    return len(values), len(rows) >= _CENSUS_ROW_CAP, values


def _at_least(count: int, capped: bool) -> str:
    return f"at least {count}" if capped else str(count)


def _family_rows(census: dict) -> list[dict]:
    """Font families as `{value}` rows, since the census names that key `family`."""
    return [
        {"value": row.get("family") or row.get("stack")}
        for row in _rows(census, "fonts", "families")
        if isinstance(row, dict)
    ]


def _em_dash_finding(dom_text: str) -> CriticFinding | None:
    words = len(_WORD.findall(dom_text))
    dashes = dom_text.count(_EM_DASH)
    if words < _MIN_WORDS_FOR_DENSITY or dashes == 0:
        return None
    per_1k = dashes * 1000 / words
    if per_1k <= EM_DASHES_PER_1K_LIMIT:
        return None

    receipt = f"{dashes} em-dashes in {words:,} words, {per_1k:.1f} per 1,000"
    for line in dom_text.splitlines():
        stripped = line.strip()
        if _EM_DASH in stripped and len(stripped) > 40:
            receipt = f'{receipt}. For example: "{stripped[:140]}"'
            break

    return CriticFinding(
        severity="minor" if per_1k < EM_DASHES_PER_1K_LIMIT * 2 else "major",
        region="body copy",
        quote=receipt,
        why=(
            "No single one of these is wrong. Together they are a habit, and it "
            "is the habit a language model falls into when it is trying to sound "
            "considered, so a page this dense with them reads as machine-written "
            "to the readers most likely to be evaluating you."
        ),
        fix=(
            "Read each one and ask what it is doing. Most are a full stop or a "
            "comma. A few are parentheses. Keep the handful that genuinely mark "
            "an interruption in the sentence."
        ),
    )


def _heading_findings(structure: dict) -> list[CriticFinding]:
    headings = structure.get("headings")
    if not isinstance(headings, dict) or not headings:
        return []

    def level(name: str) -> int:
        try:
            return max(int(headings.get(name) or 0), 0)
        except (TypeError, ValueError):
            return 0

    found: list[CriticFinding] = []
    h1 = level("h1")
    if h1 == 0:
        found.append(
            CriticFinding(
                severity="major",
                region="page structure",
                quote="h1 elements on the page: 0",
                why=(
                    "The first-level heading is what a search engine, and the "
                    "answer engines now sitting in front of them, read as the "
                    "subject of the page. With none, they guess from whatever "
                    "text happens to come first."
                ),
                fix=(
                    "Make the main headline an h1. There should be exactly one, "
                    "and it should say what the product is."
                ),
            )
        )
    elif h1 > 1:
        found.append(
            CriticFinding(
                severity="minor",
                region="page structure",
                quote=f"h1 elements on the page: {h1}",
                why=(
                    "Several top-level headings declare several subjects and "
                    "leave the reader, human or machine, to pick one."
                ),
                fix="Keep the real headline as h1 and demote the rest to h2.",
            )
        )

    for parent, child in (("h2", "h3"), ("h3", "h4")):
        if level(child) > 0 and level(parent) == 0:
            found.append(
                CriticFinding(
                    severity="minor",
                    region="page structure",
                    quote=f"{child} headings: {level(child)}, with {parent}: 0",
                    why=(
                        "The outline has a rung missing, so anything reading "
                        "structure rather than looking at the page meets a jump "
                        "it has to guess across."
                    ),
                    fix=(
                        f"Either promote those {child} headings to {parent}, or "
                        f"give them a {parent} to sit under."
                    ),
                )
            )
    return found


def _label_finding(census: dict) -> CriticFinding | None:
    """A label above nearly every section is a template's rhythm, not a device."""
    labels = census.get("labels")
    structure = census.get("structure")
    if not isinstance(labels, dict) or not isinstance(structure, dict):
        return None
    above = labels.get("above_heading")
    sections = structure.get("sections")
    if not isinstance(above, int) or not isinstance(sections, int):
        return None
    if sections < 4 or above < 2:
        # Too few sections for a rhythm to exist, or too few labels to be one.
        return None

    allowed = max(1, int(sections * LABELLED_SECTION_SHARE))
    if above <= allowed:
        return None

    return CriticFinding(
        severity="major" if above >= sections else "minor",
        region="section headings",
        # Not "N of M sections": a card title is a heading too, so labels above
        # headings routinely outnumber sections and "14 of 9" is nonsense. The
        # section count is the yardstick for how much labelling a page of this
        # length can carry, not a denominator.
        quote=(
            f"{above} small upper-case labels sit above a heading, on a page "
            f"with {sections} sections."
        ),
        why=(
            "One of these tells the reader what kind of thing is coming. One "
            "above every section is a rhythm rather than a signal: the reader "
            "stops seeing them, and the page loses the device it was using."
        ),
        fix=(
            "Delete most of them. A section's place on the page already says "
            "what it is, and the headline can carry the rest. Keep the two or "
            "three where the label genuinely tells the reader something the "
            "heading does not."
        ),
    )


def _action_finding(census: dict) -> CriticFinding | None:
    """One destination wearing several different labels.

    Grouped by where the action *goes*, not by what it appears to mean. Two
    buttons pointing at the same path with different words are provably the
    same ask; anything softer than that would be this module guessing at intent,
    which is the vision reviewers' job.
    """
    actions = census.get("actions")
    if not isinstance(actions, list) or not actions:
        return None

    by_destination: dict[str, list[str]] = {}
    for row in actions:
        if not isinstance(row, dict):
            continue
        where = row.get("where")
        label = str(row.get("label") or "").strip()
        if not isinstance(where, str) or not where or not label:
            continue
        seen = by_destination.setdefault(where, [])
        if label.casefold() not in {existing.casefold() for existing in seen}:
            seen.append(label)

    worst = max(
        (pair for pair in by_destination.items() if len(pair[1]) > 1),
        key=lambda pair: len(pair[1]),
        default=None,
    )
    if worst is None:
        return None

    where, labels = worst
    quoted = ", ".join(f'"{label}"' for label in labels[:6])
    return CriticFinding(
        severity="major" if len(labels) >= 4 else "minor",
        region="calls to action",
        quote=f"{len(labels)} different labels all go to {where}: {quoted}",
        why=(
            "Repeating the ask down a long page is right — a reader who has "
            "scrolled should not have to scroll back. Renaming it each time is "
            "not. The reader cannot tell whether these are one action or "
            "several, so the page reads as offering choices it does not have."
        ),
        fix=(
            "Pick the clearest of these and use that exact wording every time "
            "the page asks. The repetition is the point; the variation is not."
        ),
    )


def _sprawl_finding(
    rows: list[dict],
    *,
    limit: int,
    region: str,
    noun: str,
    why: str,
    fix: str,
    ignore: set[str] | None = None,
) -> CriticFinding | None:
    """One finding for "more distinct X than a system would use"."""
    count, capped, values = _distinct(rows, ignore=ignore)
    if count <= limit:
        return None
    shown = ", ".join(values[:8])
    return CriticFinding(
        severity="major" if count > limit * 2 else "minor",
        region=region,
        quote=(
            f"{_at_least(count, capped)} distinct {noun} in use: {shown}. "
            f"A system would use about {limit}."
        ),
        why=why,
        fix=fix,
    )


def measure_page(capture: object) -> CriticDimension | None:
    """Count what can be counted on a captured page, or None if nothing could be.

    Takes the capture structurally rather than by import, so this module stays
    out of the browser-runtime import chain and can be tested with a plain
    object carrying `dom_text` and `style_census`.

    **None is a real answer and the caller must respect it.** `capture` treats a
    failed style census as something that must never fail the capture, so a
    capture can arrive with an empty census and very little text. Scoring that
    100 would be worse than saying nothing: it would put a perfect score on a
    page nothing was measured on, lift the gauntlet's mean, and make a page look
    better for having defeated the census. This codebase already names the
    inverse of that defect — a zero that means "we did not look" — as the one it
    produces most often. A hundred that means the same thing is the same bug
    with the sign flipped.
    """
    dom_text = str(getattr(capture, "dom_text", "") or "")
    raw_census = getattr(capture, "style_census", None)
    census: dict = raw_census if isinstance(raw_census, dict) else {}

    if not census and len(_WORD.findall(dom_text)) < _MIN_WORDS_FOR_DENSITY:
        return None

    findings: list[CriticFinding] = []
    strengths: list[str] = []

    em_dash = _em_dash_finding(dom_text)
    if em_dash:
        findings.append(em_dash)

    raw_structure = census.get("structure")
    structure: dict = raw_structure if isinstance(raw_structure, dict) else {}
    findings.extend(_heading_findings(structure))

    labels = _label_finding(census)
    if labels:
        findings.append(labels)

    actions = _action_finding(census)
    if actions:
        findings.append(actions)

    radius = _sprawl_finding(
        _rows(census, "shape", "border_radius"),
        limit=RADIUS_SCALE_LIMIT,
        region="components",
        noun="corner radii",
        # Square corners are a choice, not a rung on a radius scale. So is
        # fully-round: `50%` is a circle (an avatar, a dot) and `999px` is a
        # pill (a tag, a toggle). Neither is a step on a px scale, and counting
        # them made a page with avatars and pills look like it had no system
        # even when its actual scale was three values. Found running this
        # against Saibyl's own landing page on 2026-08-26.
        ignore={"0px", "0", "0%", "50%", "100%", "999px", "9999px"},
        why=(
            "A reader will not name this, and it is a large part of why a page "
            "feels assembled rather than designed."
        ),
        fix=(
            "Pick two or three radii and apply them by element size: small for "
            "chips and inputs, medium for cards, large for full-width panels."
        ),
    )
    if radius:
        findings.append(radius)

    fonts = _sprawl_finding(
        _family_rows(census),
        limit=FONT_FAMILY_LIMIT,
        region="typography",
        noun="font families",
        why=(
            "More typefaces are rendering than a pairing needs. Past a display "
            "face, a text face and a mono, the extras are usually an embed or a "
            "widget bringing its own, which the page then wears."
        ),
        fix=(
            "Find what is loading the extras. If it is a third-party embed, "
            "restyle it; if it is a fallback firing, the intended face is not "
            "loading for some readers."
        ),
    )
    if fonts:
        findings.append(fonts)

    colors = _sprawl_finding(
        _rows(census, "color", "text"),
        limit=TEXT_COLOR_LIMIT,
        region="typography",
        noun="text colours",
        why=(
            "Each one was probably reasonable where it was written. Together "
            "they read as a page with no rule about emphasis."
        ),
        fix=(
            "Reduce to a set with jobs: ink, a muted grey, a link colour, and a "
            "state colour. Anything left over is decoration."
        ),
    )
    if colors:
        findings.append(colors)

    shadows = _sprawl_finding(
        _rows(census, "shape", "box_shadow"),
        limit=SHADOW_LIMIT,
        region="components",
        noun="shadows",
        ignore={"none"},
        why=(
            "Shadow is how a surface says how far off the page it sits, so this "
            "many is claiming more levels of depth than the page has things to "
            "put on them."
        ),
        fix=(
            "Define two or three elevations and use them. Tint each shadow "
            "toward the background rather than pure black."
        ),
    )
    if shadows:
        findings.append(shadows)

    images = structure.get("images")
    if census and isinstance(images, int) and images == 0:
        findings.append(
            CriticFinding(
                severity="major",
                region="page",
                quote="img elements on the page: 0",
                why=(
                    "Some of the best pages on the web are purely typographic, "
                    "so this can be deliberate. It is worth being sure it was, "
                    "because a reader deciding whether to trust a product "
                    "usually wants to see the thing."
                ),
                fix=(
                    "Show the product doing its job. A screenshot of real "
                    "output beats an illustration of the idea."
                ),
            )
        )

    # Strengths are stated only where something was measured. Never inferred
    # from the absence of a finding on something this module never looked at.
    if census:
        radius_count, _, _ = _distinct(
            _rows(census, "shape", "border_radius"), ignore={"0px", "0", "0%"}
        )
        if 0 < radius_count <= RADIUS_SCALE_LIMIT:
            strengths.append(
                f"Corner radii come from a scale of {radius_count}, used consistently."
            )
        family_count, _, _ = _distinct(_family_rows(census))
        if 0 < family_count <= FONT_FAMILY_LIMIT:
            strengths.append(
                f"{family_count} typefaces render, which is a pairing rather than a pile."
            )
    if em_dash is None and len(_WORD.findall(dom_text)) >= _MIN_WORDS_FOR_DENSITY:
        strengths.append("The copy does not lean on the em-dash.")

    score = 100 - sum(_SEVERITY_COST.get(f.severity, 0) for f in findings)
    return CriticDimension(
        key=MEASURED_KEY,
        score=max(0, min(100, score)),
        findings=findings,
        strengths=strengths,
    )
