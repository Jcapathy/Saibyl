# PUBLIC INTERFACE
# ─────────────────────────────────────────────────────────
# generate_revision(capture, critique, dna, *, reference=None,
#                   max_rounds=3, target_overall=75,
#                   organization_id=None) -> RevisionResult   [async]
# compose_fix_prompts(critique, dna) -> list[dict]
# RevisionResult, RevisionRound, RevisionError
# ─────────────────────────────────────────────────────────
"""The revision generator: rewrite a page until it survives the gauntlet
(PRD_V3 §4d).

The loop is draft → judge → revise: one vision call writes a complete,
self-contained HTML page; `capture_html` renders it through the same pipeline
that rendered the original; `run_critic_gauntlet` re-scores the render with
the same six reviewers (and the same reference site, when one rode along).
The loop stops when the overall score clears the target or the round budget
runs out — and the round that scored highest is the one returned, because a
later round can regress and a regression must never be presented as the
result. Every round's scores are recorded either way; an unmoved or worsened
number is reported as what it is.

The generator is under the same honesty discipline as the critics:

- **The page's real words are the only source of facts.** The prompt carries
  the extracted page text and forbids inventing claims, prices, customers, or
  features; a needed-but-missing fact becomes a visible `[OWNER: fill in]`
  placeholder instead of a plausible fabrication.
- **The critique is the work order.** Every finding's fix rides in the prompt
  as an instruction to apply, grouped by dimension, and every strength rides
  as something the new page must not lose (three live critic rounds showed
  edits sanding off what worked whenever the preserve list went missing).
- **The design brief is honored or deliberately replaced, never drifted
  from.** When the check extracted a design brief, it rides in the prompt as
  the system to follow — unless the review says the system itself is the
  problem, in which case the model must build a coherent replacement and
  declare that in an HTML comment at the top of the document.
- **A reference site is numbers, not vibes.** When the founder named a site
  to stand beside, its measured style census rides in the prompt as the
  discipline to hit — letter-spacing, radius vocabulary, weight band.

`compose_fix_prompts` is the other §4d output: the same critique, recomposed
deterministically (no model call) into paste-ready prompt blocks for the
founder's own coding tool — one block per dimension with findings, plus a
rebuild-to-the-brief block when a design brief exists.

Every generation call lands in the cost ledger as `website_revision`; the
judge rounds land as `website_critics` through the gauntlet's own context
(nested stages replace the outer one for their duration), so §4e can price
the two stages from measured usage, separately.
"""
from __future__ import annotations

import json

import structlog
from pydantic import BaseModel, Field

from app.core.llm_client import llm_vision
from app.services.billing.usage_ledger import usage_context
from app.services.website.capture import WebsiteCapture, capture_html
from app.services.website.critics import CritiqueResult, run_critic_gauntlet

logger = structlog.get_logger()

# A whole page rides in the answer: HTML plus an inline stylesheet routinely
# passes 20K tokens, and at the default 4,096 ceiling the document truncates
# mid-tag and fails the parse twice in a row — the same per-artifact-ceiling
# lesson the DESIGN.md payload taught (CRITICS_LOG, 2026-08-16). Sized for the
# largest honest page, not the average one.
_GENERATION_MAX_TOKENS = 32_000

# How much of the original page's extracted text rides as the facts source.
# The cut is annotated so the model knows the tail is missing rather than
# concluding the page had nothing more to say.
_PAGE_TEXT_CHARS = 20_000

# How much of a reference site's measurement table rides along — the same
# bound the critics put on a census-in-prompt.
_REFERENCE_CENSUS_CHARS = 6_000


# ── public result models ─────────────────────────────────────────────


class RevisionRound(BaseModel):
    round: int
    overall_score: int = Field(ge=0, le=100)
    dimension_scores: dict[str, int]


class RevisionResult(BaseModel):
    html: str  # the best round's full HTML document
    rounds: list[RevisionRound]  # every round judged, in order
    best_round: int
    scores_before: dict  # {"overall": int, <dimension>: int, ...}
    scores_after: dict  # same shape, from the best round
    critique_after: dict  # the best round's full critique
    capture_after: WebsiteCapture  # the best round's render
    fix_prompts: list[dict]  # compose_fix_prompts(...) of the original critique


