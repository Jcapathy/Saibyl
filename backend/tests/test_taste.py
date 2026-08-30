"""The standard must not be satisfiable by deleting things.

**This is the defect the module was written to close.** On 2026-08-27 the
founder ran the revision loop on saibyl.com. `measured` went 35 -> 73 while
`design` — a model actually looking at the page — fell 95 -> 72. Net +5, so the
loop declared a win and returned a plainer page. His description: "there's not
really much to it."

The cause is that every rule in `measured.py` is a variety penalty — too many
radii, too many colours, too many shadows. Penalties are satisfied by removal,
so the rubric's maximum sits at the empty page.

`test_a_stripped_page_scores_badly` is the regression guard for exactly that,
and it is the reason `TasteRule.kind` exists at all.
"""
from __future__ import annotations

from types import SimpleNamespace

from app.services.website.taste import (
    TASTE_KEY,
    TASTE_RULES,
    check_taste,
    taste_dimension,
    taste_prompt_section,
    taste_score,
)


def _capture(census: dict) -> SimpleNamespace:
    return SimpleNamespace(style_census=census)


def _healthy_census(**overrides) -> dict:
    census = {
        "font_families": {"Manrope": 40, "Playfair Display": 6},
        "text_colors": {"#14294a": 30, "#60718e": 20},
        "background_colors": {"#ffffff": 25, "#f8fbff": 10},
        "border_colors": {"#dbe6f5": 8},
        "labels": {"total": 3, "above_heading": 2},
        "structure": {
            "headings": {"h1": 1, "h2": 6},
            "buttons": 4,
            "links": 22,
            "images": 3,
            "sections": 8,
        },
        "actions": [
            {"label": "Start your first run", "where": "/signup"},
            {"label": "Start your first run", "where": "/signup"},
        ],
    }
    census.update(overrides)
    return census


def _verdict(verdicts, rule_id):
    return next(v for v in verdicts if v.rule.id == rule_id)


# ── the regression that matters ──────────────────────────────────────────────

def test_a_stripped_page_scores_badly():
    """The wireframe case. `measured` would give this a near-perfect score.

    No images, no buttons, no headings, one font, two colours — a page with
    every variety penalty satisfied because there is nothing left to vary.
    """
    bare = {
        "font_families": {"Helvetica": 20},
        "text_colors": {"#111111": 20},
        "background_colors": {"#ffffff": 20},
        "border_colors": {},
        "labels": {"total": 0, "above_heading": 0},
        "structure": {
            "headings": {"h1": 0, "h2": 0},
            "buttons": 0,
            "links": 0,
            "images": 0,
            "sections": 2,
        },
        "actions": [],
    }
    verdicts = check_taste(_capture(bare))
    score = taste_score(verdicts)

    assert score is not None
    assert score < 50, (
        f"a page stripped to nothing scored {score}; deletion is still a "
        "winning move and the revision loop will find it again"
    )

    for rule_id in ("requires_an_image", "requires_one_h1", "requires_an_action"):
        assert not _verdict(verdicts, rule_id).passed, f"{rule_id} passed on a bare page"


def test_requirements_exist_at_all():
    """A rubric of violations alone has its maximum at the empty page."""
    kinds = {rule.kind for rule in TASTE_RULES}
    assert "requirement" in kinds
    assert sum(1 for r in TASTE_RULES if r.kind == "requirement") >= 3


def test_a_healthy_page_scores_well():
    verdicts = check_taste(_capture(_healthy_census()))
    score = taste_score(verdicts)
    assert score is not None and score >= 90, f"a sound page scored {score}"


# ── individual rules ─────────────────────────────────────────────────────────

def test_the_banned_display_faces_are_caught():
    census = _healthy_census(font_families={"Fraunces": 30, "Inter": 10})
    verdict = _verdict(check_taste(_capture(census)), "no_banned_display_face")
    assert not verdict.passed
    assert "fraunces" in (verdict.quote or "").lower()


