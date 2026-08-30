# PUBLIC INTERFACE
# ─────────────────────────────────────────────────────────
# run_critic_gauntlet(capture, *, reference=None, organization_id=None)
#     -> CritiqueResult   [async]
# CritiqueResult, CriticDimension, CriticFinding, CriticError
# ─────────────────────────────────────────────────────────
"""The critic gauntlet: six reviewers judge a rendered page (PRD_V3 §4b).

Each reviewer is ONE vision call with its own rubric, and each is blind to the
other five — that independence is the design. Specialists who cannot see each
other's verdicts give uncorrelated reads, so where they agree the agreement is
evidence rather than echo. Nothing connects them, so they run concurrently.

The reviewers judge what a visitor is shown, not what the HTML intends: the
desktop screenshot for how the page reads, earns trust, and routes a reader to
action; the extracted page text for the words; the phone screenshot for what a
phone actually renders. A finding may quote only what is visible in that
evidence — the prompt forbids inventing content — and every finding ends in an
instruction the founder can paste into their coding tool unedited, per the §5
standard ("improve your value proposition" is a defect, not a finding).

The sixth reviewer judges the look itself, by measurement. The page's computed
styles arrive as counted facts — fonts, colors, radii, shadows, spacing — so
"the type feels loose" becomes a number instead of a mood. Given a reference
site, it stops asking "is this good?" and asks "how does this differ from the
benchmark, in measured values?", quoting both numbers for every gap — and its
call is the only one that carries two screenshots. The other five reviewers
receive one measured line from the same styles for grounding; their rubrics
are unchanged.

Six or nothing: a reviewer that cannot finish fails the whole gauntlet with
its dimension named, because a five-reviewer verdict presented as the page's
score would be a number quietly missing a sixth of its meaning.

The overall score is the rounded mean of the six dimension scores, and the
one-sentence page takeaway comes from the copy reviewer, whose rubric is the
message a stranger actually receives.
"""
from __future__ import annotations

import asyncio
import json
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from typing import Literal

import structlog
from pydantic import BaseModel, Field, ValidationError

from app.core.llm_client import _extract_json, llm_vision
from app.services.billing.usage_ledger import usage_context
from app.services.website.capture import WebsiteCapture

logger = structlog.get_logger()

# How much extracted page text rides along. The screenshot-first reviewers get
# an extract for cross-reference; the copy reviewer gets the text as primary
# evidence and therefore more of it.
_DOM_EXCERPT_CHARS = 4_000
_DOM_PRIMARY_CHARS = 12_000

# How much of a style-measurement table rides in the design reviewer's prompt.
# The capture side aggregates before it stores, so a table this long already
# means an unusually baroque page; the cut keeps the prompt bounded either way.
_CENSUS_CHARS = 6_000

# `llm_vision`'s bound on one encoded image (~4.5MB of base64). Guarded here,
# before the call, so the failure a founder sees names the screenshot and the
# remedy instead of surfacing a transport error. Downscaling is the capture
# side's job; this is the honest stop when it did not happen.
_MAX_BASE64_BYTES = 4_500_000


# ── public result models ─────────────────────────────────────────────


class CriticFinding(BaseModel):
    severity: Literal["critical", "major", "minor"]
    region: str
    # The prose reviewers may honestly leave this empty for purely visual
    # findings (a spacing gap has nothing to quote); forcing it there made the
    # hierarchy reviewer fail whole runs. The DESIGN reviewer's quotes are its
    # measured values and MUST NOT be empty — enforced by _MeasuredFinding on
    # its parse path, so the retry nudge lands only where the receipt is a
    # number. Both facts were found by live gates, not by mocked tests.
    quote: str
    why: str
    fix: str


class CriticDimension(BaseModel):
    key: str
    score: int = Field(ge=0, le=100)
    findings: list[CriticFinding]
    strengths: list[str]


class CritiqueResult(BaseModel):
    overall_score: int = Field(ge=0, le=100)
    page_takeaway: str
    dimensions: list[CriticDimension]


class CriticError(Exception):
    """A reviewer could not finish, so no page verdict exists.

    Carries `dimension` so a caller can say which reviewer failed without
    parsing the message. The message itself is written for the founder who
    ran the check, not for a log reader.
    """

    def __init__(self, dimension: str, message: str):
        super().__init__(message)
        self.dimension = dimension


# ── what each reviewer returns over the wire ─────────────────────────


class _CriticResponse(BaseModel):
    score: int = Field(ge=0, le=100)
    findings: list[CriticFinding]
    strengths: list[str]


class _CopyResponse(_CriticResponse):
    page_takeaway: str


class _MeasuredFinding(CriticFinding):
    """A design-reviewer finding: the quote carries measured values, never air."""

    quote: str = Field(min_length=1)


