"""The revision generator (PRD_V3 §4d): rewrite, re-render, re-judge, best wins.

The contract under test:

**`capture_html` is the same pipeline with the network unplugged.** A provided
HTML string renders through the exact machinery a URL capture uses — desktop
1440 and mobile 390 full-page screenshots, DOM text, meta tags, style census —
but the document is set directly (no navigation, no SSRF question) and an
abort route is installed before it loads, so a generated page can neither
beacon out nor hang on a dead CDN. `url` and `final_url` are both the honest
"about:revision".

**The gauntlet loop stops honestly and returns the best round, never merely
the last.** Stop at the target or the round cap; a later round that regresses
stays on the record in `rounds` but never ships as the result. The next
round's prompt carries the previous HTML and the new critique — findings to
apply, strengths to keep.

**Generation is under the facts discipline.** The prompt carries the page's
real words as the only source of facts, every finding's fix as an
instruction, the design brief when one exists, the reference site's measured
census when one rode along — and the whole page rides in the answer, so the
call's ceiling is 32,000 tokens (the per-artifact-ceiling lesson).

**Failure honesty.** Output that is not a complete HTML document gets exactly
one retry carrying the complaint, then a founder-readable `RevisionError`. A
judge failure after a completed round returns the best-so-far; on round one
it is an error, because no verdict exists to stand behind.

**`compose_fix_prompts` is deterministic.** One paste-ready block per
dimension with findings, measured quotes included, a rebuild-to-the-brief
block only when a design brief exists — and no composed string uses a word a
founder has to learn.

No live browser, no network, no model calls anywhere in this file: the
Playwright seam, `llm_vision`, `capture_html`, and `run_critic_gauntlet` are
all stood in.
"""
from __future__ import annotations

import re
from contextlib import contextmanager
from types import SimpleNamespace

import pytest

from app.services.website import capture as capture_mod
from app.services.website import revise
from app.services.website.capture import REVISION_URL, WebsiteCapture, capture_html
from app.services.website.critics import CriticDimension, CriticFinding, CritiqueResult
from app.services.website.revise import (
    RevisionError,
    RevisionResult,
    compose_fix_prompts,
    generate_revision,
)

# ---------------------------------------------------------------------------
# capture_html: a browserless Playwright stand-in (the capture tests' idiom,
# extended with set_content and route)
# ---------------------------------------------------------------------------


class _FakePage:
    def __init__(self, spec: dict, viewport: dict, calls: list):
        self._spec = spec
        self._viewport = viewport
        self._calls = calls
        self.url = "about:blank"

    async def set_content(self, html, timeout=None, wait_until=None):
        self._calls.append(("set_content", self._viewport["width"], html, timeout, wait_until))

    async def title(self):
        return self._spec.get("title", "")

    async def evaluate(self, script: str):
        # Keyed on marker substrings the module guarantees in its script constants.
        if "getComputedStyle" in script:
            return self._spec.get("census_raw", {})
        if "querySelectorAll('meta')" in script:
            return dict(self._spec.get("meta", {}))
        if "innerText" in script:
            return self._spec.get("dom_text", "")
        if "scrollHeight" in script:
            return self._spec.get("page_height", 900)
        raise AssertionError(f"unexpected evaluate script: {script!r}")

    async def screenshot(self, **kwargs):
        self._calls.append(("screenshot", self._viewport["width"], kwargs))
        return f"png-{self._viewport['width']}".encode()


class _FakeContext:
    def __init__(self, page: _FakePage, viewport: dict, calls: list):
        self._page = page
        self._viewport = viewport
        self._calls = calls
        self.closed = False
        self.default_timeout_ms: int | None = None

    def set_default_timeout(self, ms: int) -> None:
        # Bounds Playwright's own actions after the document loads. A
        # model-written page is small, but the same pipeline serves live sites
        # where an unbounded screenshot is how a capture hung for fifteen
        # minutes.
        self.default_timeout_ms = ms

    async def new_page(self):
        return self._page

    async def route(self, pattern, handler):
        self._calls.append(("route", self._viewport["width"], pattern, handler))

    async def close(self):
        self.closed = True


class _FakeBrowser:
    def __init__(self, spec: dict, calls: list):
        self._spec = spec
        self._calls = calls
        self.closed = False

    async def new_context(self, **kwargs):
        self._calls.append(("new_context", kwargs))
        viewport = kwargs["viewport"]
        return _FakeContext(_FakePage(self._spec, viewport, self._calls), viewport, self._calls)

    async def close(self):
        self.closed = True


class _FakeAsyncPlaywright:
    def __init__(self, browser: _FakeBrowser):
        self._browser = browser

    async def __aenter__(self):
        async def launch(**_kwargs):
            return self._browser

        return SimpleNamespace(chromium=SimpleNamespace(launch=launch))

    async def __aexit__(self, *_exc):
        return False


