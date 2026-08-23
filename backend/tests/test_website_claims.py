"""The revision may not claim what the founder's page never claimed.

The regression case is real. On 2026-08-22 a fintech revision delivered a page
asserting SOC 2 Type II, ISO 27001, PCI DSS Level 1, authorisation by the
Central Bank of Ireland and a seven-line fee table — none of it in the captured
source. The generator's prompt forbade exactly that, in two separate sections,
and was overridden anyway. `test_the_ledgerline_page_is_caught` carries the
delivered sentences verbatim.

These tests are as much about **precision** as detection: a false finding costs
a regeneration and then tells a founder they fabricated something they actually
wrote, which is a worse failure than the one being prevented. Roughly half of
what follows asserts that ordinary pages come back clean.
"""
from __future__ import annotations

from app.services.website.claims import (
    MAX_CLAIMS,
    UnsupportedClaim,
    claim_complaint,
    unsupported_claims,
)

# The captured source: a payments page that says nothing about compliance.
_SOURCE = """
Ledgerline closes the books for multi-entity finance teams. Connect your banks,
map your chart of accounts once, and let the ledger reconcile every entity
overnight. Pricing starts at $1,200 a month per entity on an annual contract.
Most teams are live in a week.
"""


def _texts(claims: list[UnsupportedClaim]) -> set[str]:
    return {c.text.lower() for c in claims}


# ── the regression ───────────────────────────────────────────────────


def test_the_ledgerline_page_is_caught():
    """Every fabricated badge from the live failure, in its delivered wording."""
    delivered = """
    <main>
    <section><h2>Security and compliance</h2>
    <p>PCI DSS Level 1 certified (recertified annually). SOC 2 Type II report
    available under NDA. ISO 27001 certified.</p>
    <p>Funds are safeguarded under our authorisation from the Central Bank of
    Ireland. Customer funds are held in segregated accounts at partner banks.</p>
    <p>Data is encrypted at rest with AES-256. Data in transit is protected
    with TLS 1.2 or higher.</p></section>
    </main>
    """

    found = _texts(unsupported_claims(_SOURCE, delivered))

    assert {"pci dss", "soc 2", "iso 27001", "central bank of ireland",
            "aes-256", "tls"} <= found


def test_the_invented_fee_table_is_caught():
    """The same page invented a whole fee schedule."""
    delivered = """
    <table><tr><td>2.9% + 30¢</td><td>2.7% + 5¢</td></tr>
    <tr><td>International cards +1.5%</td><td>Currency conversion +1% spread</td></tr>
    <tr><td>0.25% + 25¢ per payout</td></tr></table>
    """

    found = _texts(unsupported_claims(_SOURCE, delivered))

    assert {"2.9%", "1.5%", "0.25%"} <= found
    assert any("¢" in text for text in found), "the cent amounts went unnoticed"


def test_certifications_are_reported_before_figures():
    """Ordered by what a false one costs. A badge outranks a percentage."""
    delivered = "<p>We are SOC 2 certified and 40% faster.</p>"

    kinds = [c.kind for c in unsupported_claims(_SOURCE, delivered)]

    assert kinds == sorted(kinds, key=lambda k: {"certification": 0, "figure": 1}[k])
    assert kinds[0] == "certification"


# ── precision: the page's own facts are never reported ───────────────


def test_a_badge_the_founder_already_claims_is_not_reported():
    source = "Ledgerline is SOC 2 Type II certified and ISO 27001 certified."
    delivered = "<p>SOC 2 Type II. ISO/IEC 27001.</p>"

    assert unsupported_claims(source, delivered) == []


def test_a_price_restated_from_the_source_is_not_reported():
    """The source states a price once; the page may repeat it anywhere."""
    delivered = """
    <p>$1,200 a month per entity.</p><p>From $1,200/entity/month.</p>
    <aside>$ 1200 per entity</aside>
    """

    assert unsupported_claims(_SOURCE, delivered) == []


def test_thousands_separators_and_trailing_zeros_are_typography():
    source = "Plans start at $1200 and fees are 2.9%."
    delivered = "<p>$1,200.00 and 2.90%</p>"

    assert unsupported_claims(source, delivered) == []