class _DesignResponse(_CriticResponse):
    findings: list[_MeasuredFinding]


# ── the rules every reviewer carries ─────────────────────────────────

#: Mirrors the frontend's banned-word list and `report_agent.HOUSE_STYLE`: the
#: reviewer's findings render in the founder UI, so the model is told the same
#: vocabulary rule every other author of founder-facing sentences follows.
VOCABULARY_RULE = """\
VOCABULARY — the reader is the founder who owns this page, not a market
researcher. Never use any of these words in a finding, strength, fix, or
takeaway: ICP, variant, A/B, adversarial, cohort, arena, lens, archetype,
canonical, valence, simulation, project. Write "the page", "the reader",
"the people you sell to", "a version" instead."""

_SHARED_RULES = """\
HOW TO REVIEW — these rules are the review:
- Name the exact element, sentence, number, or button, every time. "Make the
  value clearer" is a failed finding; a real finding quotes the words that
  fail and says why they fail.
- "quote" carries only words actually visible in the screenshot or the page
  text above. Never invent, complete from memory, or paraphrase into a
  quote. If a problem is purely visual, leave "quote" empty and pin the spot
  with "region".
- "region" says where on the page, precisely enough to find in five seconds:
  "hero headline", "third pricing card", "footer, right column".
- "why" states the concrete cost of the problem in one or two sentences.
- "fix" is an instruction the founder can paste into their coding tool
  unedited: name the element, give the exact new copy or the exact change.
  An observation is not a fix.
- "strengths" lists what already works and what a redesign must not lose —
  each one names the exact element or sentence it protects.
- "severity": "critical" defeats the page's purpose; "major" is a measurable
  drag on it; "minor" is polish.
- "score" is 0-100, anchored: 90+ exceptional, ship it as it is; 70s solid
  with real gaps; 50s significant problems; below 40 broken for its purpose.
- TODAY IS {today}. You do not otherwise know what day it is, and your sense
  of "current" is older than this page. Never call a date on the page future,
  stale, or expired by reasoning from your own sense of now; compare it to the
  date above or say nothing about it. The same applies to versions, frameworks
  and integrations: you cannot tell from your training whether one is still
  supported.
{vocabulary_rule}"""


def _review_rules(today: str) -> str:
    """The shared rules, with the date supplied rather than assumed.

    **The critics did not know what year it was.** The credibility reviewer
    flagged "© 2026" as *"the copyright year is 2026, which is in the future"*
    on six sample pages in a row, on 2026-08-26. It is not in the future; the
    model was reasoning from a training cutoff.

    That is worse than an ordinary wrong finding, because the founder reading it
    cannot tell which of them holds the stale calendar, and the obvious fix is
    to back-date their own footer. A critique that talks somebody into making
    their page worse is the failure this module exists to prevent.

    `clearance/tracks.py` had already established the pattern, taking
    `search_date` as an argument rather than reading `datetime.now()` deep in
    the logic. This is that precedent applied where it was missed.
    """
    return _SHARED_RULES.format(vocabulary_rule=VOCABULARY_RULE, today=today)

# The answer shapes are appended verbatim (never `.format`-ed), so the JSON
# braces stay literal.
_JSON_INSTRUCTION = """\
ANSWER FORMAT — return ONLY a JSON object, no prose before or after it, no
code fences, exactly this shape:
{"score": <integer 0-100>,
 "findings": [{"severity": "critical" | "major" | "minor",
               "region": "<where on the page>",
               "quote": "<words visible on the page, or empty>",
               "why": "<the concrete cost>",
               "fix": "<a paste-ready instruction>"}],
 "strengths": ["<what a redesign must not lose>"]}"""

_JSON_INSTRUCTION_COPY = """\
ANSWER FORMAT — return ONLY a JSON object, no prose before or after it, no
code fences, exactly this shape:
{"score": <integer 0-100>,
 "page_takeaway": "<one sentence: what the page actually communicates>",
 "findings": [{"severity": "critical" | "major" | "minor",
               "region": "<where on the page>",
               "quote": "<words visible on the page, or empty>",
               "why": "<the concrete cost>",
               "fix": "<a paste-ready instruction>"}],
 "strengths": ["<what a redesign must not lose>"]}"""

_JSON_NUDGE = (
    "Your previous answer could not be read. Return ONLY valid JSON exactly "
    "in the shape requested — no prose before or after it, no code fences."
)

# Founder-facing failure sentences, kept as templates so the vocabulary scan
# can read them the way it reads the prompts.
_TOO_LARGE_ERROR = (
    "The {label} review could not run: the {which} is too large to send for "
    "review (about {size_mb:.1f} MB once prepared for sending; the limit is "
    "about {limit_mb:.1f} MB). Capture the page at a smaller size and run "
    "the check again."
)
_UNREADABLE_ERROR = (
    "The {label} review answered twice in a form that could not be read, so "
    "no verdict was produced. Run the page check again."
)
_FAILED_ERROR = (
    "The {label} review could not finish ({error}). No verdict was produced "
    "— run the page check again."
)


