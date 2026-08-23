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

- **The page's real words are the only source of facts, and that is checked
  rather than asked for.** The prompt carries the extracted page text and
  forbids inventing claims, prices, customers or features; a needed-but-missing
  fact becomes a visible `[OWNER: fill in]` placeholder. Because a live fintech
  revision ignored exactly that instruction and shipped invented certifications
  (2026-08-22), every generated document is then scanned by `claims`, a pure
  function with no model call: anything claim-shaped that is absent from the
  source triggers one retry naming the sentences, a page still claiming a
  certification loses the best-round tie-break to an honest one, and whatever
  survives rides on `RevisionResult.unsupported_claims` to the founder.
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
from app.services.website.claims import (
    UnsupportedClaim,
    claim_complaint,
    unsupported_claims,
)
from app.services.website.critics import CritiqueResult, run_critic_gauntlet
from app.services.website.verticals import brief_section, classify_vertical

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
    #: Claims the delivered page makes that the founder's page never made, after
    #: the retry that tried to remove them. Empty is the ordinary case; a
    #: non-empty list must reach the founder, not just the log — an unreported
    #: fabrication is worse than a reported one, because they publish it.
    unsupported_claims: list[UnsupportedClaim] = []


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
- When a section you were planning needs a fact the page text does not
  contain, BUILD THE SECTION DIFFERENTLY. Make the point with what the page
  does support, or drop that point and give the space to a claim you can
  stand behind. A page is allowed to say less. Removing a trust strip you
  cannot fill is a complete page with fewer claims; leaving three bracketed
  blanks in it is a broken page.
- Reach for the placeholder [OWNER: fill in <what>] ONLY for a single
  self-contained value the founder can supply in seconds — a price, a launch
  date, a customer count — and only where the sentence around it still reads
  as finished English. Never use it for a headline, never for social proof,
  and never more than twice in the whole document.
