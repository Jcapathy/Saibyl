# PUBLIC INTERFACE
# ─────────────────────────────────────────────────────────
# extract_design_dna(capture, *, organization_id=None) -> DesignDNA   [async]
# DesignDNA, DesignTokens, DesignDNAError
# ─────────────────────────────────────────────────────────
"""Design DNA: the page's style system, read from measured numbers (PRD_V3 §4).

Great design critique is anchored in measured tokens, not vision vibes — "your
letter-spacing is X" beats "feels a bit loose". The capture side already
measures the page (`WebsiteCapture.style_census`); this module is the one
vision call that turns those numbers plus the desktop screenshot into a named,
role-assigned design system: a palette with roles, a type system, a spacing
and shape vocabulary, do/don'ts, a maturity score, and a complete DESIGN.md
artifact a founder can paste into their coding tool to get on-brand output.

The census is the receipt. The model names colors and assigns roles; it never
invents a value — the prompt forbids any hex that the census did not measure,
so every token in the artifact is a number someone actually rendered.

One call, strict JSON, one nudged retry, then a readable failure — the same
parse/retry idiom as `critics.py`, and the same vocabulary discipline: the
prompt carries the shared vocabulary rule, and no string of ours uses a word a
founder has to learn.
"""
from __future__ import annotations

import json

import structlog
from pydantic import BaseModel, Field, ValidationError

from app.core.llm_client import _extract_json, llm_vision
from app.services.billing.usage_ledger import usage_context
from app.services.website.capture import WebsiteCapture
from app.services.website.critics import VOCABULARY_RULE

logger = structlog.get_logger()

# How much extracted page text rides along for cross-reference; the screenshot
# and the census are the primary evidence.
_DOM_EXCERPT_CHARS = 4_000


# ── public result models ─────────────────────────────────────────────


class DesignTokens(BaseModel):
    palette: list[dict]  # {hex, name, role}
    fonts: list[dict]  # {family, weights, role}
    radii: dict
    shadows: list[str]
    spacing: dict
    theme: str


class DesignDNA(BaseModel):
    characterization: str  # one evocative line ("midnight precision instrument")
    summary: str  # 3-5 sentence prose read of the system
    tokens: DesignTokens
    dos: list[str]
    donts: list[str]
    style_tags: list[str]
    maturity_level: int = Field(ge=1, le=7)
    maturity_rationale: str
    design_md: str  # the full DESIGN.md markdown artifact


class DesignDNAError(Exception):
    """The design read could not finish; the message is founder-readable."""


# ── the prompt ───────────────────────────────────────────────────────

# `{vocabulary_rule}` is filled from `critics.VOCABULARY_RULE` so the banned
# list lives in exactly one place; the JSON shape is appended verbatim (never
# `.format`-ed) so its braces stay literal.
_DNA_TEMPLATE = """\
DESIGN DNA EXTRACTION

You are reading the design system out of a live page. The attached image is a
full-page desktop screenshot; below it are MEASURED style numbers taken from
the rendered page (the census), and an extract of the page text. Your job is
to name the system the page actually uses — its palette, its type, its
spacing rhythm, its shape vocabulary — and write it up so the founder who
owns the page can hand it to a coding tool and get on-brand output.

THE CENSUS IS THE RECEIPT — these rules are absolute:
- Every claim about a color, font, size, weight, spacing value, radius, or
  shadow must cite a value that appears in the census below.
- Only hex values present in the census may appear anywhere in your answer.
  You name colors and assign them roles; you never invent a hex, adjust one,
  or add one the census did not measure.
- The screenshot tells you how the measured values are USED — which color is
  the ground, which is the ink, which is the accent. Read roles from the
  image; read values from the census.

FONT-SLOP SIGNAL: if the census shows the primary font is a default stack —
system-ui, -apple-system, Segoe UI, Arial, Helvetica, Times, or one bare
fallback family doing all the work — say so explicitly in the summary and in
the maturity rationale. A default stack is the single strongest tell of
template output.

MATURITY LADDER — "maturity_level" is the HIGHEST level whose signature the
page EXHIBITS, with one sentence of cited evidence as "maturity_rationale":
1 — generic AI-template tells: default font stacks, a stock hero, no
    consistent palette.
2 — the beginnings of a reference-driven style: a palette exists, but the
    pairing or the rhythm is inconsistent.
3 — a coherent style system: consistent palette, deliberate font pairing, a
    spacing rhythm that repeats.
4 — custom media assets: photography, illustration, or video made for this
    page rather than stock.
5 — polished components and micro-interactions visible in the rendering.
6 — conversion architecture: deliberate image-to-call-to-action sequencing
    down the page.
7 — an extractable, internally consistent design identity: the rules below
    could restyle another page and it would still read as this brand.

STYLE TAGS — "style_tags" carries 1 to 3 tags, chosen from exactly this list
and no other: Light Canvas, Clean SaaS, Editorial Type, Soft Gradients,
Monochrome UI, Minimalist Brand, High Contrast, Premium Design,
Dark Instrument, Playful.

DESIGN.MD — "design_md" is a complete markdown document the founder can paste
into their coding tool (Claude Code, Cursor). Its sections, in order:
1. A title line naming the site, then the one-line characterization in
   italics — the same evocative line as "characterization": concrete and
   sensory, the register of "midnight precision instrument", never
   marketing fluff.
2. The prose read of the system — the same 3-5 sentences as "summary".
3. "## Palette" — a markdown table with columns Hex, Name, Role. Hexes only
   from the census.
4. "## Typography" — each family with its measured weights and its role,
   then the type scale exactly as measured (the font-size histogram,
   most-used first).
5. "## Spacing & Shape" — the spacing vocabulary (name the base unit if the
   census detected one), the radius vocabulary, and the shadow vocabulary,
   each value with its role.
6. "## Do" and "## Don't" — the same lists as "dos" and "donts": rules
   derived from what the page already does consistently, each concrete
   enough to check ("Do: keep body text at 16px/1.6", "Don't: introduce a
   second accent color").
7. "## Agent Prompt Guide" — a quick color reference (hex, then its role,
   one per line) followed by exactly three example component prompts, each
   a complete instruction the founder can paste into their coding tool to
   get an on-brand component (for example a pricing card, a nav bar, a
   testimonial block) — every prompt naming the real hexes, family, radius,
   and spacing values from the census.

{vocabulary_rule}

PAGE TITLE: {title}

MEASURED STYLE CENSUS (the receipt — every value claim cites it):
{census_text}

PAGE TEXT (an extract, for cross-reference):
{dom_excerpt}"""

