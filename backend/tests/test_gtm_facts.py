"""GTM copy may not carry a number the material never contained.

Every fabrication pinned here was sent, or was one download away from being
sent, to a real person. All three builders already forbade this in their
system prompts and all three overrode it — see `gtm/facts.py`.

The precision half matters as much: this copy is meant to be read aloud on a
call, so a checker that replaces "three things to say next" with a placeholder
does more damage than the invention it prevents.
"""
from __future__ import annotations

from pydantic import BaseModel

from app.services.gtm.facts import (
    MISSING_NUMBER,
    count_placeholders,
    scrub_unsourced,
    sourced_numbers,
)

#: What the answer-pack generator was given for the Ledgerline run: the
#: founder's price, and buyers' own words.
MATERIAL = """
PRODUCT: Ledgerline
THE PRODUCT IN THE FOUNDER'S WORDS: $1,200 a month per entity, annual contract.
MEASURED OBJECTIONS, most load-bearing first:
- objection: Monthly cost is too high
  raised by: 8 buyers
  their words: We spend 15-20 hours a month on reconciliation across 3 entities.
"""


class _Row(BaseModel):
    respond: str
    notes: list[str] = []


class _Pack(BaseModel):
    rows: list[_Row]
    battlecards: list[dict] = []


def _scrub(text: str) -> tuple[str, list[str]]:
    pack, replaced = scrub_unsourced(_Pack(rows=[_Row(respond=text)]), MATERIAL)
    return pack.rows[0].respond, replaced


# ── the fabrications that shipped ────────────────────────────────────


def test_the_invented_labour_maths_is_replaced():
    """"If your controller is at $150k a year loaded… costs you about $700…
    pays for itself if it saves you more than 17 hours a month." None of those
    figures is in the material, for a product that has never been sold."""
    text, replaced = _scrub(
        "If your controller is at $150k a year loaded, this costs you about "
        "$700 in labor. It pays for itself if it saves more than 17 hours a month."
    )

    assert "$150k" not in text
    assert "$700" not in text
    assert "17 hours" not in text
    assert text.count(MISSING_NUMBER) == 3
    assert len(replaced) == 3


def test_the_invented_customer_benchmark_is_replaced():
    """"Most controllers we talk to are spending 30-50 hours a month" — a
    pre-launch product talks to no controllers."""
    text, _ = _scrub("Most controllers we talk to spend 30-50 hours a month on this.")

    assert "30-50 hours" not in text
    assert MISSING_NUMBER in text
    assert text.endswith("on this."), "the sentence around it was damaged"


def test_the_invented_in_house_tuning_cost_is_replaced():
    """"the 500 hours it takes to tune an in-house system" — "500" appears
    nowhere in 110,575 characters of source."""
    text, _ = _scrub("You don't pay for the 500 hours it takes to tune an in-house system.")

    assert "500 hours" not in text
    assert MISSING_NUMBER in text


def test_the_twelve_times_wrong_price_is_replaced():
    """"a $3,600/year luxury" — the founder's price is $1,200 a month per
    entity, so this is 12x off. It reached a LinkedIn body."""
    text, _ = _scrub("The difference between a $3,600/year luxury and real relief.")

    assert "$3,600" not in text
    assert MISSING_NUMBER in text


def test_the_unsourced_half_of_a_real_statistic_is_replaced():
    """"catches 80% of attacks. Your CISO wants to know about the other 20%" —
    80 was said by a buyer about their own regex filter; 20 appears nowhere."""
    material = 'their words: our regex filter catches 80% of the obvious ones.'
    pack, _ = scrub_unsourced(
        _Pack(rows=[_Row(respond="It catches 80% of attacks. What about the other 20%?")]),
        material,
    )
    text = pack.rows[0].respond

    assert "80%" in text, "a figure the buyer actually said was removed"
    assert "20%" not in text
    assert text.count(MISSING_NUMBER) == 1


def test_the_invented_time_to_value_is_replaced():
    text, _ = _scrub("Most teams see it visible in 30-60 days.")

    assert "30-60 days" not in text
    assert MISSING_NUMBER in text


