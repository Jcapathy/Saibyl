"""The vocabulary rule, applied to the artifact that leaves the building.

`frontend/src/test/ia.test.ts` holds every screen to a list of words a founder
should never have to learn. It cannot see this side of the wire, and the gap was
visible in the shipped product: every page said "the people who argue against
you" while the 27-page PDF a founder takes to a board meeting said "adversarial
cohort" on eight of them.

Two scans, because the report has two authors.

**The document.** `build_report_html` is pure, so this renders the whole thing
and reads what a reader reads — text nodes, the attributes that are announced,
and the `content:` strings that print in the running head. Scanning the render
rather than the source is the stronger check: a string that never reaches a page
cannot fail, and a string that reaches one cannot hide behind an `if`.

**The sentences the server composes.** The disclosure, the scoreboard verdict
and the quality caveats are written once in the analysis artifact and rendered
verbatim by the viewer, the print page, the PDF and the JSON export — PRD §4
requires all four to say the same thing. So they are checked at the source,
where fixing one fixes four, rather than at each renderer.

The fixture is not exempt. Its data values stand in for what a real run writes,
and a fixture that says "cohort" where a real objection label would not is a
scan of the easy half. The one place discipline vocabulary is *allowed* to enter
the fixture is a value the server itself writes as an enum — `originating_cohort`
is `"adversarial"` in the database — because rendering that raw is exactly the
leak this file exists to catch.
"""
from __future__ import annotations

import re
from datetime import UTC, datetime

import pytest

from app.services.export.report_document import (
    COHORT_NAMES,
    SUPPORTED_SCHEMA_VERSION,
    DocumentSection,
    ReportDocumentInput,
    build_report_html,
)
from app.services.intelligence.analysis_builder import (
    _adversarial_disclosure,
    _flashpoints,
    _quality,
    _timeline,
)
from app.services.intelligence.analysis_data import (
    DEFAULT_VARIANT_KEY,
    Arena,
    MeasuredEvent,
    RunData,
)
from app.services.intelligence.analysis_schema import SimulationAnalysis
from app.services.intelligence.report_agent import (
    HOUSE_STYLE,
    REPORT_SYSTEM_PROMPT,
    WRITER_PROMPTS,
    _prompt,
)
from app.services.intelligence.variant_scoreboard import build_scoreboard
from tests.analysis_fixtures import (
    REPORT_ID,
    SECTION_MARKDOWN,
    SIMULATION_ID,
    make_analysis,
    make_scoreboard,
)

# ── the list ─────────────────────────────────────────────────────────

#: Mirrors `JARGON` in `frontend/src/test/ia.test.ts`. Two lists rather than one
#: is the "two sources of truth" class, and it is accepted here only because the
#: alternative is a build step that reads TypeScript from pytest. The mirror is
#: asserted by eye at review time; the cost of drift is a word this side keeps
#: and the frontend drops, which is a smaller failure than either list being
#: absent.
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
    # `s?` because the plural is the form that ships. `\bsimulation\b` does not
    # match "Simulations", and that hole let the word survive a green frontend
    # run until somebody screenshotted the sidebar.
    return re.compile(rf"\b{re.escape(word)}s?\b", re.IGNORECASE)


def _hits(text: str) -> list[str]:
    return [word for word in JARGON if _pattern(word).search(text)]


# ── what a reader actually reads ─────────────────────────────────────

_TAG = re.compile(r"<[^>]+>")
_STYLE = re.compile(r"<style\b[^>]*>(.*?)</style>", re.DOTALL | re.IGNORECASE)
_SVG = re.compile(r"<svg\b.*?</svg>", re.DOTALL | re.IGNORECASE)
_CSS_CONTENT = re.compile(r"content:\s*\"([^\"]*)\"")
_SPOKEN_ATTR = re.compile(r"\b(?:alt|title|aria-label)\s*=\s*\"([^\"]*)\"")
_ENTITY = re.compile(r"&[a-zA-Z]+;|&#\d+;")


