"""What a machine sees, as opposed to what a person does.

Every signal here is a count or a structural yes/no. There is no threshold in
the module and there is none asserted here — the question that would ordinarily
want one, *"is enough of this page visible without JavaScript"*, is answered by
asking whether the page's own headline survives into the crawler's HTML.
"""
from __future__ import annotations

from app.services.website.machine import AI_CRAWLERS, read_machine_signals

_SHELL = (
    '<!doctype html><html><head><title>App</title></head>'
    '<body><div id="root"></div><script src="/app.js"></script></body></html>'
)

_SERVED = (
    '<!doctype html><html><head>'
    '<meta name="description" content="Find out what buyers object to.">'
    '<link rel="canonical" href="https://example.com/">'
    '<script type="application/ld+json">'
    '{"@type":"SoftwareApplication","name":"Example"}</script>'
    "</head><body><h1>Find out what buyers will object to</h1>"
    '<img src="a.png" alt="a screenshot"></body></html>'
)


def test_a_client_rendered_page_hides_its_headline_from_the_crawler():
    """The defect this signal exists for. The founder sees a headline; GPTBot
    and ClaudeBot do not run JavaScript and receive an empty div."""
    signals = read_machine_signals(
        raw_html=_SHELL,
        rendered_headline="Find out what buyers will object to",
        rendered_text="Find out what buyers will object to ... the rest of the page",
    )

    assert signals["headline_reaches_the_crawler"] is False
    assert signals["h1_in_raw_html"] == 0


def test_a_served_page_carries_its_headline_to_the_crawler():
    signals = read_machine_signals(
        raw_html=_SERVED,
        rendered_headline="Find out what buyers will object to",
        rendered_text="Find out what buyers will object to",
    )

    assert signals["headline_reaches_the_crawler"] is True
    assert signals["h1_in_raw_html"] == 1


def test_a_headline_split_across_tags_still_counts_as_present():
    """`<h1>Ship <em>faster</em></h1>` is one headline. Matching on the raw
    markup rather than its text would fail a page that carries it perfectly."""
    raw = "<html><body><h1>Ship <em>faster</em> than the others</h1></body></html>"
    signals = read_machine_signals(
        raw_html=raw, rendered_headline="Ship faster than the others"
    )

    assert signals["headline_reaches_the_crawler"] is True


def test_a_page_with_no_headline_abstains_rather_than_failing():
    """A page with no h1 is a finding `standard` already makes. Answering False
    here would report one defect twice under two different names."""
    signals = read_machine_signals(raw_html=_SHELL, rendered_headline="")

    assert signals["headline_reaches_the_crawler"] is None


def test_structured_data_types_are_read_out():
    signals = read_machine_signals(raw_html=_SERVED)

    assert signals["structured_data"]["blocks"] == 1
    assert signals["structured_data"]["types"] == ["SoftwareApplication"]


def test_a_page_with_no_structured_data_says_so():
    """linear.app, measured 2026-08-30: a benchmark design site with none."""
    signals = read_machine_signals(raw_html=_SHELL)

    assert signals["structured_data"] == {"blocks": 0, "types": []}


def test_the_description_and_the_declared_address_are_detected():
    served = read_machine_signals(raw_html=_SERVED)
    shell = read_machine_signals(raw_html=_SHELL)

    assert served["has_description"] is True
    assert served["has_declared_address"] is True
    assert shell["has_description"] is False
    assert shell["has_declared_address"] is False


def test_images_without_alt_text_are_counted():
    raw = '<img src="a.png" alt="fine"><img src="b.png"><img src="c.png" alt="">'
    signals = read_machine_signals(raw_html=raw)

    assert signals["images_in_raw_html"] == 3
    assert signals["images_without_alt"] == 1


# ── robots.txt is grouped, and a substring search gets it wrong ──────────────


def test_a_disallow_belonging_to_another_agent_does_not_block_the_ai_crawlers():
    """The subtle one. `robots.txt` is a list of *groups*: a `Disallow: /` binds
    only to the user-agents named immediately above it. Searching the file for
    "GPTBot" and "Disallow: /" separately reports a site as blocking a crawler
    it welcomes."""
    robots = (
        "User-agent: GPTBot\nAllow: /\n\n"
        "User-agent: BadScraper\nDisallow: /\n"
    )
    signals = read_machine_signals(raw_html=_SERVED, robots_txt=robots)

    assert signals["answering_crawlers_blocked"] == []


def test_a_crawler_disallowed_in_its_own_group_is_reported():
    robots = "User-agent: *\nAllow: /\n\nUser-agent: GPTBot\nDisallow: /\n"
    signals = read_machine_signals(raw_html=_SERVED, robots_txt=robots)

    assert signals["answering_crawlers_blocked"] == ["GPTBot"]


def test_a_wildcard_disallow_blocks_every_answering_crawler():
    """The site that quietly deletes itself from every model's answers."""
    signals = read_machine_signals(raw_html=_SERVED, robots_txt="User-agent: *\nDisallow: /\n")

    assert set(signals["answering_crawlers_blocked"]) == set(AI_CRAWLERS)


def test_several_agents_sharing_one_group_are_all_blocked():
    robots = "User-agent: GPTBot\nUser-agent: ClaudeBot\nDisallow: /\n"
    signals = read_machine_signals(raw_html=_SERVED, robots_txt=robots)

    assert set(signals["answering_crawlers_blocked"]) == {"GPTBot", "ClaudeBot"}


def test_a_partial_disallow_is_not_a_block():
    """`Disallow: /admin` is housekeeping, not an exclusion from search."""
    robots = "User-agent: GPTBot\nDisallow: /admin\nDisallow: /internal\n"
    signals = read_machine_signals(raw_html=_SERVED, robots_txt=robots)

    assert signals["answering_crawlers_blocked"] == []


def test_comments_do_not_confuse_the_parser():
    robots = "# User-agent: GPTBot\n# Disallow: /\nUser-agent: *\nAllow: /\n"
    signals = read_machine_signals(raw_html=_SERVED, robots_txt=robots)

    assert signals["answering_crawlers_blocked"] == []


def test_an_unfetched_llms_txt_is_none_rather_than_absent():
    """A False here would say "this site has no llms.txt". None says "nobody
    looked" — the distinction this codebase has got wrong most often."""
    assert read_machine_signals(raw_html=_SERVED)["has_llms_txt"] is None
    assert read_machine_signals(raw_html=_SERVED, llms_txt_found=False)["has_llms_txt"] is False


def test_an_empty_capture_produces_signals_rather_than_an_exception():
    """A pasted-HTML capture has no server response. It must degrade, not raise."""
    signals = read_machine_signals(raw_html="")

    assert signals["crawler_text_chars"] == 0
    assert signals["headline_reaches_the_crawler"] is None
    assert signals["structured_data"]["blocks"] == 0