def test_the_social_proof_bar_a_live_revision_invented():
    """What actually shipped, and it was not copied — it was blended.

    The critics illustrated the *shape* of a trust signal with examples: "e.g.
    'Over 500 million learners'", "e.g. '4.7 star from 2.4M reviews'", "'800M+
    downloads'". Every one is marked `e.g.` and asserts nothing.

    The delivered page then read `500M+ downloads worldwide · 4.7 star App
    Store` — a download count no example contained, made by fusing the 500M
    from one illustration with the noun from another. So the failure is not
    transcription; the generator cannot tell an illustration inside a fix
    instruction from a fact it may use, and confabulates from the seed.
    """
    source = (
        "Fernway teaches you a language in three-minute spoken sessions that "
        "fit into idle moments of your day."
    )
    delivered = (
        '<div class="proof-bar"><span>500M+ downloads worldwide</span>'
        "<span>4.7 star App Store from 2.4M reviews</span></div>"
    )

    found = _texts(unsupported_claims(source, delivered))

    assert any("500m+ downloads" in t for t in found)
    assert any("2.4m reviews" in t for t in found), (
        "a review count is always an assertion; nothing on a page lets a "
        "reader total it up"
    )


def test_a_count_a_reader_could_total_from_the_page_is_not_reported():
    """`languages`, `countries` and friends are left out of the scale nouns.

    Duolingo's page carries a ribbon of ~42 language links, so "40+ languages"
    is a true statement its owner can defend — but this module counts digits in
    the source, not list items, so including the noun would report a defensible
    figure as an invention. A miss costs less than an accusation.
    """
    source = "Learn Spanish, French, German, Japanese, Korean and more."
    delivered = "<p>Choose from 40+ languages.</p>"

    assert unsupported_claims(source, delivered) == []


def test_an_idiom_is_not_a_price():
    """"100 cents on the dollar" is a figure of speech.

    `_normalise` folds "<digit> cents" to "<digit>¢" so a page writing "30
    cents" matches a source writing "30¢". That fold turned the idiom into a
    money figure, and the page restating its own source was accused of
    inventing it.
    """
    source = "Sellers keep 100 cents on the dollar of every tip."
    delivered = "<p>You keep 100 cents on the dollar.</p>"

    assert unsupported_claims(source, delivered) == []


def test_the_cents_fold_still_works_for_actual_money():
    source = "We charge 30¢ per payout."
    delivered = "<p>Just 30 cents per payout.</p>"

    assert unsupported_claims(source, delivered) == []


def test_an_accreditation_is_caught_in_either_word_order():
    """The compressed spelling is the rewrite's voice; the spelled-out one is
    how a lab writes it. Matching only the first told a founder who wrote the
    second that they had invented their own accreditation."""
    source = "Chartwell helps clinics submit prior authorisations."

    for phrasing in (
        "<p>We are CAP-accredited.</p>",
        "<p>Our lab is accredited by the CAP.</p>",
        "<p>Accredited by the College of American Pathologists.</p>",
    ):
        found = unsupported_claims(source, phrasing)
        assert any(c.kind == "certification" for c in found), phrasing


def test_an_accreditation_the_source_states_survives_either_way():
    source = "Our lab is accredited by the College of American Pathologists."
    delivered = "<p>CAP-accredited since 2019.</p>"

    assert not [c for c in unsupported_claims(source, delivered)
                if c.kind == "certification"]


def test_a_rounded_source_figure_is_reporting_it_not_inventing_one():
    """The one false positive a live run produced.

    The source said `1.70269159%`; the page wrote `1.70%` and the founder was
    told it was a claim their page could not support. Being accused of
    inventing a number you quoted accurately is the worst failure this module
    can have, because it teaches a founder to ignore the whole section.
    """
    source = "About 1.70269159% of global GDP is processed through Stripe."
    delivered = "<p>1.70% of global GDP runs through Stripe.</p>"

    assert unsupported_claims(source, delivered) == []