def visible_text(html: str) -> list[str]:
    """Every run of text the reader sees, from the page and from the margins.

    SVG is read for its `<text>` nodes and then removed, so axis labels and
    chart legends are scanned as copy while path data is not mistaken for one.
    The stylesheet is read only for `content:` — that is the running head and
    the page footer, which print on every page and are as much copy as a
    paragraph is.
    """
    out: list[str] = []

    for style in _STYLE.findall(html):
        out.extend(_CSS_CONTENT.findall(style))
    body = _STYLE.sub(" ", html)

    for svg in _SVG.findall(body):
        out.extend(re.findall(r"<text\b[^>]*>([^<]*)</text>", svg))
    body = _SVG.sub(" ", body)

    out.extend(_SPOKEN_ATTR.findall(body))
    out.extend(_TAG.sub("\n", body).split("\n"))

    return [
        cleaned
        for cleaned in (_ENTITY.sub(" ", chunk).strip() for chunk in out)
        if cleaned
    ]


# ── the document under test ──────────────────────────────────────────


def _doc(analysis: SimulationAnalysis) -> ReportDocumentInput:
    """The same input shape `test_report_document.py` builds, one artifact in."""
    return ReportDocumentInput(
        org_name="Northwind Capital",
        simulation_name="Series B positioning test",
        report_title="Predictive intelligence report",
        prediction_goal="Will growth-stage buyers switch off what they use today?",
        generated_at=datetime(2026, 8, 3, 15, 0, tzinfo=UTC),
        report_id=REPORT_ID,
        simulation_id=SIMULATION_ID,
        platforms=["reddit", "hacker_news", "linkedin"],
        max_rounds=5,
        variants=3,
        agent_count=25,
        run_started="01 August 2026",
        schema_version=SUPPORTED_SCHEMA_VERSION,
        artifact=analysis.model_dump(mode="json"),
        sections=[
            DocumentSection("Executive Summary", "The room turned on cost, not speed."),
            DocumentSection("Platform Dynamics", SECTION_MARKDOWN),
            DocumentSection("Strategic Implications", "Lead with cost. Publish the price."),
        ],
    )


ARTIFACTS = {
    # Every shape of the document, because a section that does not render
    # cannot fail a scan of the render. The two scoreboard cases differ in the
    # copy they emit — a named winner and a refusal are written separately.
    "no scoreboard": lambda: make_analysis(),
    "winner named": lambda: make_analysis(scoreboard=make_scoreboard(with_winner=True)),
    "no winner": lambda: make_analysis(scoreboard=make_scoreboard(with_winner=False)),
}


@pytest.mark.parametrize("shape", sorted(ARTIFACTS))
def test_the_exported_document_uses_no_word_a_founder_has_to_learn(shape):
    html = build_report_html(_doc(ARTIFACTS[shape]()))
    offenders = [
        f'"{word}" in {chunk!r}'
        for chunk in visible_text(html)
        for word in _hits(chunk)
    ]
    assert offenders == []


def test_shortening_the_group_label_did_not_drop_the_synthetic_disclosure():
    """PRD §4 survives the rename.

    "Incumbent-aligned (synthetic)" carried the word in the chart label itself.
    The replacement is shorter because the row label has no truncation and 104pt
    of room, so the obligation moved to the caption and the callout. This asserts
    it actually arrived there rather than being dropped in the edit.
    """
    html = build_report_html(_doc(make_analysis()))
    cover = html.split('<section class="doc-section" id="contents"', 1)[0]

    assert "synthetic" in cover  # the disclosure callout, on page one
    assert "Both sides are synthetic" in html  # the cohort figure's caption
    assert "Everybody in this run is synthetic" in html  # the method section
    assert COHORT_NAMES["adversarial"] in html
    assert all(len(name) <= 28 for name in COHORT_NAMES.values())


def test_the_scan_can_see_the_page():
    """The canary.

    A `visible_text` that returned nothing would make every assertion above
    pass by finding nothing to check — the vacuous-test failure this codebase
    has shipped three times. So: the scan finds the cover, a figure caption
    from inside an SVG, and the running footer from inside the stylesheet.
    """
    chunks = visible_text(build_report_html(_doc(make_analysis())))
    assert len(chunks) > 100
    joined = "\n".join(chunks)
    assert "Northwind Capital" in joined
    assert "Saibyl · Saido Labs LLC" in joined  # from `content:` in the stylesheet
    assert any("Reddit" == chunk for chunk in chunks)  # an SVG axis label


