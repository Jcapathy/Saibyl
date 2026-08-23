"""A report may not state a figure its own evidence never contained.

`REACT_PROMPT` already says so, under a heading declaring it is not style
guidance. Two live runs on 2026-08-22 ignored it and produced paid sections
whose numbers contradicted the artifact they came from. Both are pinned here
with their real measured values.

The precision half matters as much as the detection half: a report is dense
with numbers, and a verifier that cries wolf on rounding or on round numbers
would be turned off within a week.
"""
from __future__ import annotations

from app.services.intelligence.report_facts import (
    MAX_FIGURES,
    figure_complaint,
    sourced_values,
    unsourced_figures,
)

#: What the Parry section was actually shown.
PARRY_EVIDENCE = """
[Measured analysis — the only source of numbers for this report]
Run of 25 agents over 3 rounds, 75 events.
{"by_platform": {"twitter_x": {"mean_sentiment": -0.4653, "oppose_pct": 80.56,
"n": 36}, "reddit": {"mean_sentiment": -0.091, "oppose_pct": 41.03, "n": 39}},
"overall": {"mean": -0.27, "ci_low": -0.40, "ci_high": -0.14, "delta": 0.137},
"stance": {"oppose": 60, "neutral": 12, "support": 24}, "buyers": 17,
"engaged": 8}
"""

#: A seeded `measured_findings` blob in the shape `react_tools` really returns:
#: integer-rich, because it carries a count for every objection. The hand-
#: trimmed blobs above have an artificially sparse integer set, and a check
#: that only asks "does this digit appear somewhere" passes everything here.
MEASURED_FINDINGS_EVIDENCE = """
[Measured analysis — the only source of numbers for this report]
25 people, 5 rounds, 180 events measured.
{"quality": {"agents_measured": 25, "events_measured": 180, "posts": 31},
"sentiment_curve": [-0.05, -0.18, -0.41, -0.62, -0.64],
"objections": [{"label": "client relationship", "agent_count": 18,
"first_round_seen": 1}, {"label": "price", "agent_count": 13,
"first_round_seen": 1}, {"label": "migration", "agent_count": 11,
"first_round_seen": 2}, {"label": "tone", "agent_count": 9,
"first_round_seen": 2}, {"label": "trust", "agent_count": 8,
"first_round_seen": 3}, {"label": "support", "agent_count": 6,
"first_round_seen": 3}, {"label": "export", "agent_count": 5,
"first_round_seen": 4}, {"label": "audit", "agent_count": 4,
"first_round_seen": 4}, {"label": "seats", "agent_count": 3,
"first_round_seen": 5}, {"label": "onboarding", "agent_count": 2,
"first_round_seen": 5}], "buyers": 8}
"""

#: The scoreboard block, which `build_lens_context` writes into the prompt with
#: its confidence intervals rendered as en-dashed ranges.
SCOREBOARD_EVIDENCE = """
[Measured analysis — the only source of numbers for this report]
MESSAGE SCOREBOARD — this run tested 2 messages against one shared audience
  - Founder-sender: objective 34.0% (95% CI 12.3%–45.6%, n=25 agents),
    virality 71/100
  - Tool-sender: objective 18.0% (95% CI 6.1%–29.9%, n=25 agents),
    virality 44/100
VERDICT FROM THE MEASUREMENT: the two versions' intervals overlap (12.3%–45.6%
against 6.1%–29.9%), so the test did not separate them.
"""

#: What the Ledgerline section was shown.
LEDGER_EVIDENCE = """
[Measured analysis — the only source of numbers for this report]
25 agents, 3 rounds, 100% coverage.
{"valence": 0.04, "ci_low": -0.15, "ci_high": 0.22, "undecided_pct": 50.67,
"polarization_pct": 46.48, "load_bearing": [12.82, 8.93],
"by_platform": {"reddit": {"active": 13, "support_pct": 30.77},
"twitter_x": {"active": 12, "support_pct": 11.11}}, "buyers": 8,
"time_savings_agents": 2}
"""


def _texts(figures) -> set[str]:
    return {f.text for f in figures}


# ── the fabrications that actually shipped ───────────────────────────


