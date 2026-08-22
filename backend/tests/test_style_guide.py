"""The guide is read out of the page, or it is fiction.

A style guide written *alongside* a design is wrong the first time the design
changes, and nobody notices — that is the failure mode this module exists to
make impossible. Every value it prints is extracted from the delivered file,
so the two cannot disagree.

What is guarded here:

1. The extraction is real — the values printed are the page's own, and the
   long tail of one-off colours is cut rather than presented as a system.
2. Absence is absence. A page with no shadows gets no shadow section; a
   check with no gallery row gets no provenance section. The guide never
   fills a gap with a plausible default, because a founder handing this to a
   designer would have no way to tell the invented line from the measured
   one.
"""
from __future__ import annotations

from app.services.website.style_guide import (
    build_style_guide,
    extract_tokens,
    visible_copy,
)

PAGE = """<html><head><style>
body { font-family: Manrope, sans-serif; background: #f8fbff; color: #14294a }
.h  { font-family: "Playfair Display", serif; color: #14294a }
.cta { background: #286cf0; border-radius: 12px;
       box-shadow: 0 1px 2px rgba(0,0,0,.06) }
.card { background: #f8fbff; border-radius: 12px; color: #286cf0 }
.odd { color: #ff00ff }
</style></head><body><h1>Ship faster</h1></body></html>"""


def test_the_tokens_are_the_pages_own():
    tokens = extract_tokens(PAGE)
    found = dict(tokens.colors)

    assert found["#f8fbff"] == 2
    assert found["#286cf0"] == 2
    assert found["#14294a"] == 2
    assert tokens.faces == ["Manrope", "Playfair Display"]
    assert tokens.radii == ["12px"]
    assert tokens.shadows == ["0 1px 2px rgba(0,0,0,.06)"]


def test_a_quoted_multi_word_face_is_not_skipped():
    """The faces most worth naming are the ones that must be quoted — every
    multi-word family is written `"Playfair Display"` or `'DM Mono'`. A rule
    that stopped at the opening quote dropped them silently, leaving a guide
    that named one face for a two-face page."""
    assert extract_tokens(
        '<style>h1{font-family:"Playfair Display",serif}'
        "code{font-family:'DM Mono',monospace}</style>"
    ).faces == ["Playfair Display", "DM Mono"]


def test_an_inline_style_attribute_does_not_swallow_the_markup_after_it():
    """A `style=` attribute is closed by a quote, not by a semicolon, so the
    capture runs past the declaration's real end and the cut has to happen
    after it."""
    assert extract_tokens(
        '<div style="font-family: Manrope, sans-serif" class="hero">'
    ).faces == ["Manrope"]


def test_a_font_variable_is_followed_to_the_face_it_names():
    """Found on real pages: modern build output almost never names a family at
    the point of use. A guide answering "your heading font is
    var(--font-mono)" is technically accurate and completely useless."""
    html = (
        "<style>:root{--font-display:'Geist Sans',sans-serif;"
        "--font-mono:\"Geist Mono\",monospace}"
        "h1{font-family:var(--font-display)}code{font-family:var(--font-mono)}"
        "</style>"
    )
    assert extract_tokens(html).faces == ["Geist Sans", "Geist Mono"]


def test_an_undefined_variable_names_nothing_rather_than_itself():
    """The face may be defined in a stylesheet we never fetched. Saying
    nothing is honest; printing the variable name is not."""
    assert extract_tokens("<style>h1{font-family:var(--missing)}</style>").faces == []


def test_css_keywords_are_not_typefaces():
    """Also found on real pages. `inherit` in a face list sends the reader
    looking for a font that does not exist."""
    html = (
        "<style>a{font-family:inherit}b{font-family:unset}"
        "c{font-family:Manrope,sans-serif}</style>"
    )
    assert extract_tokens(html).faces == ["Manrope"]


def test_an_escaped_declaration_does_not_yield_a_typeface_called_backslash():
    """Found on a real page: a font-family inside an embedded script is
    written `font-family:\\"Uncut Sans\\"`, and the naive read takes the
    backslash as the name. One nonsense line makes a founder distrust the
    whole guide."""
    html = '<script>el.style="font-family:\\"Uncut Sans\\",sans-serif"</script>'
    assert "\\" not in extract_tokens(html).faces
    assert extract_tokens(html).faces in ([], ["Uncut Sans"])


def test_a_variable_cycle_gives_up_instead_of_looping():
    html = "<style>:root{--a:var(--b);--b:var(--a)}h1{font-family:var(--a)}</style>"
    assert extract_tokens(html).faces == []


def test_an_important_none_is_still_no_shadow():
    """Found on a real page. `!important` is about precedence, not shape — and
    a page whose only "shadow" is `none !important` has no shadows."""
    assert extract_tokens("<style>a{box-shadow:none !important}</style>").shadows == []
    assert extract_tokens(
        "<style>a{box-shadow:0 1px 2px #0001 !important}</style>"
    ).shadows == ["0 1px 2px #0001"]


def test_the_type_advice_matches_the_number_of_faces():
    """A one-face page told to beware "a fourth face" reads as boilerplate,
    and boilerplate is how a reader learns to skip the rest."""
    one = build_style_guide(
        url="", page_text="<style>h1{font-family:Inter,sans-serif}</style>"
    )
    assert "One face" in one
    assert "fourth face" not in one


def test_a_colour_used_once_is_not_a_token():
    """The cut is the point. A swatch chart listing every one-off value —
    a border at 4% opacity, a shadow tint — is not a system anybody can act
    on, and presenting it as one invites the next editor to treat noise as
    intent."""
    assert "#ff00ff" not in dict(extract_tokens(PAGE).colors)