def _install_fake_playwright(monkeypatch, spec: dict) -> tuple[list, _FakeBrowser]:
    calls: list = []
    browser = _FakeBrowser(spec, calls)
    module = SimpleNamespace(
        async_playwright=lambda: _FakeAsyncPlaywright(browser),
        Error=Exception,
        TimeoutError=TimeoutError,
    )
    monkeypatch.setattr(capture_mod, "_import_playwright", lambda: module)
    return calls, browser


class _FakeInterceptedRoute:
    """What Playwright hands the route handler: a request and two verbs."""

    def __init__(self, url: str):
        self.request = SimpleNamespace(url=url)
        self.aborted = False
        self.continued = False

    async def abort(self):
        self.aborted = True

    async def continue_(self):
        self.continued = True


_RAW_CENSUS = {
    "sampled": 12,
    "font_families": {'"Space Grotesk", sans-serif': 10},
    "font_weights": {"400": 8},
    "font_sizes": {"16px": 9},
    "letter_spacing": {"headings": {"-0.02em": 2}, "body": {"normal": 8}},
    "line_heights": {"24px": 9},
    "text_colors": {"rgb(16, 20, 24)": 10},
    "background_colors": {"rgb(245, 242, 236)": 3},
    "border_colors": {},
    "border_radii": {"8px": 4},
    "box_shadows": {},
    "spacing": {"24px": 9, "8px": 6},
    "structure": {"headings": {"h1": 1}, "buttons": 1, "links": 2, "images": 0},
}

_HTML_IN = "<html><head><title>Rewritten</title></head><body><main>Hi</main></body></html>"


async def test_capture_html_renders_the_document_through_the_shared_pipeline(monkeypatch):
    calls, browser = _install_fake_playwright(monkeypatch, {
        "title": "Rewritten",
        "meta": {"description": "A rewritten page."},
        "dom_text": "Hi",
        "census_raw": dict(_RAW_CENSUS),
        "page_height": 1200,
    })

    result = await capture_html(_HTML_IN, timeout_s=30)

    assert isinstance(result, WebsiteCapture)
    # No address exists for a string-rendered page, and the capture says so.
    assert result.url == result.final_url == REVISION_URL == "about:revision"

    # The document is SET, never navigated to: one pass per viewport, in
    # order, each with the caller's timeout in ms and the load wait.
    assert not [c for c in calls if c[0] == "goto"]
    set_calls = [c for c in calls if c[0] == "set_content"]
    assert [c[1] for c in set_calls] == [1440, 390]
    assert all(c[2] == _HTML_IN for c in set_calls)
    assert all(c[3] == 30_000 and c[4] == "load" for c in set_calls)

    # The same evidence bundle a URL capture produces, per viewport.
    assert result.title == "Rewritten"
    assert result.dom_text == "Hi"
    assert result.meta["description"] == "A rewritten page."
    assert result.screenshot_desktop == b"png-1440"
    assert result.screenshot_mobile == b"png-390"
    context_calls = [c for c in calls if c[0] == "new_context"]
    assert context_calls[1][1].get("is_mobile") is True

    # The style census runs and normalizes through the shared machinery.
    census = result.style_census
    assert census["fonts"]["families"][0]["family"] == "Space Grotesk"
    assert census["color"]["text"][0]["value"] == "#101418"
    assert census["spacing"]["base_unit_px"] == 8

    assert browser.closed


async def test_capture_html_installs_the_abort_route_before_the_document_loads(monkeypatch):
    calls, _browser = _install_fake_playwright(monkeypatch, {"dom_text": "Hi"})

    await capture_html(_HTML_IN)

    # One catch-all route per context, and always before the document is set:
    # a route installed after set_content would let the page's resources race
    # out to the network during the load.
    route_calls = [c for c in calls if c[0] == "route"]
    assert [c[1] for c in route_calls] == [1440, 390]
    assert all(c[2] == "**/*" for c in route_calls)
    ordered = [c[0] for c in calls if c[0] in ("route", "set_content")]
    assert ordered == ["route", "set_content", "route", "set_content"]

    # The handler itself: an external request is aborted — beacon or dead CDN
    # alike — while a data: URI (which never leaves the page) continues.
    handler = route_calls[0][3]
    external = _FakeInterceptedRoute("https://cdn.example/lib.js")
    await handler(external)
    assert external.aborted and not external.continued

    inline = _FakeInterceptedRoute("data:image/svg+xml;base64,PHN2Zz48L3N2Zz4=")
    await handler(inline)
    assert inline.continued and not inline.aborted


# ---------------------------------------------------------------------------
# generate_revision fixtures: a checked page, its critique, its design brief
# ---------------------------------------------------------------------------

DESKTOP = b"original-desktop-screenshot"