def test_the_scan_would_fail_if_the_copy_regressed():
    """And the canary's other half: the pattern actually matches.

    Asserting a list is empty proves nothing about the matcher. This feeds it
    the sentence the shipped PDF really carried.
    """
    assert _hits("Adversarial cohort disclosure") == ["adversarial", "cohort"]
    assert _hits("Objective rate by message arena") == ["arena"]
    assert _hits("Measured valence by archetype") == ["archetype", "valence"]
    assert _hits("Simulations") == ["simulation"]  # the plural hole
    assert _hits("A shared audience read every message.") == []


# ── the sentences composed once and rendered four times ──────────────
#
# These run the real composers over a real `RunData` rather than reading the
# fixture's hand-written strings. Scanning the fixture would check a sentence
# somebody typed into a test file against a rule somebody typed into the same
# test file — the shape that has already agreed with a wrong implementation
# three times in this build. The composer is the thing that ships.


def _event(
    event_id: str,
    agent: str,
    *,
    valence: float,
    adversarial: bool = False,
    round_number: int = 1,
    version: str = DEFAULT_VARIANT_KEY,
) -> MeasuredEvent:
    return MeasuredEvent(
        id=event_id,
        agent_id=agent,
        agent_username=agent,
        archetype="Incumbent user" if adversarial else "Growth-stage buyer",
        platform="hacker_news",
        round_number=round_number,
        event_type="post",
        content="Three weeks of migration for a 10% gain is not a trade I can defend.",
        valence=valence,
        stance="oppose" if valence < 0 else "support",
        intensity=0.6,
        intent="adopt" if valence > 0.5 else None,
        is_novel_claim=False,
        objections=["switching-cost"],
        variant=version,
        takeaway="It costs less to switch than to stay.",
        is_adversarial=adversarial,
        adversarial_role="incumbent_power_user" if adversarial else None,
    )


def _run(*, named_competitors: list[str], versions: int) -> RunData:
    """A small run of each shape the composed sentences branch on.

    Two rounds so a turning point can be described, both kinds of agent so the
    disclosure and the mixed-headline caveat are both emitted, and enough
    agents per version that the scoreboard has something to refuse.
    """
    keys = [f"v{i}" for i in range(versions)]
    # Round 2 is markedly worse than round 1 so a turning point is described.
    # Without that the flashpoint list is empty and the scan of its sentence
    # passes by having nothing to read.
    by_round = {1: 0.7, 2: -0.3}
    events = [
        _event(
            f"{key}-b{i}-r{r}", f"buyer-{i}", valence=value, version=key, round_number=r
        )
        for key in keys
        for i in range(6)
        for r, value in by_round.items()
    ] + [
        _event(
            f"{key}-a{i}-r{r}", f"adv-{i}", valence=value - 0.5, adversarial=True,
            version=key, round_number=r,
        )
        for key in keys
        for i in range(4)
        for r, value in by_round.items()
    ]
    return RunData(
        simulation_id="11111111-2222-3333-4444-555555555555",
        organization_id="org-1",
        prediction_goal="Will growth-stage buyers switch off what they use today?",
        max_rounds=2,
        events=events,
        agents_total=10,
        archetypes=["Growth-stage buyer", "Incumbent user"],
        platforms=["hacker_news"],
        events_total=len(events),
        events_measured=len(events) - 2,  # forces the coverage caveat
        measurement_model="claude-haiku-4-5",
        agents_adversarial=4,
        adversarial_archetypes=["Incumbent user"],
        adversarial_roles={"incumbent_power_user": 4},
        adversarial_share_configured=0.4,
        named_competitors=named_competitors,
        lens="marketing" if versions > 1 else "founder",
        founder_stage="pre_launch_positioning",
        objective="book a demo" if versions > 1 else None,
        arenas=[
            Arena(variant_key=key, label=f"Message {key.upper()}", content="Copy.")
            for key in keys
        ]
        if versions > 1
        else [],
    )