class RevisionError(Exception):
    """The revision could not be produced; the message is founder-readable."""


# ── the generation prompt, section by section ────────────────────────

_HEADER = """\
PAGE REVISION — round {round_no}

You are rewriting a founder's web page so it survives the review that failed
it. You produce the COMPLETE new page: one self-contained HTML document a
browser can open exactly as you return it."""

_EVIDENCE_FIRST = (
    "The attached image is a full-page desktop screenshot of the page as it "
    "is today."
)
_EVIDENCE_LATER = (
    "The attached image is a full-page desktop screenshot of your previous "
    "revision, exactly as a browser rendered it."
)

_PAGE_TEXT_SECTION = """\
THE PAGE'S REAL WORDS (extracted from the page — the only source of facts):
{page_text}"""

_FACT_RULES = """\
FACT DISCIPLINE — these rules are absolute:
- The page text above is the only source of facts. Every claim, number,
  price, name, and feature you write must already appear there. Tighten,
  reorder, and clarify the page's real claims; never invent a claim, a
  price, a customer, or a feature.
- If a section needs a fact the page text does not contain, write the
  placeholder [OWNER: fill in] where the fact belongs and move on. A visible
  placeholder is honest; a plausible invention is not."""

_FINDINGS_HEADER = """\
WHAT THE REVIEW FOUND — apply every numbered fix below; each one is an
instruction, not a suggestion:"""

_STRENGTHS_HEADER = """\
KEEP WHAT SCORED WELL — the review named these strengths; the new page must
not lose them:"""

_PREVIOUS_HTML_SECTION = """\
YOUR PREVIOUS REVISION — the review above judged this exact document. Apply
the fixes to it and keep what scored well:
```html
{previous_html}
```"""

_DESIGN_BRIEF_SECTION = """\
THE PAGE'S DESIGN BRIEF (measured from the page as it is today):
```markdown
{design_md}
```
Honor this system — its palette, its type, its spacing and shape vocabulary
— unless the review above says the system itself is the problem. In that
case build one coherent replacement system, and declare that you did in an
HTML comment at the very top of the document, naming what you replaced and
why."""

_REFERENCE_SECTION = """\
THE DISCIPLINE TO HIT — style numbers measured from {reference_title}, the
site the founder wants to stand beside. Match the discipline these numbers
describe — the letter-spacing, the radius vocabulary, the weight band — as
measured values, not as a mood:
{reference_census}"""

_HARD_REQUIREMENTS = """\
HARD REQUIREMENTS — the page is rejected if any of these fails:
- One complete, self-contained HTML document. All CSS lives inline in one
  <style> block. Fonts are system-font stacks, or at most one Google Fonts
  <link> and nothing else remote.
- No external JavaScript. No external images: where an image belongs, draw a
  CSS or inline-SVG placeholder and label it visibly as a placeholder.
- Responsive: below 660px wide the layout reads as a single column.
- Semantic HTML: <header>, <main>, <section>, <footer>, real heading levels,
  real <a> and <button> elements — not styled <div>s doing their jobs.
{vocabulary_rule}"""

#: The rendered-text spelling of the house banned-word list (the reviewers'
#: rule bans them from findings; this bans them from the page itself).
RENDERED_VOCABULARY_RULE = """\
- The page's rendered text is read by strangers. None of these words may
  appear anywhere in it: ICP, variant, A/B, adversarial, cohort, arena,
  lens, archetype, canonical, valence, simulation, project. Write plain
  words a visitor already knows."""

_ANSWER_FORMAT = """\
ANSWER FORMAT — return ONLY the HTML document itself. The first characters
of your answer are "<!doctype html>", the last are "</html>". No prose
before or after it, no code fences."""

# The retry carries the complaint, not just a repeat of the question — a
# retry that repeats the question gets the same wrong answer (CRITICS_LOG,
# 2026-08-16).
_HTML_COMPLAINT = (
    "Your previous answer was rejected because it was not a complete HTML "
    'document: it must start with "<!doctype html>" (or "<html") and end '
    'with "</html>", with no prose or code fences around it. Return ONLY '
    "the document."
)