ORIGINAL_CRITIQUE = {
    "overall_score": 58,
    "page_takeaway": "A tool that builds web pages.",
    "dimensions": [
        {
            "key": "hierarchy",
            "score": 55,
            "findings": [
                {
                    "severity": "major",
                    "region": "hero headline",
                    "quote": "Build faster",
                    "why": "The claim says nothing concrete.",
                    "fix": 'Replace the hero headline with "Ship your first web app this weekend".',
                },
                {
                    "severity": "minor",
                    "region": "second section",
                    "quote": "",
                    "why": "The section order buries the proof.",
                    "fix": "Move the customer results section directly under the hero.",
                },
            ],
            "strengths": ["The single green button stands out above the fold."],
        },
        {
            "key": "design",
            "score": 48,
            "findings": [
                {
                    "severity": "major",
                    "region": "border-radius",
                    "quote": "radius values: 2px, 4px, 6px, 10px, 12px, 24px",
                    "why": "Six radii is no system.",
                    "fix": "Use 8px for cards and 999px for pills; remove the other radius values.",
                }
            ],
            "strengths": ["The near-black text color reads well."],
        },
        {"key": "copy", "score": 70, "findings": [], "strengths": ["The no-card promise is clear."]},
    ],
}

DNA = {
    "design_md": "# Example — design brief\n\n*calm paper ledger*\n\n## Palette\n| Hex | Name | Role |",
    "tokens": {"theme": "light"},
}

REFERENCE_CENSUS = {
    "fonts": {"families": [{"family": "Suisse Intl", "count": 131}]},
    "text": {"letter_spacing": {"body": [{"value": "-0.011em", "count": 120}]}},
    "shape": {"border_radius": [{"value": "6px", "count": 18}]},
}


def _capture(**overrides) -> WebsiteCapture:
    fields = dict(
        url="https://example.com",
        final_url="https://example.com/",
        title="Example — build faster",
        dom_text="Build faster. Trusted by 40 teams. $29 per month. Start a free run today.",
        meta={"og:title": "Example"},
        screenshot_desktop=DESKTOP,
        screenshot_mobile=b"original-mobile-screenshot",
        style_census={},
    )
    fields.update(overrides)
    return WebsiteCapture(**fields)


def _reference() -> WebsiteCapture:
    return WebsiteCapture(
        url="https://benchmark.example",
        final_url="https://benchmark.example/",
        title="Benchmark — the bar",
        dom_text="The page the founder wants to stand beside.",
        meta={},
        screenshot_desktop=b"reference-desktop",
        screenshot_mobile=b"reference-mobile",
        style_census=REFERENCE_CENSUS,
    )


def _verdict(
    overall: int,
    *,
    fix: str = "Tighten the hero to one sentence.",
    strength: str = "The gold button owns the action.",
) -> CritiqueResult:
    return CritiqueResult(
        overall_score=overall,
        page_takeaway="A tool that builds pages.",
        dimensions=[
            CriticDimension(
                key="hierarchy",
                score=overall,
                findings=[
                    CriticFinding(
                        severity="major",
                        region="hero headline",
                        quote="Build things",
                        why="Still says nothing concrete.",
                        fix=fix,
                    )
                ],
                strengths=[strength],
            ),
            CriticDimension(key="design", score=max(overall - 5, 0), findings=[], strengths=[]),
        ],
    )


def _doc(n: int) -> str:
    return (
        f'<!doctype html>\n<html lang="en"><head><title>Round {n}</title></head>'
        f"<body><main>Round {n}</main></body></html>"
    )


def _render_of(html: str) -> WebsiteCapture:
    return WebsiteCapture(
        url=REVISION_URL,
        final_url=REVISION_URL,
        title="Rendered revision",
        dom_text="rendered text",
        meta={},
        screenshot_desktop=b"render:" + html.encode()[-40:],
        screenshot_mobile=b"render-mobile",
        style_census={},
    )


class _FakeVision:
    def __init__(self, replies: list):
        self.replies = list(replies)
        self.calls: list[SimpleNamespace] = []
        self.probe = None  # optional: sampled at call time, recorded per call

    async def __call__(
        self,
        prompt,
        images,
        *,
        media_type="image/png",
        system=None,
        temperature=0.3,
        max_tokens=4096,
    ):
        self.calls.append(
            SimpleNamespace(
                prompt=prompt,
                images=list(images),
                max_tokens=max_tokens,
                inside_stage=self.probe() if self.probe else None,
            )
        )
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return reply


class _FakeCaptureHtml:
    def __init__(self):
        self.calls: list[str] = []

    async def __call__(self, html: str, *, timeout_s: int = 45) -> WebsiteCapture:
        self.calls.append(html)
        return _render_of(html)


class _FakeGauntlet:
    def __init__(self, verdicts: list):
        self.verdicts = list(verdicts)
        self.calls: list[SimpleNamespace] = []

    async def __call__(self, capture, *, reference=None, organization_id=None):
        self.calls.append(
            SimpleNamespace(capture=capture, reference=reference, organization_id=organization_id)
        )
        verdict = self.verdicts.pop(0)
        if isinstance(verdict, Exception):
            raise verdict
        return verdict


