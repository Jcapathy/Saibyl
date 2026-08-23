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


def test_the_meeting_asks_the_widened_verb_list_still_damaged():
    """The third live check, and the reason the test was turned around.

    Each of these was mangled into "[TODO: your number] next week?" by an
    exemption that asked whether booking language sat around the number: "keep
    it to" was not a verb it knew, and four of these have no verb at all. These
    are subject lines and CTAs — the lines a sequence lives or dies on — and
    because the damage is counted in `placeholders_to_fill` it reads to the
    founder as a fact they forgot to supply rather than copy the tool broke.
    """
    for line in (
        "I'll keep it to 15 minutes.",
        "20 minutes next week?",
        "Would 20 minutes on Tuesday work?",
        "Open to 20 minutes Thursday?",
        "If 15 minutes is easier, say when.",
        "30 minutes with your ops lead would settle it.",
        "Any interest in 15 minutes?",
    ):
        text, replaced = _scrub(line)
        assert replaced == [], f"scrubbed a meeting ask in: {line}"
        assert text == line


def test_a_product_benchmark_is_never_exempted_by_the_meeting_rule():
    """The regression a judge caught before it shipped.

    Fixing the damaged calls-to-action above turned this predicate into
    exempt-by-default, and every one of these — all previously scrubbed —
    walked straight through. None carries a rate, a hyphen or a savings verb,
    so none of the newer guards sees them; only the requirement that an offer
    of time actually *look* like one does.

    The asymmetry is the point. Exempting wrongly puts an invented benchmark in
    a stranger's inbox under the founder's name. Checking wrongly leaves a
    counted, visible placeholder in a CTA. These are not the same mistake.
    """
    for line in (
        "Reviews are done in 20 minutes.",
        "Close the books in 90 minutes.",
        "Setup is 15 minutes.",
        "Onboarding is complete in 30 minutes.",
        "Reconciliation now finishes in 90 minutes instead of days.",
        "Month-end close drops to 2 hours.",
    ):
        text, replaced = _scrub(line)
        assert replaced, f"an invented benchmark was exempted: {line}"
        assert MISSING_NUMBER in text


def test_a_booking_verb_alone_no_longer_exempts_a_product_benchmark():
    """The round-one blocker in its most natural phrasing.

    The exemption list carried the verbs a benchmark is written with — `takes`,
    `got`, `get`, `have`, `spend`, `free up`, `need`, `under`, `no more than` —
    and a hit on any of them returned True unconditionally, before the size
    test, the savings-verb test or the interrogative test ever ran. Every line
    here is a twin of one this file already pins as a fabrication, separated
    from it by a digit or a copula: "Setup **is** 15 minutes." was scrubbed all
    along and "Setup **takes** 15 minutes." was not, and "the close takes
    **900** minutes" was caught only by accident, by being too big to be a
    meeting. With MAX_MEETING_MINUTES at 120, every plausible invented
    benchmark walked through under the founder's name.
    """
    for line in (
        "The month-end close takes 90 minutes of manual work.",
        "Setup takes 15 minutes.",
        "Reconciliation takes 90 minutes a close.",
        "We free up 90 minutes a close for every controller.",
        "You get 45 minutes back per entity.",
        "You have 100 minutes of manual reconciliation every close.",
        "Month-end close takes 2 hours.",
        "Onboarding takes 90 minutes.",
        # The same shape wearing the two quantifiers that sat in the same list.
        "Reviews are done in under 20 minutes.",
        "It needs no more than 30 minutes.",
    ):
        text, replaced = _scrub(line)
        assert replaced, f"a booking verb exempted an invented benchmark: {line}"
        assert MISSING_NUMBER in text


def test_the_asks_those_verbs_used_to_carry_still_survive():
    """The other side of the same trade, which is why the verbs were listed.

    Dropping them from the exemption list is only safe because the shape
    underneath is recognised: an offer to show someone something is a meeting
    whatever noun it is called by, and "20 minutes of your time" is the oldest
    ask in cold copy. Both of these were exempted by `under` and `need` before,
    and both are call-to-action lines.
    """
    for line in (
        "Happy to keep it under 15 minutes.",
        "I'd need 20 minutes of your time.",
        "Let me run you through it in 15 minutes.",
    ):
        text, replaced = _scrub(line)
        assert replaced == [], f"scrubbed a meeting ask in: {line}"
        assert text == line


