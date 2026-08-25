"""The two measured checks that needed the census extended (2026-08-25).

Both count something the census did not previously collect: how many sections
carry a small upper-case label above their heading, and whether one destination
is reached by several differently-worded actions.

The second is the interesting one. It groups by **where an action goes**, never
by what it appears to mean. Two buttons pointing at one path with different
words are demonstrably the same ask; inferring that "Get started" and "Try free"
are the same intent would be this module guessing, which is the vision
reviewers' job and not a measurement.
"""
from __future__ import annotations

from types import SimpleNamespace

from app.services.website.measured import measure_page


def _capture(census: dict) -> SimpleNamespace:
    return SimpleNamespace(dom_text="", style_census=census)


def _labelled(*, above: int, sections: int) -> dict:
    return {
        "labels": {"total": above, "above_heading": above},
        "structure": {"headings": {"h1": 1}, "images": 2, "sections": sections},
    }


def _acts(*pairs: tuple[str, str | None]) -> dict:
    return {
        "actions": [{"label": label, "where": where} for label, where in pairs],
        "structure": {"headings": {"h1": 1}, "images": 2, "sections": 5},
    }


def _regions(dimension) -> list[str]:
    return [f.region for f in dimension.findings]


# ── Section labels ───────────────────────────────────────────────────────────

def test_a_label_above_every_section_is_a_finding():
    dimension = measure_page(_capture(_labelled(above=9, sections=9)))

    finding = next(f for f in dimension.findings if f.region == "section headings")
    assert "9 small upper-case labels" in finding.quote
    assert "9 sections" in finding.quote
    assert finding.severity == "major"
    assert finding.fix


def test_more_labels_than_sections_reads_as_a_sentence():
    """A card title is a heading too, so labels above headings routinely
    outnumber sections. The first live capture of Saibyl's own page reported
    "14 of 9 sections", which is not a thing anyone can say out loud."""
    dimension = measure_page(_capture(_labelled(above=14, sections=9)))

    finding = next(f for f in dimension.findings if f.region == "section headings")
    assert "14 small upper-case labels sit above a heading" in finding.quote
    assert "of 9 sections" not in finding.quote


def test_using_the_label_sparingly_is_not_a_finding():
    """The device is fine. The rhythm is the defect."""
    dimension = measure_page(_capture(_labelled(above=3, sections=9)))

    assert "section headings" not in _regions(dimension)


def test_a_short_page_is_not_judged_on_label_rhythm():
    """Two labels over three sections is not a template, it is a short page."""
    dimension = measure_page(_capture(_labelled(above=2, sections=3)))

    assert "section headings" not in _regions(dimension)


def test_a_census_without_the_label_fields_is_silent_rather_than_zero():
    """A capture taken before the census collected these has no `labels` key.
    Reading that as "zero labels" would invent a strength, and reading it as a
    finding would invent a defect."""
    dimension = measure_page(
        _capture({"structure": {"headings": {"h1": 1}, "images": 1}})
    )

    assert "section headings" not in _regions(dimension)


# ── One destination, several labels ──────────────────────────────────────────

def test_one_destination_wearing_several_labels_is_reported_with_all_of_them():
    dimension = measure_page(
        _capture(
            _acts(
                ("Start your first run", "/signup"),
                ("Run yours", "/signup"),
                ("Prove it sells", "/signup"),
                ("Start at your stage", "/signup"),
            )
        )
    )

    finding = next(f for f in dimension.findings if f.region == "calls to action")
    assert "4 different labels all go to /signup" in finding.quote
    assert '"Run yours"' in finding.quote
    assert finding.severity == "major"


def test_repeating_one_label_down_the_page_is_not_a_finding():
    """Repetition is the point: a reader a thousand pixels down should not have
    to scroll back. Variation is the defect."""
    dimension = measure_page(
        _capture(
            _acts(
                ("Start your first run", "/signup"),
                ("Start your first run", "/signup"),
                ("Start your first run", "/signup"),
            )
        )
    )

    assert "calls to action" not in _regions(dimension)


def test_the_same_words_pointing_at_different_places_is_not_a_finding():
    """An ordinary page. Grouping by label rather than by destination would
    report this one and miss the real one."""
    dimension = measure_page(
        _capture(_acts(("Learn more", "/pricing"), ("Learn more", "/about")))
    )

    assert "calls to action" not in _regions(dimension)


def test_case_alone_does_not_make_two_labels_different():
    dimension = measure_page(
        _capture(_acts(("Start free", "/signup"), ("START FREE", "/signup")))
    )

    assert "calls to action" not in _regions(dimension)


def test_actions_with_no_destination_are_never_grouped_together():
    """A button carries no path, so nothing is known about where it goes. Three
    unknown destinations are not one destination, and treating them as one would
    report every form on the web."""
    dimension = measure_page(
        _capture(_acts(("Save", None), ("Cancel", None), ("Delete", None)))
    )

    assert "calls to action" not in _regions(dimension)


def test_the_worst_destination_is_the_one_reported():
    """One finding, not one per destination. The founder gets the clearest
    instance rather than a list to triage."""
    dimension = measure_page(
        _capture(
            _acts(
                ("Buy", "/checkout"),
                ("Purchase", "/checkout"),
                ("Sign up", "/signup"),
                ("Get started", "/signup"),
                ("Try it free", "/signup"),
            )
        )
    )

    actions = [f for f in dimension.findings if f.region == "calls to action"]
    assert len(actions) == 1
    assert "/signup" in actions[0].quote
