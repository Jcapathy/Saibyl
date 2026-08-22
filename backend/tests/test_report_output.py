"""What a founder reads must not be the model talking to itself.

`clean_report_output` runs twice — once before the database write and once
before display — and until 2026-08-22 it had no tests at all. It leaked twice
in one day, in two separate paid reports, both times on the same missing
opener:

    "I need to gather comprehensive evidence before writing this section.
     ## Reception and Belief: What Landed and What Read as Marketing"

The alternation listed `I'll|I will|Let me`. "I need to" was not in it, though
"gather" was already in `_PREAMBLE_VERBS`. One missing opener, and the first
words of a section somebody paid for were the model narrating its own homework.
Both leaked sentences are pinned verbatim below.

The second half covers `_closing_call`, which decides whether a report is
delivered at all when one of its two closing model calls does not return.
"""
from __future__ import annotations

import asyncio

import pytest
from structlog.testing import capture_logs

from app.services.intelligence import report_agent
from app.services.intelligence.report_agent import (
    ReACTConfig,
    _closing_call,
    _figure_checked,
    clean_report_output,
)

# ── the openers, including the two that actually shipped ─────────────


def test_the_opener_that_leaked_into_two_paid_reports():
    leaked = (
        "I need to gather comprehensive evidence before writing this section. "
        "## Reception and Belief: What Landed and What Read as Marketing\n\n"
        "The room split early."
    )

    cleaned = clean_report_output(leaked)

    assert not cleaned.startswith("I need to")
    assert "comprehensive evidence" not in cleaned
    assert cleaned.startswith("## Reception and Belief")
    assert "The room split early." in cleaned


def test_the_other_leaked_opener():
    leaked = (
        "I need to gather comprehensive data before writing this section. "
        "## Reception Arc\n\nBuyers arrived sceptical."
    )

    cleaned = clean_report_output(leaked)

    assert cleaned.startswith("## Reception Arc")
    assert "Buyers arrived sceptical." in cleaned


@pytest.mark.parametrize(
    "opener",
    [
        "I'll",
        "I will",
        "I need to",
        "I'll need to",
        "I should",
        "I must",
        "I want to",
        "I'm going to",
        "I am going to",
        "Let me",
        "Let's",
        "First, I'll",
    ],
)
def test_every_declared_opener_is_stripped(opener):
    """The list is generous on purpose — the guard is the verb, not the opener,
    and one missing entry is all it took last time."""
    text = f"{opener} analyze the run data first. ## Findings\n\nThe result."

    cleaned = clean_report_output(text)

    assert cleaned.startswith("## Findings"), f"{opener!r} survived"


def test_an_opener_through_an_answer_marker_goes_whole():
    text = (
        "I need to review the events, then check the analytics, then write.\n"
        "TOOL: load_events()\n"
        "ANSWER: ## Findings\n\nThe room agreed."
    )

    cleaned = clean_report_output(text)

    assert cleaned.startswith("## Findings")
    assert "TOOL:" not in cleaned
    assert "ANSWER:" not in cleaned


# ── precision: the report's own prose must survive ───────────────────


def test_ordinary_report_prose_is_untouched():
    """The rule fires only on an opener *followed by* a preamble verb, which
    is what keeps it off the document. A report writes about the founder and
    the room in the third person; it never narrates its own process."""
    prose = (
        "## What the room believed\n\n"
        "Buyers should review their reconciliation workflow before they "
        "evaluate a replacement. The founder will want to check the pricing "
        "objection first: it was raised by eight of twenty-five people, and "
        "answering it would let them start on the rest."
    )

    assert clean_report_output(prose) == prose


def test_a_recommendation_addressed_to_the_founder_survives():
    prose = "You should gather three reference customers before you launch."

    assert clean_report_output(prose) == prose


def test_an_opener_without_a_preamble_verb_survives():
    """"I want to be clear" is prose, not a preamble."""
    prose = "I want to be clear about what this measures."

    assert clean_report_output(prose) == prose


