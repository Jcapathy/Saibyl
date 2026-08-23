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
from app.services.intelligence.report_facts import unsourced_figures

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


def test_a_verbatim_buyer_quote_is_not_a_preamble():
    """The evidence sounds exactly like a preamble, because it is first person.

    `REACT_PROMPT` requires "direct quotes from the people in the run" and
    `agent_interview` returns first-person text, so "I'll review it…" is what a
    buyer quote looks like. Unanchored, the rule deleted the quote and left the
    quotation marks standing — three times, since it runs at section write, DB
    write and render.
    """
    prose = (
        "One agency owner put it plainly: \"I'll review it with my co-founder "
        "before we commit.\" That hesitation is the whole finding."
    )

    assert clean_report_output(prose) == prose


def test_a_second_verbatim_quote_shape_survives_too():
    prose = 'A buyer wrote: "I must check whether it exports to Xero." Nobody answered.'

    assert clean_report_output(prose) == prose


def test_a_preamble_line_with_no_period_does_not_swallow_the_table_after_it():
    """`[^.]*` crossed newlines, so a preamble line with no terminal period ran
    to the first "." anywhere — including the one inside a decimal. The
    headline, the header row, the separator row and half the first data row
    went with it, and the section opened on "62 | 80.6% |"."""
    text = (
        "I'll focus on Reddit and Hacker News\n\n"
        "| Platform | Sentiment | Opposed |\n"
        "|---|---|---|\n"
        "| Reddit | -0.62 | 80.6% |\n"
        "| Hacker News | -0.11 | 41.0% |\n\n"
        "Reddit ran the deeper negative."
    )

    cleaned = clean_report_output(text)

    assert cleaned.startswith("| Platform | Sentiment | Opposed |")
    assert "|---|---|---|" in cleaned
    assert "| Reddit | -0.62 | 80.6% |" in cleaned
    assert "I'll focus" not in cleaned, "the preamble line itself must still go"


def test_an_analyst_paragraph_opening_based_on_the_findings_is_not_deleted():
    """Rule 1d was MULTILINE, so `^` matched any line start and DOTALL ran to
    the end of the paragraph. "Based on the…" / "From the…" is ordinary analyst
    prose and a natural opener anywhere in a section; it was deleted whole,
    with no log line and nothing left behind."""
    prose = (
        "## Who reacted how\n\n"
        "Based on the measured findings, the room split into three groups by "
        "round three, and the split held.\n\n"
        "The finance buyer never moved."
    )

    assert clean_report_output(prose) == prose


def test_a_paragraph_opening_from_the_platform_data_keeps_its_heading_off_the_table():
    prose = (
        "## Platform split\n\n"
        "From the platform data, Reddit ran meaningfully more negative than "
        "Hacker News across every round.\n\n"
        "| Platform | Sentiment |\n"
        "|---|---|"
    )

    assert clean_report_output(prose) == prose


def test_a_real_self_referential_preamble_at_the_top_still_goes():
    """The case rule 1d was written for: it sits before the section, and the
    section starts at a heading."""
    text = (
        "I have extensive evidence across five rounds.\n\n"
        "## Reception and Belief\n\nThe room split early."
    )

    cleaned = clean_report_output(text)

    assert cleaned.startswith("## Reception and Belief")
    assert "extensive evidence" not in cleaned


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


#: A correct section — round-by-round arc, measured shares, nothing invented
#: except the one figure that triggers the retry. This is what was replaced by
#: a 38-character stub in a run with a stubbed model.
LONG_SECTION = (
    "## Platform dynamics\n\n"
    "**Twitter/X carried the argument and Reddit never caught up.**\n\n"
    "Twitter/X ran at -0.4653 across the run with 80.56% opposed, against "
    "-0.091 and 41.03% on Reddit. The gap opened in round two and never "
    "closed, and it is the single most decision-relevant number in this "
    "report: the room that argued hardest is the room the launch post was "
    "written for.\n\n"
    "The finance buyer moved first and moved furthest. The engineer who has "
    "to migrate stayed roughly where they started, which is the more useful "
    "signal — they were never the objection, and every round spent answering "
    "them was a round not spent on the client-relationship thread. The agency "
    "owner arrived sceptical, softened in round three, and hardened again "
    "once the tone of the automated reminder was shown.\n\n"
    "**What this predicts.** If the launch post runs as written, the "
    "client-relationship objection carries. Reddit hit -0.35 in the round "
    "where it spread, and nothing in the arc suggests it reverses on its own. "
    "The fix is not more evidence; it is changing who sends the message, "
    "which is the one variable the room reacted to consistently across all "
    "five rounds and both platforms.\n"
)

STUB = "The room turned negative over the run."


@pytest.mark.asyncio
async def test_a_stub_does_not_replace_a_section_just_by_having_fewer_figures(
    monkeypatch,
):
    """The only acceptance test was `survivors >= figures`, which is monotone in
    how much text the rewrite deletes — and the complaint itself offers "remove
    the sentence that depends on it". A 1,000-character correct section came
    back as 38 characters, logged as a successful correction."""
    _install(monkeypatch, [f"ANSWER: {STUB}"])

    with capture_logs() as logs:
        result = await _check(LONG_SECTION)

    assert result == LONG_SECTION
    rejected = next(e for e in logs if e["event"] == "report_figure_retry_too_short")
    assert rejected["after_chars"] == len(STUB)
    assert not any(e["event"] == "report_figures_corrected" for e in logs)