def test_the_inverted_platform_table_is_caught():
    """The worst one. Both figures invented *and the direction reversed*, with
    the section's whole thesis built on the inversion."""
    section = (
        "**Reddit went deeper negative while Twitter/X stayed shallow.**\n\n"
        "| Mean sentiment (overall) | Reddit -0.35 | Twitter/X -0.19 |\n\n"
        "Reddit's threading let adversaries compound the critique."
    )

    found = _texts(unsourced_figures(PARRY_EVIDENCE, section))

    assert "-0.35" in found
    assert "-0.19" in found


def test_the_impossible_cross_platform_count_is_caught():
    """Each agent posts to exactly one platform, so this cannot happen at all."""
    section = (
        "Total people active was ~13 of 25 on Reddit and ~18 of 25 on "
        "Twitter/X. Buyers who engaged on both platforms numbered about 6."
    )

    found = _texts(unsourced_figures(LEDGER_EVIDENCE, section))

    assert any("18 of 25" in text for text in found), (
        "13 and 25 are both measured; 18 is not, and 13+18 exceeds the room"
    )


def test_the_inverted_credibility_table_is_caught():
    """Reported Reddit ~25% vs Twitter/X ~40%; measured support is 30.77% and
    11.11% — reversed, and no claim-level metric exists at all."""
    section = "Claim credibility: Reddit ~25% accept, Twitter/X ~40% accept."

    found = _texts(unsourced_figures(LEDGER_EVIDENCE, section))

    assert {"25%", "40%"} <= found


def test_a_fabricated_subgroup_count_is_caught():
    """"5 of 8 primarily Reddit, 6 of 8 primarily Twitter/X" — 11 of 8."""
    section = "Of 8 total buyers: 5 of 8 leaned Reddit and 6 of 8 leaned Twitter/X."

    found = unsourced_figures(LEDGER_EVIDENCE, section)

    assert any("6 of 8" in f.text for f in found)


def test_a_figure_invented_wholesale_is_caught():
    """"5 of 17 buyers raised time savings" against a measured agent_count of 2."""
    section = "Time savings came up for 5 of 17 buyers."

    assert unsourced_figures(LEDGER_EVIDENCE, section)


# ── precision: measured reporting must pass untouched ────────────────


def test_the_measured_values_themselves_are_never_reported():
    section = (
        "Twitter/X ran meaningfully more negative (-0.4653, 80.56% opposed, "
        "n=36) than Reddit (-0.091, 41.03% opposed, n=39). Overall the room "
        "sat at -0.27 (95% CI -0.40 to -0.14)."
    )

    assert unsourced_figures(PARRY_EVIDENCE, section) == []


def test_rounding_a_measured_value_is_reporting_it_not_inventing_one():
    """-0.4653 written as -0.47, and 80.56% written as 81%."""
    section = "Twitter/X averaged -0.47 with 81% opposed."

    assert unsourced_figures(PARRY_EVIDENCE, section) == []


def test_a_share_may_be_written_as_a_percentage_or_a_proportion():
    evidence = 'Measured: {"support_rate": 0.3077, "n": 39} across the run.'
    section = "Support ran at 30.77% of the room."

    assert unsourced_figures(evidence, section) == []


def test_bare_integers_are_not_treated_as_measurements():
    """A report is thick with round numbers, years and list positions. Flagging
    them would bury a real finding under noise."""
    section = (
        "Round 3 was the turning point. We identify 4 distinct kinds of buyer "
        "below, across 3 rounds in 2026. See section 2 for the breakdown."
    )

    assert unsourced_figures(PARRY_EVIDENCE, section) == []


def test_the_real_minus_sign_and_approximation_marks_are_folded():
    """Models write −0.4653 with U+2212 and ~0.4653 in prose."""
    section = "Twitter/X sat at −0.4653, or ~80.56% opposed."

    assert unsourced_figures(PARRY_EVIDENCE, section) == []


def test_a_confidence_label_is_not_a_share():
    """`95% CI` is the format `REACT_PROMPT` *requires*.

    Read as a percentage it is unsourced in every run, so the check would fire
    on precisely the sections that followed the measurement rules — the worst
    possible false positive.
    """
    section = "The room sat at -0.27 (95% CI -0.40 to -0.14, 25 people)."

    assert unsourced_figures(PARRY_EVIDENCE, section) == []