def test_a_question_counts_wherever_its_mark_falls():
    """The interrogative test read four characters and no further.

    `_SENTENCE_SPLIT` eats the `?`, so the mark is read off the raw text — but
    slicing that text to four characters meant it only counted when it landed
    beside the number. "Any interest in 15 minutes?" passed with its mark at
    index 0; every question with words between the duration and the mark came
    back as "Would [TODO: your number] be useful?" in a subject line, and the
    damage was counted into `placeholders_to_fill` as a fact the founder owed.
    """
    for line in (
        "Would 15 minutes be useful?",
        "Does 15 minutes sound reasonable?",
        "Is 20 minutes worth it to you?",
        "Would 20 minutes help?",
        "Is 30 minutes too much to ask?",
        "Would 30 minutes with the team be useful?",
    ):
        text, replaced = _scrub(line)
        assert replaced == [], f"mangled a question CTA in: {line}"
        assert text == line


def test_a_question_in_the_next_sentence_does_not_launder_the_claim_before_it():
    """Which mark ends *this* clause, not whether one exists nearby. Reading
    forward without that bound would exempt the benchmark on the strength of
    the CTA behind it."""
    text, replaced = _scrub("Setup takes 15 minutes. Would that work?")

    assert replaced == ["15 minutes"]
    assert MISSING_NUMBER in text


def test_a_forward_window_in_a_promise_is_not_a_request():
    """`_WINDOW_BEFORE` matched `next` and `coming` alongside `last` and
    `past`, and returned True before the size, savings-verb and adjective tests
    ran. A window behind reports nothing about the product; a window ahead in a
    declarative sentence is a payback or time-to-value promise for a company
    with no customers to measure it on — the family this file already pins in
    "Most teams see it visible in 30-60 days.", which was caught only because
    it happens to carry no window word.
    """
    for line in (
        "In the next 30 days you'll cut the close in half.",
        "Teams like yours recover the cost in the next 90 days.",
        "You will see it in the coming 6 weeks.",
        "Your next 90 days look like this.",
    ):
        text, replaced = _scrub(line)
        assert replaced, f"a forward window exempted a promise: {line}"
        assert MISSING_NUMBER in text


def test_a_window_that_really_is_asking_still_survives():
    """The lookback twin, and a window ahead inside an actual request."""
    for line in (
        "Reply with the worst prior auth denial you've seen in the last 6 months.",
        "Do you have anything in the next 2 weeks?",
    ):
        text, replaced = _scrub(line)
        assert replaced == [], f"scrubbed a request in: {line}"
        assert text == line


def test_a_duration_bigger_than_a_meeting_is_a_claim_in_any_unit():
    """The size test existed only in hours.

    "Tuning takes 500 hours" was caught and the identical fabrication written
    in minutes or seconds walked through, exempted by its own verb — and
    minutes is the unit a model reaches for when it invents a per-task
    benchmark. A meeting is at most about two hours; nothing longer is an offer
    of someone's time, and nothing measured in seconds ever was.
    """
    for line in (
        "The month-end close takes 900 minutes of manual work.",
        "Reconciliation takes 400 minutes a close.",
        "You have 600 minutes of manual reconciliation every close.",
        "Setup takes 90 seconds.",
        "Manual matching takes 45 seconds per line item.",
    ):
        text, replaced = _scrub(line)
        assert len(replaced) == 1, f"exempted a product claim in: {line}"
        assert MISSING_NUMBER in text


def test_a_rate_written_with_a_slash_or_as_an_adverb_is_still_a_claim():
    """The rate test is what lets the exemption be generous, and it could only
    see "a month" and "per week". "/week", "/month" and "weekly" are the forms
    a savings claim is actually written in — "we free up 2 hours/week" is the
    invented benefit this module opens with, for a product with no customers.
    """
    for line in (
        "We free up 2 hours/week for every controller.",
        "You get 2 hours/week back.",
        "It takes 2 hours weekly to reconcile.",
        "Your team will spend 90 minutes/week chasing this.",
    ):
        text, replaced = _scrub(line)
        assert len(replaced) == 1, f"exempted a rate in: {line}"
        assert MISSING_NUMBER in text


def test_a_savings_verb_makes_a_meeting_sized_duration_a_claim():
    """"We save you 90 minutes" asserts a benefit; it does not ask for time."""
    text, replaced = _scrub("We save you 90 minutes per close.")

    assert replaced == ["90 minutes"]
    assert MISSING_NUMBER in text