@pytest.mark.asyncio
async def test_a_correction_that_drops_a_sentence_is_still_accepted(monkeypatch):
    """The floor must not reject the ordinary case: the complaint's own remedy
    is to replace the figure or drop the sentence carrying it."""
    trimmed = LONG_SECTION.replace(
        "Reddit hit -0.35 in the round where it spread, and nothing in the "
        "arc suggests it reverses on its own. ",
        "",
    )
    assert trimmed != LONG_SECTION
    _install(monkeypatch, [f"ANSWER: {trimmed}"])

    assert await _check(LONG_SECTION) == trimmed.strip()


@pytest.mark.asyncio
async def test_a_figure_retry_that_hangs_is_bounded(monkeypatch):
    """`llm_complete` has no timeout of its own, and this retry runs on the
    result of both closing calls and all three section answers. A hang here
    strands `markdown_content` NULL with every section row `complete` — the
    incident `_CLOSING_CALL_TIMEOUT_S` was added for, one call later."""
    async def _never_returns_complete(messages, **kwargs):
        await asyncio.sleep(3600)

    monkeypatch.setattr(report_agent, "llm_complete", _never_returns_complete)
    monkeypatch.setattr(report_agent, "_CLOSING_CALL_TIMEOUT_S", 0.05)

    with capture_logs() as logs:
        result = await asyncio.wait_for(_check(INVENTED), timeout=5)

    assert result == INVENTED, "a wedged retry took the whole report with it"
    failed = next(e for e in logs if e["event"] == "report_figure_retry_failed")
    assert "TimeoutError" in failed["error"]


@pytest.mark.asyncio
async def test_the_invented_figures_are_logged_with_their_values(monkeypatch):
    _install(monkeypatch, [f"ANSWER: {HONEST}"])

    with capture_logs() as logs:
        await _check(INVENTED)

    flagged = next(e for e in logs if e["event"] == "report_section_unsourced_figures")
    assert flagged["section"] == "Platform dynamics"
    assert set(flagged["figures"]) == {"-0.35", "-0.19"}


# ── the checker must be shown what the writer was shown ──────────────
#
# `report_facts` documents its evidence as "precisely what the model was
# shown". Since the message scoreboard was added, `lens_context` has carried
# measured numbers of its own — each version's objective rate, its 95% CI
# bounds and its virality score — and reached the writer through the prompt and
# the checker not at all.

SCOREBOARD_LENS = """
MESSAGE SCOREBOARD — this run tested 2 messages against one shared audience
  - Founder-sender: objective 34.0% (95% CI 12.3%–45.6%, n=25 agents),
    virality 71/100
  - Tool-sender: objective 18.0% (95% CI 6.1%–29.9%, n=25 agents),
    virality 44/100
VERDICT FROM THE MEASUREMENT: the intervals overlap, so the test did not
separate them.
"""

SCOREBOARD_ANSWER = (
    "The founder-sender version hit objective 34.0% "
    "(95% CI 12.3%-45.6%, n=25 agents)."
)


class _Analytics:
    """What `simulation_analytics` returns: a summary line and a data dict."""

    def __init__(self, atype):
        self.summary = f"{atype}: 25 people, 5 rounds, 180 events measured."
        self.data = {
            "quality": {"agents_measured": 25, "events_measured": 180},
            "sentiment_curve": [-0.05, -0.18, -0.41, -0.62, -0.64],
            "stance": {"oppose_pct": 60.0, "support_pct": 24.0},
            "by_platform": {"reddit": {"mean_sentiment": -0.091, "n": 39}},
        }


@pytest.mark.asyncio
async def test_the_scoreboard_the_writer_was_shown_is_evidence_to_the_checker(
    monkeypatch,
):
    """On every multi-version run — the Marketing lens the scoreboard exists for
    — the section that correctly reported the measured comparison was the one
    accused of inventing it, and the retry pushed the model to drop the
    comparison the run was paid for."""
    seen: list[str] = []

    async def _analytics(_sim_id, atype):
        return _Analytics(atype)

    async def _answers(messages, **kwargs):
        return f"ANSWER: ## Versions\n\n{SCOREBOARD_ANSWER}"

    async def _capture(answer, evidence_text, *, section_title, config):
        seen.append(evidence_text)
        return answer

    monkeypatch.setattr(report_agent, "simulation_analytics", _analytics)
    monkeypatch.setattr(report_agent, "llm_complete", _answers)
    monkeypatch.setattr(report_agent, "_figure_checked", _capture)

    await report_agent._run_react_loop(
        report_agent.SectionPlan(title="Versions", research_angles=["which landed"]),
        "00000000-0000-0000-0000-000000000001",
        "will freelancers pay for this",
        ReACTConfig(),
        platforms="reddit",
        lens_context=SCOREBOARD_LENS,
    )

    assert seen, "the section was never figure-checked"
    assert "virality 71/100" in seen[0]
    assert unsourced_figures(seen[0], SCOREBOARD_ANSWER) == [], (
        "the measured version comparison was reported as invented"
    )


# ── the stat card the summary must not invent ────────────────────────


def test_the_stat_cards_do_not_mandate_an_engagement_score():
    """Part D required "| Engagement | <engagement score X.X / 10> |", and
    nothing in the prompt's inputs carries an engagement score — `lens_context`,
    the only place a virality score exists, is not passed to this prompt. So the
    model had to supply the number, in the first table a founder reads, on every
    run."""
    prompt = report_agent.EXECUTIVE_SUMMARY_PROMPT

    assert "| Engagement |" not in prompt
    assert "engagement score" not in prompt.lower().replace(
        "no engagement score", ""
    )
    assert "IMPORTANT for Engagement:" in prompt, (
        "a mandated row removed without a rule against re-adding it comes back"
    )


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
