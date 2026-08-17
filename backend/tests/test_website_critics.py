"""The website critic gauntlet (PRD_V3 §4b): five reviewers, one verdict.

The contract under test:

- Five vision calls, one per reviewer, each blind to the others, each carrying
  the screenshot its rubric judges — the mobile reviewer gets the phone
  screenshot, the other four the desktop one.
- Valid JSON from all five parses into one `CritiqueResult` whose overall
  score is the rounded mean of the five dimension scores, and whose takeaway
  sentence comes from the copy reviewer.
- An unreadable answer gets exactly one nudged retry, then a `CriticError`
  naming the dimension.
- One reviewer failing fails the whole gauntlet — never four dimensions
  presented as five.
- Every call lands inside the `website_critics` ledger stage.
- No template string of ours — errors, keys, labels, rubrics — uses a word a
  founder has to learn, and every prompt instructs the model likewise.

`llm_vision` and `WebsiteCapture` are built in parallel and stood in at the
import boundary, the `test_clearance_api._install_services` idiom: the
stand-ins are seeded before the module under test is imported, so these tests
run whether or not the sibling modules exist yet. `llm_vision` is mocked in
every test regardless — no live calls.
"""
from __future__ import annotations

import json
import re
import sys
import types
from contextlib import contextmanager
from types import SimpleNamespace

import pytest
from pydantic import BaseModel


def _bootstrap():
    """Seed sibling stand-ins, then import the module under test.

    A function rather than module-level statements so every import in this
    file sits in the import block while the seeding still runs first.
    """
    import app.core.llm_client as llm_client_module

    if not hasattr(llm_client_module, "llm_vision"):

        async def llm_vision_placeholder(
            prompt,
            images,
            *,
            media_type="image/png",
            system=None,
            temperature=0.3,
            max_tokens=4096,
        ):
            raise AssertionError("llm_vision must be patched in these tests")

        llm_client_module.llm_vision = llm_vision_placeholder

    try:
        from app.services.website import capture as capture_module
    except ImportError:
        capture_module = types.ModuleType("app.services.website.capture")

        class WebsiteCapture(BaseModel):  # mirrors the sibling contract
            url: str
            final_url: str
            title: str
            dom_text: str
            meta: dict[str, str]
            screenshot_desktop: bytes
            screenshot_mobile: bytes

        capture_module.WebsiteCapture = WebsiteCapture
        sys.modules["app.services.website.capture"] = capture_module

    from app.services.website import critics

    return critics, capture_module.WebsiteCapture


critics, WebsiteCapture = _bootstrap()
CriticError = critics.CriticError
CritiqueResult = critics.CritiqueResult
run_critic_gauntlet = critics.run_critic_gauntlet


# ---------------------------------------------------------------------------
# Fixtures: a captured page and a scriptable vision stand-in
# ---------------------------------------------------------------------------

DESKTOP = b"desktop-screenshot-bytes"
MOBILE = b"mobile-screenshot-bytes"

#: Mean 381 / 5 = 76.2, so a correct rounded mean (76) differs from a
#: truncated one (75) and from any single dimension's score.
SCORES = {"hierarchy": 82, "credibility": 71, "conversion": 64, "copy": 90, "mobile": 74}
TAKEAWAY = "A tool that helps small teams build web apps faster."


def _capture(**overrides) -> WebsiteCapture:
    fields = dict(
        url="https://example.com",
        final_url="https://example.com/",
        title="Example — build faster",
        dom_text="Build faster. Start a free run today. Trusted by 40 teams.",
        meta={"og:title": "Example", "description": "Build faster."},
        screenshot_desktop=DESKTOP,
        screenshot_mobile=MOBILE,
    )
    fields.update(overrides)
    return WebsiteCapture(**fields)


def _payload(key: str) -> str:
    body = {
        "score": SCORES[key],
        "findings": [
            {
                "severity": "major",
                "region": "hero headline",
                "quote": "Build faster",
                "why": "The claim never says what gets built faster, so it lands on no one.",
                "fix": 'Replace the hero headline with "Ship your first web app this weekend".',
            }
        ],
        "strengths": [f"({key}) The single green button stands out above the fold."],
    }
    if key == "copy":
        body["page_takeaway"] = TAKEAWAY
    return json.dumps(body)


_DIMENSION_MARKER = re.compile(r"REVIEW DIMENSION: (\w+)")


def _dimension_of(prompt: str) -> str:
    match = _DIMENSION_MARKER.search(prompt)
    assert match, "a reviewer prompt carried no dimension marker"
    return match.group(1)