def test_a_magnitude_word_is_part_of_the_figure_not_decoration():
    """The three-order-of-magnitude hole.

    The money span stopped at "$3", which keys as 3 — and the material says "3
    entities", so "Teams like yours lose $3 million a year" reported zero
    replacements and the artifact reported zero placeholders. A fabricated
    "$20 billion market" is the cheapest sentence a model can write and the
    most damaging one a cold email can carry.
    """
    for line in (
        "Teams like yours lose $3 million a year to this.",
        "We save mid-market teams $8 million annually.",
        "It is a $20 billion market.",
    ):
        text, replaced = _scrub(line)
        assert len(replaced) == 1, f"a magnitude word was ignored in: {line}"
        assert MISSING_NUMBER in text

    # And it still fails against the founder's own words, not just the room's.
    founder = "Ledgerline is $1,200 a month per entity across 3 entities."
    pack, replaced = scrub_unsourced(
        _Pack(rows=[_Row(respond="Teams like yours lose $3 million a year to this.")]),
        MATERIAL,
        product_material=founder,
    )
    assert replaced == ["$3 million"]


def test_a_figure_the_material_states_with_a_magnitude_word_survives():
    """The other half: "$3 million" in the material licenses copy that says it,
    and copy that writes the same figure in digits."""
    material = "their words: we write off $3 million a year on this."

    for line in ("That is $3 million a year.", "That is $3,000,000 a year."):
        pack, replaced = scrub_unsourced(_Pack(rows=[_Row(respond=line)]), material)

        assert replaced == [], f"scrubbed a sourced figure in: {line}"
        assert pack.rows[0].respond == line


def test_money_and_percentages_spelled_out_are_checked_too():
    """"Cuts 40 percent of the manual work" and "9,000 USD" matched no claim
    branch at all, so nothing ever looked at them."""
    for line in (
        "Cuts 40 percent of the manual work.",
        "They quoted us 9,000 USD for the migration.",
    ):
        text, replaced = _scrub(line)
        assert len(replaced) == 1, f"never checked: {line}"
        assert MISSING_NUMBER in text


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


def test_a_price_a_buyer_got_wrong_is_not_laundered_into_product_prose():
    """The laundering path a live check found still open.

    The material handed to the generator contains the buyers' own words, so a
    number a buyer said counted as sourced. One buyer botched the arithmetic —
    $1,200 per entity per month read as "$3,600/year" — and the messaging doc
    restated it as the product's own per-entity figure, 12x off, in prose.
    A price is a fact about the product, so the founder's words are its only
    authority.
    """
    founder = "Ledgerline is $1,200 a month per entity on an annual contract."
    material = founder + "\n their words: so it's a $3,600/year luxury, really."

    pack, replaced = scrub_unsourced(
        _Pack(rows=[_Row(respond="At $3,600/year per entity, the ROI is clear.")]),
        material,
        product_material=founder,
    )

    assert "$3,600" not in pack.rows[0].respond
    assert replaced == ["$3,600"]


def test_the_founders_own_price_still_survives_that_narrowing():
    founder = "Ledgerline is $1,200 a month per entity on an annual contract."

    pack, replaced = scrub_unsourced(
        _Pack(rows=[_Row(respond="At $1,200 a month per entity, that is the trade.")]),
        founder + "\n their words: too expensive.",
        product_material=founder,
    )

    assert replaced == []
    assert "$1,200" in pack.rows[0].respond


def test_an_inactive_price_guard_says_so():
    """Silence here reads as safety, and it wasn't.

    All three sample runs reached this with no price in the founder-side
    material, so the narrowing was inert on every one while the code looked
    like a live guard. The intake truncates the project description and the ICP
    synthesis drops pricing, so the price survives only in the buyer
    archetypes — which this function must never read. Until that is fixed
    upstream, the log line is the only thing telling the difference between
    "nothing was laundered" and "nothing was watching".
    """
    from structlog.testing import capture_logs

    with capture_logs() as logs:
        scrub_unsourced(
            _Pack(rows=[_Row(respond="It costs $500.")]),
            MATERIAL,
            product_material="Basecrate gives backend teams a database branch.",
        )

    entry = next(e for e in logs if e["event"] == "gtm_price_narrowing_inactive")
    assert entry["reason"] == "founder material states no price"


