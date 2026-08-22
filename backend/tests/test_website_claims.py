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


# ── social proof ─────────────────────────────────────────────────────


def test_an_invented_customer_count_is_caught():
    delivered = "<p>Trusted by 4,000 finance teams.</p>"

    claims = unsupported_claims(_SOURCE, delivered)

    assert [c.kind for c in claims] == ["scale"]


def test_a_customer_count_the_source_states_is_not_reported():
    source = "Trusted by 4,000 finance teams closing their books with us."
    delivered = "<p>4,000 teams.</p>"

    assert unsupported_claims(source, delivered) == []


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