# ── the five page rubrics ────────────────────────────────────────────

_HIERARCHY_TEMPLATE = """\
REVIEW DIMENSION: hierarchy

You are reviewing how this page reads at a glance. The attached image is a
full-page desktop screenshot; judge what it shows.

Judge four things:
1. The 5-second test — a stranger looks for five seconds. Can they say what
   this is, who it is for, and what to do next? Name exactly which words or
   elements answered them, and which failed them.
2. Scan order — where does the eye land first, second, third? If elements
   compete for first place or the order buries the point, name the elements
   that compete.
3. Section rhythm — read top to bottom: does the page unfold as an argument
   (what it is, why believe it, what to do), or as a pile of blocks? Name the
   section where the thread breaks.
4. Type scale — are the heading sizes doing the ranking, or do same-size
   blocks flatten the page? Quote the headings that sit at the wrong weight.

PAGE TITLE: {title}

PAGE STYLE (one measured line from the page's own styles): {census_digest}

PAGE TEXT (an extract, for cross-reference — the screenshot is the evidence):
{dom_excerpt}

{review_rules}"""

_CREDIBILITY_TEMPLATE = """\
REVIEW DIMENSION: credibility

You are reviewing whether this page earns a stranger's trust. The attached
image is a full-page desktop screenshot; judge what it shows.

Judge four things:
1. Trust signals — real names, real numbers, dates, customers, pictures of
   the actual product? Name what is present, and what a skeptical buyer
   would notice is missing.
2. Claim specificity — quote the claims. Which are checkable ("cuts review
   time 40%") and which could never be checked ("world-class",
   "revolutionary")? The weakest claim on the page is a finding; quote it.
3. Internal contradictions — places where the page disagrees with itself: a
   price here and a different price there, a promise the feature list does
   not keep. Quote both sides of any contradiction.
4. Tags vs page — the tags below are what search results and link previews
   show. Do they promise the same product this page delivers? Quote any
   drift between them and the page.

PAGE TITLE: {title}

PAGE STYLE (one measured line from the page's own styles): {census_digest}

PAGE TAGS (what search results and link previews will show):
{meta_lines}

PAGE TEXT (an extract, for cross-reference):
{dom_excerpt}

{review_rules}"""

_CONVERSION_TEMPLATE = """\
REVIEW DIMENSION: conversion

You are reviewing the route from landing on this page to acting on it. The
attached image is a full-page desktop screenshot; judge what it shows.

Judge four things:
1. Path to action — what is the one thing this page wants a visitor to do,
   and how far down the page does a visitor read before it is offered? Name
   the step and every detour before it.
2. Button and link quality — quote every call to action verbatim. Does each
   say what happens next ("Start a free page check") or is it a mystery box
   ("Submit", "Learn more")? Weak button copy is a finding per button.
3. Friction — every field, click, choice, or unanswered question standing
   between arriving and acting. Name each one and whether it earns its
   place.
4. Abandonment points — the spots where a nearly-convinced reader gives up:
   a price with no context, a form asking too much too early, a section that
   ends with nowhere to go. Name the exact spot.

PAGE TITLE: {title}

PAGE STYLE (one measured line from the page's own styles): {census_digest}

PAGE TEXT (an extract, for cross-reference):
{dom_excerpt}

{review_rules}"""

_COPY_TEMPLATE = """\
REVIEW DIMENSION: copy

You are reviewing the words on this page. The page text below is the primary
evidence; the attached desktop screenshot shows where each sentence lives.

Judge four things:
1. Message takeaway — after one read, what would a stranger say this product
   is and does? Report that sentence as "page_takeaway": what the page
   actually communicates, in a stranger's words — not what it should say,
   and not a verdict on it.
2. Term burden — every term a reader must already know before the page makes
   sense. Quote each term, and give the plain-words replacement in the fix.
3. Sentence-level failures — quote the sentences that run too long, hedge,
   say nothing, or bury their point. The fix rewrites the sentence.
4. Reading level — could a sharp fourteen-year-old follow this page? Quote
   the passages that assume otherwise.

PAGE TITLE: {title}

PAGE STYLE (one measured line from the page's own styles): {census_digest}

PAGE TEXT (the primary evidence — quote from it):
{dom_text}

{review_rules}"""