_JSON_INSTRUCTION = """\
ANSWER FORMAT — return ONLY a JSON object, no prose before or after it, no
code fences, exactly this shape:
{"characterization": "<one evocative line>",
 "summary": "<3-5 sentences on the system as a whole>",
 "tokens": {"palette": [{"hex": "<a hex from the census>",
                         "name": "<a short color name>",
                         "role": "<what it does on the page>"}],
            "fonts": [{"family": "<a first family from the census>",
                       "weights": ["<a weight in use>"],
                       "role": "<heading, body, accent, ...>"}],
            "radii": {"<a radius value from the census>": "<where it is used>"},
            "shadows": ["<a shadow value from the census>"],
            "spacing": {"<a spacing value, or base_unit_px>": "<its place in the rhythm>"},
            "theme": "<light, dark, or mixed>"},
 "dos": ["<a concrete rule the page already follows>"],
 "donts": ["<a concrete rule the page never breaks>"],
 "style_tags": ["<1-3 tags from the list above>"],
 "maturity_level": <integer 1-7>,
 "maturity_rationale": "<one sentence citing the evidence>",
 "design_md": "<the complete DESIGN.md markdown document, as one JSON string>"}"""

_JSON_NUDGE = (
    "Your previous answer could not be read. Return ONLY valid JSON exactly "
    "in the shape requested — no prose before or after it, no code fences."
)

# Founder-facing failure sentences, kept as templates so the vocabulary scan
# can read them the way it reads the prompt.
_UNREADABLE_ERROR = (
    "The design read of the page answered twice in a form that could not be "
    "read, so no design profile was produced. Run the page check again."
)
_FAILED_ERROR = (
    "The design read of the page could not finish ({error}). No design "
    "profile was produced — run the page check again."
)

_NO_CENSUS_TEXT = (
    "(no style numbers could be measured for this page — say so in the "
    "summary, read only what the screenshot shows, and with no census there "
    "are no hex values you may name)"
)


# ── wiring ───────────────────────────────────────────────────────────


def _excerpt(text: str, limit: int) -> str:
    cleaned = (text or "").strip()
    if not cleaned:
        return "(no text could be read from the page)"
    if len(cleaned) <= limit:
        return cleaned
    return cleaned[:limit].rstrip() + "\n[cut here — the rest of the page text did not fit]"


def _census_text(census: dict) -> str:
    """The census as prompt text: plain JSON, already capped at capture time."""
    if not census:
        return _NO_CENSUS_TEXT
    return json.dumps(census, indent=2)


def _build_prompt(capture: WebsiteCapture) -> str:
    filled = _DNA_TEMPLATE.format(
        vocabulary_rule=VOCABULARY_RULE,
        title=capture.title or "(the page has no title)",
        census_text=_census_text(capture.style_census or {}),
        dom_excerpt=_excerpt(capture.dom_text, _DOM_EXCERPT_CHARS),
    )
    return filled + "\n\n" + _JSON_INSTRUCTION


def _try_parse(raw: str) -> DesignDNA | None:
    try:
        return DesignDNA.model_validate_json(_extract_json(raw))
    except ValidationError:
        return None


async def extract_design_dna(
    capture: WebsiteCapture,
    *,
    organization_id: str | None = None,
) -> DesignDNA:
    """One vision call: screenshot + census + text extract -> a DesignDNA.

    Attributed to the cost ledger as `website_design_dna`. An unreadable
    answer gets exactly one nudged retry; a second unreadable answer, or
    anything the transport raises, becomes a `DesignDNAError` whose message
    the founder can read.
    """
    prompt = _build_prompt(capture)
    screenshot = capture.screenshot_desktop
    try:
        with usage_context("website_design_dna", organization_id=organization_id):
            # The payload embeds a whole DESIGN.md inside the JSON — at the
            # default 4,096 max_tokens the response truncates mid-document and
            # both parse attempts fail (found by the first live gate, not by
            # the mocked tests). The ceiling is sized for the largest honest
            # artifact, not for the average one.
            raw = await llm_vision(prompt, [screenshot], max_tokens=16384)
            parsed = _try_parse(raw)
            if parsed is None:
                raw = await llm_vision(
                    prompt + "\n\n" + _JSON_NUDGE, [screenshot], max_tokens=16384
                )
                parsed = _try_parse(raw)
    except Exception as exc:
        raise DesignDNAError(
            _FAILED_ERROR.format(error=f"{type(exc).__name__}: {exc}")
        ) from exc
    if parsed is None:
        raise DesignDNAError(_UNREADABLE_ERROR)

    logger.info(
        "website_design_dna_extracted",
        url=capture.url,
        maturity_level=parsed.maturity_level,
        style_tags=parsed.style_tags,
        palette_size=len(parsed.tokens.palette),
        design_md_chars=len(parsed.design_md),
    )
    return parsed