def test_a_percentage_is_not_licensed_by_an_unrelated_count():
    """The coincidence that hid a real fabrication.

    Checking percentages against every number present means a run of 25 agents
    licenses "25%", 3 rounds licenses "3%", and 75 events licenses "75%". A
    share is only sourced by a value that is itself a share.
    """
    section = "Roughly 25% of the room accepted the claim."

    found = unsourced_figures(PARRY_EVIDENCE, section)

    assert [f.text for f in found] == ["25%"], (
        "the agent count licensed an unrelated percentage"
    )


def test_percentage_checking_is_skipped_when_nothing_is_a_share():
    """No shares in the evidence means no basis to judge one, and guessing
    would report every percentage in the section."""
    evidence = 'Measured: {"events": 75, "agents": 25, "rounds": 3} for this run.'
    section = "About 40% of the room objected."

    assert unsourced_figures(evidence, section) == []


def test_a_decimal_inside_a_percentage_is_not_a_separate_figure():
    """The regex backtracked around its own lookahead and reported "80.5"
    inside "80.56%" — a figure nobody wrote."""
    section = "Twitter/X ran at 80.56% opposed."

    assert unsourced_figures(PARRY_EVIDENCE, section) == []


def test_a_round_by_round_arc_is_not_read_as_five_fabrications():
    """The guard that stopped a range being read as a negative blocked the match
    at the `-`, so "Round 3 -0.41" restarted one character later and the sign
    was read off — reporting a measured -0.41 as an invented +0.41.

    `REACT_PROMPT` demands exactly this prose ("Describe trajectory arcs with
    specific turning points"), so the check fired on the sections that followed
    the measurement rules, and every figure in them.
    """
    section = (
        "The arc is monotonic. Round 1 -0.05, Round 2 -0.18, Round 3 -0.41, "
        "Round 4 -0.62, Round 5 -0.64."
    )

    assert unsourced_figures(MEASURED_FINDINGS_EVIDENCE, section) == []


def test_a_negative_after_a_digit_and_a_space_keeps_its_sign():
    """The narrow form of the above, at the regex."""
    found = _texts(unsourced_figures(MEASURED_FINDINGS_EVIDENCE, "Round 3 -0.41 was the low."))

    assert found == set(), "the sign was read off a measured value"

    invented = _texts(unsourced_figures(MEASURED_FINDINGS_EVIDENCE, "Round 3 -0.37 was the low."))

    assert invented == {"-0.37"}, "and a real fabrication still has its sign"


def test_a_confidence_interval_range_is_not_a_negative_percentage():
    """`_scoreboard_block` writes "(95% CI 12.3%–45.6%, n=25 agents)" itself, and
    `_normalise` folds the en-dash to a hyphen. Read as a sign, the upper bound
    became "-45.6%" — a number nobody wrote, reported to the model as one it
    invented, with a retry telling it to delete a correct measured bound."""
    section = (
        "The founder-sender version hit objective 34.0% "
        "(95% CI 12.3%-45.6%, n=25 agents)."
    )

    assert unsourced_figures(SCOREBOARD_EVIDENCE, section) == []

    # And the same bound cited on its own. This is the half the evidence side
    # of the fix carries: read as a sign, the evidence held -45.6 and never
    # 45.6, so a section quoting the upper bound was reported as inventing it.
    assert unsourced_figures(
        SCOREBOARD_EVIDENCE, "The upper bound of 45.6% is where this could land."
    ) == []


#: Long enough to clear `MIN_EVIDENCE_CHARS`, which silently returns nothing
#: for a section with less evidence than that behind it.
SHARE_EVIDENCE = """
[Measured analysis — the only source of numbers for this report]
25 people, 5 rounds, 180 events measured, 100% coverage.
{"stance": {"support_pct": 35.0, "oppose_pct": 40.0, "neutral_pct": 25.0},
"net_sentiment_pct": -12.0, "n": 25, "rounds": 5}
"""


def test_a_plain_prose_percentage_range_is_not_a_negative_either():
    section = "Between 35-40% of buyers said they would switch."

    assert unsourced_figures(SHARE_EVIDENCE, section) == []


def test_a_percentage_that_really_is_negative_keeps_its_sign():
    """The guard must not eat the minus off a genuine negative share."""
    assert unsourced_figures(SHARE_EVIDENCE, "Net sentiment closed at -12.0%.") == []
    assert _texts(
        unsourced_figures(SHARE_EVIDENCE, "Net sentiment closed at -21.0%.")
    ) == {"-21.0%"}