class _FakeVision:
    """Stands in for `llm_vision`; scripts one reply queue per dimension.

    A dict value that is an Exception is raised instead of answered. A list
    is consumed front to back, its last entry repeating — so a two-entry list
    scripts a first answer and a retry answer.
    """

    def __init__(self, scripts: dict[str, list[str] | Exception]):
        self.scripts = scripts
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
        dimension = _dimension_of(prompt)
        self.calls.append(
            SimpleNamespace(
                dimension=dimension,
                prompt=prompt,
                images=list(images),
                media_type=media_type,
                inside_stage=self.probe() if self.probe else None,
            )
        )
        script = self.scripts[dimension]
        if isinstance(script, Exception):
            raise script
        return script.pop(0) if len(script) > 1 else script[0]


def _install_vision(monkeypatch, **overrides) -> _FakeVision:
    scripts: dict[str, list[str] | Exception] = {key: [_payload(key)] for key in SCORES}
    scripts.update(overrides)
    fake = _FakeVision(scripts)
    monkeypatch.setattr(critics, "llm_vision", fake)
    return fake


# ---------------------------------------------------------------------------
# Five independent calls, each with its own evidence
# ---------------------------------------------------------------------------


async def test_five_reviews_run_each_with_the_screenshot_its_rubric_judges(monkeypatch):
    fake = _install_vision(monkeypatch)

    await run_critic_gauntlet(_capture())

    assert len(fake.calls) == 5
    by_dim = {call.dimension: call for call in fake.calls}
    assert set(by_dim) == set(SCORES), "a reviewer ran twice or not at all"

    assert by_dim["mobile"].images == [MOBILE], "the mobile reviewer judged the wrong screen"
    for key in ("hierarchy", "credibility", "conversion", "copy"):
        assert by_dim[key].images == [DESKTOP], f"the {key} reviewer judged the wrong screen"

    # The evidence rides with the rubric that needs it.
    assert "og:title" in by_dim["credibility"].prompt, "tags never reached the trust reviewer"
    assert _capture().dom_text in by_dim["copy"].prompt, "the page text never reached the copy reviewer"

    # Blind by construction: no prompt mentions another reviewer's dimension.
    for call in fake.calls:
        others = set(SCORES) - {call.dimension}
        leaked = [o for o in others if f"REVIEW DIMENSION: {o}" in call.prompt]
        assert not leaked, f"{call.dimension} could see {leaked}"

    # And every prompt carries the vocabulary rule verbatim, on the wire.
    for call in fake.calls:
        assert critics.VOCABULARY_RULE in call.prompt


# ---------------------------------------------------------------------------
# Valid answers become one verdict
# ---------------------------------------------------------------------------


async def test_valid_answers_become_one_result_with_the_rounded_mean(monkeypatch):
    _install_vision(monkeypatch)

    result = await run_critic_gauntlet(_capture())

    assert isinstance(result, CritiqueResult)
    assert [d.key for d in result.dimensions] == list(SCORES)
    assert {d.key: d.score for d in result.dimensions} == SCORES
    assert result.overall_score == round(sum(SCORES.values()) / 5) == 76
    assert result.page_takeaway == TAKEAWAY, "the takeaway is the copy reviewer's sentence"

    finding = result.dimensions[0].findings[0]
    assert finding.severity == "major"
    assert finding.quote == "Build faster"
    assert finding.fix.startswith("Replace the hero headline")
    assert all(d.strengths for d in result.dimensions), "a redesign needs to know what to keep"


# ---------------------------------------------------------------------------
# An unreadable answer: one nudged retry, then a named failure
# ---------------------------------------------------------------------------


async def test_an_unreadable_answer_gets_one_nudged_retry_then_fails_naming_the_dimension(
    monkeypatch,
):
    fake = _install_vision(
        monkeypatch, copy=["I looked at the page and it seems fine!", "still not json"]
    )

    with pytest.raises(CriticError) as excinfo:
        await run_critic_gauntlet(_capture())

    assert excinfo.value.dimension == "copy"
    assert "copy" in str(excinfo.value)

    copy_calls = [call for call in fake.calls if call.dimension == "copy"]
    assert len(copy_calls) == 2, "exactly one retry, no more"
    assert "only valid json" not in copy_calls[0].prompt.lower()
    assert "only valid json" in copy_calls[1].prompt.lower(), "the retry carried no nudge"


async def test_a_bad_first_answer_heals_on_the_retry(monkeypatch):
    fake = _install_vision(monkeypatch, copy=["```json\ngarbage", _payload("copy")])

    result = await run_critic_gauntlet(_capture())

    assert result.page_takeaway == TAKEAWAY
    assert len([call for call in fake.calls if call.dimension == "copy"]) == 2
    assert len(fake.calls) == 6, "the other four reviewers were not re-run"


# ---------------------------------------------------------------------------
# Five or nothing
# ---------------------------------------------------------------------------