# Founder-facing failure sentences, kept as constants so the vocabulary scan
# can read them the way it reads the prompt sections.
_UNPARSEABLE_ERROR = (
    "The rewritten page came back twice in a form that is not a complete web "
    "page, so no revision was produced. Run the revision again."
)
_GENERATION_FAILED_ERROR = (
    "The page rewrite could not finish ({error}). No revision was produced — "
    "run the revision again."
)
_FIRST_JUDGE_FAILED_ERROR = (
    "The rewritten page could not be reviewed ({error}), so there is no "
    "verdict on it. No revision was produced — run the revision again."
)


# ── prompt assembly ──────────────────────────────────────────────────


def _cut(text: str, limit: int) -> str:
    cleaned = (text or "").strip()
    if not cleaned:
        return "(no text could be read from the page)"
    if len(cleaned) <= limit:
        return cleaned
    return cleaned[:limit].rstrip() + "\n[cut here — the rest of the page text did not fit]"


def _findings_block(critique: dict) -> str:
    """The critique's findings, grouped by dimension, each fix numbered."""
    blocks: list[str] = []
    for dimension in critique.get("dimensions") or []:
        findings = dimension.get("findings") or []
        if not findings:
            continue
        lines = [f"{dimension.get('key', 'page')} (scored {dimension.get('score', '?')}/100):"]
        for number, finding in enumerate(findings, 1):
            line = (
                f"  {number}. [{finding.get('severity', 'major')}] "
                f"{finding.get('region', 'the page')} — {finding.get('fix', '')}"
            )
            quote = str(finding.get("quote") or "").strip()
            if quote:
                line += f' (on the page now: "{quote}")'
            lines.append(line)
        blocks.append("\n".join(lines))
    return "\n".join(blocks) or "(the review recorded no itemized findings)"


def _strengths_block(critique: dict) -> str:
    strengths = [
        str(strength)
        for dimension in critique.get("dimensions") or []
        for strength in dimension.get("strengths") or []
    ]
    if not strengths:
        return "(the review named no strengths to protect)"
    return "\n".join(f"- {strength}" for strength in strengths)


def _reference_census_text(reference: WebsiteCapture) -> str:
    census = getattr(reference, "style_census", None)
    if not isinstance(census, dict) or not census:
        return "(no style numbers could be measured from the reference site)"
    rendered = json.dumps(census, indent=1, sort_keys=True, ensure_ascii=False, default=str)
    if len(rendered) > _REFERENCE_CENSUS_CHARS:
        rendered = (
            rendered[:_REFERENCE_CENSUS_CHARS].rstrip()
            + "\n[cut here — the rest of the measurements did not fit]"
        )
    return rendered


def _generation_prompt(
    *,
    round_no: int,
    page_text: str,
    critique: dict,
    dna: dict | None,
    reference: WebsiteCapture | None,
    previous_html: str | None,
) -> str:
    sections = [
        _HEADER.format(round_no=round_no),
        _EVIDENCE_FIRST if previous_html is None else _EVIDENCE_LATER,
        _PAGE_TEXT_SECTION.format(page_text=_cut(page_text, _PAGE_TEXT_CHARS)),
        _FACT_RULES,
        _FINDINGS_HEADER + "\n" + _findings_block(critique),
        _STRENGTHS_HEADER + "\n" + _strengths_block(critique),
    ]
    if previous_html is not None:
        # Uncapped by design: the document was produced under the generation
        # ceiling, so it is bounded by construction, and a revision of half a
        # page would silently drop the other half.
        sections.append(_PREVIOUS_HTML_SECTION.format(previous_html=previous_html))
    design_md = str((dna or {}).get("design_md") or "").strip()
    if design_md:
        sections.append(_DESIGN_BRIEF_SECTION.format(design_md=design_md))
    if reference is not None:
        sections.append(
            _REFERENCE_SECTION.format(
                reference_title=reference.title or "(the reference site has no title)",
                reference_census=_reference_census_text(reference),
            )
        )
    sections.append(_HARD_REQUIREMENTS.format(vocabulary_rule=RENDERED_VOCABULARY_RULE))
    sections.append(_ANSWER_FORMAT)
    return "\n\n".join(sections)


# ── generation: one call, one complained retry, then the truth ───────