def test_an_impossible_count_is_caught_on_evidence_that_contains_both_halves():
    """The membership check is nearly inert on real evidence.

    31 and 25 both appear in a seeded findings blob — 31 as a post count, 25 as
    the number of people — so "31 of 25 people" passed on digit membership
    alone. It is impossible whatever the evidence holds, and that is the half
    of the check that does not depend on how sparse the evidence happened to be.
    """
    section = "Total people active was 31 of 25 across the run."

    assert any(
        "31 of 25" in f.text for f in unsourced_figures(MEASURED_FINDINGS_EVIDENCE, section)
    )


def test_another_impossible_count_with_both_halves_present():
    """"11 of 8 buyers" — 11 is a measured objection count and 8 is the buyer
    count, so both halves are sourced and the pair is still impossible."""
    section = "Of the buyers, 11 of 8 leaned towards keeping their current tool."

    assert any(
        "11 of 8" in f.text for f in unsourced_figures(MEASURED_FINDINGS_EVIDENCE, section)
    )


def test_a_possible_count_from_measured_parts_is_left_alone():
    """Counts sharing a denominator may legitimately sum past it: an objection
    count is per objection, and people raise more than one. Flagging that would
    fire on the sections that read the evidence properly."""
    section = (
        "18 of 25 people raised the client relationship, and 13 of 25 raised "
        "the price."
    )

    assert unsourced_figures(MEASURED_FINDINGS_EVIDENCE, section) == []


# ── derived figures: arithmetic on measured values is measurement ────
#
# The checker had no subtraction and no absolute value, so it fired on the one
# sentence shape *three* prompts mandate — `REPORT_SYSTEM_PROMPT` rule 3,
# `CONCLUSION_PROMPT`'s formatting rules, and `EXECUTIVE_SUMMARY_PROMPT` Part
# B's worked example. Each hit spends an Opus call after the section is already
# written and paid for, and the acceptance test (fewer flagged figures, >=60%
# of length) then rewards a rewrite that simply deletes the comparison. The
# founder pays for "declined 0.59 points from -0.05 to -0.64" and receives
# "declined".

#: The seeded shapes as `analysis_schema` really returns them: a headline
#: block with a signed trajectory delta, and the platform split.
DERIVED_EVIDENCE = """
[Measured analysis — the only source of numbers for this report]
25 people, 5 rounds, 180 events measured.
{"headline": {"valence": {"mean": -0.3814, "ci_low": -0.52, "ci_high": -0.24},
"trajectory_delta": -0.44}, "sentiment_curve": [-0.05, -0.18, -0.41, -0.62,
-0.64], "stance": {"oppose_pct": 55.2, "support_pct": 21.0}}
[Measured platform split — the only source of per-platform numbers]
{"platforms": {"reddit": {"mean_valence": -0.62, "oppose_pct": 61.4,
"mean_intensity": 0.7, "n": 39}, "hackernews": {"mean_valence": -0.11,
"oppose_pct": 33.3, "mean_intensity": 0.4, "n": 22}}}
"""


def test_the_executive_summary_prompts_own_worked_example_is_not_a_fabrication():
    """`EXECUTIVE_SUMMARY_PROMPT` Part B, example 3, word for word. 0.51 is in
    no artifact anywhere — it is -0.11 minus -0.62."""
    section = (
        "**Reddit is where the argument happens.** Sentiment hit -0.62 on "
        "Reddit against -0.11 on Hacker News - a 0.51 gap between the two."
    )

    assert unsourced_figures(DERIVED_EVIDENCE, section) == []


def test_a_decline_stated_as_a_magnitude_is_the_measured_delta():
    """`_supported` compared signed Decimals; English puts the sign in the
    verb. -0.44 *is* the evidence's `trajectory_delta`."""
    section = "Sentiment declined 0.44 points across the run."

    assert unsourced_figures(DERIVED_EVIDENCE, section) == []


def test_the_shape_rule_three_mandates_survives():
    """REPORT_SYSTEM_PROMPT rule 3: 'not "sentiment declined" but "sentiment
    declined 0.59 points from -0.05 to -0.64."' — and 0.59 is stated nowhere in
    the evidence."""
    section = (
        "Sentiment declined 0.59 points from -0.05 to -0.64 over five rounds."
    )

    assert unsourced_figures(DERIVED_EVIDENCE, section) == []


def test_a_gap_between_two_measured_shares_is_not_invented():
    section = "Opposition on Reddit (61.4%) ran 28.1 points above Hacker News (33.3%)."

    assert unsourced_figures(DERIVED_EVIDENCE, section) == []