def _install(monkeypatch, *, replies: list, verdicts: list):
    vision = _FakeVision(replies)
    render = _FakeCaptureHtml()
    gauntlet = _FakeGauntlet(verdicts)
    monkeypatch.setattr(revise, "llm_vision", vision)
    monkeypatch.setattr(revise, "capture_html", render)
    monkeypatch.setattr(revise, "run_critic_gauntlet", gauntlet)
    return vision, render, gauntlet


# ---------------------------------------------------------------------------
# The loop: stop at target, cap at max_rounds, best round wins
# ---------------------------------------------------------------------------


async def test_the_loop_stops_the_moment_the_target_is_cleared(monkeypatch):
    vision, render, gauntlet = _install(monkeypatch, replies=[_doc(1)], verdicts=[_verdict(80)])
    reference = _reference()

    result = await generate_revision(
        _capture(), ORIGINAL_CRITIQUE, DNA, reference=reference, organization_id="org-9"
    )

    assert isinstance(result, RevisionResult)
    assert len(vision.calls) == 1, "the target was cleared; no second round may run"
    assert render.calls == [_doc(1)], "the generated document is what got rendered"

    # The judge saw the render (not the original), with the same reference.
    judged = gauntlet.calls[0]
    assert judged.capture.screenshot_desktop == _render_of(_doc(1)).screenshot_desktop
    assert judged.reference is reference
    assert judged.organization_id == "org-9"

    assert result.html == _doc(1)
    assert result.best_round == 1
    assert [r.round for r in result.rounds] == [1]
    assert result.rounds[0].overall_score == 80
    assert result.rounds[0].dimension_scores == {"hierarchy": 80, "design": 75}
    assert result.scores_before == {"overall": 58, "hierarchy": 55, "design": 48, "copy": 70}
    assert result.scores_after == {"overall": 80, "hierarchy": 80, "design": 75}
    assert result.critique_after == _verdict(80).model_dump()
    assert result.capture_after.url == REVISION_URL
    assert result.capture_after.screenshot_desktop == _render_of(_doc(1)).screenshot_desktop
    # The paste-ready blocks are the deterministic composition of the
    # ORIGINAL critique — the findings the founder's own tool would fix.
    assert result.fix_prompts == compose_fix_prompts(ORIGINAL_CRITIQUE, DNA)


async def test_the_loop_caps_at_max_rounds_and_carries_each_round_forward(monkeypatch):
    vision, render, _gauntlet = _install(
        monkeypatch,
        replies=[_doc(1), _doc(2), _doc(3)],
        verdicts=[
            _verdict(60, fix="Cut the hero to eight words.", strength="Keep the gray ledger table."),
            _verdict(65, fix="Name the price next to the button."),
            _verdict(70),
        ],
    )

    result = await generate_revision(
        _capture(), ORIGINAL_CRITIQUE, None, max_rounds=3, target_overall=75
    )

    assert len(vision.calls) == 3, "the budget is three rounds, never a fourth"
    assert [r.round for r in result.rounds] == [1, 2, 3]
    assert [r.overall_score for r in result.rounds] == [60, 65, 70]
    assert result.best_round == 3
    assert result.html == _doc(3)
    assert result.scores_after["overall"] == 70, "the cap is honest: below target stays below target"

    # Round 2 revises round 1: the previous HTML rides along, the NEW
    # critique's findings replace the original's, and the new strengths are
    # the preserve list. The evidence is the previous round's render.
    second = vision.calls[1]
    assert _doc(1) in second.prompt, "round 2 never saw the page it was revising"
    assert "Cut the hero to eight words." in second.prompt
    assert "Keep the gray ledger table." in second.prompt
    assert "KEEP WHAT SCORED WELL" in second.prompt
    assert "Ship your first web app this weekend" not in second.prompt, (
        "round 2 was asked to fix the original page instead of round 1's"
    )
    assert second.images == [_render_of(_doc(1)).screenshot_desktop]

    third = vision.calls[2]
    assert _doc(2) in third.prompt
    assert "Name the price next to the button." in third.prompt


async def test_a_regression_stays_on_the_record_but_never_ships_as_the_result(monkeypatch):
    _install(monkeypatch, replies=[_doc(1), _doc(2)], verdicts=[_verdict(70), _verdict(62)])

    result = await generate_revision(
        _capture(), ORIGINAL_CRITIQUE, None, max_rounds=2, target_overall=75
    )

    # Round 2 regressed; round 1 is the result, round 2 is on the record.
    assert result.best_round == 1
    assert result.html == _doc(1)
    assert result.capture_after.screenshot_desktop == _render_of(_doc(1)).screenshot_desktop
    assert result.scores_after["overall"] == 70
    assert result.critique_after["overall_score"] == 70
    assert [r.overall_score for r in result.rounds] == [70, 62], (
        "the regression must be recorded, not erased"
    )


# ---------------------------------------------------------------------------
# The generation prompt: every section, on the wire
# ---------------------------------------------------------------------------