def test_shorthand_and_longhand_hex_are_the_same_colour():
    """`#fff` and `#ffffff` are one decision. Counted apart, each falls under
    the threshold and the page's most-used colour vanishes from its own
    guide."""
    html = "<style>a{color:#fff}b{color:#FFFFFF}c{background:#ffffff}</style>"
    assert dict(extract_tokens(html).colors)["#ffffff"] == 3


def test_the_category_is_read_from_the_copy_not_the_class_names():
    """Left raw, a Tailwind page votes with its class names. `patient` in a
    CSS selector must not weigh what `patient` in a headline weighs."""
    markup = (
        "<style>.patient-row{}.clinical-grid{}.health-hero{}.hospital-nav{}"
        ".ehr-card{}</style><h1>We make software.</h1>"
    )
    assert "patient" not in visible_copy(markup)
    assert "We make software." in visible_copy(markup)
    assert "Health and clinical software" not in build_style_guide(
        url="https://acme.example", page_text=markup
    )


def test_script_contents_never_reach_the_copy():
    html = "<script>const patient = fetchClinicalEhrHospital();</script><p>Hi</p>"
    assert "Clinical" not in visible_copy(html)


def test_a_page_with_no_system_gets_no_invented_one():
    """The honest floor. A bare page has no palette to describe, and the guide
    says nothing rather than proposing one — a founder cannot tell an invented
    line from a measured one, so there must be no invented lines."""
    guide = build_style_guide(url="https://acme.example", page_text="<p>Hello</p>")

    assert "## Colour" not in guide
    assert "## Type" not in guide
    assert "## Shape and depth" not in guide
    # But the parts that do not depend on the page still land.
    assert "## Who this page is for" in guide
    assert "## Adding to this page later" in guide


def test_a_missing_gallery_row_removes_the_section_it_would_have_filled():
    for dna in (None, {}, {"characterization": "  ", "summary": None}):
        assert "## Where this came from" not in build_style_guide(
            url="https://acme.example", page_text=PAGE, dna=dna
        )

    with_dna = build_style_guide(
        url="https://acme.example",
        page_text=PAGE,
        dna={"characterization": "A stock Bootstrap theme."},
    )
    assert "## Where this came from" in with_dna
    assert "stock Bootstrap theme" in with_dna


def test_scores_are_reported_only_when_measured():
    assert "The critics scored" not in build_style_guide(
        url="https://acme.example", page_text=PAGE, scores_after={}
    )
    assert "The critics scored" not in build_style_guide(
        url="https://acme.example", page_text=PAGE, scores_after={"dimensions": {}}
    )

    scored = build_style_guide(
        url="https://acme.example",
        page_text=PAGE,
        scores_after={"overall": 81, "dimensions": {"hierarchy": 78}},
    )
    assert "**81**" in scored
    assert "hierarchy 78" in scored


def test_the_guide_carries_the_saibyl_line():
    """Branded exports, per the design guide: an artifact a client extracts
    says who made it."""
    guide = build_style_guide(url="https://acme.example", page_text=PAGE)
    assert "Saibyl" in guide and "Saido Labs LLC" in guide


def test_a_page_with_no_url_still_produces_a_guide():
    """The url is a label, never a dependency — an empty one costs a heading
    word, not the download."""
    assert build_style_guide(url="", page_text=PAGE).startswith("# Style guide —")


# ---------------------------------------------------------------------------
# Claims the rewrite made that the founder's page never made
#
# The bundle is what gets handed to whoever publishes the page, so it is the
# surface that matters most for a fabricated certification. A live fintech
# revision shipped SOC 2, ISO 27001 and PCI DSS claims with no basis in the
# source (2026-08-22); the guide beside that page said nothing about them.
# ---------------------------------------------------------------------------

_CLAIMS = [
    {"kind": "certification", "text": "SOC 2",
     "quote": "soc 2 type ii report available under nda."},
    {"kind": "figure", "text": "2.9%",
     "quote": "2.9% + 30c per successful card charge."},
]


def test_the_guide_warns_about_claims_the_page_could_not_support():
    guide = build_style_guide(
        url="https://acme.example", page_text=PAGE, unsupported_claims=_CLAIMS
    )

    assert "## Claims to verify before you publish" in guide
    assert "**SOC 2**" in guide and "**2.9%**" in guide
    # The quote is what makes it actionable: the founder searches index.html.
    assert "soc 2 type ii report available under nda." in guide


def test_the_warning_lands_before_the_founder_has_read_anything_else():
    """A founder skims a style guide. The section is worthless below the fold."""
    guide = build_style_guide(
        url="https://acme.example", page_text=PAGE, unsupported_claims=_CLAIMS
    )

    assert guide.index("Claims to verify") < guide.index("## Who this page is for")
    assert guide.index("Claims to verify") < guide.index("## Colour")


def test_certifications_are_called_out_as_the_dangerous_group():
    guide = build_style_guide(url="https://a.example", page_text=PAGE,
                              unsupported_claims=_CLAIMS)

    assert "### Certifications, licences and regulators" in guide
    assert "customers and\nregulators act on it" in guide


def test_a_page_with_only_a_figure_gets_no_certification_warning():
    """Absence is absence here too — an over-stated warning is its own noise."""
    guide = build_style_guide(
        url="https://a.example",
        page_text=PAGE,
        unsupported_claims=[_CLAIMS[1]],
    )

    assert "## Claims to verify before you publish" in guide
    assert "### Certifications, licences and regulators" not in guide
    assert "regulators act on it" not in guide


def test_a_clean_page_gets_no_claims_section_at_all():
    for value in (None, [], "not a list"):
        guide = build_style_guide(
            url="https://a.example", page_text=PAGE, unsupported_claims=value
        )
        assert "Claims to verify" not in guide