def test_an_invented_before_and_after_is_replaced():
    text, _ = _scrub("It turns a 45-minute manual hunt into a 5-minute triage.")

    assert "45-minute" not in text and "5-minute" not in text
    assert text.count(MISSING_NUMBER) == 2


# ── precision: the founder's and the buyers' own numbers survive ─────


def test_the_founders_own_price_survives():
    text, replaced = _scrub("At $1,200 a month per entity, that is the trade.")

    assert "$1,200" in text
    assert replaced == []


def test_a_number_the_buyer_actually_said_survives():
    text, replaced = _scrub("You told us 15-20 hours a month goes to this.")

    assert "15-20 hours" in text
    assert replaced == []


def test_the_same_figure_written_differently_still_counts_as_sourced():
    """$1,200 in the material covers 1200 and 1.2k in the copy."""
    text, replaced = _scrub("That is 1200 a month, or 1.2k if you prefer.")

    assert MISSING_NUMBER not in text
    assert replaced == []


def test_a_meeting_length_is_not_a_claim_about_the_product():
    """Caught by the existing messaging-doc suite, which is the point of it.

    This copy asks for meetings constantly. Scrubbing the ask produces "Can we
    book [TODO: your number]?" — a nonsense blank in the one line that has to
    work — while catching nothing, because a meeting length was never a claim.
    """
    for line in (
        "Can we book 20 minutes?",
        "Happy to grab 15 minutes next week.",
        "Worth a 30-minute call?",
        "Could you spare 10 minutes on Thursday?",
    ):
        text, replaced = _scrub(line)
        assert replaced == [], f"scrubbed a meeting length in: {line}"
        assert text == line


def test_the_meeting_asks_that_were_actually_damaged_in_production():
    """The first exemption anchored on the characters immediately before the
    number, and a live check found it failing on most real outbound copy.
    Every line here was generated and mangled for real; the article in "set up
    **a** 30-minute call" alone defeated it.
    """
    for line in (
        "Would it make sense to set up a 30-minute technical call with your "
        "security lead?",
        "Worth 20 minutes?",
        "If you've got 15 minutes in the next few days, I can show you.",
        "The thing I wanted to show you takes 15 minutes—and it's about your "
        "actual traffic.",
        "Happy to spend 20 minutes next week walking through it.",
        "Worth a 30-minute technical walkthrough?",
        # Found by the second live check, on the medical run.
        "Do you have 15 minutes this week to see if it fits?",
        "Can we spend 30 minutes walking through how your top three denial "
        "types would flow through the system?",
        "Would be worth 20 minutes to see if it matches.",
        "Chartwell's worth 15 minutes.",
    ):
        text, replaced = _scrub(line)
        assert replaced == [], f"scrubbed a meeting ask in: {line}"
        assert text == line


def test_a_duration_must_match_its_unit_not_just_its_digits():
    """The escape a live check found.

    Material holding "8 months" and "12 years" licensed a cold first-touch
    email claiming clinics "bleed 8-12 days waiting on prior auth" — a market
    benchmark nobody measured, assembled from two unrelated numbers. The number
    is not the claim; the number and its unit are.
    """
    material = "their words: it drags on for 8 months, and we have 12 years of history."
    pack, replaced = scrub_unsourced(
        _Pack(rows=[_Row(respond="Most clinics bleed 8-12 days on prior auth.")]),
        material,
    )

    assert "8-12 days" not in pack.rows[0].respond
    assert replaced == ["8-12 days"]


def test_a_duration_the_material_states_with_that_unit_survives():
    """Both ends of a stated range count, and a unit whose name starts with a
    magnitude letter ("8 months") must not be read as eight million."""
    material = "their words: we lose 15-20 hours a month to this, over 8 months."

    for line in ("It costs you 15 hours.", "That is 20 hours gone.", "After 8 months."):
        pack, replaced = scrub_unsourced(_Pack(rows=[_Row(respond=line)]), material)

        assert replaced == [], f"scrubbed a sourced duration in: {line}"
        assert pack.rows[0].respond == line