async def test_one_reviewer_failing_fails_the_whole_gauntlet(monkeypatch):
    _install_vision(monkeypatch, credibility=RuntimeError("the model timed out"))

    with pytest.raises(CriticError) as excinfo:
        await run_critic_gauntlet(_capture())

    assert excinfo.value.dimension == "credibility"
    assert "credibility" in str(excinfo.value), "the failure does not say which review broke"
    assert "the model timed out" in str(excinfo.value), "the failure does not say why"


async def test_an_oversized_screenshot_is_a_readable_failure_before_any_call(monkeypatch):
    fake = _install_vision(monkeypatch)
    big = b"\x89" * 6_000_000  # ~8 MB once encoded, past llm_vision's ~4.5 MB bound

    with pytest.raises(CriticError) as excinfo:
        await run_critic_gauntlet(_capture(screenshot_desktop=big))

    assert excinfo.value.dimension == "hierarchy", "failures surface in presentation order"
    message = str(excinfo.value)
    assert "screenshot" in message and "too large" in message
    assert "8.0 MB" in message and "4.5 MB" in message, "the founder deserves the numbers"
    assert all(call.images == [MOBILE] for call in fake.calls), (
        "an oversized screenshot was sent anyway"
    )


# ---------------------------------------------------------------------------
# Cost attribution
# ---------------------------------------------------------------------------


async def test_every_call_lands_inside_the_website_critics_ledger_stage(monkeypatch):
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

    monkeypatch.setattr(critics, "usage_context", _recording_usage)
    fake = _install_vision(monkeypatch)
    fake.probe = lambda: inside["now"]

    await run_critic_gauntlet(_capture(), organization_id="org-1")

    assert entered == [("website_critics", None, "org-1")]
    assert len(fake.calls) == 5
    assert all(call.inside_stage for call in fake.calls), (
        "a reviewer call ran outside the ledger stage"
    )


# ---------------------------------------------------------------------------
# Vocabulary: our strings, and the rule the prompts carry
# (mechanics mirror tests/test_report_vocabulary.py)
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
    # `s?` because the plural is the form that ships (test_report_vocabulary's
    # lesson: `\bsimulation\b` does not match "Simulations").
    return re.compile(rf"\b{re.escape(word)}s?\b", re.IGNORECASE)


def _hits(text: str) -> list[str]:
    return [word for word in JARGON if _pattern(word).search(text)]


def _rendered_strings() -> dict[str, str]:
    """Every template string of ours that can reach a founder.

    Rubric templates are scanned with their `{review_rules}` slot unfilled, so
    the vocabulary rule — which must name the banned words to ban them — does
    not trip the scan of the strings around it.
    """
    out = {
        "error.too_large": critics._TOO_LARGE_ERROR,
        "error.unreadable": critics._UNREADABLE_ERROR,
        "error.failed": critics._FAILED_ERROR,
        "nudge": critics._JSON_NUDGE,
        "rules": critics._SHARED_RULES,
        "shape.default": critics._JSON_INSTRUCTION,
        "shape.copy": critics._JSON_INSTRUCTION_COPY,
    }
    for critic in critics._CRITICS:
        out[f"key.{critic.key}"] = critic.key
        out[f"label.{critic.key}"] = critic.label
        out[f"template.{critic.key}"] = critic.template
    return out


def test_no_string_of_ours_uses_a_word_a_founder_has_to_learn():
    offenders = [
        f'{name}: "{word}" in {text[:60]!r}'
        for name, text in _rendered_strings().items()
        for word in _hits(text)
    ]
    assert offenders == []


def test_the_scan_would_catch_a_regression():
    """The canary: the matcher matches and the scan has something to read."""
    assert _hits("An adversarial cohort in the arena") == ["adversarial", "cohort", "arena"]
    assert _hits("Simulations") == ["simulation"]  # the plural hole
    assert _hits("The reader sees a page and a person.") == []
    assert len(_rendered_strings()) == 7 + 3 * len(critics._CRITICS)


def test_every_reviewer_prompt_carries_the_vocabulary_rule():
    """The findings are written by a model, so the prompt is the lever."""
    for critic in critics._CRITICS:
        assert "{review_rules}" in critic.template, f"{critic.key} does not carry the rule"

    assert critics.VOCABULARY_RULE in critics._REVIEW_RULES

    # The rule and the scan are two spellings of one list; a word in one and
    # not the other is a word the reviewer is free to use.
    missing = [w for w in JARGON if w.lower() not in critics.VOCABULARY_RULE.lower()]
    assert missing == []

    # And a rubric that skipped the slot is refused, not quietly filled.
    with pytest.raises(KeyError):
        critics._fill("a rubric with no rules and a {title}", title="x")


def test_the_shared_rules_pin_the_evidence_and_scoring_anchors():
    rules = critics._REVIEW_RULES
    assert "Never invent" in rules, "the quote-only-what-you-see rule went missing"
    for anchor in ("90+", "70s", "50s", "below 40"):
        assert anchor in rules, f"the {anchor} scoring anchor went missing"
