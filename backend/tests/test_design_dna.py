"""Design DNA extraction: measured tokens in, one strict-JSON vision read out.

The contract under test:

- One vision call carrying the DESKTOP screenshot and, in the prompt, the
  style census as text (the receipt) plus the page-text extract — so every
  token claim can be grounded in a measured number.
- The prompt pins the grounding rule (only hexes present in the census may
  appear), embeds the maturity ladder, the style-tag taxonomy, the font-slop
  signal, and the DESIGN.md section plan.
- Valid JSON parses into a `DesignDNA`; an unreadable answer gets exactly one
  nudged retry, then a `DesignDNAError` — the `critics.py` idiom.
- The call lands inside the `website_design_dna` ledger stage.
- No template string of ours uses a word a founder has to learn, and the
  prompt instructs the model likewise (the shared vocabulary rule, verbatim).

`llm_vision` is mocked in every test — no live calls, no browser.
"""
from __future__ import annotations

import json
import re
from contextlib import contextmanager
from types import SimpleNamespace

import pytest

from app.services.website import design_dna
from app.services.website.capture import WebsiteCapture
from app.services.website.critics import VOCABULARY_RULE
from app.services.website.design_dna import DesignDNA, DesignDNAError, extract_design_dna

# ---------------------------------------------------------------------------
# Fixtures: a captured page with a census, and a scriptable vision stand-in
# ---------------------------------------------------------------------------

DESKTOP = b"desktop-screenshot-bytes"
MOBILE = b"mobile-screenshot-bytes"

#: A census as `capture._normalize_census` would emit it — distinctive values
#: ("#f5f2ec", "Space Grotesk") the prompt tests key on.
CENSUS = {
    "sampled_elements": 240,
    "fonts": {
        "families": [
            {"stack": '"Space Grotesk", sans-serif', "family": "Space Grotesk", "count": 120},
            {"stack": "Georgia, serif", "family": "Georgia", "count": 40},
        ],
        "weights": [{"value": "400", "count": 90}, {"value": "700", "count": 40}],
        "sizes": [{"value": "16px", "count": 150}, {"value": "48px", "count": 6}],
    },
    "text": {
        "letter_spacing": {
            "headings": [{"value": "-0.02em", "count": 6}],
            "body": [{"value": "normal", "count": 200}],
        },
        "line_heights": [{"value": "25.6px", "count": 150}],
    },
    "color": {
        "text": [{"value": "#101418", "count": 200}],
        "background": [{"value": "#f5f2ec", "count": 60}],
        "border": [{"value": "#dcdcdc", "count": 12}],
    },
    "shape": {
        "border_radius": [{"value": "8px", "count": 30}],
        "box_shadow": [{"value": "rgba(0, 0, 0, 0.08) 0px 1px 2px 0px", "count": 9}],
    },
    "spacing": {
        "values": [{"value": "24px", "count": 80}, {"value": "8px", "count": 44}],
        "base_unit_px": 8,
    },
    "structure": {"headings": {"h1": 1, "h2": 4}, "buttons": 3, "links": 12, "images": 6},
}


def _capture(**overrides) -> WebsiteCapture:
    fields = dict(
        url="https://example.com",
        final_url="https://example.com/",
        title="Example — build faster",
        dom_text="Build faster. Start a free run today. Trusted by 40 teams.",
        meta={"og:title": "Example", "description": "Build faster."},
        screenshot_desktop=DESKTOP,
        screenshot_mobile=MOBILE,
        style_census=CENSUS,
    )
    fields.update(overrides)
    return WebsiteCapture(**fields)


def _payload(**overrides) -> str:
    body = {
        "characterization": "warm paper, sharp ink",
        "summary": (
            "A light page grounded on #f5f2ec paper with #101418 ink. "
            "Space Grotesk carries the headings at 700; the body sits at "
            "16px on a measured 8px rhythm. One radius, one soft shadow."
        ),
        "tokens": {
            "palette": [
                {"hex": "#f5f2ec", "name": "Paper", "role": "page ground"},
                {"hex": "#101418", "name": "Ink", "role": "text"},
            ],
            "fonts": [
                {"family": "Space Grotesk", "weights": ["700"], "role": "headings"},
                {"family": "Georgia", "weights": ["400"], "role": "body"},
            ],
            "radii": {"8px": "cards and buttons"},
            "shadows": ["rgba(0, 0, 0, 0.08) 0px 1px 2px 0px"],
            "spacing": {"base_unit_px": 8, "24px": "section gaps"},
            "theme": "light",
        },
        "dos": ["Keep body text at 16px on the 8px rhythm."],
        "donts": ["Never introduce a hex outside the measured palette."],
        "style_tags": ["Clean SaaS", "Minimalist Brand"],
        "maturity_level": 3,
        "maturity_rationale": (
            "A consistent palette and one deliberate pairing repeat page-wide, "
            "but the imagery is stock."
        ),
        "design_md": "# Example — Design DNA\n\n*warm paper, sharp ink*\n\n## Palette\n",
    }
    body.update(overrides)
    return json.dumps(body)