_MOBILE_TEMPLATE = """\
REVIEW DIMENSION: mobile

You are reviewing this page as a phone shows it. The attached image is a
full-page PHONE screenshot — judge that image, not a remembered desktop
layout.

Judge four things:
1. Stacking — desktop columns become one phone column. Does the order still
   tell the story, or did stacking bury the point, or strand an image from
   the words that explain it? Name the sections.
2. Legibility — text that has gone small, thin, cramped, or low-contrast on
   the phone. Quote the text.
3. Tap targets — buttons and links too small or too close together to hit
   with a thumb. Name each one.
4. First-screen delivery — the first screenful, before any scrolling: does
   it say what this is and offer one thing to do? Name what made it in, and
   what is missing that should be there.

PAGE TITLE: {title}

PAGE STYLE (one measured line from the page's own styles): {census_digest}

PAGE TEXT (an extract, for cross-reference — the phone screenshot is the
evidence):
{dom_excerpt}

{review_rules}"""


# ── the sixth rubric: the look, measured ─────────────────────────────
#
# The design reviewer's method is not "is this good?" but "what do the
# numbers say?" — every signal it checks is grounded in the style
# measurements the capture side counts from the page's computed styles.
# One reviewer, two modes: judged alone, or judged against a reference
# site with every visible gap quoted as both measured values.

_DESIGN_KEY = "design"
_DESIGN_LABEL = "design"

#: The signals both design modes check — one block so the two rubrics can
#: never drift apart on what an undesigned page looks like.
_DESIGN_SIGNALS = """\
1. Font choice — if the primary typeface is a browser default or system stack
   (Arial, Helvetica, Times New Roman, "system-ui", "-apple-system",
   "Segoe UI"), that is the single loudest tell of an undesigned page. Report
   it as a finding of severity "major" at the least — "critical" if the whole
   page is set in it — and name the font the measurements show.
2. Color discipline — count the accent colors in the measurements. A designed
   page spends one accent, and that accent owns every action. Report how many
   accents this page spends and which color, if any, owns the buttons.
3. Corner radii — a designed page uses at most three or four radius values;
   eight different radii is no system at all. Count the distinct radii in the
   measurements and name the values.
4. Shadows — do the shadows form a short ladder (none, resting, raised), or
   is every shadow its own recipe? Count the distinct shadows.
5. Spacing rhythm — do the measured gaps repeat one base unit (the
   measurements include a base-unit estimate), or is every gap improvised?
   Name the values that fall off the rhythm.
6. Imagery and icons — one family (all line icons, or all photos with one
   treatment), or styles mixed on one page? Name the elements that break the
   family; the screenshot is the evidence for this one."""

#: Widens the shared quote rule for this reviewer only: its evidence is
#: numbers, so a quote of measured values is a quote of the page. The live
#: gate showed the model writing measurements into "why" and leaving "quote"
#: empty — an empty quote now fails validation, so the rule is stated as the
#: hard requirement it is.
_DESIGN_EVIDENCE_RULE = """\
For this review the style measurements below are page evidence. HARD
REQUIREMENT: the "quote" field of EVERY finding MUST contain the measured
value(s) that prove it — never prose, never empty. Example of a valid quote:
"radius values: 2px, 4px, 6px, 10px, 12px, 24px". Put the argument in "why";
put the numbers in "quote"; put the element or style property in "region".
A finding whose quote is empty will be rejected and the whole review
discarded."""

_DESIGN_TEMPLATE = (
    """\
REVIEW DIMENSION: design

You are reviewing whether this page's look is a designed system or an
accident. The attached image is a full-page desktop screenshot. Below it are
the page's style measurements — the fonts, colors, corner radii, shadows,
and spacing values the page actually computes, with how often each occurs.
Be ruthless, and judge with the numbers: a finding grounded in a measurement
outranks an impression.

Judge six things:
"""
    + _DESIGN_SIGNALS
    + """

"""
    + _DESIGN_EVIDENCE_RULE
    + """
"score" here measures how much of a coherent visual system exists at all:
90+ is a disciplined system, below 40 means no system is present.

PAGE TITLE: {title}

STYLE MEASUREMENTS (counted from the page's own styles):
{census}

{standard}

{review_rules}"""
)

