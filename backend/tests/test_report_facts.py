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