def test_a_gap_between_two_measured_intensities_is_not_invented():
    section = "Reddit's mean intensity of 0.7 ran 0.3 above Hacker News's 0.4."

    assert unsourced_figures(DERIVED_EVIDENCE, section) == []


def test_a_wrong_gap_between_two_correct_values_is_still_caught():
    """The half that makes the escape narrow enough to keep. Both operands are
    measured and correctly reported; the gap between them is not what it says."""
    section = "The gap between Reddit (-0.62) and Hacker News (-0.11) was 0.93 points."

    assert _texts(unsourced_figures(DERIVED_EVIDENCE, section)) == {"0.93"}


def test_a_gap_resting_on_invented_operands_is_not_rescued():
    """An operand must itself be sourced before it can anchor anything.
    Otherwise a model could invent a pair, subtract them, and license all
    three."""
    section = "Reddit sat at -0.35 against Twitter/X at -0.19, a 0.16 gap."

    found = _texts(unsourced_figures(DERIVED_EVIDENCE, section))

    assert {"-0.35", "-0.19", "0.16"} <= found


def test_a_difference_is_only_read_from_the_same_sentence():
    """Differencing every pair in the evidence would license nearly any decimal
    in range: a seeded findings blob holds hundreds of numbers. The mandated
    shape states both operands and their gap in one breath, so that is all this
    reads. -0.62 minus -0.11 is 0.51 — but not here."""
    section = (
        "Reddit ran hot and Hacker News did not. The verdict was a 0.51 shift."
    )

    assert _texts(unsourced_figures(DERIVED_EVIDENCE, section)) == {"0.51"}


def test_the_inverted_platform_table_survives_the_derived_escape():
    """The worst fabrication that shipped, re-checked against the evidence the
    escape was built on. Neither the sign fold nor the difference rule may
    rescue it."""
    section = (
        "**Reddit went deeper negative while Twitter/X stayed shallow.**\n\n"
        "| Mean sentiment (overall) | Reddit -0.35 | Twitter/X -0.19 |\n\n"
        "Reddit's threading let adversaries compound the critique."
    )

    found = _texts(unsourced_figures(PARRY_EVIDENCE, section))

    assert {"-0.35", "-0.19"} <= found


def test_a_thousands_separator_is_typography():
    evidence = 'Measured: {"events": 12500, "agents": 25} in this run.'
    section = "The room produced 12,500.0 scored events."

    assert unsourced_figures(evidence, section) == []


# ── refusing to guess ────────────────────────────────────────────────


def test_a_section_with_no_evidence_reports_nothing():
    """Nothing to check against means everything would be reported, which is
    a different failure from the one this prevents."""
    assert unsourced_figures("", "The room sat at -0.35 with 40% opposed.") == []
    assert unsourced_figures("too short", "-0.35 and 40%") == []


def test_an_empty_section_reports_nothing():
    assert unsourced_figures(PARRY_EVIDENCE, "") == []


def test_findings_are_capped():
    section = " ".join(f"metric -0.{n:03d} recorded" for n in range(101, 160))

    assert len(unsourced_figures(PARRY_EVIDENCE, section)) == MAX_FIGURES


def test_the_same_figure_twice_is_one_finding():
    section = "Reddit hit -0.35 early. By round three Reddit was still -0.35."

    assert len(unsourced_figures(PARRY_EVIDENCE, section)) == 1


# ── the sourced set ──────────────────────────────────────────────────


def test_every_number_in_the_evidence_counts_as_sourced():
    values = sourced_values(PARRY_EVIDENCE)

    assert all(str(v) in {str(x) for x in values} for v in (25, 3, 75))
    assert any(str(v) == "-0.4653" for v in values)
    assert any(str(v) == "80.56" for v in values)


# ── the complaint ────────────────────────────────────────────────────


def test_the_complaint_names_each_figure_and_quotes_the_section_back():
    figures = unsourced_figures(
        PARRY_EVIDENCE, "The table reported Reddit -0.35 against Twitter/X -0.19."
    )
    complaint = figure_complaint(figures)

    for figure in figures:
        assert figure.text in complaint
        assert figure.quote in complaint
    assert "do not estimate one by reading" in complaint
    assert "ANSWER:" in complaint, "the retry must say how to return the section"
