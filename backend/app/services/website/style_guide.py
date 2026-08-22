# PUBLIC INTERFACE
# ─────────────────────────────────────────────────────────
# build_style_guide(url, page_text, dna, scores_after) -> str
# extract_tokens(html) -> StyleTokens
# ─────────────────────────────────────────────────────────
"""The rules that came with the page, written down.

A redesign handed over as a single HTML file decays the first time somebody
adds a section to it: the next person reads the markup, guesses at the system,
and guesses differently. The guide travels with the page so the founder, their
designer, or the coding tool they paste it into is working from the same
system rather than reverse-engineering one.

**Everything here is derived, never invented.** The colours and faces are read
out of the delivered HTML itself, so the guide cannot describe a system the
page does not have — which is the failure mode of every style guide written
alongside a design rather than from it. The category section is the same brief
that shaped the page. Where a value is absent it is omitted rather than filled
with a plausible default.

No model call. A founder who has already paid for the revision pays nothing to
take it away, and a guide that costs nothing to regenerate is a guide that
stays true after the next edit.
"""
from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass

from app.services.website.verticals import brief_for, classify_vertical

# Colours worth naming. A page uses a long tail of one-off values — borders at
# 4% opacity, a shadow tint — and listing all of them produces a swatch chart
# nobody can act on. The cut is deliberate: a colour used once is not a token.
_MIN_COLOR_USES = 2
_MAX_COLORS = 10
_MAX_FACES = 4

_HEX = re.compile(r"#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6}|[0-9a-fA-F]{8})\b")
_SCRIPT_OR_STYLE = re.compile(
    r"<(script|style)\b[^>]*>.*?</\1\s*>", re.I | re.S
)
_TAG = re.compile(r"<[^>]+>")
# Font stacks are the one declaration that routinely contains quotes — every
# multi-word family is written `"Playfair Display"` or `'DM Mono'`. So this one
# runs to the end of the declaration and lets `_first_family` do the cutting;
# stopping at a quote the way the rules below do would silently skip exactly
# the faces most worth naming.
_FONT_FAMILY = re.compile(r"font-family\s*:\s*([^;}]+)", re.I)
_MAX_FACE_CHARS = 64

# Custom properties, so `font-family: var(--font-mono)` can be answered with
# the face the page actually loads. Modern build output almost never names a
# family at the point of use.
_CUSTOM_PROP = re.compile(r"(--[\w-]+)\s*:\s*([^;}]+)")
_VAR_REF = re.compile(r"var\(\s*(--[\w-]+)", re.I)

# Not typefaces. A guide listing `inherit` as one of a page's four faces is
# worse than a guide listing three: it sends the reader looking for a font
# that does not exist.
_NOT_A_FACE = frozenset(
    {"inherit", "initial", "unset", "revert", "revert-layer", "none", "auto"}
)
_RADIUS = re.compile(r"border-radius\s*:\s*([^;\"'}]+)", re.I)
_SHADOW = re.compile(r"box-shadow\s*:\s*([^;\"'}]+)", re.I)


@dataclass(frozen=True)
class StyleTokens:
    colors: list[tuple[str, int]]
    faces: list[str]
    radii: list[str]
    shadows: list[str]


def _normalize_hex(value: str) -> str:
    v = value.lower()
    if len(v) == 4:  # #abc -> #aabbcc
        return "#" + "".join(c * 2 for c in v[1:])
    return v


def _first_family(stack: str, props: dict[str, str], _depth: int = 0) -> str:
    """The face a stack actually asks for, before its fallbacks.

    The stack may have been captured past its real end — a `style=` attribute
    is closed by a quote, not by a semicolon — so the cut happens here rather
    than in the pattern. A quoted name runs to its closing quote; a bare one
    stops at the first comma or quote, whichever the page reaches first.

    `var(--font-mono)` is followed to what the page defines it as, because
    modern build output almost never names a family at the point of use and
    a guide that answered "your heading font is var(--font-mono)" would be
    technically accurate and completely useless. Two hops, then it gives up
    rather than chasing a cycle.
    """
    text = stack.strip()
    if not text:
        return ""

    ref = _VAR_REF.match(text)
    if ref:
        if _depth >= 2:
            return ""
        target = props.get(ref.group(1))
        return _first_family(target, props, _depth + 1) if target else ""

    if text[0] in "\"'":
        name = text[1:].split(text[0])[0]
    else:
        name = re.split(r"[,\"'>]", text)[0]

    # A face has a name. Escaped declarations inside embedded scripts
    # (`font-family:\"Uncut Sans\"`) otherwise yield a typeface called `\`,
    # which is the kind of line that makes a founder distrust the whole guide.
    name = name.strip().strip("\\").strip()
    if not name or len(name) > _MAX_FACE_CHARS or name.lower() in _NOT_A_FACE:
        return ""
    if not any(c.isalnum() for c in name):
        return ""
    return name