#: Every branch the composed sentences take. `named` and `unnamed` are separate
#: because the disclosure writes a different sentence for each, and only one of
#: them was ever covered — the unnamed branch, which is why "the material
#: uploaded to this project" survived the vocabulary migration untouched.
COMPOSED_RUNS = {
    "no competitor named": lambda: _run(named_competitors=[], versions=1),
    "competitor named": lambda: _run(named_competitors=["Parry"], versions=1),
    "several versions": lambda: _run(named_competitors=[], versions=3),
}


def _composed(run: RunData) -> dict[str, str]:
    """Strings the server writes into the artifact and every renderer prints.

    Checked at the composer because the viewer, the print page, the PDF and the
    JSON export all read these verbatim. A fix applied at one renderer leaves
    the other three wrong, which is the shape PRD §4 forbids.
    """
    timeline = _timeline(run)
    out: dict[str, str] = {
        "adversarial.disclosure": _adversarial_disclosure(run).disclosure,
        "quality.caveats": " ".join(
            _quality(run, timeline, overall_n=10).caveats
        ),
        "flashpoint.description": " ".join(
            point.description or "" for point in _flashpoints(run, timeline, [])
        ),
    }
    scoreboard = build_scoreboard(run)
    if scoreboard is not None:
        out["scoreboard.verdict"] = scoreboard.verdict
        out["scoreboard.unpaired_verdict"] = scoreboard.unpaired_verdict
    return out


@pytest.mark.parametrize("shape", sorted(COMPOSED_RUNS))
def test_the_artifacts_composed_sentences_are_written_in_the_same_words(shape):
    composed = _composed(COMPOSED_RUNS[shape]())
    offenders = [
        f'{field}: "{word}" in {text!r}'
        for field, text in composed.items()
        for word in _hits(text)
    ]
    assert offenders == []


# ── the half a scan cannot reach ─────────────────────────────────────


def test_every_writer_prompt_carries_the_vocabulary_rule():
    """The narrative sections are written by a model, so the prompt is the lever.

    A scan of the rendered document cannot see them — they arrive as stored
    markdown and are passed through. What *is* checkable is that every prompt
    reaching the writer carries the substitution table, and that filling one
    without it is impossible rather than merely discouraged.
    """
    for name, template in WRITER_PROMPTS:
        assert "{house_style}" in template, f"{name} does not carry the rule"

    assert HOUSE_STYLE in REPORT_SYSTEM_PROMPT

    # And `_prompt` refuses a template that skipped it, rather than quietly
    # filling the rest — the failure mode that let the report drift in the
    # first place was a rule nothing enforced.
    with pytest.raises(KeyError):
        _prompt("a prompt with no rule in it and a {field}", field="x")


def test_the_vocabulary_rule_names_every_banned_word():
    """The two lists must agree, or the block teaches around the scan.

    `HOUSE_STYLE` is prose a model reads and `JARGON` is a regex list a test
    reads. They are two spellings of one rule, and a word in one and not the
    other is a word the writer is free to use.
    """
    missing = [word for word in JARGON if word.lower() not in HOUSE_STYLE.lower()]
    assert missing == []


def test_every_composed_sentence_was_actually_composed():
    """The canary for the block above: each branch emitted something to scan.

    An empty disclosure or a `None` verdict would pass the scan by carrying no
    words at all, which is the same vacuous pass as an empty file list.
    """
    named = _composed(COMPOSED_RUNS["competitor named"]())
    assert "Parry" in named["adversarial.disclosure"]
    unnamed = _composed(COMPOSED_RUNS["no competitor named"]())
    assert len(unnamed["adversarial.disclosure"]) > 100
    assert unnamed["quality.caveats"].strip()
    assert unnamed["flashpoint.description"].strip()
    versions = _composed(COMPOSED_RUNS["several versions"]())
    assert versions["scoreboard.verdict"].strip()
    assert versions["scoreboard.unpaired_verdict"].strip()