def test_rounding_does_not_launder_a_different_figure():
    """The tolerance is rounding at the stated precision, not fuzziness."""
    source = "About 1.70269159% of global GDP."
    delivered = "<p>2.40% of global GDP.</p>"

    assert _texts(unsupported_claims(source, delivered)) == {"2.40%"}


def test_a_rounded_match_must_share_the_unit():
    """`$2.9` does not evidence `2.9%` — the symbol is what says what is being
    measured."""
    source = "Plans start at $2.9 per seat."
    delivered = "<p>We take 2.9% of every charge.</p>"

    assert _texts(unsupported_claims(source, delivered)) == {"2.9%"}


def test_the_word_percent_and_the_symbol_are_the_same_claim():
    source = "We recover 30 percent of the time spent on reconciliation."
    delivered = "<p>Recover 30% of the time.</p>"

    assert unsupported_claims(source, delivered) == []


def test_a_licence_spelled_the_founders_way_is_not_reported_as_invented():
    """The asymmetry that made this module accuse founders of inventing their
    own licence.

    The same pattern decides both sides, so a badge written only in the
    compressed spelling a rewriter reaches for — "SEC-registered", "e-money
    institution" — never matched the ordinary phrasing the founder's page
    carries. The result is the worst finding this module can produce: a
    certification, in the style guide's explicitly dangerous group, aimed at
    somebody who holds it.
    """
    assert unsupported_claims(
        "Northwind Advisors is registered with the SEC as an investment adviser.",
        "<p>An SEC-registered investment adviser you can hold to account.</p>",
    ) == []
    assert unsupported_claims(
        "Payflow is an authorised electronic money institution in Ireland.",
        "<p>Authorised as an e-money institution.</p>",
    ) == []


def test_the_same_asymmetry_is_closed_where_it_repeats():
    """Word order, one entry over: "cleared by the FDA" and "256-bit AES" are
    how a founder writes what the rewrite compresses to "FDA-cleared" and
    "AES-256"."""
    assert unsupported_claims(
        "Our device is cleared by the FDA for use in clinical settings.",
        "<p>FDA-cleared for use in clinical settings.</p>",
    ) == []
    assert unsupported_claims(
        "Records are encrypted at rest with 256-bit AES.",
        "<p>AES-256 encryption at rest.</p>",
    ) == []


def test_a_regulator_spelled_out_is_the_same_badge_as_its_acronym():
    """The sixth through sixteenth instance of the asymmetry, closed as a
    family rather than one entry at a time.

    "Authorised and regulated by the Financial Conduct Authority" is the
    legally-standard sentence on essentially every UK fintech page, so an FCA
    entry that matched only the acronym told the highest-value fintech founder
    alive, in an artifact they paid for, that they had fabricated their own
    regulator — and burned a 32,000-token retry per round on a complaint the
    model cannot satisfy.
    """
    both_ways = [
        (
            "Ledgerline Ltd is authorised and regulated by the Financial Conduct "
            "Authority under firm reference number 912345.",
            "<p>Money movement for UK businesses, built by an FCA-regulated team.</p>",
        ),
        (
            "Acme is registered with the Financial Crimes Enforcement Network.",
            "<p>FinCEN registered since 2021.</p>",
        ),
        (
            "Deposits are insured by the Federal Deposit Insurance Corporation.",
            "<p>FDIC insured to $250,000.</p>",
        ),
        (
            "Acme Securities is a member of the Financial Industry Regulatory Authority.",
            "<p>A FINRA member firm.</p>",
        ),
        (
            "Chartered and regulated by the National Credit Union Administration.",
            "<p>NCUA regulated.</p>",
        ),
        (
            "Our device is cleared by the U.S. Food and Drug Administration.",
            "<p>FDA clearance in hand.</p>",
        ),
        (
            "Our controls are mapped to NIST SP 800-53.",
            "<p>NIST 800-53 aligned.</p>",
        ),
        (
            "The device holds 510k clearance.",
            "<p>510(k) cleared for clinical use.</p>",
        ),
        (
            "Our attestation is issued under SSAE No. 18.",
            "<p>An SSAE 18 report is available.</p>",
        ),
        (
            "Granted through the De Novo authorization pathway.",
            "<p>De Novo classification granted.</p>",
        ),
        (
            "Acme Payments is a registered MSB.",
            "<p>A licensed money services business.</p>",
        ),
    ]

    offenders = [
        (source[:40], [c.text for c in unsupported_claims(source, delivered)])
        for source, delivered in both_ways
        if [c for c in unsupported_claims(source, delivered) if c.kind == "certification"]
    ]
    assert offenders == []