def test_three_slop_palette_values_trip_it_and_one_does_not():
    """One warm hex is a coincidence; the palette is the tell."""
    one = _healthy_census(background_colors={"#f5f1ea": 20, "#ffffff": 5})
    assert _verdict(check_taste(_capture(one)), "not_the_slop_palette").passed

    palette = _healthy_census(
        background_colors={"#f5f1ea": 20},
        text_colors={"#1a1714": 18},
        border_colors={"#b08947": 6},
    )
    verdict = _verdict(check_taste(_capture(palette)), "not_the_slop_palette")
    assert not verdict.passed


def test_an_eyebrow_over_every_section_is_a_rhythm_not_a_signal():
    """The founder's own page: 9 labels across 10 sections."""
    census = _healthy_census(
        labels={"total": 9, "above_heading": 9},
        structure={
            "headings": {"h1": 1, "h2": 9},
            "buttons": 4, "links": 20, "images": 2, "sections": 10,
        },
    )
    verdict = _verdict(check_taste(_capture(census)), "eyebrow_restraint")
    assert not verdict.passed
    assert "9" in (verdict.quote or "")


def test_a_few_eyebrows_on_a_long_page_are_fine():
    census = _healthy_census(
        labels={"total": 3, "above_heading": 3},
        structure={
            "headings": {"h1": 1, "h2": 9},
            "buttons": 4, "links": 20, "images": 2, "sections": 10,
        },
    )
    assert _verdict(check_taste(_capture(census)), "eyebrow_restraint").passed


def test_one_destination_wearing_several_labels_is_caught():
    census = _healthy_census(actions=[
        {"label": "Start your first run", "where": "/signup"},
        {"label": "Try it free", "where": "/signup"},
        {"label": "Get started", "where": "/signup"},
    ])
    verdict = _verdict(check_taste(_capture(census)), "one_destination_one_label")
    assert not verdict.passed
    assert "/" in (verdict.quote or "")


def test_two_labels_for_two_destinations_is_not_a_finding():
    census = _healthy_census(actions=[
        {"label": "Start your first run", "where": "/signup"},
        {"label": "See a full run", "where": "#rehearsal"},
    ])
    assert _verdict(check_taste(_capture(census)), "one_destination_one_label").passed


# ── abstention, not false comfort ────────────────────────────────────────────

def test_a_page_that_defeats_the_census_returns_no_verdicts():
    assert check_taste(_capture({})) == []
    assert check_taste(SimpleNamespace(style_census=None)) == []


def test_an_unmeasurable_page_scores_none_rather_than_perfect():
    """A 100 meaning "we could not look" is the same bug as a 0 meaning it."""
    assert taste_score(check_taste(_capture({}))) is None


def test_a_rule_that_cannot_be_decided_abstains_rather_than_passing():
    """No `images` key at all: the rule must not report a clean pass."""
    census = _healthy_census(structure={
        "headings": {"h1": 1}, "buttons": 2, "links": 5, "sections": 4,
    })
    verdict = _verdict(check_taste(_capture(census)), "requires_an_image")
    assert verdict.quote is None


# ── the two renderings stay married ──────────────────────────────────────────

def test_every_rule_carries_both_a_check_and_a_sentence():
    """One row, two outputs. The prose and the predicate cannot drift."""
    for rule in TASTE_RULES:
        assert callable(rule.predicate), rule.id
        assert rule.why.strip() and rule.fix.strip(), rule.id
        assert rule.severity in {"critical", "major", "minor"}, rule.id
        assert rule.kind in {"requirement", "violation"}, rule.id


def test_the_prompt_section_is_rendered_from_the_same_rules():
    section = taste_prompt_section()
    for rule in TASTE_RULES:
        assert rule.fix[:40] in section, f"{rule.id} missing from the prompt"
    assert "not against any other site" in section
    assert "Do not reward a page for being empty" in section


def test_the_dimension_key_is_pinned():
    """`test_website_critics.py` spells this literal rather than importing it,
    because importing `taste` at its module scope would pull an unstubbed second
    copy of `critics`. This is the assertion that keeps the two in step."""
    assert TASTE_KEY == "standard"


# ── the dimension the report renders ─────────────────────────────────────────