async def test_the_prompt_carries_the_evidence_and_the_discipline(monkeypatch):
    vision, _render, _gauntlet = _install(monkeypatch, replies=[_doc(1)], verdicts=[_verdict(80)])
    page = _capture()

    await generate_revision(page, ORIGINAL_CRITIQUE, DNA, reference=_reference())

    call = vision.calls[0]
    # A whole page rides in the answer — the ceiling is sized for it.
    assert call.max_tokens == 32_000
    assert call.images == [DESKTOP], "round 1's evidence is the original desktop screenshot"

    prompt = call.prompt
    # The page's real words are the only source of facts, and the prompt says
    # what to do when one is missing: **rebuild the section without it.**
    #
    # It used to say "write the placeholder", and three live runs showed what
    # that produces — a Duolingo rewrite whose trust strip was seven bracketed
    # blanks, scored 76 -> 63 with credibility 68 -> 32. A founder cannot
    # publish that, so it is not finished work however honest it is. The
    # placeholder survives only as a last resort for a single fillable value.
    assert page.dom_text in prompt
    assert "only source of facts" in prompt
    assert "never invent" in prompt
    assert "BUILD THE SECTION DIFFERENTLY" in prompt
    assert "A page is allowed to say less" in prompt
    assert "[OWNER: fill in <what>]" in prompt
    assert "never more than twice" in prompt

    # Every finding rides as an instruction, grouped under its dimension,
    # with the measured quote where the finding carries one.
    assert "hierarchy (scored 55/100):" in prompt
    assert 'Replace the hero headline with "Ship your first web app this weekend".' in prompt
    assert "Move the customer results section directly under the hero." in prompt
    assert "radius values: 2px, 4px, 6px, 10px, 12px, 24px" in prompt

    # The strengths are the preserve list.
    assert "The single green button stands out above the fold." in prompt
    assert "The no-card promise is clear." in prompt

    # The design brief rides whole, with the honor-or-replace instruction.
    assert "calm paper ledger" in prompt
    assert "HTML comment" in prompt

    # The reference census is numbers to hit, and the site is named.
    assert "Suisse Intl" in prompt
    assert "-0.011em" in prompt
    assert "Benchmark — the bar" in prompt
    assert "letter-spacing" in prompt

    # The hard requirements: self-contained, responsive, semantic, no jargon
    # in rendered text, and only the document in the answer.
    assert "self-contained" in prompt
    assert "660px" in prompt and "single column" in prompt
    assert "inline-SVG placeholder" in prompt
    assert "None of these words may" in prompt and "ICP" in prompt
    assert '"<!doctype html>"' in prompt and "No prose" in prompt


async def test_without_a_brief_or_reference_those_sections_stay_out(monkeypatch):
    vision, _render, _gauntlet = _install(monkeypatch, replies=[_doc(1)], verdicts=[_verdict(80)])

    await generate_revision(_capture(), ORIGINAL_CRITIQUE, None)

    prompt = vision.calls[0].prompt
    assert "DESIGN BRIEF" not in prompt
    assert "DISCIPLINE TO HIT" not in prompt


# ---------------------------------------------------------------------------
# Failure honesty
# ---------------------------------------------------------------------------


def test_a_fenced_or_prose_trailed_document_still_parses_to_the_document():
    doc = _doc(1)
    assert revise._parse_document(f"```html\n{doc}\n```") == doc
    assert revise._parse_document(doc + "\n\nI hope this helps!") == doc
    assert revise._parse_document("Here is the new page: " + doc) is None
    assert revise._parse_document("<html><body>half a page, no close") is None


async def test_an_unparseable_answer_gets_one_retry_that_names_the_complaint(monkeypatch):
    vision, _render, _gauntlet = _install(
        monkeypatch,
        replies=["Sure! Here is my read of the page and what I would change...", _doc(1)],
        verdicts=[_verdict(80)],
    )

    result = await generate_revision(_capture(), ORIGINAL_CRITIQUE, None)

    assert result.html == _doc(1)
    assert len(vision.calls) == 2, "exactly one retry, no more"
    assert revise._HTML_COMPLAINT not in vision.calls[0].prompt
    assert vision.calls[1].prompt.endswith(revise._HTML_COMPLAINT), (
        "the retry must carry the complaint — a repeat of the question gets "
        "the same wrong answer"
    )


async def test_two_unparseable_answers_are_a_readable_failure(monkeypatch):
    vision, render, gauntlet = _install(
        monkeypatch,
        replies=["prose, not a page", "<html><body>started but never closed"],
        verdicts=[],
    )

    with pytest.raises(RevisionError) as excinfo:
        await generate_revision(_capture(), ORIGINAL_CRITIQUE, None)

    message = str(excinfo.value)
    assert "no revision was produced" in message.lower()
    assert len(vision.calls) == 2
    assert render.calls == [] and gauntlet.calls == [], (
        "nothing unparseable may reach the render or the judges"
    )