def test_the_spelled_out_regulator_is_still_caught_when_the_source_is_silent():
    """The widening may not cost detection: a page naming a regulator the
    source never mentions is reported whichever spelling it uses."""
    for delivered, expected in (
        ("<p>An FCA-regulated team.</p>", "FCA"),
        ("<p>Authorised by the Financial Conduct Authority.</p>", "FCA"),
        ("<p>FDIC insured deposits.</p>", "FDIC"),
        ("<p>Insured by the Federal Deposit Insurance Corporation.</p>", "FDIC"),
        ("<p>The device holds 510k clearance.</p>", "510(k)"),
        ("<p>A registered MSB.</p>", "money services business"),
    ):
        assert expected.lower() in _texts(unsupported_claims(_SOURCE, delivered)), delivered


def test_a_spelled_out_name_that_is_also_an_ordinary_phrase_is_not_the_badge():
    """The widening has the same precision bar every other entry has: a
    spelled-out alternation earns its place only if a page could not mean it
    as anything but the badge. "Built for the payment card industry" is who a
    payments founder sells to, not a certification they hold."""
    delivered = "<p>Built for the payment card industry and the teams inside it.</p>"

    assert "pci dss" not in _texts(unsupported_claims(_SOURCE, delivered))
    # The standard's full name is still the standard.
    assert "pci dss" in _texts(
        unsupported_claims(
            _SOURCE,
            "<p>We meet the Payment Card Industry Data Security Standard.</p>",
        )
    )


def test_a_money_figure_is_not_a_medical_clearance():
    """"510k" earns its place as the founder's spelling of "510(k)" only
    because it cannot fire on "$510k in payouts" — a payments page telling a
    founder they invented an FDA clearance would be the same false accusation
    in a new costume."""
    delivered = "<p>We have processed $510k in payouts across 1,510k records.</p>"

    assert "510(k)" not in _texts(unsupported_claims(_SOURCE, delivered))


def test_a_badge_the_founder_never_claimed_is_still_caught_either_way():
    """The widening may not cost detection: a page that names a regulator the
    source never mentions is reported whichever spelling it uses."""
    for delivered in (
        "<p>Northwind is registered with the SEC.</p>",
        "<p>Northwind is an SEC-registered adviser.</p>",
    ):
        assert _texts(unsupported_claims(_SOURCE, delivered)) == {"sec registration"}

    # And the collision the entry avoids the bare acronym for stays avoided.
    assert unsupported_claims(_SOURCE, "<p>Sign up in 30 sec. Registration is free.</p>") == []


def test_a_compressed_magnitude_is_the_same_figure():
    """Rewriting `$5 million` as `$5M` is the single most likely thing a copy
    rewriter does to a headline number. Keyed as strings the two did not match,
    and `_rounds_to` could not rescue them because `Decimal("5m")` raises — so
    the founder was told in a paid artifact that they invented a revenue figure
    they wrote themselves, and it cost a retry generation call each time."""
    assert unsupported_claims(
        "We have processed $5 million in payouts.", "<p>$5M in payouts.</p>"
    ) == []
    # And in the other direction, which is the same claim.
    assert unsupported_claims(
        "We have processed $5M in payouts.", "<p>$5 million in payouts.</p>"
    ) == []
    assert unsupported_claims(
        "Ledgerline has processed over €1 million for finance teams.",
        "<p>Over €1M processed.</p>",
    ) == []
    # Scale counts the same way.
    assert unsupported_claims(
        "Trusted by 50,000 creators worldwide.", "<p>Trusted by 50k creators.</p>"
    ) == []


