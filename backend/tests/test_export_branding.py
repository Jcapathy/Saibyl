"""An exported report carries the brand, or this fails.

The surface most likely to be forwarded to somebody who has never seen the app
is the one that shipped with no brand on it at all: a generic print palette and
a spaced-out all-caps `SAIBYL` wordmark that appears nowhere else in the
product. A founder's PDF is read by their co-founder, their investor and their
customer, and it should look like it came from the company whose page they
signed up on.

These assertions are deliberately about the STYLESHEET and the DOCUMENT rather
than about rendered pixels, because they must run everywhere. `render_pdf`
needs WeasyPrint's native stack, which a Windows workstation does not have — so
the pixel-level tests in `test_pdf_export.py` skip there, and branding would
have been unverified on the machine where it is most often edited.

`docs/DESIGN_GUIDE.md` is the prose; this is the ratchet.
"""
from __future__ import annotations

import re

from app.services.export.print_stylesheet import build_stylesheet

# The product's values, from `frontend/src/pages/landing.css` and the Tailwind
# token remap. Hardcoded rather than imported: the point is to notice when the
# export drifts from the product, and importing the same constant from the
# module under test would assert only that a name equals itself.
INK = "#14294a"
ACCENT = "#286cf0"
VIOLET = "#6a4fe0"


def test_the_export_palette_is_the_products_palette():
    css = build_stylesheet("Acme Corp")

    assert INK in css, "the export is not using the product's ink"
    assert ACCENT in css, "the export is not using the product's one accent"
    assert VIOLET in css, "the emphasis hue is missing from the cover"

    # The palette it shipped with. Finding these again means somebody restored
    # the generic print styling over the brand.
    for stale in ("#14181d", "#1f3b5c"):
        assert stale not in css, f"the pre-brand palette value {stale} is back"


def test_the_cover_carries_the_lockup_as_the_product_writes_it():
    from app.services.export import report_document

    source = report_document.__dict__["_cover"].__code__.co_consts
    markup = " ".join(c for c in source if isinstance(c, str))

    assert "brand-mark" in markup, "the cover lost its brand mark"
    assert "Saibyl" in markup, "the cover lost the wordmark"
    assert "BY SAIDO LABS" in markup, "the cover lost the Saido Labs line"

    # The spelling that appears nowhere else in the product. If it comes back,
    # somebody has reverted the lockup.
    assert ">SAIBYL<" not in markup, "the all-caps wordmark is back"


def test_the_brand_faces_are_named_before_the_fallbacks():
    """Named first so the real type is used wherever it exists.

    The container installs only Liberation and DejaVu, so these fall back
    today — that is expected and the identity does not depend on it. What must
    not happen is the brand faces being absent from the stack entirely, which
    is how installing the fonts later silently changes nothing.
    """
    css = build_stylesheet("Acme Corp")

    for face, fallback in (
        ("Manrope", "Liberation Sans"),
        ("Playfair Display", "Liberation Serif"),
        ("DM Mono", "DejaVu Sans Mono"),
    ):
        assert face in css, f"{face} is not named in any stack"
        # And it must come first in whichever stack carries it.
        stack = next(
            (line for line in css.splitlines() if face in line and "font-family" in line),
            None,
        )
        assert stack is not None, f"{face} appears but not in a font-family"
        assert stack.index(face) < stack.index(fallback), (
            f"{face} is listed after {fallback}; the fallback would always win"
        )


def test_no_meaning_is_carried_by_hue_alone():
    """The greyscale rule, as a check rather than a comment.

    A report is printed in black and white more often than anyone admits. The
    stylesheet's own docstring commits to this; the cheap mechanical part of it
    is that the accent is never the only thing distinguishing text — so it may
    not appear as a bare `color:` on body copy.
    """
    css = build_stylesheet("Acme Corp")

    body_rules = re.findall(r"\bp\s*\{[^}]*\}", css)
    for rule in body_rules:
        assert ACCENT not in rule, (
            "body copy is tinted with the accent; greyscale would lose it"
        )


def test_the_stylesheet_is_well_formed():
    """The formatting escape that has bitten this file before.

    `build_stylesheet` is one big f-string, so an unescaped brace silently
    produces a stylesheet that WeasyPrint parses as far as the error and then
    abandons — which loses the page furniture rather than raising.
    """
    css = build_stylesheet('A client "with quotes" & an ampersand')

    assert css.count("{") == css.count("}"), "unbalanced braces in the stylesheet"
    assert "@page" in css and "@top-left" in css, "page furniture is missing"
    assert "{{" not in css, "an unexpanded literal brace survived the f-string"