async def test_a_judge_failure_after_a_completed_round_returns_the_best_so_far(monkeypatch):
    vision, _render, _gauntlet = _install(
        monkeypatch,
        replies=[_doc(1), _doc(2)],
        verdicts=[_verdict(70), RuntimeError("the model timed out")],
    )

    result = await generate_revision(
        _capture(), ORIGINAL_CRITIQUE, None, max_rounds=3, target_overall=75
    )

    assert result.best_round == 1
    assert result.html == _doc(1)
    assert [r.round for r in result.rounds] == [1], "the rounds record where the loop stopped"
    assert len(vision.calls) == 2, "no round three after the judge failure"


async def test_a_judge_failure_on_round_one_is_a_revision_error(monkeypatch):
    _install(monkeypatch, replies=[_doc(1)], verdicts=[RuntimeError("the model timed out")])

    with pytest.raises(RevisionError) as excinfo:
        await generate_revision(_capture(), ORIGINAL_CRITIQUE, None)

    message = str(excinfo.value)
    assert "could not be reviewed" in message
    assert "no revision was produced" in message.lower()


# ---------------------------------------------------------------------------
# Cost attribution
# ---------------------------------------------------------------------------


async def test_generation_lands_inside_the_website_revision_ledger_stage(monkeypatch):
    entered: list[tuple[str, str | None, str | None]] = []
    inside = {"now": False}

    @contextmanager
    def _recording_usage(stage, simulation_id=None, organization_id=None):
        entered.append((stage, simulation_id, organization_id))
        inside["now"] = True
        try:
            yield
        finally:
            inside["now"] = False

    monkeypatch.setattr(revise, "usage_context", _recording_usage)
    vision, _render, _gauntlet = _install(monkeypatch, replies=[_doc(1)], verdicts=[_verdict(80)])
    vision.probe = lambda: inside["now"]

    await generate_revision(_capture(), ORIGINAL_CRITIQUE, None, organization_id="org-9")

    assert entered == [("website_revision", None, "org-9")]
    assert all(call.inside_stage for call in vision.calls), (
        "a generation call ran outside the ledger stage"
    )


# ---------------------------------------------------------------------------
# compose_fix_prompts: deterministic paste-ready blocks
# ---------------------------------------------------------------------------


def test_fix_prompts_group_per_dimension_with_numbered_instructions():
    prompts = compose_fix_prompts(ORIGINAL_CRITIQUE, None)

    # One block per dimension WITH findings: hierarchy and design, in the
    # critique's order; copy had none and gets none; no brief, no rebuild.
    assert [p["title"] for p in prompts] == ["Fix the reading order", "Fix the look"]
    assert [p["scope"] for p in prompts] == ["hierarchy", "design"]

    hierarchy = prompts[0]["prompt"]
    assert hierarchy.startswith("You are editing my website's code")
    assert "1. hero headline — Replace the hero headline" in hierarchy
    assert "2. second section — Move the customer results section" in hierarchy
    assert hierarchy.endswith("Change nothing else.")
    # The quote rides only where the finding carries one.
    assert '(on the page now: "Build faster")' in hierarchy
    assert hierarchy.count("on the page now") == 1

    design = prompts[1]["prompt"]
    assert "Use 8px for cards and 999px for pills" in design
    assert '(on the page now: "radius values: 2px, 4px, 6px, 10px, 12px, 24px")' in design, (
        "the measured quote is the receipt and must ride in the paste block"
    )


def test_the_rebuild_block_rides_only_when_a_design_brief_exists():
    with_brief = compose_fix_prompts(ORIGINAL_CRITIQUE, DNA)
    assert [p["title"] for p in with_brief] == [
        "Fix the reading order",
        "Fix the look",
        "Rebuild to the design brief",
    ]
    rebuild = with_brief[-1]["prompt"]
    assert "```markdown" in rebuild, "the brief must be fenced for pasting"
    assert "calm paper ledger" in rebuild, "the brief must ride whole"

    for dna in (None, {}, {"design_md": ""}):
        titles = [p["title"] for p in compose_fix_prompts(ORIGINAL_CRITIQUE, dna)]
        assert "Rebuild to the design brief" not in titles


def test_a_critique_with_no_findings_composes_no_prompts():
    empty = {"overall_score": 90, "dimensions": [{"key": "copy", "score": 90, "findings": []}]}
    assert compose_fix_prompts(empty, None) == []


# ---------------------------------------------------------------------------
# Vocabulary: our strings, and everything we compose
# (mechanics mirror test_website_critics.py)
# ---------------------------------------------------------------------------

JARGON = (
    "ICP",
    "variant",
    "A/B",
    "adversarial",
    "cohort",
    "arena",
    "lens",
    "archetype",
    "canonical",
    "valence",
    "simulation",
    "project",
)


def _pattern(word: str) -> re.Pattern[str]:
    return re.compile(rf"\b{re.escape(word)}s?\b", re.IGNORECASE)


def _hits(text: str) -> list[str]:
    return [word for word in JARGON if _pattern(word).search(text)]