def test_folding_a_magnitude_does_not_launder_a_different_number():
    """The fold is arithmetic, not fuzziness: $5M is $5,000,000 and nothing
    else."""
    assert _texts(
        unsupported_claims("We have processed $5 million in payouts.", "<p>$50M in payouts.</p>")
    ) == {"$50m"}


def test_a_unit_written_as_a_word_is_the_same_figure():
    """`_normalise` folded "per cent" to "%" and nothing folded "cents" to "¢",
    so the source stated no figure at all and the page's own fee was reported
    as invented."""
    assert unsupported_claims(
        "We charge 30 cents per transaction.", "<p>Just 30¢ per transaction.</p>"
    ) == []
    assert _texts(
        unsupported_claims("We charge 30 cents per transaction.", "<p>Just 45¢ per transaction.</p>")
    ) == {"45¢"}


def test_bare_numbers_are_not_claims():
    """A step number, a year and a phone number are not facts about the business."""
    delivered = """
    <ol><li>1. Connect</li><li>2. Map</li><li>3. Close</li></ol>
    <footer>© 2026 Ledgerline. Call 555 0134. Live in 7 days.</footer>
    """

    assert unsupported_claims(_SOURCE, delivered) == []


def test_short_badges_do_not_match_inside_ordinary_words():
    """`ce mark` hides inside "acceptance marking"; `sec` inside "30 sec"."""
    delivered = """
    <p>Acceptance marking is automatic. Reconciliation runs in 30 sec.</p>
    <p>A basic plan covers three entities.</p>
    """

    assert unsupported_claims(_SOURCE, delivered) == []


def test_managed_detection_is_not_the_eu_medical_device_regulation():
    """Every security founder writes MDR; almost none mean the EU regulation."""
    delivered = "<p>Our MDR service watches your prompts around the clock.</p>"

    assert "eu mdr" not in _texts(unsupported_claims(_SOURCE, delivered))


# ── the source is read as text, never as markup ──────────────────────


def test_a_stylesheet_is_not_evidence_for_a_claim():
    """The guard that makes the check safe for a caller holding raw HTML.

    Left unstripped, a `<style>` block full of percentages would license any
    percentage the page cared to claim — `width: 99%` would evidence "99%
    uptime".
    """
    source_html = "<style>.bar{width:99%}</style><p>Ledgerline closes the books.</p>"
    delivered = "<p>99% uptime, guaranteed.</p>"

    assert _texts(unsupported_claims(source_html, delivered)) == {"99%"}


def test_markup_in_the_delivered_page_is_not_read_as_copy():
    """A class name is not a claim; only what a reader sees is."""
    delivered = '<div class="soc2-badge pci-grid"><p>Close your books.</p></div>'

    assert unsupported_claims(_SOURCE, delivered) == []


def test_a_literal_angle_bracket_in_the_source_does_not_delete_the_facts_after_it():
    """The strip has to know a tag from a "less than", and it did not.

    `<[^>]+>` read the "<" in "Setup takes <5 minutes" as a tag opening and
    deleted everything up to the next ">" — the "Read the docs >" two lines
    later — so the founder's own price and their own metric stopped being
    evidence. `unsupported_claims` reported both back to them as invented, and
    `claim_complaint` then ordered a whole-document rewrite replacing them with
    "[OWNER: fill in]": the delivered page loses the real price, and the
    survivors land in the paid style guide under "Claims to verify before you
    publish". "<5 minutes" plus a "Learn more >" is ordinary marketing copy.
    """
    page_text = (
        "Acme Payroll\n"
        "Setup takes <5 minutes and churn is <1%.\n"
        "Plans start at $29 per month and we cut payroll errors by 40%.\n"
        "Read the docs >\n"
    )
    delivered = (
        "<p>Payroll from $29 per month. Teams cut payroll errors by 40%. "
        "Setup takes under five minutes.</p>"
    )

    assert unsupported_claims(page_text, delivered) == []


def test_the_stylesheet_guard_survives_the_narrower_strip():
    """The reason `visible_copy` runs on the source at all: a caller holding
    raw HTML must not be able to license a claim with a `<style>` block. The
    narrower tag rule may not cost that."""
    source_html = "<style>.bar{width:99%}</style><p>Ledgerline closes the books.</p>"

    assert _texts(unsupported_claims(source_html, "<p>99% uptime, guaranteed.</p>")) == {"99%"}