def test_the_dimension_carries_findings_and_a_score():
    census = _healthy_census(
        structure={
            "headings": {"h1": 0, "h2": 4},
            "buttons": 2, "links": 9, "images": 0, "sections": 6,
        },
    )
    dimension = taste_dimension(_capture(census))

    assert dimension is not None
    assert dimension.key == TASTE_KEY
    assert 0 <= dimension.score <= 100
    regions = {f.region for f in dimension.findings}
    assert "page" in regions, "a missing image and a missing h1 both live on the page"
    # Every rendered finding must carry the measurement it is complaining about.
    assert all(f.quote for f in dimension.findings)
    assert all(f.why and f.fix for f in dimension.findings)


def test_the_dimension_names_what_the_page_got_right():
    """A report that lists only failures reads as a verdict on the founder."""
    dimension = taste_dimension(_capture(_healthy_census()))
    assert dimension is not None
    assert dimension.strengths, "a sound page was given no credit for anything"


def test_an_unmeasurable_page_yields_no_dimension():
    """Rather than a 100. The mean then runs over the opinions alone."""
    assert taste_dimension(_capture({})) is None


def test_the_standard_never_names_another_site_as_the_yardstick():
    """The founder's objection: a founder wants their page made better, not
    ranked against somebody else's."""
    section = taste_prompt_section().lower()
    for competitor in ("linear", "stripe.com", "vercel", "benchmark against"):
        assert competitor not in section


# ── the count, not the weight, was the defect (2026-08-30) ───────────────────
#
# `standard` was calibrated against six real pages. It was not too lenient, as
# the launch-readiness handoff supposed — it was reading two census fields that
# answered narrower questions than the rules asked, and reporting the gap as
# the founder's fault. Both are regression-guarded below.


def test_a_page_illustrated_without_img_elements_still_shows_the_product():
    """anthropic.com: zero `<img>`, sixteen visible inline SVGs.

    It was failing a *requirement* — the heaviest non-critical penalty in the
    rubric at 18 x 1.5 — and being told to "show the product doing its job".
    Re-measured through this code path, the page scores 100.
    """
    census = _healthy_census()
    census["structure"] = {**census["structure"], "images": 0, "visual_media": 4}
    verdict = _verdict(check_taste(_capture(census)), "requires_an_image")
    assert verdict.passed, "a page drawn in SVG was told it had no imagery"


# ── motion, and the reader who asked for less of it (2026-08-30) ────────────
#
# Motion was invisible to this product until this date: the census recorded
# none, no reviewer asked, and both screenshots are still images. Saibyl's own
# design law calls collapsing animation under `prefers-reduced-motion` "not
# optional" and had never checked it on anyone else's page.


def _with_motion(**motion) -> SimpleNamespace:
    return SimpleNamespace(style_census=_healthy_census(), motion=motion)


def test_a_page_that_keeps_moving_through_the_preference_is_told_so():
    verdict = _verdict(
        check_taste(
            _with_motion(
                animated_elements=9, transitioned_elements=66, respects_reduced_motion=False
            )
        ),
        "motion_stops_when_asked",
    )

    assert not verdict.passed
    assert "75 elements still move" in (verdict.quote or "")


def test_a_page_that_collapses_its_motion_passes():
    verdict = _verdict(
        check_taste(
            _with_motion(
                animated_elements=9, transitioned_elements=66, respects_reduced_motion=True
            )
        ),
        "motion_stops_when_asked",
    )

    assert verdict.passed


def test_a_still_page_is_not_told_to_animate():
    """Stillness is a choice, not a defect. `respects_reduced_motion` is None
    when there was no motion to reduce, and this rule is "if you animate,
    honour the request to stop" — never "you should animate", which would be a
    preference invented here."""
    verdict = _verdict(
        check_taste(
            _with_motion(
                animated_elements=0, transitioned_elements=0, respects_reduced_motion=None
            )
        ),
        "motion_stops_when_asked",
    )

    assert verdict.passed