def _revise_strings() -> dict[str, str]:
    """Every template string of revise.py that can reach a founder or a page.

    `RENDERED_VOCABULARY_RULE` is excluded the way the critics' rule is: it
    must name the banned words to ban them. `_HARD_REQUIREMENTS` is scanned
    with its rule slot unfilled for the same reason.
    """
    out = {
        "header": revise._HEADER,
        "evidence.first": revise._EVIDENCE_FIRST,
        "evidence.later": revise._EVIDENCE_LATER,
        "section.page_text": revise._PAGE_TEXT_SECTION,
        "section.facts": revise._FACT_RULES,
        "section.findings": revise._FINDINGS_HEADER,
        "section.strengths": revise._STRENGTHS_HEADER,
        "section.previous": revise._PREVIOUS_HTML_SECTION,
        "section.brief": revise._DESIGN_BRIEF_SECTION,
        "section.reference": revise._REFERENCE_SECTION,
        "section.requirements": revise._HARD_REQUIREMENTS,
        "section.answer": revise._ANSWER_FORMAT,
        "complaint": revise._HTML_COMPLAINT,
        "error.unparseable": revise._UNPARSEABLE_ERROR,
        "error.generation": revise._GENERATION_FAILED_ERROR,
        "error.first_judge": revise._FIRST_JUDGE_FAILED_ERROR,
        "fix.context": revise._FIX_CONTEXT_LINE,
        "fix.closing": revise._FIX_CLOSING_LINE,
        "rebuild.title": revise._REBUILD_TITLE,
        "rebuild.context": revise._REBUILD_CONTEXT,
        "rebuild.closing": revise._REBUILD_CLOSING_LINE,
    }
    for key, (title, scope) in revise._FIX_TITLES.items():
        out[f"fix.title.{key}"] = title
        out[f"fix.scope.{key}"] = scope
    return out


def test_no_revise_string_uses_a_word_a_founder_has_to_learn():
    offenders = [
        f'{name}: "{word}" in {text[:60]!r}'
        for name, text in _revise_strings().items()
        for word in _hits(text)
    ]
    assert offenders == []


def test_composed_fix_prompts_are_jargon_clean_end_to_end():
    offenders = [
        f'{entry["title"]}.{field}: {word}'
        for entry in compose_fix_prompts(ORIGINAL_CRITIQUE, DNA)
        for field in ("title", "scope", "prompt")
        for word in _hits(entry[field])
    ]
    assert offenders == []


def test_the_jargon_scan_would_catch_a_regression():
    assert _hits("An adversarial cohort in the arena") == ["adversarial", "cohort", "arena"]
    assert _hits("Simulations") == ["simulation"]
    assert _hits("The founder rewrites the page.") == []
    assert len(_revise_strings()) == 21 + 2 * len(revise._FIX_TITLES)


# ---------------------------------------------------------------------------
# Invented facts: caught, retried, and never allowed to win on score
#
# The regression is live. On 2026-08-22 a fintech revision shipped a page
# claiming SOC 2 Type II, ISO 27001, PCI DSS Level 1 and authorisation by the
# Central Bank of Ireland, none of it in the captured source. The prompt
# forbade exactly that in two separate sections. The gauntlet — which judges a
# screenshot and never sees the source page's facts — scored it *up*.
# ---------------------------------------------------------------------------


def _doc_saying(n: int, body: str) -> str:
    return (
        f'<!doctype html>\n<html lang="en"><head><title>Round {n}</title></head>'
        f"<body><main>{body}</main></body></html>"
    )


#: A badge the founder's page (`_capture().dom_text`) never mentions.
_FORGED = "We are SOC 2 Type II certified and ISO 27001 certified."


async def test_a_clean_page_is_not_retried(monkeypatch):
    vision, _render, _gauntlet = _install(
        monkeypatch, replies=[_doc(1)], verdicts=[_verdict(80)]
    )

    result = await generate_revision(_capture(), ORIGINAL_CRITIQUE, DNA)

    assert len(vision.calls) == 1, "an honest page paid for a retry it did not need"
    assert result.unsupported_claims == []


async def test_an_invented_certification_gets_one_retry_that_names_it(monkeypatch):
    vision, _render, _gauntlet = _install(
        monkeypatch,
        replies=[_doc_saying(1, _FORGED), _doc(1)],
        verdicts=[_verdict(80)],
    )

    result = await generate_revision(_capture(), ORIGINAL_CRITIQUE, DNA)

    assert len(vision.calls) == 2
    complaint = vision.calls[1].prompt
    assert "SOC 2" in complaint and "ISO 27001" in complaint
    assert _FORGED.lower() in complaint.lower(), "the model was not quoted to itself"
    assert "[OWNER: fill in]" in complaint, "the complaint named no correct answer"
    # The retry removed them, so nothing rides out with the page.
    assert result.unsupported_claims == []


async def test_a_fabrication_that_survives_the_retry_rides_out_with_the_page(
    monkeypatch,
):
    """Reported, never silently dropped — the founder is about to publish it."""
    _install(
        monkeypatch,
        replies=[_doc_saying(1, _FORGED), _doc_saying(1, _FORGED)],
        verdicts=[_verdict(80)],
    )

    result = await generate_revision(_capture(), ORIGINAL_CRITIQUE, DNA, max_rounds=1)

    assert result.html, "a flagged page is still worth more than no page"
    assert {c.text for c in result.unsupported_claims} == {"SOC 2", "ISO 27001"}
    assert all(c.kind == "certification" for c in result.unsupported_claims)