_DESIGN_TEMPLATE_REFERENCE = (
    """\
REVIEW DIMENSION: design

You are reviewing whether this page's look is a designed system or an
accident, judged against THE STANDARD below. TWO images are attached: the
FIRST is a full-page desktop screenshot of the founder's page; the SECOND is
a site whose feel the founder said they are aiming for. Below are style
measurements for both pages — the fonts, colors, corner radii, shadows, and
spacing values each page actually computes, with how often each occurs.

**The second site is direction, not the bar.** The founder is not being
ranked against it, and a page is not worse for looking unlike it. Use it only
to understand the feel they are reaching for; judge the page itself against
the standard and against whether its own system holds together. Never write a
finding whose argument is that the other site does something differently.

Judge six things about the founder's page:
"""
    + _DESIGN_SIGNALS
    + """

Where the direction site does something the standard also asks for and this
page does not, you may write that as a finding — but the argument must be the
standard's, not "theirs is different". Quote this page's measured value; cite
theirs only as an illustration of what the founder said they wanted.

In "strengths", name what this page already does well and must not lose. A
rewrite that flattens what works is a worse page, whatever it scores.

"""
    + _DESIGN_EVIDENCE_RULE
    + """
"score" here measures how much of a coherent visual system exists at all:
90+ is a disciplined system, below 40 means no system is present. It is the
same scale as a review with no direction site, because the founder's score
must not move just because they named somewhere they admire.

PAGE TITLE: {title}

STYLE MEASUREMENTS OF THIS PAGE (counted from the page's own styles):
{census}

THE DIRECTION THE FOUNDER NAMED: {reference_title}

STYLE MEASUREMENTS OF THAT SITE (context only, never the bar):
{reference_census}

{standard}

{review_rules}"""
)


# ── wiring ───────────────────────────────────────────────────────────


def _excerpt(text: str, limit: int) -> str:
    cleaned = (text or "").strip()
    if not cleaned:
        return "(no text could be read from the page)"
    if len(cleaned) <= limit:
        return cleaned
    return cleaned[:limit].rstrip() + "\n[cut here — the rest of the page text did not fit]"


def _meta_lines(meta: object) -> str:
    if isinstance(meta, dict):
        lines = [f"{key}: {value}" for key, value in meta.items() if str(value).strip()]
        if lines:
            return "\n".join(lines)
    elif meta:
        return str(meta)
    return "(the page ships no tags — that absence is itself worth judging)"


def _style_census(capture: WebsiteCapture) -> dict | None:
    """The capture's style measurements, if the capture side took any.

    Read with `getattr` because `style_census` is landing on `WebsiteCapture`
    in parallel with this module: a capture made before that field exists must
    still get a full gauntlet, with the measurements honestly reported as
    absent rather than crashing the design review.
    """
    census = getattr(capture, "style_census", None)
    return census if isinstance(census, dict) else None


def _named_counts(value: object) -> list[tuple[str, float]]:
    """Read one measurement table into (name, count) pairs, most common first.

    Tolerant of shape — a `{value: count}` mapping, a list of entries, or a
    list of dicts naming their value — because the digest is grounding, not a
    contract: an unreadable table degrades to an absent line, never an error.
    """
    if isinstance(value, dict):
        pairs = [
            (str(name), count if isinstance(count, int | float) else 0.0)
            for name, count in value.items()
        ]
        return sorted(pairs, key=lambda pair: -pair[1])
    if isinstance(value, list):
        pairs = []
        for entry in value:
            if isinstance(entry, dict):
                name = next(
                    (entry[key] for key in ("value", "name", "family", "color") if entry.get(key)),
                    None,
                )
                if name is None:
                    continue
                count = entry.get("count", 0)
                pairs.append((str(name), count if isinstance(count, int | float) else 0.0))
            elif entry is not None:
                pairs.append((str(entry), 0.0))
        return sorted(pairs, key=lambda pair: -pair[1])
    return []


def _census_lookup(table: dict, *keys: str) -> object:
    for key in keys:
        if key in table:
            return table[key]
    return None


def _census_digest(census: dict | None) -> str:
    """One measured line — top font, leading colors, base unit — for the five
    page reviewers. Cheap grounding so "the hero font" and "the accent color"
    in their findings name what the page actually computes."""
    if not census:
        return "(no style measurements were taken)"
    parts: list[str] = []

    fonts = _census_lookup(census, "fonts", "font_families", "families")
    if isinstance(fonts, dict):
        nested = _census_lookup(fonts, "families", "family")
        if nested is not None:
            fonts = nested
    ranked_fonts = _named_counts(fonts)
    if ranked_fonts:
        parts.append(f"main font {ranked_fonts[0][0]}")

    colors = _census_lookup(census, "accent_colors", "accents", "text_colors", "colors")
    ranked_colors = [name for name, _ in _named_counts(colors)[:3]]
    if ranked_colors:
        parts.append("leading colors " + ", ".join(ranked_colors))

    base_unit = _census_lookup(census, "spacing_base_unit", "base_unit", "base_unit_guess")
    if base_unit is None:
        spacing = census.get("spacing")
        if isinstance(spacing, dict):
            base_unit = _census_lookup(spacing, "base_unit", "base_unit_guess", "base_unit_px")
    if base_unit is not None:
        parts.append(f"spacing base unit {base_unit}")

    if not parts:
        return "(style measurements were taken, but no summary line could be read from them)"
    return "; ".join(parts)