def test_an_engaged_price_guard_is_silent():
    from structlog.testing import capture_logs

    with capture_logs() as logs:
        scrub_unsourced(
            _Pack(rows=[_Row(respond="At $1,200 a month.")]),
            MATERIAL,
            product_material="Ledgerline is $1,200 a month per entity.",
        )

    assert not [e for e in logs if e["event"] == "gtm_price_narrowing_inactive"]


def test_money_falls_back_to_the_whole_material_when_no_price_was_stated():
    """Narrowing to founder material that names no price would blank every
    money figure in the document — a worse trade than the rare laundered one.
    """
    pack, replaced = scrub_unsourced(
        _Pack(rows=[_Row(respond="They quoted us $9,000 for the migration.")]),
        "their words: they quoted us $9,000 for the migration.",
        product_material="Ledgerline closes the books for multi-entity teams.",
    )

    assert replaced == []
    assert "$9,000" in pack.rows[0].respond


def test_a_currency_word_with_no_figure_does_not_engage_the_narrowing():
    """The guard engaged and empty, which is worse than the guard off.

    The narrowing was gated on `_HAS_CURRENCY`, which matches a bare "$" or the
    word USD with no digit required. A product summary of exactly the shape the
    ICP synthesizer is prompted to write — one or two sentences on what the
    product is — names a currency and no price often enough: "Priced in USD on
    annual contracts", "reconciles ledgers in USD, EUR and GBP". `prices` then
    came back empty, every money span failed against it including the buyers'
    own measured costs, and the `elif` warning branch was skipped, so the one
    signal added specifically so silence would not read as safety never fired.
    """
    from structlog.testing import capture_logs

    product = (
        "Ledgerline turns month-end into a same-day close for multi-entity "
        "finance teams. Priced in USD on annual contracts."
    )

    with capture_logs() as logs:
        pack, replaced = scrub_unsourced(
            _Pack(
                rows=[
                    _Row(
                        respond="You told us NetSuite quoted $9,000 and you "
                        "pay $400 a month today."
                    )
                ]
            ),
            "their words: NetSuite quoted us $9,000 and we pay $400 a month today.",
            product_material=product,
        )

    assert replaced == []
    assert "$9,000" in pack.rows[0].respond and "$400" in pack.rows[0].respond
    entry = next(e for e in logs if e["event"] == "gtm_price_narrowing_inactive")
    assert entry["reason"] == "founder material states no price"


def test_a_price_written_in_words_still_engages_the_narrowing():
    """The other half: "40 dollars a seat" is a stated price, and the check
    that decides whether the founder named one has to read money written the
    way `_CLAIM_SPAN` reads it, not just the symbols."""
    from structlog.testing import capture_logs

    founder = "Basecrate is 40 dollars a seat, billed annually."

    with capture_logs() as logs:
        pack, replaced = scrub_unsourced(
            _Pack(rows=[_Row(respond="At 90 dollars a seat, the ROI is clear.")]),
            MATERIAL + "\n their words: we were quoted 90 dollars a seat.",
            product_material=founder,
        )

    assert replaced == ["90 dollars"]
    assert not [e for e in logs if e["event"] == "gtm_price_narrowing_inactive"]


def test_a_blank_the_model_already_wrote_is_left_alone():
    """Nesting a marker inside a marker corrupts the artifact.

    `count_placeholders` stops at the first `]`, so the outer blank is
    truncated and the rest of its text is orphaned. A live run shipped
    "[TODO: … 2x/week tutoring at [TODO: your number]/hour is [TODO: your
    number]/month …]" — unusable copy the founder cannot even repair, because
    the number that was there is gone.
    """
    written = (
        "[TODO: We can show the ROI math: 2x/week tutoring at $80/hour is "
        "$640/month against our $69/year.]"
    )

    pack, replaced = scrub_unsourced(_Pack(rows=[_Row(respond=written)]), MATERIAL)

    assert pack.rows[0].respond == written
    assert replaced == []
    assert count_placeholders(pack.rows[0].respond) == 1


def test_a_claim_outside_a_blank_is_still_scrubbed_on_the_same_line():
    written = "[TODO: your example] and we save you 40 hours a month."

    pack, replaced = scrub_unsourced(_Pack(rows=[_Row(respond=written)]), MATERIAL)

    assert "[TODO: your example]" in pack.rows[0].respond
    assert "40 hours" not in pack.rows[0].respond
    assert replaced == ["40 hours"]


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
