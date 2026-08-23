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
from app.services.website.verticals import classify_vertical

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


_VAR_PAGE = """<html><head><style>
:root{--ink:#141414;--paper:#faf8f5;--accent:#c8452e;--muted:#6b6b6b;--line:#e6e0d8;
      --card-radius:14px}
body { background: var(--paper); color: var(--ink) }
h1 { color: var(--ink); border-bottom: 1px solid var(--line) }
a { color: var(--accent) }
.note { color: var(--muted) }
.card { border-radius: var(--card-radius) }
</style></head><body><h1>Ship faster</h1></body></html>"""


def test_a_palette_held_in_custom_properties_is_still_a_palette():
    """The page shape the generator is told to produce: one inline `<style>`,
    a `:root` palette, `var(--…)` at every point of use. Each hex then occurs
    exactly once — in `:root` — so counting literals alone put the whole
    palette under the two-use cut and deleted the Colour table, which is the
    main content of the guide the founder paid for. The module already follows
    `var()` for fonts; a colour is no different."""
    found = dict(extract_tokens(_VAR_PAGE).colors)

    assert found["#141414"] == 3  # defined once, used twice
    assert found["#faf8f5"] == 2
    assert found["#c8452e"] == 2
    assert found["#6b6b6b"] == 2
    assert found["#e6e0d8"] == 2

    guide = build_style_guide(url="https://acme.example", page_text=_VAR_PAGE)
    assert "## Colour" in guide
    assert "`#141414`" in guide


def test_a_radius_named_by_a_variable_is_printed_as_the_shape_it_holds():
    """The same defect one declaration over. `border-radius: var(--card-radius)`
    printed as `var(--card-radius)` is the technically-accurate, completely
    useless answer the font read already refuses."""
    tokens = extract_tokens(_VAR_PAGE)

    assert tokens.radii == ["14px"]
    assert not any("var(" in radius for radius in tokens.radii)


def test_an_undefined_shape_variable_names_nothing_rather_than_itself():
    assert extract_tokens("<style>.c{border-radius:var(--missing)}</style>").radii == []


def test_the_closing_steps_never_point_at_a_table_that_is_not_there():
    """A numbered instruction referring to a Colour table the guide does not
    contain is how a founder learns to distrust the rest of it."""
    without = build_style_guide(url="https://acme.example", page_text="<p>Hello</p>")
    assert "## Colour" not in without
    assert "table above" not in without

    with_colors = build_style_guide(url="https://acme.example", page_text=PAGE)
    assert "## Colour" in with_colors
    assert "Take colours from the table above." in with_colors


def test_the_category_survives_the_plural_the_page_actually_uses():
    """Marketing copy is written in the plural, and the classifier was blind to
    it: the same sentence about a "clinic" and a "patient" classified as health
    and the one about "clinics" and "patients" fell through to `general`, so
    the guide told the founder their page was for **General** and the
    generation prompt got the generic brief. Invisible, because `general` is
    also the honest answer for thin evidence."""
    singular = "<p>Our clinic software helps every patient and provider in the hospital.</p>"
    plural = "<p>Our clinics software helps every patients and providers in the hospitals.</p>"
    realistic = (
        "<p>Chartline gives clinics one place to see their patients. Care teams "
        "at 40 practices chase referrals with providers. Physicians spend less "
        "time in charts, across independent practices and the hospitals they "
        "refer into.</p>"
    )

    for markup in (singular, plural, realistic):
        assert "Health and clinical software" in build_style_guide(
            url="https://chartline.example", page_text=markup
        ), f"the category was lost on: {markup[:60]}"


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


# ── only well-formed markup is markup ────────────────────────────────
#
# `<[^>]+>` read the "<" in "Setup takes <5 minutes" as a tag opening and
# deleted everything up to the next ">" — a "Learn more >" three sentences
# later. `claims._normalise` runs this over the founder's own extracted page
# text, so the span in between stopped being evidence: their real price and
# their real metric came back to them in a paid artifact as invented claims,
# and the rewrite that followed replaced both with "[OWNER: fill in]".

_COPY_WITH_ANGLES = (
    "Acme Payroll\n"
    "Setup takes <5 minutes and churn is <1%.\n"
    "Plans start at $29 per month and we cut payroll errors by 40%.\n"
    "Read the docs >\n"
)


def test_a_literal_angle_bracket_in_copy_is_copy_not_a_tag():
    copy = visible_copy(_COPY_WITH_ANGLES)

    assert "<5 minutes" in copy
    assert "<1%" in copy
    assert "$29 per month" in copy, "the founder's own price was deleted as markup"
    assert "40%" in copy, "the founder's own metric was deleted as markup"
    assert "Read the docs >" in copy


def test_well_formed_markup_is_still_stripped():
    """The widening may not cost the strip: real tags, declarations and
    comments all still go, including a comment whose body carries a ">" — the
    generator is asked to declare a replaced design system in exactly that."""
    html = (
        "<!doctype html><html><head><style>.p{width:99%}</style></head>"
        "<!-- replaced the system: 8px > 4px, one accent -->"
        "<body><h1 data-x='a'>Ship faster</h1><p>Read <a href='#'>more</a>.</p>"
        "</body></html>"
    )

    copy = visible_copy(html)

    assert copy == "Ship faster Read more ."
    assert "99%" not in copy, "a stylesheet is not copy"
    assert "8px" not in copy, "a comment is not copy"


def test_the_guide_reads_the_same_category_the_generator_does():
    """Two sides, one page. `revise._generation_prompt` classifies the raw
    extracted text and `build_style_guide` classifies `visible_copy` of it, so
    a strip that ate plain copy made the guide and the page disagree about who
    the page is for."""
    page_text = (
        "Chartwell Clinical\n"
        "Prior authorisations in <5 minutes.\n"
        "Built for clinics, hospitals and patient intake teams handling "
        "patient records and clinical workflows for providers.\n"
        "Read the docs >"
    )

    assert classify_vertical(page_text) == classify_vertical(visible_copy(page_text))
    assert "Health and clinical software" in build_style_guide(
        url="https://chartwell.example", page_text=page_text
    )


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