# ── social proof ─────────────────────────────────────────────────────


def test_an_invented_customer_count_is_caught():
    delivered = "<p>Trusted by 4,000 finance teams.</p>"

    claims = unsupported_claims(_SOURCE, delivered)

    assert [c.kind for c in claims] == ["scale"]


def test_a_customer_count_the_source_states_is_not_reported():
    source = "Trusted by 4,000 finance teams closing their books with us."
    delivered = "<p>4,000 teams.</p>"

    assert unsupported_claims(source, delivered) == []


def test_the_or_more_mark_is_not_a_different_customer_count():
    """"Trusted by 4,000+ teams" is the most common social-proof spelling on a
    landing page, and adding or dropping the "+" is the most likely thing a
    copy rewriter does to it. Keyed with the "+" attached, both directions
    reported the founder's own customer count back to them as invented."""
    assert unsupported_claims(
        "Trusted by 4,000 teams who ship every day.",
        "<p>Trusted by 4,000+ teams who ship every day.</p>",
    ) == []
    assert unsupported_claims(
        "Trusted by 4,000+ teams who ship every day.",
        "<p>Trusted by 4,000 teams who ship every day.</p>",
    ) == []
    # And across the magnitude letter, which is the same claim again.
    assert unsupported_claims(
        "Trusted by 50,000 creators worldwide.", "<p>Join 50k+ creators today.</p>"
    ) == []


def test_a_count_written_with_a_magnitude_and_a_plus_is_still_caught():
    """The other half of the same gap. After a magnitude letter the "+" ended
    the match before the noun, so a wholly fabricated "Join 50k+ creators" was
    never flagged at all — an invented customer count waved through for being
    spelled the way landing pages spell it."""
    found = unsupported_claims(_SOURCE, "<p>Join 50k+ creators today. And 12m+ users.</p>")

    assert {c.kind for c in found} == {"scale"}
    assert _texts(found) == {"50k+ creators", "12m+ users"}


def test_the_or_more_mark_does_not_launder_a_different_count():
    """Dropping the "+" from the key is typography, not fuzziness: 4,000+ is
    4,000 and nothing else."""
    assert _texts(
        unsupported_claims(
            "Trusted by 4,000 teams.", "<p>Trusted by 40,000+ teams.</p>"
        )
    ) == {"40,000+ teams"}


# ── the finding has to be actionable ─────────────────────────────────


def test_the_quote_lets_the_founder_find_the_claim_on_the_page():
    delivered = (
        "<p>Close faster. SOC 2 Type II report available under NDA. "
        "Get started today.</p>"
    )

    claim = next(c for c in unsupported_claims(_SOURCE, delivered)
                 if c.text == "SOC 2")

    assert "report available under nda" in claim.quote
    assert "get started today" not in claim.quote, "the quote ran past its sentence"


def test_findings_are_capped():
    """A page that trips dozens has one systemic problem, not thirty."""
    delivered = "<p>" + " ".join(f"{n}% better" for n in range(1, 60)) + "</p>"

    assert len(unsupported_claims(_SOURCE, delivered)) == MAX_CLAIMS


def test_an_empty_page_claims_nothing():
    assert unsupported_claims(_SOURCE, "") == []
    assert unsupported_claims("", "") == []


# ── the complaint carried by the retry ───────────────────────────────


def test_the_complaint_names_every_claim_and_quotes_the_model_to_itself():
    """A retry that repeats the question gets the same wrong answer, and this
    failure is the strongest case for that rule: the prompt already forbade
    invention twice, in plain words, and was overridden regardless.
    """
    claims = unsupported_claims(
        _SOURCE,
        "<p>SOC 2 Type II certified. Fees are 2.9% + 30¢.</p>",
    )
    complaint = claim_complaint(claims)

    for claim in claims:
        assert claim.text in complaint
        assert claim.quote in complaint
    assert "[OWNER: fill in]" in complaint, (
        "the complaint must name the correct answer, not only the wrong one"
    )
