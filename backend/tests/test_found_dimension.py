"""The ninth dimension: whether a machine can read the page at all.

Every other reader in the gauntlet judges the page a person gets. This one
judges the HTML the server sent, which is what an answering crawler receives.
"""
from __future__ import annotations

from types import SimpleNamespace

from app.services.website.found import FOUND_KEY, machine_dimension

_CLEAN = {
    "crawler_text_chars": 11859,
    "rendered_text_chars": 9845,
    "headline_reaches_the_crawler": True,
    "h1_in_raw_html": 1,
    "structured_data": {"blocks": 1, "types": ["Organization", "SoftwareApplication"]},
    "has_description": True,
    "has_declared_address": True,
    "images_in_raw_html": 4,
    "images_without_alt": 0,
    "answering_crawlers_blocked": [],
    "has_llms_txt": True,
}


def _capture(**overrides) -> SimpleNamespace:
    return SimpleNamespace(machine={**_CLEAN, **overrides})


def _regions(dimension) -> set[str]:
    return {f.region for f in dimension.findings}


def test_a_fully_legible_page_scores_100_and_is_told_what_it_got_right():
    dimension = machine_dimension(_capture())

    assert dimension is not None
    assert dimension.key == FOUND_KEY
    assert dimension.score == 100
    assert dimension.findings == []
    assert dimension.strengths


def test_blocking_the_answering_crawlers_is_the_finding_that_outranks_the_rest():
    """A page nothing is allowed to fetch cannot be cited however good it is."""
    dimension = machine_dimension(_capture(answering_crawlers_blocked=["GPTBot", "ClaudeBot"]))

    finding = next(f for f in dimension.findings if f.region == "crawler access")
    assert finding.severity == "critical"
    assert "GPTBot" in finding.quote
    assert dimension.score == 66


def test_a_page_whose_words_arrive_only_after_javascript_is_told_so():
    """The single-page app that looks finished to its founder and is an empty
    shell to every crawler that answers questions."""
    dimension = machine_dimension(_capture(headline_reaches_the_crawler=False))

    finding = next(f for f in dimension.findings if f.region == "what a crawler receives")
    assert finding.severity == "critical"
    assert "javascript" in finding.why.casefold()


def test_a_page_with_no_headline_at_all_is_not_told_twice():
    """`standard` already reports a missing h1. Reporting it again here under a
    different name would make one defect look like two."""
    dimension = machine_dimension(_capture(headline_reaches_the_crawler=None))

    assert "what a crawler receives" not in _regions(dimension)
    assert dimension.score == 100


def test_no_structured_data_is_a_finding():
    """linear.app, measured 2026-08-30: scores 100 on the visual standard and
    ships none of this."""
    dimension = machine_dimension(_capture(structured_data={"blocks": 0, "types": []}))

    finding = next(f for f in dimension.findings if "structured data" in f.quote)
    assert finding.severity == "major"
    assert dimension.score == 82


def test_images_without_alt_text_are_judged_by_proportion():
    """One unlabelled image in twenty is an oversight; most of them is a page a
    machine and a screen reader both read as partly blank."""
    few = machine_dimension(_capture(images_in_raw_html=20, images_without_alt=1))
    most = machine_dimension(_capture(images_in_raw_html=20, images_without_alt=15))

    assert next(f for f in few.findings if f.region == "images").severity == "minor"
    assert next(f for f in most.findings if f.region == "images").severity == "major"


def test_a_page_with_no_images_is_not_told_about_alt_text():
    dimension = machine_dimension(_capture(images_in_raw_html=0, images_without_alt=0))

    assert "images" not in _regions(dimension)


def test_the_llms_txt_finding_admits_it_is_a_convention_rather_than_a_standard():
    """The codebase's rule on contested claims: say so in the finding, so a
    founder can weigh it rather than treat it as a requirement."""
    dimension = machine_dimension(_capture(has_llms_txt=False))

    finding = next(f for f in dimension.findings if "llms.txt" in f.quote)
    assert finding.severity == "minor"
    assert "convention" in finding.why.casefold()
    assert "standard" in finding.why.casefold()


def test_an_unfetched_llms_txt_produces_no_finding_either_way():
    """None means nobody looked. Reporting a missing file on that basis would
    be the "a zero meaning we did not look" defect wearing a new hat."""
    dimension = machine_dimension(_capture(has_llms_txt=None))

    assert not any("llms.txt" in f.quote for f in dimension.findings)


def test_a_capture_with_no_machine_signals_yields_no_dimension():
    """A pasted-HTML review never made a request, so there is no server
    response to read and no address to resolve robots.txt against. Scoring it
    100 would credit a page for being unmeasurable; scoring it 0 would blame
    the founder for the input they were invited to give."""
    assert machine_dimension(SimpleNamespace(machine={})) is None
    assert machine_dimension(SimpleNamespace()) is None


def test_the_worst_page_floors_at_zero_rather_than_going_negative():
    dimension = machine_dimension(
        _capture(
            answering_crawlers_blocked=["GPTBot", "ClaudeBot"],
            headline_reaches_the_crawler=False,
            structured_data={"blocks": 0, "types": []},
            has_description=False,
            has_declared_address=False,
            images_in_raw_html=10,
            images_without_alt=10,
            has_llms_txt=False,
        )
    )

    assert dimension.score == 0


def test_no_finding_makes_the_founder_learn_an_acronym():
    """A founder has a website, not a discipline. The dimension is "being
    found"; the tags have plain-English names."""
    dimension = machine_dimension(
        _capture(
            structured_data={"blocks": 0, "types": []},
            has_description=False,
            has_declared_address=False,
            has_llms_txt=False,
            answering_crawlers_blocked=["GPTBot"],
            headline_reaches_the_crawler=False,
        )
    )

    prose = " ".join(f"{f.quote} {f.why} {f.fix}" for f in dimension.findings).casefold()
    for jargon in (" aeo", " seo", " geo ", "canonical", "schema.org"):
        assert jargon not in prose, f"the report made the founder learn {jargon!r}"