# ── the closing calls, and what happens when they do not return ──────


async def _never_returns():
    await asyncio.sleep(3600)


async def _explodes():
    raise RuntimeError("upstream returned 529")


async def _works():
    return "I'll summarise the findings. ## Summary\n\nThe room split."


@pytest.mark.asyncio
async def test_a_closing_call_that_returns_is_cleaned_and_passed_through():
    result = await _closing_call(_works(), what="Executive Summary", report_id="r1")

    assert result is not None
    assert result.startswith("## Summary")


@pytest.mark.asyncio
async def test_a_closing_call_that_raises_gives_back_nothing_rather_than_raising():
    """The sections are already written and already paid for when these run.

    Letting a failed summary propagate is what turned a missing summary into a
    missing report — twice on 2026-08-22, with tens of thousands of characters
    of finished content stranded in `report_sections` and `markdown_content`
    never written.
    """
    result = await _closing_call(_explodes(), what="Executive Summary", report_id="r1")

    assert result is None


@pytest.mark.asyncio
async def test_a_closing_call_that_hangs_is_bounded(monkeypatch):
    """`llm_complete` has no timeout of its own. This is the only bound."""
    monkeypatch.setattr(
        "app.services.intelligence.report_agent._CLOSING_CALL_TIMEOUT_S", 0.05
    )

    result = await asyncio.wait_for(
        _closing_call(_never_returns(), what="conclusion", report_id="r1"),
        timeout=5,
    )

    assert result is None, "a wedged closing call took the whole report with it"


@pytest.mark.asyncio
async def test_a_failed_closing_call_is_logged_at_error_level():
    """It went unnoticed for a day because nothing said so above warning."""
    with capture_logs() as logs:
        await _closing_call(_explodes(), what="Executive Summary", report_id="r-42")

    entry = next(e for e in logs if e["event"] == "report_closing_call_failed")
    assert entry["log_level"] == "error"
    assert entry["report_id"] == "r-42"
    assert entry["what"] == "Executive Summary"
    assert "RuntimeError" in entry["error"]


# ── the figure correction pass ───────────────────────────────────────
#
# A section may not state a figure its own evidence never contained. The rule
# is already in REACT_PROMPT under a heading saying it is not style guidance,
# and two live runs overrode it — see `report_facts` for the numbers.

EVIDENCE = """
[Measured analysis — the only source of numbers for this report]
{"by_platform": {"twitter_x": {"mean_sentiment": -0.4653, "oppose_pct": 80.56},
"reddit": {"mean_sentiment": -0.091, "oppose_pct": 41.03}}, "agents": 25}
"""

HONEST = "Twitter/X ran at -0.4653 with 80.56% opposed; Reddit at -0.091."
INVENTED = "Reddit hit -0.35 while Twitter/X sat at -0.19."


class _FakeComplete:
    """Records calls and replays scripted answers, like the revise tests."""

    def __init__(self, replies):
        self.replies = list(replies)
        self.prompts: list[str] = []

    async def __call__(self, messages, **kwargs):
        self.prompts.append(messages[-1]["content"])
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return reply


def _install(monkeypatch, replies):
    fake = _FakeComplete(replies)
    monkeypatch.setattr(report_agent, "llm_complete", fake)
    return fake


async def _check(answer):
    return await _figure_checked(
        answer, EVIDENCE, section_title="Platform dynamics", config=ReACTConfig()
    )


@pytest.mark.asyncio
async def test_a_section_reporting_measured_figures_is_not_retried(monkeypatch):
    fake = _install(monkeypatch, [])

    result = await _check(HONEST)

    assert result == HONEST
    assert fake.prompts == [], "an honest section paid for a correction it did not need"