def _parse_document(raw: str) -> str | None:
    """The answer as a complete HTML document, or None.

    A fenced document is still the document (the fence lines are stripped),
    but prose before the doctype or a missing `</html>` is a failed answer —
    half a page judged as the page would be the capture pipeline lying.
    Anything after the final `</html>` is trailing prose, and is dropped.
    """
    text = (raw or "").strip()
    if text.startswith("```"):
        lines = [line for line in text.split("\n") if not line.strip().startswith("```")]
        text = "\n".join(lines).strip()
    lowered = text.lower()
    if not lowered.startswith(("<!doctype", "<html")):
        return None
    end = lowered.rfind("</html>")
    if end == -1:
        return None
    return text[: end + len("</html>")]


async def _generate_html(prompt: str, evidence: bytes) -> str:
    """One vision call producing the page; unreadable output gets exactly one
    retry that names the complaint, then a founder-readable failure."""
    try:
        raw = await llm_vision(prompt, [evidence], max_tokens=_GENERATION_MAX_TOKENS)
        html = _parse_document(raw)
        if html is None:
            raw = await llm_vision(
                prompt + "\n\n" + _HTML_COMPLAINT, [evidence], max_tokens=_GENERATION_MAX_TOKENS
            )
            html = _parse_document(raw)
    except Exception as exc:
        raise RevisionError(
            _GENERATION_FAILED_ERROR.format(error=f"{type(exc).__name__}: {exc}")
        ) from exc
    if html is None:
        raise RevisionError(_UNPARSEABLE_ERROR)
    return html


# ── the gauntlet loop ────────────────────────────────────────────────


def _scores_of(critique: dict) -> dict:
    """A critique as `{"overall": int, <dimension>: int, ...}`."""
    scores: dict = {"overall": int(critique.get("overall_score") or 0)}
    for dimension in critique.get("dimensions") or []:
        key = dimension.get("key")
        if key:
            scores[str(key)] = int(dimension.get("score") or 0)
    return scores


class _Round(BaseModel):
    """One completed round, kept whole so the best one can be returned."""

    number: int
    html: str
    render: WebsiteCapture
    verdict: CritiqueResult


async def generate_revision(
    capture: WebsiteCapture,
    critique: dict,
    dna: dict | None,
    *,
    reference: WebsiteCapture | None = None,
    max_rounds: int = 3,
    target_overall: int = 75,
    organization_id: str | None = None,
) -> RevisionResult:
    """Rewrite the page through gauntlet rounds and return the best revision.

    Each round: generate a complete self-contained page (one vision call,
    `website_revision` in the cost ledger), render it with `capture_html`,
    judge the render with `run_critic_gauntlet` (same reference site as the
    original check, when one was given). Stop at `target_overall` or after
    `max_rounds`; between rounds the next prompt carries the previous HTML
    and the new critique's findings. The best round — never merely the last —
    is the result; every judged round's scores are in `rounds` regardless.

    Failure honesty: output that is not a complete HTML document gets one
    retry carrying the complaint, then `RevisionError`. A render or judge
    failure after at least one completed round returns the best-so-far with
    `rounds` stopping at the last verdict; the same failure on round one is a
    `RevisionError`, because no verdict exists to stand behind.
    """
    if max_rounds < 1:
        raise ValueError("max_rounds must be at least 1")

    rounds: list[RevisionRound] = []
    best: _Round | None = None
    current_critique = critique
    previous_html: str | None = None
    evidence = capture.screenshot_desktop

    with usage_context("website_revision", organization_id=organization_id):
        for round_no in range(1, max_rounds + 1):
            prompt = _generation_prompt(
                round_no=round_no,
                page_text=capture.dom_text,
                critique=current_critique,
                dna=dna,
                reference=reference,
                previous_html=previous_html,
            )
            html = await _generate_html(prompt, evidence)

            try:
                render = await capture_html(html)
                verdict = await run_critic_gauntlet(
                    render, reference=reference, organization_id=organization_id
                )
            except Exception as exc:
                if best is None:
                    raise RevisionError(
                        _FIRST_JUDGE_FAILED_ERROR.format(error=f"{type(exc).__name__}: {exc}")
                    ) from exc
                # A judged revision in hand beats an unjudged one on the
                # floor: stop here and stand behind the best completed round.
                logger.warning(
                    "website_revision_judge_failed",
                    round=round_no,
                    completed_rounds=len(rounds),
                    error=f"{type(exc).__name__}: {exc}",
                )
                break

            rounds.append(
                RevisionRound(
                    round=round_no,
                    overall_score=verdict.overall_score,
                    dimension_scores={d.key: d.score for d in verdict.dimensions},
                )
            )
            if best is None or verdict.overall_score > best.verdict.overall_score:
                best = _Round(number=round_no, html=html, render=render, verdict=verdict)
            if verdict.overall_score >= target_overall:
                break

            previous_html = html
            current_critique = verdict.model_dump()
            evidence = render.screenshot_desktop

    assert best is not None  # round one either completed or raised above
    scores_before = _scores_of(critique)
    scores_after = _scores_of(best.verdict.model_dump())
    logger.info(
        "website_revision_complete",
        url=capture.url,
        rounds=len(rounds),
        best_round=best.number,
        overall_before=scores_before.get("overall"),
        overall_after=scores_after.get("overall"),
        target_overall=target_overall,
    )
    return RevisionResult(
        html=best.html,
        rounds=rounds,
        best_round=best.number,
        scores_before=scores_before,
        scores_after=scores_after,
        critique_after=best.verdict.model_dump(),
        capture_after=best.render,
        fix_prompts=compose_fix_prompts(critique, dna),
    )