async def test_a_retry_that_invents_more_never_replaces_the_answer_it_retried(monkeypatch):
    """The complaint demands a whole-document rewrite, so the rewrite can
    fabricate differently rather than less.

    Round one claims SOC 2 — one forged badge. The retry comes back with ISO
    27001, PCI DSS and HIPAA — three. Accepted on parseability alone, the
    strictly-worse document is the one the founder downloads and publishes, and
    "it came back second" is not a reason to ship more invented badges than the
    answer it replaced. This is the rule `_is_better` already applies between
    rounds, applied inside one.
    """
    _install(
        monkeypatch,
        replies=[
            _doc_saying(1, "We are SOC 2 Type II certified."),
            _doc_saying(
                1, "ISO 27001 certified, PCI DSS Level 1, and HIPAA compliant."
            ),
        ],
        verdicts=[_verdict(80)],
    )

    result = await generate_revision(_capture(), ORIGINAL_CRITIQUE, DNA, max_rounds=1)

    assert "SOC 2" in result.html, "the less-fabricating first document was discarded"
    assert "HIPAA" not in result.html and "PCI DSS" not in result.html
    assert {c.text for c in result.unsupported_claims} == {"SOC 2"}


async def test_a_retry_that_invents_fewer_badges_is_still_the_one_that_ships(monkeypatch):
    """The rule is fewest fabrications, not "keep the first answer" — a retry
    that trades two badges for one is the improvement the retry was bought
    for."""
    _install(
        monkeypatch,
        replies=[
            _doc_saying(1, _FORGED),  # SOC 2 and ISO 27001
            _doc_saying(1, "We are SOC 2 Type II certified."),
        ],
        verdicts=[_verdict(80)],
    )

    result = await generate_revision(_capture(), ORIGINAL_CRITIQUE, DNA, max_rounds=1)

    assert "ISO 27001" not in result.html
    assert {c.text for c in result.unsupported_claims} == {"SOC 2"}


async def test_an_honest_page_beats_a_higher_scoring_fabrication(monkeypatch):
    """The heart of it.

    Round one forges two badges and scores 84 — above the target. Round two is
    clean and scores 78. Ranking on score alone ships the forgery, and "it
    scored six points better" is not an answer a founder can give a regulator.
    """
    _install(
        monkeypatch,
        # round 1: forged, and forged again on the retry — then round 2, clean.
        replies=[_doc_saying(1, _FORGED), _doc_saying(1, _FORGED), _doc(2)],
        verdicts=[_verdict(84), _verdict(78)],
    )

    result = await generate_revision(_capture(), ORIGINAL_CRITIQUE, DNA, max_rounds=2)

    assert len(result.rounds) == 2, (
        "round one cleared the target while forging a badge and the loop stopped "
        "there, so the score the target measured was earned by the fabrication"
    )
    assert result.best_round == 2
    assert result.scores_after["overall"] == 78
    assert "soc 2" not in result.html.lower()
    assert result.unsupported_claims == []
    # Both rounds stay on the record regardless of which one shipped.
    assert [r.overall_score for r in result.rounds] == [84, 78]


async def test_a_price_is_reported_but_does_not_override_the_score(monkeypatch):
    """Only certifications are disqualifying.

    A figure is noisier to detect and far cheaper to be wrong about in either
    direction, so it is reported to the founder and left at that.
    """
    _install(
        monkeypatch,
        replies=[
            _doc_saying(1, "Just $99 a month."),
            _doc_saying(1, "Just $99 a month."),
        ],
        verdicts=[_verdict(84)],
    )

    result = await generate_revision(_capture(), ORIGINAL_CRITIQUE, DNA, max_rounds=2)

    assert len(result.rounds) == 1, "a flagged figure should not cost an extra round"
    assert [c.kind for c in result.unsupported_claims] == ["figure"]
    assert result.unsupported_claims[0].text == "$99"


async def test_claims_are_measured_against_the_founders_page_not_the_last_round(
    monkeypatch,
):
    """Otherwise a fabrication that survives round one becomes its own evidence."""
    _install(
        monkeypatch,
        replies=[
            _doc_saying(1, _FORGED),
            _doc_saying(1, _FORGED),
            _doc_saying(2, _FORGED),
            _doc_saying(2, _FORGED),
        ],
        verdicts=[_verdict(60), _verdict(62)],
    )

    result = await generate_revision(_capture(), ORIGINAL_CRITIQUE, DNA, max_rounds=2)

    # Round two carried round one's HTML in its prompt. If the check read that
    # instead of the capture, the badges would count as supported and vanish.
    assert {c.text for c in result.unsupported_claims} == {"SOC 2", "ISO 27001"}