def extract_tokens(html: str) -> StyleTokens:
    """The system the page actually uses, read from the page."""
    colors = Counter(_normalize_hex(m.group(0)) for m in _HEX.finditer(html))

    props = {m.group(1): m.group(2) for m in _CUSTOM_PROP.finditer(html)}

    faces: list[str] = []
    for match in _FONT_FAMILY.finditer(html):
        first = _first_family(match.group(1), props)
        if first and first.lower() not in {f.lower() for f in faces}:
            faces.append(first)

    def _tail(pattern: re.Pattern[str], limit: int) -> list[str]:
        seen: list[str] = []
        for m in pattern.finditer(html):
            # `!important` is about precedence, not shape — and it is what let
            # a "shadow" of `none !important` reach a real page's guide.
            value = " ".join(m.group(1).replace("!important", " ").split())
            if value and value.lower() != "none" and value not in seen:
                seen.append(value)
            if len(seen) >= limit:
                break
        return seen

    return StyleTokens(
        colors=[
            (hexv, n)
            for hexv, n in colors.most_common(_MAX_COLORS)
            if n >= _MIN_COLOR_USES
        ],
        faces=faces[:_MAX_FACES],
        radii=_tail(_RADIUS, 6),
        shadows=_tail(_SHADOW, 4),
    )


def visible_copy(html: str) -> str:
    """The words a reader sees, without the machinery around them.

    The category is decided from what the page *says*, never from how it is
    built. Left raw, a Tailwind page votes with its class names and a React
    bundle votes with its variable names — `patient` in a CSS selector would
    weigh the same as `patient` in a headline, and a devtools page dense with
    `api`/`sdk` in its script tags would classify itself.
    """
    stripped = _SCRIPT_OR_STYLE.sub(" ", html)
    return " ".join(_TAG.sub(" ", stripped).split())


def _dna_line(dna: object, key: str) -> str:
    if isinstance(dna, dict):
        value = dna.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _score_line(scores_after: object) -> str:
    """The measured verdict on the delivered page, if there is one."""
    if not isinstance(scores_after, dict):
        return ""
    overall = scores_after.get("overall")
    if overall is None:
        return ""
    dims = scores_after.get("dimensions")
    detail = ""
    if isinstance(dims, dict) and dims:
        parts = [f"{k.replace('_', ' ')} {v}" for k, v in sorted(dims.items())]
        detail = " — " + ", ".join(parts)
    return f"The critics scored this page **{overall}** overall{detail}."


_CLAIM_HEADINGS = {
    "certification": "Certifications, licences and regulators",
    "figure": "Prices and percentages",
    "scale": "Customer counts",
}

_CLAIM_INTRO = """\
**Check these before you publish.** The rewrite put the statements below on
your page, and none of them appear anywhere in the words we read off your
current site. Some may be true and simply absent from the page we captured —
if so, this is your reminder to say them somewhere provable. Any that are not
true have to come out before this page goes live."""

_CLAIM_WARNING = """\
The first group is the dangerous one. A certification, licence or regulator
named on a page you did not earn is not a wording problem — customers and
regulators act on it. Delete anything in that group you cannot evidence."""