def test_a_lookback_window_in_a_request_is_not_a_claim():
    """"reply with the worst denial you've seen in the last 6 months" asks a
    question. Scrubbed, it asks for nothing."""
    text, replaced = _scrub(
        "Reply with the worst prior auth denial you've seen in the last 6 months."
    )

    assert replaced == []
    assert "6 months" in text


def test_a_rate_is_always_a_claim_even_when_it_carries_a_booking_verb():
    """The guard that lets the verb list be generous. Nobody books a meeting
    "a month", so "controllers spend 30-50 hours a month" stays checked even
    though "spend" is a booking verb."""
    text, replaced = _scrub("Most controllers spend 30-50 hours a month on this.")

    assert "30-50 hours" not in text
    assert len(replaced) == 1


def test_a_long_duration_is_a_claim_even_when_it_carries_a_booking_verb():
    """Without a size limit, "takes" would exempt "500 hours"."""
    text, replaced = _scrub("Tuning an in-house system takes 500 hours.")

    assert "500 hours" not in text
    assert len(replaced) == 1


def test_a_duration_that_is_a_claim_is_still_caught_next_to_one_that_is_not():
    """The distinction is context, not length — otherwise the exemption above
    would swallow "a 45-minute manual hunt"."""
    text, replaced = _scrub(
        "Can we book 20 minutes? It turns a 45-minute hunt into a 5-minute triage."
    )

    assert "20 minutes" in text
    assert "45-minute" not in text and "5-minute" not in text
    assert len(replaced) == 2


def test_bare_counts_are_left_alone():
    """This copy is read aloud on a call. Replacing "three things" with a
    placeholder does more damage than the invention it prevents."""
    text, replaced = _scrub(
        "There are 3 things to say next, and step 2 is the important one. "
        "We support 24/7 coverage across 5 regions."
    )

    assert replaced == []
    assert text.count(MISSING_NUMBER) == 0


def test_quotes_are_never_reached_because_generated_models_have_none():
    """The boundary that already works. `_Generated` models carry no quote
    field, so the buyers' own words are attached after this runs and can never
    be scrubbed. Asserted on the real models so the property cannot rot.
    """
    from app.services.gtm import answer_pack, outbound

    for model in (answer_pack._Generated, outbound._GeneratedStep):
        assert not any(
            "quote" in name.lower() for name in model.model_fields
        ), f"{model.__name__} gained a quote field; scrubbing would now reach it"


# ── the walk ─────────────────────────────────────────────────────────


def test_every_string_is_reached_including_nested_ones():
    pack, replaced = scrub_unsourced(
        _Pack(
            rows=[_Row(respond="Saves 99 hours.", notes=["Costs $8,400 a year."])],
            battlecards=[{"where_we_win": "We are 40% faster."}],
        ),
        MATERIAL,
    )

    assert MISSING_NUMBER in pack.rows[0].respond
    assert MISSING_NUMBER in pack.rows[0].notes[0]
    assert MISSING_NUMBER in pack.battlecards[0]["where_we_win"]
    assert len(replaced) == 3


def test_the_scrubbed_payload_is_the_same_type():
    pack, _ = scrub_unsourced(_Pack(rows=[_Row(respond="ok")]), MATERIAL)

    assert isinstance(pack, _Pack)


def test_the_sourced_set_reads_the_material():
    values = sourced_numbers(MATERIAL)

    assert "1200" in values
    assert "8" in values
    assert "15" in values and "20" in values


# ── the placeholder counter ──────────────────────────────────────────


def test_the_counter_counts_the_shape_not_two_literals():
    """Artifacts reported `placeholders_to_fill: 0` while carrying four
    different TODOs, which a founder reads as "ready to send"."""
    text = (
        "Down to [TODO: validated time savings] with [TODO: customer name], "
        "against [TODO: benchmark hours saved] and [TODO: entity count]."
    )

    assert count_placeholders(text) == 4


def test_the_counter_still_counts_the_two_it_always_did():
    assert count_placeholders(f"{MISSING_NUMBER} and [TODO: your example]") == 2


def test_copy_with_nothing_to_fill_counts_zero():
    assert count_placeholders("Ready to send.") == 0
    assert count_placeholders("") == 0