def _census_text(census: dict | None) -> str:
    """The full measurement table, rendered for the design reviewer."""
    if not census:
        return "(no style measurements could be taken from this page)"
    rendered = json.dumps(census, indent=1, sort_keys=True, ensure_ascii=False, default=str)
    if len(rendered) > _CENSUS_CHARS:
        rendered = (
            rendered[:_CENSUS_CHARS].rstrip()
            + "\n[cut here — the rest of the measurements did not fit]"
        )
    return rendered


def _shared_context(capture: WebsiteCapture) -> dict[str, str]:
    return {
        "title": capture.title or "(the page has no title)",
        "census_digest": _census_digest(_style_census(capture)),
        "dom_excerpt": _excerpt(capture.dom_text, _DOM_EXCERPT_CHARS),
    }


def _credibility_context(capture: WebsiteCapture) -> dict[str, str]:
    return {**_shared_context(capture), "meta_lines": _meta_lines(capture.meta)}


def _copy_context(capture: WebsiteCapture) -> dict[str, str]:
    return {
        "title": capture.title or "(the page has no title)",
        "census_digest": _census_digest(_style_census(capture)),
        "dom_text": _excerpt(capture.dom_text, _DOM_PRIMARY_CHARS),
    }


@dataclass(frozen=True)
class _Critic:
    key: str
    label: str  # names the reviewer in founder-facing failure text
    template: str
    uses_mobile: bool  # which screenshot is this reviewer's evidence
    response_model: type[_CriticResponse]
    context: Callable[[WebsiteCapture], dict[str, str]]
    json_shape: str


#: Order is presentation order in the result, and the order failures are
#: reported in when more than one reviewer breaks. The design reviewer is not
#: in this tuple: its rubric depends on whether a reference site rides along,
#: so `_design_critic` builds it per run, and it always presents last.
_CRITICS: tuple[_Critic, ...] = (
    _Critic(
        key="hierarchy",
        label="hierarchy",
        template=_HIERARCHY_TEMPLATE,
        uses_mobile=False,
        response_model=_CriticResponse,
        context=_shared_context,
        json_shape=_JSON_INSTRUCTION,
    ),
    _Critic(
        key="credibility",
        label="credibility",
        template=_CREDIBILITY_TEMPLATE,
        uses_mobile=False,
        response_model=_CriticResponse,
        context=_credibility_context,
        json_shape=_JSON_INSTRUCTION,
    ),
    _Critic(
        key="conversion",
        label="conversion path",
        template=_CONVERSION_TEMPLATE,
        uses_mobile=False,
        response_model=_CriticResponse,
        context=_shared_context,
        json_shape=_JSON_INSTRUCTION,
    ),
    _Critic(
        key="copy",
        label="copy clarity",
        template=_COPY_TEMPLATE,
        uses_mobile=False,
        response_model=_CopyResponse,
        context=_copy_context,
        json_shape=_JSON_INSTRUCTION_COPY,
    ),
    _Critic(
        key="mobile",
        label="mobile experience",
        template=_MOBILE_TEMPLATE,
        uses_mobile=True,
        response_model=_CriticResponse,
        context=_shared_context,
        json_shape=_JSON_INSTRUCTION,
    ),
)


def _design_context(capture: WebsiteCapture, reference: WebsiteCapture | None) -> dict[str, str]:
    # The standard is rendered from `TASTE_RULES`, the same table the counted
    # `standard` dimension scores against — so the sentences this reviewer is
    # held to and the arithmetic that grades the page cannot drift apart.
    # Imported here rather than at module scope: `taste` imports `CriticDimension`
    # from this module, and the cycle only stays broken because both directions
    # are lazy.
    from app.services.website.taste import taste_prompt_section

    context = {
        "title": capture.title or "(the page has no title)",
        "census": _census_text(_style_census(capture)),
        "standard": taste_prompt_section(),
    }
    if reference is not None:
        context["reference_title"] = reference.title or "(the site has no title)"
        context["reference_census"] = _census_text(_style_census(reference))
    return context


def _design_critic(reference: WebsiteCapture | None) -> _Critic:
    """The sixth reviewer, built per run: one critic, two rubrics.

    Alone, it judges whether the page's measurements describe a designed
    system at all; given a reference, it also measures every visible gap
    between the two pages and quotes both values.
    """
    return _Critic(
        key=_DESIGN_KEY,
        label=_DESIGN_LABEL,
        template=_DESIGN_TEMPLATE_REFERENCE if reference is not None else _DESIGN_TEMPLATE,
        response_model=_DesignResponse,
        uses_mobile=False,
        context=lambda capture: _design_context(capture, reference),
        json_shape=_JSON_INSTRUCTION,
    )