class _FakeVision:
    """Stands in for `llm_vision`; replies front to back, last entry repeating.

    An Exception entry is raised instead of answered.
    """

    def __init__(self, replies: list):
        self.replies = list(replies)
        self.calls: list[SimpleNamespace] = []
        self.probe = None  # optional: sampled at call time, recorded per call

    async def __call__(
        self,
        prompt,
        images,
        *,
        media_type="image/png",
        system=None,
        temperature=0.3,
        max_tokens=4096,
    ):
        self.calls.append(
            SimpleNamespace(
                prompt=prompt,
                images=list(images),
                inside_stage=self.probe() if self.probe else None,
            )
        )
        reply = self.replies.pop(0) if len(self.replies) > 1 else self.replies[0]
        if isinstance(reply, Exception):
            raise reply
        return reply


def _install_vision(monkeypatch, *replies) -> _FakeVision:
    fake = _FakeVision(list(replies) or [_payload()])
    monkeypatch.setattr(design_dna, "llm_vision", fake)
    return fake


# ---------------------------------------------------------------------------
# One call, carrying the receipt
# ---------------------------------------------------------------------------


async def test_the_prompt_carries_the_census_and_the_desktop_screenshot(monkeypatch):
    fake = _install_vision(monkeypatch)

    await extract_design_dna(_capture())

    assert len(fake.calls) == 1
    call = fake.calls[0]
    assert call.images == [DESKTOP], "the design read judged the wrong screen"

    # The census rides as text — the measured values are in the prompt.
    assert "#f5f2ec" in call.prompt, "the measured hexes never reached the model"
    assert "Space Grotesk" in call.prompt
    assert '"base_unit_px": 8' in call.prompt
    assert "-0.02em" in call.prompt

    # And the page's other evidence rides alongside.
    assert "Example — build faster" in call.prompt
    assert _capture().dom_text in call.prompt
    assert VOCABULARY_RULE in call.prompt, "the vocabulary rule never reached the model"


async def test_the_prompt_pins_grounding_ladder_taxonomy_and_the_artifact_shape(monkeypatch):
    fake = _install_vision(monkeypatch)

    await extract_design_dna(_capture())
    prompt = fake.calls[0].prompt

    # The receipt rule: the model assigns roles, it does not invent hexes.
    assert "Only hex values present in the census" in prompt
    assert "Only hex values present in the census" in design_dna._DNA_TEMPLATE

    # The maturity ladder is embedded, all seven rungs of it.
    assert "MATURITY LADDER" in prompt
    for rung in ("1 —", "2 —", "3 —", "4 —", "5 —", "6 —", "7 —"):
        assert rung in prompt, f"ladder rung {rung!r} went missing"
    assert "FONT-SLOP SIGNAL" in prompt, "the default-stack tell went uninstructed"

    # The tag taxonomy, complete — a tag not offered is a tag never assigned.
    for tag in (
        "Light Canvas", "Clean SaaS", "Editorial Type", "Soft Gradients",
        "Monochrome UI", "Minimalist Brand", "High Contrast", "Premium Design",
        "Dark Instrument", "Playful",
    ):
        assert tag in prompt, f"style tag {tag!r} went missing from the taxonomy"

    # The DESIGN.md section plan, so the artifact has the refero shape.
    for section in ("## Palette", "## Typography", "## Spacing & Shape",
                    "## Do", "## Don't", "## Agent Prompt Guide"):
        assert section in prompt, f"DESIGN.md section {section!r} went missing"


async def test_an_empty_census_is_named_not_papered_over(monkeypatch):
    fake = _install_vision(monkeypatch)

    await extract_design_dna(_capture(style_census={}))

    prompt = fake.calls[0].prompt
    assert "no style numbers could be measured" in prompt
    assert "no hex values you may name" in prompt


# ---------------------------------------------------------------------------
# A valid answer becomes a DesignDNA
# ---------------------------------------------------------------------------


async def test_a_valid_answer_parses_into_design_dna(monkeypatch):
    _install_vision(monkeypatch)

    result = await extract_design_dna(_capture())

    assert isinstance(result, DesignDNA)
    assert result.characterization == "warm paper, sharp ink"
    assert result.tokens.palette[0] == {"hex": "#f5f2ec", "name": "Paper", "role": "page ground"}
    assert result.tokens.fonts[0]["family"] == "Space Grotesk"
    assert result.tokens.radii == {"8px": "cards and buttons"}
    assert result.tokens.theme == "light"
    assert result.style_tags == ["Clean SaaS", "Minimalist Brand"]
    assert result.maturity_level == 3
    assert "stock" in result.maturity_rationale
    assert result.dos and result.donts
    assert result.design_md.startswith("# Example — Design DNA")


