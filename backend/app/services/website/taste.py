# PUBLIC INTERFACE
# ─────────────────────────────────────────────────────────
# TASTE_RULES, TasteRule, TasteVerdict, TASTE_KEY
# check_taste(capture) -> list[TasteVerdict]
# taste_dimension(capture) -> CriticDimension | None
# taste_prompt_section() -> str        # the prose, for a vision reviewer
# taste_score(verdicts) -> int | None
# ─────────────────────────────────────────────────────────
"""One standard, two renderings: a number for us, a sentence for the founder.

**Why this exists.** The counted check (`measured.py`) is built entirely from
*variety penalties* — too many radii, too many colours, too many shadows, too
many em-dashes. Every one of them is satisfied by deleting things. On
2026-08-27 the revision loop found that gradient and took it: on the founder's
own page, `measured` went 35 -> 73 while `design`, judged by a model actually
looking at the page, fell 95 -> 72. Net +5 overall, so the loop reported a win
and handed back a plainer page. His words for the result were that there was
"not really much to it".

A rubric made only of penalties has a maximum at the empty page. So this module
carries two kinds of rule:

- a **violation** is a thing the page does that it should not, and
- a **requirement** is a thing the page must *have*.

Requirements are the half that deletion cannot satisfy. A page stripped to bare
type still fails "show the product doing its job" and still fails "one first-
level heading", and it earns nothing for having removed the buttons whose
contrast it was failing.

**Where the rules come from.** The founder's own design-taste standard, not an
invention of this file. Each rule below quotes the standard's own reasoning in
`why`, because a founder-facing sentence that paraphrases a rule tends to drift
away from what the rule actually checks.

**One row, two outputs, and that is the point.** `predicate` is what scores;
`why` and `fix` are what the founder reads. They live on the same row so they
cannot disagree. Where the prose and the check have drifted apart in the past,
the founder was told to fix something the score did not measure — and the score
penalised something no sentence explained.

Nothing here calls a model. Every verdict is arithmetic over the census the
capture already collected, which makes it reproducible across runs — the
property the vision dimensions do not have, and the reason this half of the
report can be trusted twice.
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

import structlog

from app.services.website.critics import CriticDimension, CriticFinding

logger = structlog.get_logger()

#: What the founder sees this dimension called. `measured` is the arithmetic of
#: the page's own consistency; this is the standard it is held to.
TASTE_KEY = "standard"


# ── the shapes ───────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class TasteRule:
    """A single rule, carrying its own check and its own explanation."""

    id: str
    #: `requirement` — the page must have this. `violation` — must not do this.
    #: The split is load-bearing: a rubric of violations alone peaks at a blank
    #: page, which is the defect this module was written to close.
    kind: str
    region: str
    severity: str
    #: Returns the offending measurement when the rule is broken, or None when
    #: the page is fine. Returning the measurement rather than a bool is what
    #: lets `quote` cite a number the founder can go and look at.
    predicate: Callable[[dict], str | None]
    #: Why it matters, in the standard's own terms. Shown to the founder and
    #: rendered into the vision prompt.
    why: str
    #: What to do about it. Never "consider" — an instruction.
    fix: str


@dataclass(frozen=True)
class TasteVerdict:
    rule: TasteRule
    passed: bool
    quote: str | None = None
    meta: dict = field(default_factory=dict)


# ── census helpers ───────────────────────────────────────────────────────────
#
# The census is a dict of `{value: count}` maps built by `capture.py`. It is
# read defensively throughout: a page that defeats the census still captures,
# and a rule that raises on a thin census would take the whole check down with
# it. A rule that cannot be decided abstains — see `check_taste`.

def _counts(census: dict, key: str) -> dict:
    value = (census or {}).get(key)
    return value if isinstance(value, dict) else {}


def _structure(census: dict) -> dict:
    value = (census or {}).get("structure")
    return value if isinstance(value, dict) else {}


def _headings(census: dict) -> dict:
    value = _structure(census).get("headings")
    return value if isinstance(value, dict) else {}


def _int(value: object) -> int | None:
    return value if isinstance(value, int) else None


def _norm_hex(value: str) -> str:
    return value.strip().lower().replace(" ", "")


# ── the standard ─────────────────────────────────────────────────────────────

#: Display serifs the standard names outright. Quoted: "Specifically BANNED as
#: defaults: `Fraunces` and `Instrument_Serif` (the two LLM-favorite display
#: serifs)." A page reaching for one of these has almost always reached for it
#: by default rather than by decision.
_BANNED_DEFAULT_FACES = ("fraunces", "instrument serif", "instrument_serif")

#: The palette the standard calls "the second-most-recurring AI-tell": warm
#: beige grounds with brass/clay accents and an espresso near-black. Every
#: premium-consumer page generated by a model reaches for it, so a founder
#: whose page carries it looks like every other generated page.
_SLOP_PALETTE = {
    "#f5f1ea", "#f7f5f1", "#fbf8f1", "#efeae0", "#ece6db", "#faf7f1", "#e8dfcb",
    "#b08947", "#b6553a", "#9a2436", "#9c6e2a", "#bc7c3a", "#7d5621",
    "#1a1714", "#1a1814", "#1b1814",
}


def _no_banned_display_face(census: dict) -> str | None:
    families = _counts(census, "font_families")
    hits = [
        name for name in families
        if any(banned in name.lower() for banned in _BANNED_DEFAULT_FACES)
    ]
    if not hits:
        return None
    return ", ".join(sorted(hits)[:3])


def _not_the_slop_palette(census: dict) -> str | None:
    seen: set[str] = set()
    for key in ("background_colors", "text_colors", "border_colors"):
        for value in _counts(census, key):
            if _norm_hex(value) in _SLOP_PALETTE:
                seen.add(_norm_hex(value))
    # One is a coincidence. Three is the palette.
    if len(seen) < 3:
        return None
    return ", ".join(sorted(seen)[:6])


def _eyebrow_restraint(census: dict) -> str | None:
    labels = (census or {}).get("labels")
    labels = labels if isinstance(labels, dict) else {}
    above = _int(labels.get("above_heading"))
    sections = _int(_structure(census).get("sections"))
    if above is None or not sections:
        return None
    # The standard allows the device, and objects to the rhythm. Two or three
    # on a long page is a signal; one above every section is wallpaper.
    if above <= 3 or above < sections * 0.6:
        return None
    return f"{above} upper-case labels sit above a heading, across {sections} sections"


def _page_shows_the_product(census: dict) -> str | None:
    images = _int(_structure(census).get("images"))
    if images is None:
        return None
    if images > 0:
        return None
    return "img elements on the page: 0"


def _one_first_level_heading(census: dict) -> str | None:
    h1 = _int(_headings(census).get("h1"))
    if h1 is None:
        return None
    if h1 == 1:
        return None
    return f"h1 elements on the page: {h1}"


def _page_asks_for_something(census: dict) -> str | None:
    buttons = _int(_structure(census).get("buttons")) or 0
    actions = (census or {}).get("actions")
    actions = actions if isinstance(actions, list) else []
    if buttons or actions:
        return None
    return "no button, and no action with a destination, anywhere on the page"


def _one_destination_one_label(census: dict) -> str | None:
    actions = (census or {}).get("actions")
    if not isinstance(actions, list):
        return None
    by_dest: dict[str, set[str]] = {}
    for action in actions:
        if not isinstance(action, dict):
            continue
        where, label = action.get("where"), action.get("label")
        if not where or not label:
            continue
        by_dest.setdefault(str(where), set()).add(str(label).strip())
    worst = max(
        (labels for labels in by_dest.values() if len(labels) > 1),
        key=len,
        default=None,
    )
    if not worst:
        return None
    return " / ".join(sorted(worst)[:4])


TASTE_RULES: tuple[TasteRule, ...] = (
    TasteRule(
        id="requires_an_image",
        kind="requirement",
        region="page",
        severity="major",
        predicate=_page_shows_the_product,
        why=(
            "A reader deciding whether to trust a product wants to see the thing. "
            "Some of the best pages on the web are purely typographic, so this can "
            "be deliberate — it is worth being sure it was."
        ),
        fix=(
            "Show the product doing its job. A screenshot of real output beats an "
            "illustration of the idea."
        ),
    ),
    TasteRule(
        id="requires_one_h1",
        kind="requirement",
        region="page",
        severity="major",
        predicate=_one_first_level_heading,
        why=(
            "One first-level heading is what tells a reader, a screen reader and a "
            "search engine what this page is. None leaves the question open; "
            "several answer it differently in the same document."
        ),
        fix="Give the page exactly one h1 — the sentence you would want quoted.",
    ),
    TasteRule(
        id="requires_an_action",
        kind="requirement",
        region="page",
        severity="critical",
        predicate=_page_asks_for_something,
        why=(
            "A page with nothing to press is a brochure. Whatever the reader has "
            "just been persuaded of, there is nowhere to put it."
        ),
        fix="Add the one thing you want the reader to do, where they finish reading.",
    ),
    TasteRule(
        id="no_banned_display_face",
        kind="violation",
        region="typography",
        severity="major",
        predicate=_no_banned_display_face,
        why=(
            "These are the display serifs a model reaches for when it is asked to "
            "make something feel editorial. They are not wrong, but they are the "
            "default, and a reader who has seen four other pages this month wearing "
            "the same face reads yours as one of them."
        ),
        fix=(
            "Pick a face because it suits this brand. If a serif is genuinely right, "
            "rotate to one that is not the automatic choice."
        ),
    ),
    TasteRule(
        id="not_the_slop_palette",
        kind="violation",
        region="colour",
        severity="major",
        predicate=_not_the_slop_palette,
        why=(
            "Warm beige ground, brass or clay accent, espresso near-black: this is "
            "the palette every generated premium page arrives in. Carrying three or "
            "more of its exact values is the single fastest way to look machine-made, "
            "because the brand disappears into a template a reader already knows."
        ),
        fix=(
            "Keep the palette if the brand genuinely earned it. Otherwise move to a "
            "family that is not the default reach — cold luxury, forest, cobalt on "
            "cream, terracotta on slate."
        ),
    ),
    TasteRule(
        id="eyebrow_restraint",
        kind="violation",
        region="section headings",
        severity="minor",
        predicate=_eyebrow_restraint,
        why=(
            "One of these tells the reader what kind of thing is coming. One above "
            "every section is a rhythm rather than a signal: the reader stops seeing "
            "them, and the page loses the device it was using."
        ),
        fix=(
            "Delete most of them. A section's place on the page already says what it "
            "is. Keep the two or three that tell the reader something the heading does not."
        ),
    ),
    TasteRule(
        id="one_destination_one_label",
        kind="violation",
        region="actions",
        severity="major",
        predicate=_one_destination_one_label,
        why=(
            "The same destination wearing several different labels reads as several "
            "different offers. A reader who declined one has quietly declined them all, "
            "without knowing they were the same door."
        ),
        fix=(
            "Say the same thing every time you ask. One destination, one label, "
            "repeated as often as the page needs it."
        ),
    ),
)


# ── running it ───────────────────────────────────────────────────────────────

def check_taste(capture: object) -> list[TasteVerdict]:
    """Judge a captured page against the standard.

    A rule whose predicate returns `None` because the census could not answer
    it **abstains** rather than passing. A page that defeats the census must not
    come back looking flawless — that is the "a zero meaning we did not look"
    failure this codebase names as the one it produces most often, and a pass
    meaning the same thing is that bug with the sign flipped.
    """
    census = getattr(capture, "style_census", None)
    if not isinstance(census, dict) or not census:
        logger.info("taste_no_census", detail="census empty; no verdicts returned")
        return []

    verdicts: list[TasteVerdict] = []
    for rule in TASTE_RULES:
        try:
            quote = rule.predicate(census)
        except Exception:
            logger.warning("taste_rule_raised", rule_id=rule.id, exc_info=True)
            continue
        # Both kinds read the same way: a quote means the page is offending.
        # A requirement's predicate returns the *absence* it found.
        verdicts.append(TasteVerdict(rule=rule, passed=quote is None, quote=quote))
    return verdicts


#: What each failure costs. A requirement is weighted above a violation of the
#: same severity on purpose: not having the thing is worse than having too many
#: of it, and this is the arithmetic that stops a stripped page from scoring.
_WEIGHT = {"critical": 34, "major": 18, "minor": 7}


def taste_score(verdicts: list[TasteVerdict]) -> int | None:
    """0-100, or None when nothing could be judged.

    `None` rather than 100: an empty verdict list means the census could not be
    read, and reporting a perfect score for a page nobody could measure is the
    inverse of the bug it looks like.
    """
    graded = [v for v in verdicts if v.quote is not None or v.passed]
    if not graded:
        return None
    score = 100
    for verdict in graded:
        if verdict.passed:
            continue
        cost = _WEIGHT.get(verdict.rule.severity, 10)
        if verdict.rule.kind == "requirement":
            cost = int(cost * 1.5)
        score -= cost
    return max(0, min(100, score))


def taste_dimension(capture: object) -> CriticDimension | None:
    """The standard as a dimension the report already knows how to render.

    `None` when nothing could be judged, for the same reason `measure_page`
    returns `None` on an empty census: appending a 100 would score a page for
    having defeated the measurement, and this codebase's most-repeated defect is
    a number that means "we did not look" being read as "there is nothing wrong".

    Not subject to the six-or-nothing rule. There is no model call and no
    network call here, so there is nothing to fail at — it either has verdicts
    or it does not.
    """
    verdicts = check_taste(capture)
    score = taste_score(verdicts)
    if score is None:
        return None

    findings = [
        CriticFinding(
            severity=v.rule.severity,
            region=v.rule.region,
            quote=v.quote or "",
            why=v.rule.why,
            fix=v.rule.fix,
        )
        for v in verdicts
        if not v.passed and v.quote is not None
    ]

    # What the page got right, named. A report that only lists failures reads as
    # a verdict on the founder rather than on the page, and the passes here are
    # the cheapest honest praise available: each one is a rule that was actually
    # checked, not an encouraging sentence.
    strengths = [
        f"{v.rule.region}: {v.rule.fix.rstrip('.')} — already true"
        for v in verdicts
        if v.passed and v.rule.kind == "requirement"
    ][:4]

    logger.info(
        "taste_dimension",
        score=score,
        failing=[v.rule.id for v in verdicts if not v.passed],
        checked=len(verdicts),
    )
    return CriticDimension(
        key=TASTE_KEY,
        score=score,
        findings=findings,
        strengths=strengths,
    )


def taste_prompt_section() -> str:
    """The same standard, as prose for a reviewer that has eyes.

    Rendered from `TASTE_RULES` rather than written out again, so the sentences
    a vision reviewer is held to and the sentences the counted check enforces
    cannot drift apart. Several rules in the standard need a rendered page to
    judge — whether a hero floats, whether a CTA wraps, whether a button's text
    can be read against its own fill — and those are the reviewer's job, not
    arithmetic's.
    """
    lines = [
        "THE STANDARD (judge the page against this, not against any other site):",
        "",
    ]
    for rule in TASTE_RULES:
        must = "The page MUST" if rule.kind == "requirement" else "The page MUST NOT"
        lines.append(f"- [{rule.region}] {must}: {rule.why} Fix: {rule.fix}")
    lines.append("")
    lines.append(
        "Judge only what you can see. Do not reward a page for being empty: a page "
        "with nothing on it fails this standard rather than passing it."
    )
    return "\n".join(lines)