def _design_images(
    capture: WebsiteCapture, reference: WebsiteCapture | None
) -> tuple[tuple[bytes, str], ...]:
    """The design reviewer's evidence, founder's page always first.

    In reference mode this is the gauntlet's only two-image call — the prompt
    tells the model the first image is the founder's page and the second the
    reference site, and this ordering is that promise kept.
    """
    ours = (capture.screenshot_desktop, "desktop screenshot of the page")
    if reference is None:
        return (ours,)
    return (
        ours,
        (reference.screenshot_desktop, "desktop screenshot of the reference site"),
    )


def _fill(template: str, **fields: object) -> str:
    """Fill a reviewer prompt, always with the shared rules in it.

    The slot is checked rather than merely supplied, for the reason
    `report_agent._prompt` documents: `str.format` accepts keyword arguments a
    template never uses, so a rubric written without the slot would silently
    ship a reviewer with no rules and no vocabulary discipline.
    """
    if "{review_rules}" not in template:
        raise KeyError(
            "review_rules: this prompt reaches a page reviewer and must carry "
            "the review rules and the vocabulary rule. Add {review_rules} to "
            "the template."
        )
    return template.format(
        review_rules=_review_rules(date.today().isoformat()), **fields
    )


def _encoded_size(raw: bytes) -> int:
    """Bytes this image occupies once base64-encoded for the model."""
    return (len(raw) + 2) // 3 * 4


def _guard_size(critic: _Critic, screenshot: bytes, which: str) -> None:
    encoded = _encoded_size(screenshot)
    if encoded > _MAX_BASE64_BYTES:
        raise CriticError(
            critic.key,
            _TOO_LARGE_ERROR.format(
                label=critic.label,
                which=which,
                size_mb=encoded / 1_000_000,
                limit_mb=_MAX_BASE64_BYTES / 1_000_000,
            ),
        )


def _try_parse(critic: _Critic, raw: str) -> tuple[_CriticResponse | None, str]:
    """Parsed response, or (None, a short complaint naming what failed).

    The complaint rides into the retry prompt: a model that produced valid
    JSON with an empty design quote was re-asked with a generic "return valid
    JSON" nudge it had already satisfied, and failed the same way twice (live
    gate). Telling it which field was rejected is what changes the answer.
    """
    try:
        return critic.response_model.model_validate_json(_extract_json(raw)), ""
    except ValidationError as exc:
        parts = [
            f"{'.'.join(str(p) for p in err['loc'])}: {err['msg']}"
            for err in exc.errors()[:3]
        ]
        return None, "; ".join(parts) or "the answer did not match the shape"


async def _run_one(
    critic: _Critic,
    capture: WebsiteCapture,
    images: tuple[tuple[bytes, str], ...] | None = None,
) -> _CriticResponse:
    """One reviewer, start to verdict.

    Any way this can go wrong becomes a `CriticError` naming the dimension:
    the size guard before the call, an unreadable answer after one nudged
    retry, and anything the transport raises. The gauntlet upgrades a single
    reviewer's failure to a whole-run failure, so the message here is the one
    the founder reads.

    `images` — (bytes, what-to-call-it-in-a-failure) pairs — overrides the
    single screenshot `uses_mobile` selects; today only the design reviewer
    passes it, because its reference mode sends two desktops in one call.
    """
    try:
        if images is None:
            which = "phone" if critic.uses_mobile else "desktop"
            screenshot = (
                capture.screenshot_mobile if critic.uses_mobile else capture.screenshot_desktop
            )
            images = ((screenshot, f"{which} screenshot of the page"),)
        for screenshot, described_as in images:
            _guard_size(critic, screenshot, described_as)

        evidence = [screenshot for screenshot, _ in images]
        prompt = _fill(critic.template, **critic.context(capture)) + "\n\n" + critic.json_shape
        raw = await llm_vision(prompt, evidence)
        parsed, complaint = _try_parse(critic, raw)
        if parsed is None:
            nudge = _JSON_NUDGE
            if complaint:
                nudge += f"\nThe previous answer was rejected because — {complaint}."
            raw = await llm_vision(prompt + "\n\n" + nudge, evidence)
            parsed, _ = _try_parse(critic, raw)
        if parsed is None:
            raise CriticError(critic.key, _UNREADABLE_ERROR.format(label=critic.label))
        return parsed
    except CriticError:
        raise
    except Exception as exc:
        raise CriticError(
            critic.key,
            _FAILED_ERROR.format(
                label=critic.label, error=f"{type(exc).__name__}: {exc}"
            ),
        ) from exc