# ---------------------------------------------------------------------------
# An unreadable answer: one nudged retry, then a named failure
# ---------------------------------------------------------------------------


async def test_an_unreadable_answer_gets_one_nudged_retry_then_fails(monkeypatch):
    fake = _install_vision(
        monkeypatch, "I studied the page and here are my thoughts!", "still not json"
    )

    with pytest.raises(DesignDNAError) as excinfo:
        await extract_design_dna(_capture())

    assert "could not be read" in str(excinfo.value)
    assert len(fake.calls) == 2, "exactly one retry, no more"
    assert "only valid json" not in fake.calls[0].prompt.lower()
    assert "only valid json" in fake.calls[1].prompt.lower(), "the retry carried no nudge"


async def test_a_bad_first_answer_heals_on_the_retry(monkeypatch):
    # An out-of-ladder maturity score is exactly as unreadable as prose.
    fake = _install_vision(monkeypatch, _payload(maturity_level=9), _payload())

    result = await extract_design_dna(_capture())

    assert result.maturity_level == 3
    assert len(fake.calls) == 2


async def test_a_transport_failure_is_a_readable_error(monkeypatch):
    _install_vision(monkeypatch, RuntimeError("the model timed out"))

    with pytest.raises(DesignDNAError) as excinfo:
        await extract_design_dna(_capture())

    message = str(excinfo.value)
    assert "the model timed out" in message, "the failure does not say why"
    assert "run the page check again" in message.lower()


# ---------------------------------------------------------------------------
# Cost attribution
# ---------------------------------------------------------------------------


async def test_the_call_lands_inside_the_website_design_dna_ledger_stage(monkeypatch):
    entered: list[tuple[str, str | None, str | None]] = []
    inside = {"now": False}

    @contextmanager
    def _recording_usage(stage, simulation_id=None, organization_id=None):
        entered.append((stage, simulation_id, organization_id))
        inside["now"] = True
        try:
            yield
        finally:
            inside["now"] = False

    monkeypatch.setattr(design_dna, "usage_context", _recording_usage)
    fake = _install_vision(monkeypatch)
    fake.probe = lambda: inside["now"]

    await extract_design_dna(_capture(), organization_id="org-1")

    assert entered == [("website_design_dna", None, "org-1")]
    assert all(call.inside_stage for call in fake.calls), (
        "the design read ran outside the ledger stage"
    )


# ---------------------------------------------------------------------------
# Vocabulary: our strings, and the rule the prompt carries
# (mechanics mirror tests/test_website_critics.py)
# ---------------------------------------------------------------------------

JARGON = (
    "ICP",
    "variant",
    "A/B",
    "adversarial",
    "cohort",
    "arena",
    "lens",
    "archetype",
    "canonical",
    "valence",
    "simulation",
    "project",
)


def _pattern(word: str) -> re.Pattern[str]:
    return re.compile(rf"\b{re.escape(word)}s?\b", re.IGNORECASE)


def _hits(text: str) -> list[str]:
    return [word for word in JARGON if _pattern(word).search(text)]


def _rendered_strings() -> dict[str, str]:
    """Every template string of ours that can reach a founder.

    The prompt template is scanned with its `{vocabulary_rule}` slot unfilled,
    so the rule — which must name the banned words to ban them — does not trip
    the scan of the strings around it.
    """
    return {
        "template": design_dna._DNA_TEMPLATE,
        "shape": design_dna._JSON_INSTRUCTION,
        "nudge": design_dna._JSON_NUDGE,
        "no_census": design_dna._NO_CENSUS_TEXT,
        "error.unreadable": design_dna._UNREADABLE_ERROR,
        "error.failed": design_dna._FAILED_ERROR,
    }


def test_no_string_of_ours_uses_a_word_a_founder_has_to_learn():
    offenders = [
        f'{name}: "{word}" in {text[:60]!r}'
        for name, text in _rendered_strings().items()
        for word in _hits(text)
    ]
    assert offenders == []


def test_the_scan_would_catch_a_regression():
    """The canary: the matcher matches and the scan has something to read."""
    assert _hits("An adversarial cohort in the arena") == ["adversarial", "cohort", "arena"]
    assert _hits("Simulations") == ["simulation"]  # the plural hole
    assert _hits("A palette, a pairing, a rhythm.") == []
    assert len(_rendered_strings()) == 6


def test_the_prompt_template_carries_the_shared_vocabulary_rule():
    """The output is written by a model, so the prompt is the lever."""
    assert "{vocabulary_rule}" in design_dna._DNA_TEMPLATE
    built = design_dna._build_prompt(_capture())
    assert VOCABULARY_RULE in built
    # The rule and the scan are two spellings of one list; a word in one and
    # not the other is a word the model is free to use.
    missing = [w for w in JARGON if w.lower() not in VOCABULARY_RULE.lower()]
    assert missing == []