- The founder publishes what you return. Anything they must edit before
  publishing is unfinished work, and a visible bracket where the evidence
  should be scores worse with a reader than the shorter, truthful page would
  have."""

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
    # What the category demands, derived from the founder's own words.
    #
    # Without this the generator inherited the page's existing design DNA and
    # polished it, so a generic page came back as a better-executed generic
    # page — and a clinical product and a payments product were designed by
    # the same instincts. The brief describes what THIS buyer must believe and
    # what the page must therefore prove; it is placed before the findings so
    # the fixes are made in the category's terms rather than in the abstract.
    #
    # `general` when the material does not clearly say — a confidently wrong
    # category brief would push the page toward conventions its buyer does not
    # hold, which is worse than no brief at all.
    vertical = classify_vertical(page_text)

    sections = [
        _HEADER.format(round_no=round_no),
        _EVIDENCE_FIRST if previous_html is None else _EVIDENCE_LATER,
        _PAGE_TEXT_SECTION.format(page_text=_cut(page_text, _PAGE_TEXT_CHARS)),
        brief_section(vertical),
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


def _fabrication(claims: list[UnsupportedClaim]) -> tuple[int, int]:
    """How much a document invented, ordered by what a false one costs.

    Invented certifications first, then everything else — the same priority
    `_is_better` uses to rank whole rounds. A page claiming one badge is worse
    than a page claiming four prices, and a badge is what a founder cannot
    explain to a regulator.
    """
    forged = sum(1 for c in claims if c.kind == "certification")
    return forged, len(claims)


async def _generate_html(
    prompt: str, evidence: bytes, page_text: str
) -> tuple[str, list[UnsupportedClaim]]:
    """One vision call producing the page, plus what it claimed without basis.

    Two things can be wrong with an answer, and they share one retry so the
    round's cost stays at two calls: the answer is not a document, or it is a
    document that invents facts. Either way the retry carries the specific
    complaint rather than a repeat of the question.

    The claims check is not advisory. The prompt already forbids invention in
    two separate sections and was overridden in production anyway (see
    `claims`), so the deterministic scan — not the instruction — is what makes
    the honesty rule real. Surviving claims come back with the page rather than
    raising: a page with a flagged figure is still worth more to the founder
    than no page, provided the flag travels with it.

    **A retry that fabricates MORE than the answer it replaces is not an
    improvement, and "it came back second" is not a reason to ship it.** The
    complaint demands a whole-document rewrite, so a rewrite can fabricate
    differently rather than less — one live shape has the first answer claiming
    SOC 2 and the retry coming back with ISO 27001, PCI DSS and HIPAA. Accepted
    on parseability alone, the strictly-worse document is what the founder
    downloads. This is the same rule `_is_better` applies between rounds
    (fewest invented certifications first), applied to the choice inside a
    round, which is where it was missing.
    """
    try:
        raw = await llm_vision(prompt, [evidence], max_tokens=_GENERATION_MAX_TOKENS)
        html = _parse_document(raw)
        claims = unsupported_claims(page_text, html) if html is not None else []

        complaint = _HTML_COMPLAINT if html is None else (
            claim_complaint(claims) if claims else None
        )
        if complaint is not None:
            raw = await llm_vision(
                prompt + "\n\n" + complaint, [evidence], max_tokens=_GENERATION_MAX_TOKENS
            )
            retried = _parse_document(raw)
            # An unreadable retry leaves the first document standing when there
            # was one — losing a whole page to fix a percentage is a worse
            # trade than reporting the percentage.
            if retried is not None:
                retried_claims = unsupported_claims(page_text, retried)
                if html is None or _fabrication(retried_claims) <= _fabrication(claims):
                    html, claims = retried, retried_claims
                else:
                    logger.warning(
                        "website_revision_retry_rejected",
                        first_claims=len(claims),
                        retry_claims=len(retried_claims),
                        first_certifications=[
                            c.text for c in claims if c.kind == "certification"
                        ],
                        retry_certifications=[
                            c.text for c in retried_claims if c.kind == "certification"
                        ],
                    )
    except Exception as exc:
        raise RevisionError(
            _GENERATION_FAILED_ERROR.format(error=f"{type(exc).__name__}: {exc}")
        ) from exc
    if html is None:
        raise RevisionError(_UNPARSEABLE_ERROR)
    if claims:
        logger.warning(
            "website_revision_unsupported_claims",
            count=len(claims),
            certifications=[c.text for c in claims if c.kind == "certification"],
        )
    return html, claims


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
    claims: list[UnsupportedClaim] = []

    @property
    def forged_badges(self) -> int:
        """How many certifications this round claimed without basis."""
        return sum(1 for c in self.claims if c.kind == "certification")


def _is_better(candidate: _Round, incumbent: _Round | None) -> bool:
    """Whether a round should replace the best one so far.

    **Fewest invented certifications first, and only then the score.** The
    gauntlet cannot see the founder's real page, so it scores a page that
    claims SOC 2 exactly as it scores one that holds it — on the live fintech
    run the fabricating round was scored *up*, credibility unmoved at 82.
    Ranking on score alone therefore means knowingly shipping the fabricating
    page whenever it lands two points higher, and "it scored better" is not an
    answer a founder can give a regulator.

    Only certifications are disqualifying. A figure or a customer count is
    reported to the founder but does not override the score: those are noisier
    to detect, and far cheaper to be wrong about in either direction.
    """
    if incumbent is None:
        return True
    if candidate.forged_badges != incumbent.forged_badges:
        return candidate.forged_badges < incumbent.forged_badges
    return candidate.verdict.overall_score > incumbent.verdict.overall_score


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
    retry carrying the complaint. After that — and for a render or judge
    failure alike — **any** of the three failures returns the best-so-far once
    at least one round has completed, with `rounds` stopping at the last
    verdict; the same failure on round one is a `RevisionError`, because no
    verdict exists to stand behind.
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
            # Always measured against the founder's own page, never against the
            # previous revision: a fabrication that survives round one would
            # otherwise become its own evidence in round two.
            #
            # **Generation is the third failure kind, and it was the one the
            # best-so-far guard did not cover.** It sat outside the try below,
            # so a transient 529 or two unparseable replies on round 2 raised
            # past a completed, rendered, gauntlet-scored round 1 and threw it
            # away — the docstring promised the opposite, and nothing is
            # refunded. It is also the likeliest of the three to fire, being
            # two model calls where the judge is one pipeline.
            try:
                html, claims = await _generate_html(prompt, evidence, capture.dom_text)
            except Exception as exc:
                if best is None:
                    # Round one: `_generate_html` already raised the
                    # founder-readable sentence for whichever way it failed,
                    # and there is no verdict to stand behind. Let it through
                    # unchanged rather than relabel it as a judge failure.
                    raise
                logger.warning(
                    "website_revision_generation_failed",
                    round=round_no,
                    completed_rounds=len(rounds),
                    error=f"{type(exc).__name__}: {exc}",
                )
                break

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
            candidate = _Round(
                number=round_no, html=html, render=render, verdict=verdict, claims=claims
            )
            if _is_better(candidate, best):
                best = candidate
            # A page that clears the target while claiming a certification the
            # founder does not hold has not finished: spend the remaining
            # rounds trying to get an honest one, since the score the target
            # measures was earned partly by the fabrication.
            if verdict.overall_score >= target_overall and not candidate.forged_badges:
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
        unsupported_claims=len(best.claims),
        forged_badges=best.forged_badges,
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
        unsupported_claims=best.claims,
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