def test_a_capture_with_no_motion_reading_abstains():
    """An older stored capture, or a runtime that could not emulate the
    preference. Neither is the founder's page ignoring anybody."""
    assert _verdict(
        check_taste(SimpleNamespace(style_census=_healthy_census(), motion={})),
        "motion_stops_when_asked",
    ).passed
    assert _verdict(
        check_taste(_capture(_healthy_census())), "motion_stops_when_asked"
    ).passed


def test_a_labelled_placeholder_does_not_count_as_imagery():
    """A box that says it is standing in for a picture is not a picture.

    The revision loop is *told* to draw one — "draw a CSS or inline-SVG
    placeholder and label it visibly as a placeholder" — so counting them let
    the loop clear this requirement with a labelled rectangle. Measured
    2026-08-30 through a real capture: a page whose only graphic read
    "[PLACEHOLDER: product screenshot]" scored **100**, and **73** with the box
    deleted. 27 points for a gesture, which is the deletion-gaming defect
    wearing the opposite costume.

    The exclusion happens in the census, so `visual_media` never counts it and
    both rubrics see the same thing.
    """
    census = _healthy_census()
    census["structure"] = {**census["structure"], "images": 0, "visual_media": 0}
    verdict = _verdict(check_taste(_capture(census)), "requires_an_image")
    assert not verdict.passed


def test_a_page_with_no_visible_imagery_at_all_still_fails():
    """The guard on the fix: news.ycombinator.com used to *pass* this rule on a
    single 18x18 logo, because one `<img>` element was the whole test."""
    census = _healthy_census()
    census["structure"] = {**census["structure"], "images": 1, "visual_media": 0}
    verdict = _verdict(check_taste(_capture(census)), "requires_an_image")
    assert not verdict.passed
    assert verdict.quote == "visible images, graphics or video on the page: 0"


def test_a_census_stored_before_visual_media_falls_back_to_the_img_count():
    """A stored capture cannot be re-measured, so the narrower count is the only
    evidence there is — and it is what those rows were already scored under."""
    census = _healthy_census()
    census["structure"] = {**census["structure"], "images": 2}
    census["structure"].pop("visual_media", None)
    assert _verdict(check_taste(_capture(census)), "requires_an_image").passed

    census["structure"] = {**census["structure"], "images": 0}
    stale = _verdict(check_taste(_capture(census)), "requires_an_image")
    assert not stale.passed
    assert stale.quote == "img elements on the page: 0"


def test_different_hosts_are_different_destinations():
    """The `where` key kept only the path, so every link to a domain root
    collapsed into one bucket. anthropic.com collapsed seven origins — status.,
    trust., platform., support., academy., www. — and was told to rename
    actions that had nothing to do with each other."""
    census = _healthy_census(
        actions=[
            {"label": "Status", "where": "https://status.example.com/"},
            {"label": "Support center", "where": "https://support.example.com/"},
            {"label": "Security and compliance", "where": "https://trust.example.com/"},
        ]
    )
    verdict = _verdict(check_taste(_capture(census)), "one_destination_one_label")
    assert verdict.passed, "three separate services were read as one destination"


def test_in_page_anchors_are_different_destinations():
    """Skip links are the sharp case: "Skip to main content" and "Skip to
    footer" are a WCAG requirement, and the rule was charging 18 points for
    them because `#main` and `#footer` both reduced to `/`."""
    census = _healthy_census(
        actions=[
            {"label": "Skip to main content", "where": "/#main"},
            {"label": "Skip to footer", "where": "/#footer"},
        ]
    )
    verdict = _verdict(check_taste(_capture(census)), "one_destination_one_label")
    assert verdict.passed, "accessibility skip links were scored as a defect"


def test_one_destination_wearing_two_labels_is_still_caught():
    """The true positive the fix must not throw away. vercel.com carries
    "Get a Demo" and "Talk to sales" to the same path, and still fails."""
    census = _healthy_census(
        actions=[
            {"label": "Get a Demo", "where": "/contact/sales"},
            {"label": "Talk to sales", "where": "/contact/sales"},
        ]
    )
    verdict = _verdict(check_taste(_capture(census)), "one_destination_one_label")
    assert not verdict.passed
    assert "Get a Demo" in (verdict.quote or "")