@pytest.mark.asyncio
async def test_invented_figures_trigger_one_retry_that_names_them(monkeypatch):
    fake = _install(monkeypatch, [f"ANSWER: {HONEST}"])

    result = await _check(INVENTED)

    assert len(fake.prompts) == 1
    complaint = fake.prompts[0]
    assert "-0.35" in complaint and "-0.19" in complaint
    assert INVENTED in complaint, "the section was not quoted back to itself"
    assert "-0.4653" in complaint, "the retry did not carry the evidence"
    assert result == HONEST


@pytest.mark.asyncio
async def test_a_correction_that_is_no_better_leaves_the_original_standing(
    monkeypatch,
):
    """A section is 800-1500 words of otherwise-good work; trading two invented
    figures for two different ones is not a correction."""
    _install(monkeypatch, ["ANSWER: Reddit hit -0.44 while Twitter/X sat at -0.77."])

    result = await _check(INVENTED)

    assert result == INVENTED


@pytest.mark.asyncio
async def test_a_partial_correction_is_accepted(monkeypatch):
    """Strictly fewer invented figures is an improvement worth keeping."""
    partial = "Reddit hit -0.091 while Twitter/X sat at -0.19."
    _install(monkeypatch, [f"ANSWER: {partial}"])

    result = await _check(INVENTED)

    assert result == partial


@pytest.mark.asyncio
async def test_a_failed_retry_leaves_the_section_intact(monkeypatch):
    _install(monkeypatch, [RuntimeError("upstream 529")])

    result = await _check(INVENTED)

    assert result == INVENTED


@pytest.mark.asyncio
async def test_an_empty_correction_leaves_the_section_intact(monkeypatch):
    _install(monkeypatch, ["ANSWER:   "])

    result = await _check(INVENTED)

    assert result == INVENTED


@pytest.mark.asyncio
async def test_the_invented_figures_are_logged_with_their_values(monkeypatch):
    _install(monkeypatch, [f"ANSWER: {HONEST}"])

    with capture_logs() as logs:
        await _check(INVENTED)

    flagged = next(e for e in logs if e["event"] == "report_section_unsourced_figures")
    assert flagged["section"] == "Platform dynamics"
    assert set(flagged["figures"]) == {"-0.35", "-0.19"}


# ── a section must be written, not echoed ────────────────────────────
#
# One of five paid sections reached a founder as 10,169 characters opening
# `<results>[{'tool': 'simulation_analytics', ...` — no headings, no prose,
# truncated mid-JSON. The loop accepted any non-TOOL response as the finished
# section.


def test_raw_tool_output_is_not_a_section():
    """The exact shape that shipped."""
    echoed = (
        "<results>\n[{'tool': 'simulation_analytics', 'type': "
        "'sentiment_over_time', 'data': {'rounds': [{'round': 1, 'mean': "
        "-0.24}, {'round': 2, 'mean': -0.28}], 'objections_"
    )

    assert not report_agent._looks_like_prose(echoed)


def test_a_bare_json_array_or_object_is_not_a_section():
    assert not report_agent._looks_like_prose('[{"round": 1, "mean": -0.24}]')
    assert not report_agent._looks_like_prose('{"tool": "simulation_analytics"}')


def test_a_written_section_is_prose_even_without_the_answer_marker():
    """Permissive on purpose: a section that ignored the response format is
    still a section, and dropping it would cost the founder more than the
    format violation does."""
    written = (
        "## Reception and Belief\n\n"
        "The room split early. Buyers who arrived with a reconciliation "
        "problem stayed engaged through round three, while the engineers "
        "disengaged after the first pricing post. Sentiment closed at -0.27."
    )

    assert report_agent._looks_like_prose(written)


def test_a_section_quoting_json_inline_is_still_prose():
    """A real section may quote a payload without being one."""
    written = (
        "## What the room measured\n\nThe analysis artifact reports "
        '`{"mean": -0.27}` for the run as a whole, which is the figure every '
        "section below is anchored to. Three buyers disputed it openly."
    )

    assert report_agent._looks_like_prose(written)


def test_an_empty_response_is_not_prose():
    assert not report_agent._looks_like_prose("")
    assert not report_agent._looks_like_prose("   \n  ")