async def run_critic_gauntlet(
    capture: WebsiteCapture,
    *,
    reference: WebsiteCapture | None = None,
    organization_id: str | None = None,
) -> CritiqueResult:
    """Run the six reviewers concurrently and assemble one verdict.

    `reference` switches the design reviewer into measured-gap mode: its one
    call carries both desktop screenshots and both pages' style measurements,
    and every visible difference comes back with both values quoted. The
    other five reviewers never see the reference — their rubrics judge the
    founder's page alone either way.

    Every call is attributed to the cost ledger as `website_critics` — the
    priced stage §4e profiles from measured usage. Six or nothing: the first
    failed reviewer, in presentation order, fails the run with its dimension
    named; the remaining verdicts are discarded rather than passed off as a
    complete review.
    """
    design = _design_critic(reference)
    roster = (*_CRITICS, design)
    with usage_context("website_critics", organization_id=organization_id):
        outcomes = await asyncio.gather(
            *(_run_one(critic, capture) for critic in _CRITICS),
            _run_one(design, capture, _design_images(capture, reference)),
            return_exceptions=True,
        )

    for outcome in outcomes:
        if isinstance(outcome, BaseException):
            raise outcome

    dimensions: list[CriticDimension] = []
    page_takeaway = ""
    for critic, response in zip(roster, outcomes, strict=True):
        dimensions.append(
            CriticDimension(
                key=critic.key,
                score=response.score,
                findings=response.findings,
                strengths=response.strengths,
            )
        )
        if isinstance(response, _CopyResponse):
            page_takeaway = response.page_takeaway.strip()

    # The counted dimension, added 2026-08-25.
    #
    # Imported here rather than at module scope because `measured` imports the
    # finding models from this module; a top-level import back would be a cycle.
    #
    # **It is not a seventh reviewer and is not subject to the six-or-nothing
    # rule.** It makes no model call and no network call, so it has nothing to
    # fail at: where a reviewer raising means the page has no verdict, this
    # either finds something or does not. It is appended after the six because
    # it reads as the receipts under the opinions.
    from app.services.website.measured import measure_page

    # None when nothing could be measured — an empty census on a page with
    # almost no text. Appending a 100 there would score a page for having
    # defeated the census, so the dimension is simply absent and the mean stays
    # over the six opinions.
    counted = measure_page(capture)
    if counted is not None:
        dimensions.append(counted)

    # The standard, appended for the same reasons and with the same contract.
    #
    # **`measured` and `standard` are not the same question, and the difference
    # is why this exists.** `measured` asks whether the page is internally
    # consistent, and every one of its rules is a variety penalty — too many
    # radii, too many colours, too many shadows. Penalties are satisfied by
    # deletion, so that rubric's maximum sits at the empty page. On 2026-08-27
    # the revision loop found exactly that gradient on saibyl.com: `measured`
    # 35 -> 73 while `design` fell 95 -> 72, and the founder was handed a page
    # with, in his words, "not really much to it".
    #
    # `standard` asks whether the page does the things a good page does, and
    # half its rules are requirements rather than violations. A stripped page
    # scores 0 here where `measured` would give it near-100.
    from app.services.website.taste import taste_dimension

    standard = taste_dimension(capture)
    if standard is not None:
        dimensions.append(standard)

    # The ninth, added 2026-08-30, and the only one that judges a reader other
    # than a person.
    #
    # **Every dimension above this line reads the page a human gets** — six
    # from a screenshot, two from the CSS. A founder's buyers increasingly ask
    # a model instead, and a model reads the HTML the server sent. Measured
    # that day: linear.app scores 100 on `standard` and ships zero structured
    # data. The two are not the same question and a page can be excellent at
    # one while invisible to the other.
    #
    # Same contract as the other two counted dimensions: no model call, no
    # six-or-nothing rule, and None rather than 100 when there is nothing to
    # judge — a pasted-HTML review has no server response and no address to
    # resolve robots.txt against.
    from app.services.website.found import machine_dimension

    found = machine_dimension(capture)
    if found is not None:
        dimensions.append(found)

    # **Scores from before this date are not comparable with scores after it.**
    # The overall is a mean across dimensions and there are now up to nine, so
    # a stored 77 from a six-, seven- or eight-dimension run is a different
    # quantity.
    # Deltas within one revision run are unaffected: before and after are both
    # measured the same way, and the delta is what `revise` reads.
    #
    # The count is "up to" rather than fixed on purpose. `measured` and
    # `standard` each return None when the census could not answer, so a page
    # that defeats measurement is scored on the opinions alone rather than
    # being handed a 100 for having been unmeasurable.
    overall = round(sum(d.score for d in dimensions) / len(dimensions))
    logger.info(
        "website_critic_gauntlet_complete",
        url=capture.url,
        overall_score=overall,
        scores={d.key: d.score for d in dimensions},
        findings=sum(len(d.findings) for d in dimensions),
    )
    return CritiqueResult(
        overall_score=overall,
        page_takeaway=page_takeaway,
        dimensions=dimensions,
    )