def _claims_section(unsupported_claims: object) -> list[str]:
    """The claims block, rendered from stored rows.

    Takes plain dicts rather than `claims.UnsupportedClaim` so this module
    never imports `claims` — `claims` imports `visible_copy` from here, and the
    other direction would close the cycle.
    """
    rows = [c for c in (unsupported_claims or []) if isinstance(c, dict)]
    if not rows:
        return []

    out = ["## Claims to verify before you publish", "", _CLAIM_INTRO, ""]
    if any(row.get("kind") == "certification" for row in rows):
        out += [_CLAIM_WARNING, ""]

    for kind in ("certification", "figure", "scale"):
        group = [row for row in rows if row.get("kind") == kind]
        if not group:
            continue
        out += [f"### {_CLAIM_HEADINGS[kind]}", ""]
        for row in group:
            text = str(row.get("text") or "").strip()
            quote = str(row.get("quote") or "").strip()
            line = f"- **{text}**"
            if quote:
                # The quote is what makes this actionable — the founder searches
                # index.html for it rather than hunting for the claim.
                line += f' — on the page as: "{quote}"'
            out.append(line)
        out.append("")
    return out


def build_style_guide(
    *,
    url: str,
    page_text: str,
    dna: object = None,
    scores_after: object = None,
    unsupported_claims: object = None,
) -> str:
    """The guide that ships beside the page."""
    tokens = extract_tokens(page_text)
    vertical = classify_vertical(visible_copy(page_text))
    brief = brief_for(vertical)

    site = url.strip() or "your site"
    out: list[str] = [
        f"# Style guide — {site}",
        "",
        "This describes the page in `index.html` beside it. Every value below "
        "was read out of that file rather than written alongside it, so the "
        "guide and the page cannot disagree.",
        "",
    ]

    verdict = _score_line(scores_after)
    if verdict:
        out += [verdict, ""]

    # Placed above everything else on purpose. A founder skims a style guide;
    # they must not have to reach the colour table before learning the page
    # claims a certification they may not hold.
    out += _claims_section(unsupported_claims)

    out += [
        "## Who this page is for",
        "",
        f"**{brief.label}.** {brief.buyer}",
        "",
        f"Before they act on anything here, they have to believe: {brief.must_believe}",
        "",
        "The page has to carry:",
        "",
        *[f"- {line}" for line in brief.evidence],
        "",
        "Reads as a warning sign to this buyer:",
        "",
        *[f"- {line}" for line in brief.red_flags],
        "",
        f"**Visual pressure.** {brief.direction}",
        "",
    ]

    if tokens.colors:
        out += [
            "## Colour",
            "",
            "Ordered by how much of the page each one carries. The first two or "
            "three are the system; the tail is detail.",
            "",
            "| Value | Uses |",
            "|---|---:|",
            *[f"| `{hexv}` | {n} |" for hexv, n in tokens.colors],
            "",
        ]

    if tokens.faces:
        out += [
            "## Type",
            "",
            *[f"- `{face}`" for face in tokens.faces],
            "",
            (
                "One face, carried by size and weight alone. Reach for a second "
                "only when it is doing work this one cannot."
                if len(tokens.faces) == 1
                else "Keep the count where it is. One face more than a page "
                "needs is the most common way a coherent page stops being one."
            ),
            "",
        ]

    if tokens.radii or tokens.shadows:
        out += ["## Shape and depth", ""]
        if tokens.radii:
            out += ["Corner radii in use: " + ", ".join(f"`{r}`" for r in tokens.radii), ""]
        if tokens.shadows:
            out += [
                "Shadows in use:",
                "",
                *[f"- `{s}`" for s in tokens.shadows],
                "",
            ]

    characterization = _dna_line(dna, "characterization")
    summary = _dna_line(dna, "summary")
    if characterization or summary:
        out += ["## Where this came from", ""]
        if characterization:
            out += [f"The site as it was: *{characterization}*", ""]
        if summary:
            out += [summary, ""]

    out += [
        "## Adding to this page later",
        "",
        "1. Take colours from the table above. A new hue is a decision, not a "
        "detail — it needs the same argument the existing ones had.",
        "2. Reuse a radius and a shadow that already appear here rather than "
        "introducing a neighbouring value; two radii four pixels apart read as "
        "a mistake rather than as a system.",
        "3. Anything that carries a number needs its source on the page. This "
        "buyer treats an unsourced figure as a reason to doubt the sourced "
        "ones.",
        "4. Where this page uses a placeholder, it is because the material did "
        "not contain the fact. Fill it in — do not delete the section and do "
        "not invent the number.",
        "",
        "---",
        "",
        "Generated by Saibyl · Saido Labs LLC, from the page it describes.",
    ]

    return "\n".join(out)
