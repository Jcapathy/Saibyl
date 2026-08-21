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