# ── paste-ready fix prompts (deterministic — no model call) ──────────

_FIX_CONTEXT_LINE = (
    "You are editing my website's code. Apply the numbered changes below "
    "exactly as written."
)
_FIX_CLOSING_LINE = "Change nothing else."

_REBUILD_TITLE = "Rebuild to the design brief"
_REBUILD_CONTEXT = (
    "You are editing my website's code. Below is the design brief measured "
    "from my page. Restyle the page to follow it exactly — palette, type, "
    "spacing, radii, shadows. Keep every claim and every sentence of content "
    "unchanged."
)
_REBUILD_CLOSING_LINE = "Change the styling only — nothing else."

#: title, founder-facing scope — per dimension key, matching the reviewers'.
_FIX_TITLES: dict[str, tuple[str, str]] = {
    "hierarchy": ("Fix the reading order", "hierarchy"),
    "credibility": ("Fix the trust signals", "credibility"),
    "conversion": ("Fix the route to action", "conversion path"),
    "copy": ("Fix the words", "copy clarity"),
    "mobile": ("Fix the phone experience", "mobile experience"),
    "design": ("Fix the look", "design"),
}


def compose_fix_prompts(critique: dict, dna: dict | None) -> list[dict]:
    """The critique as paste-ready prompt blocks for the founder's coding tool.

    One block per dimension that has findings — a context line, the findings
    as numbered instructions (region, fix, and the measured quote when the
    finding carries one), a change-nothing-else stop — plus, when a design
    brief exists, one final block that embeds the whole brief, fenced.
    Deterministic: same critique in, same prompts out, no model call.
    """
    prompts: list[dict] = []
    for dimension in critique.get("dimensions") or []:
        findings = dimension.get("findings") or []
        if not findings:
            continue
        key = str(dimension.get("key") or "page")
        title, scope = _FIX_TITLES.get(key, (f"Fix the {key}", key))
        lines = [_FIX_CONTEXT_LINE, ""]
        for number, finding in enumerate(findings, 1):
            line = f"{number}. {finding.get('region', 'the page')} — {finding.get('fix', '')}"
            quote = str(finding.get("quote") or "").strip()
            if quote:
                line += f' (on the page now: "{quote}")'
            lines.append(line)
        lines += ["", _FIX_CLOSING_LINE]
        prompts.append({"title": title, "scope": scope, "prompt": "\n".join(lines)})

    design_md = str((dna or {}).get("design_md") or "").strip()
    if design_md:
        prompts.append(
            {
                "title": _REBUILD_TITLE,
                "scope": "the whole page",
                "prompt": (
                    _REBUILD_CONTEXT
                    + "\n\n```markdown\n"
                    + design_md
                    + "\n```\n\n"
                    + _REBUILD_CLOSING_LINE
                ),
            }
        )
    return prompts
