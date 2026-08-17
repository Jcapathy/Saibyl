# PUBLIC INTERFACE
# ─────────────────────────────────────────────────────────
# run_critic_gauntlet(capture, *, organization_id=None) -> CritiqueResult   [async]
# CritiqueResult, CriticDimension, CriticFinding, CriticError
# ─────────────────────────────────────────────────────────
"""The critic gauntlet: five reviewers judge a rendered page (PRD_V3 §4b).

Each reviewer is ONE vision call with its own rubric, and each is blind to the
other four — that independence is the design. Five specialists who cannot see
each other's verdicts give five uncorrelated reads, so where they agree the
agreement is evidence rather than echo. Nothing connects them, so they run
concurrently.

The reviewers judge what a visitor is shown, not what the HTML intends: the
desktop screenshot for how the page reads, earns trust, and routes a reader to
action; the extracted page text for the words; the phone screenshot for what a
phone actually renders. A finding may quote only what is visible in that
evidence — the prompt forbids inventing content — and every finding ends in an
instruction the founder can paste into their coding tool unedited, per the §5
standard ("improve your value proposition" is a defect, not a finding).

Five or nothing: a reviewer that cannot finish fails the whole gauntlet with
its dimension named, because a four-reviewer verdict presented as the page's
score would be a number quietly missing a fifth of its meaning.

The overall score is the rounded mean of the five dimension scores, and the
one-sentence page takeaway comes from the copy reviewer, whose rubric is the
message a stranger actually receives.
"""
from __future__ import annotations

import asyncio
from collections.abc import Callable
from dataclasses import dataclass
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

# `llm_vision`'s bound on one encoded image (~4.5MB of base64). Guarded here,
# before the call, so the failure a founder sees names the screenshot and the
# remedy instead of surfacing a transport error. Downscaling is the capture
# side's job; this is the honest stop when it did not happen.
_MAX_BASE64_BYTES = 4_500_000


# ── public result models ─────────────────────────────────────────────


class CriticFinding(BaseModel):
    severity: Literal["critical", "major", "minor"]
    region: str
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
{vocabulary_rule}"""

_REVIEW_RULES = _SHARED_RULES.format(vocabulary_rule=VOCABULARY_RULE)

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
    "The {label} review could not run: the {which} screenshot of the page is "
    "too large to send for review (about {size_mb:.1f} MB once prepared for "
    "sending; the limit is about {limit_mb:.1f} MB). Capture the page at a "
    "smaller size and run the check again."
)
_UNREADABLE_ERROR = (
    "The {label} review answered twice in a form that could not be read, so "
    "no verdict was produced. Run the page check again."
)
_FAILED_ERROR = (
    "The {label} review could not finish ({error}). No verdict was produced "
    "— run the page check again."
)


# ── the five rubrics ─────────────────────────────────────────────────

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

PAGE TEXT (an extract, for cross-reference — the phone screenshot is the
evidence):
{dom_excerpt}

{review_rules}"""


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


def _shared_context(capture: WebsiteCapture) -> dict[str, str]:
    return {
        "title": capture.title or "(the page has no title)",
        "dom_excerpt": _excerpt(capture.dom_text, _DOM_EXCERPT_CHARS),
    }


def _credibility_context(capture: WebsiteCapture) -> dict[str, str]:
    return {**_shared_context(capture), "meta_lines": _meta_lines(capture.meta)}


def _copy_context(capture: WebsiteCapture) -> dict[str, str]:
    return {
        "title": capture.title or "(the page has no title)",
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
#: reported in when more than one reviewer breaks.
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
    return template.format(review_rules=_REVIEW_RULES, **fields)


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


def _try_parse(critic: _Critic, raw: str) -> _CriticResponse | None:
    try:
        return critic.response_model.model_validate_json(_extract_json(raw))
    except ValidationError:
        return None


async def _run_one(critic: _Critic, capture: WebsiteCapture) -> _CriticResponse:
    """One reviewer, start to verdict.

    Any way this can go wrong becomes a `CriticError` naming the dimension:
    the size guard before the call, an unreadable answer after one nudged
    retry, and anything the transport raises. The gauntlet upgrades a single
    reviewer's failure to a whole-run failure, so the message here is the one
    the founder reads.
    """
    try:
        which = "phone" if critic.uses_mobile else "desktop"
        screenshot = (
            capture.screenshot_mobile if critic.uses_mobile else capture.screenshot_desktop
        )
        _guard_size(critic, screenshot, which)

        prompt = _fill(critic.template, **critic.context(capture)) + "\n\n" + critic.json_shape
        raw = await llm_vision(prompt, [screenshot])
        parsed = _try_parse(critic, raw)
        if parsed is None:
            raw = await llm_vision(prompt + "\n\n" + _JSON_NUDGE, [screenshot])
            parsed = _try_parse(critic, raw)
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
    organization_id: str | None = None,
) -> CritiqueResult:
    """Run the five reviewers concurrently and assemble one verdict.

    Every call is attributed to the cost ledger as `website_critics` — the
    priced stage §4e profiles from measured usage. Five or nothing: the first
    failed reviewer, in presentation order, fails the run with its dimension
    named; the remaining verdicts are discarded rather than passed off as a
    complete review.
    """
    with usage_context("website_critics", organization_id=organization_id):
        outcomes = await asyncio.gather(
            *(_run_one(critic, capture) for critic in _CRITICS),
            return_exceptions=True,
        )

    for outcome in outcomes:
        if isinstance(outcome, BaseException):
            raise outcome

    dimensions: list[CriticDimension] = []
    page_takeaway = ""
    for critic, response in zip(_CRITICS, outcomes, strict=True):
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
