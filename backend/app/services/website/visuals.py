# PUBLIC INTERFACE
# ─────────────────────────────────────────────────────────
# render_visuals(html, *, palette) -> tuple[str, list[str]]
# VISUAL_CATALOGUE, PRIMITIVES, Palette, palette_from_brief
# ─────────────────────────────────────────────────────────
"""Graphics the rewrite can draw, made of the founder's own content.

**Why a kit instead of letting the model draw.** The revision loop already
produces a complete HTML document, so it *could* hand-write SVG. It should not:
hand-drawn SVG is a quality lottery, and the thing being gambled is the one
property this product sells — that the page does not look machine-made. The
split here is the one the rest of the codebase already uses. **The model
chooses which graphic and supplies the content; this module draws it**, so the
radii come off a scale, the shadow carries its inset highlight, and the motion
collapses under `prefers-reduced-motion` every single time.

**Nothing here is raster, and that is a product decision rather than a
convenience.** A generated hero image would raise the visual score and lower
`found`: a crawler receives an opaque blob where the argument used to be. An
SVG chart raises both, because its labels are text. The website check judges
two audiences now, and drawing in code is the only option that serves both.

There is a sharper reason too. `taste.py` exists to detect pages that look
generated, and its rules — `not_the_slop_palette`, `no_banned_display_face` —
target exactly what generated imagery produces. A Saibyl that generated
pictures would be scoring its own output with a rubric built to catch it.

**The craft is ours; the palette is the founder's.** Everything below takes a
`Palette` read from that page's own design brief. What the kit fixes is
proportion, radius, depth and motion — the things a founder's page is being
marked on — never their colours. A kit that painted every rewrite Saibyl blue
would be the "one template" defect the whole product exists to name.

**A graphic with nothing in it is worse than no graphic.** Every primitive
returns an empty string when its content is missing, so a rewrite cannot buy
the imagery requirement with an empty frame. That lesson is one day old: on
2026-08-30 a labelled placeholder was found passing `requires_an_image` and
buying 27 points, and the census now refuses to count anything that declares
itself a stand-in. Nothing here declares itself a stand-in, because nothing
here is one.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from html import escape

import structlog

logger = structlog.get_logger()


# ── the palette ──────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Palette:
    """Six roles, which is what a graphic needs and what a system defines.

    Defaults are a neutral slate rather than Saibyl's own blue: a rewrite whose
    design brief could not be read should look unbranded, not like us.
    """

    ink: str = "#1e293b"
    muted: str = "#64748b"
    accent: str = "#3b5bdb"
    accent_soft: str = "#748ffc"
    surface: str = "#ffffff"
    ground: str = "#f1f5f9"

    @property
    def gradient(self) -> str:
        return f"linear-gradient(135deg,{self.accent},{self.accent_soft})"


_HEX = re.compile(r"^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6})$")


def _hex_or(value: object, fallback: str) -> str:
    text = str(value or "").strip()
    return text if _HEX.match(text) else fallback


def palette_from_brief(brief: dict | None) -> Palette:
    """The founder's own colours, by the role their brief assigned them.

    Roles are matched loosely because the brief is model-written and its
    vocabulary drifts — "primary", "brand" and "accent" all mean the same
    thing to a designer. Anything unmatched falls back to the neutral default
    rather than to a guess, since a wrong accent is louder than a plain one.
    """
    if not isinstance(brief, dict):
        return Palette()
    tokens = brief.get("tokens")
    entries = (tokens or {}).get("palette") if isinstance(tokens, dict) else None
    if not isinstance(entries, list):
        return Palette()

    by_role: dict[str, str] = {}
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        role = str(entry.get("role") or entry.get("name") or "").casefold()
        value = _hex_or(entry.get("hex"), "")
        if role and value:
            by_role.setdefault(role, value)

    def pick(*words: str, fallback: str) -> str:
        for want in words:
            for role, value in by_role.items():
                if want in role:
                    return value
        return fallback

    base = Palette()
    return Palette(
        ink=pick("ink", "text", "foreground", "body", fallback=base.ink),
        muted=pick("muted", "secondary", "subtle", "grey", "gray", fallback=base.muted),
        accent=pick("accent", "primary", "brand", "action", fallback=base.accent),
        accent_soft=pick("soft", "light", "tint", "hover", fallback=base.accent),
        surface=pick("surface", "card", "panel", "white", fallback=base.surface),
        ground=pick("ground", "background", "canvas", "base", fallback=base.ground),
    )


# ── the shared style block ───────────────────────────────────────────────────
#
# Injected once when any primitive is used. The motion here is the entrance
# layer from the rewrite's own rule — one rise, never a loop — and it collapses
# under the reader's preference, at .01ms rather than `none` so anything
# waiting on `animationend` still fires.

_STYLE_ID = "saibyl-visuals"

_SHARED_STYLE = """<style id="{sid}">
.sv-fig{{margin:0 0 8px;max-width:100%}}
.sv-fig svg{{width:100%;height:auto;display:block}}
.sv-cap{{font:400 12.5px/1.5 system-ui,-apple-system,"Segoe UI",sans-serif;
  color:{muted};margin-top:8px}}
.sv-stats{{display:flex;flex-wrap:wrap;gap:20px;margin:0;padding:0;list-style:none}}
.sv-stat{{flex:1 1 140px;background:{surface};border:1px solid {ground};
  border-radius:16px;padding:16px 18px;
  box-shadow:0 6px 16px rgba(15,23,42,.05),inset 0 1px rgba(255,255,255,.4);
  transition:transform .22s ease}}
.sv-stat:hover{{transform:translateY(-2px)}}
.sv-stat b{{display:block;font:600 28px/1.1 system-ui,-apple-system,"Segoe UI",sans-serif;
  color:{ink};font-variant-numeric:tabular-nums}}
.sv-stat span{{display:block;margin-top:6px;
  font:400 12.5px/1.4 system-ui,-apple-system,"Segoe UI",sans-serif;color:{muted}}}
.sv-rise{{animation:sv-rise .5s cubic-bezier(.2,.7,.3,1) both}}
@keyframes sv-rise{{from{{opacity:0;transform:translateY(10px)}}
  to{{opacity:1;transform:none}}}}
@media (prefers-reduced-motion: reduce){{
  .sv-rise,.sv-stat{{animation-duration:.01ms!important;
    animation-iteration-count:1!important;transition-duration:.01ms!important}}
}}
</style>"""


def _shared_style(palette: Palette) -> str:
    return _SHARED_STYLE.format(
        sid=_STYLE_ID,
        ink=palette.ink,
        muted=palette.muted,
        surface=palette.surface,
        ground=palette.ground,
    )


# ── helpers ──────────────────────────────────────────────────────────────────


def _text(value: object, limit: int = 120) -> str:
    """Escaped, bounded, and single-line. Everything drawn here is founder copy."""
    return escape(" ".join(str(value or "").split())[:limit], quote=True)


def _number(value: object) -> float | None:
    try:
        return float(str(value).replace(",", "").strip())
    except (TypeError, ValueError):
        return None


def _rows(payload: dict, key: str = "rows") -> list[dict]:
    rows = payload.get(key)
    return [r for r in rows if isinstance(r, dict)] if isinstance(rows, list) else []


def _figure(body: str, caption: object, title: str) -> str:
    cap = _text(caption, 200)
    caption_html = f'<figcaption class="sv-cap">{cap}</figcaption>' if cap else ""
    return f'<figure class="sv-fig sv-rise" role="group" aria-label="{title}">{body}{caption_html}</figure>'


# ── the primitives ───────────────────────────────────────────────────────────
#
# Each takes the model's payload and the founder's palette, and each returns ""
# when the payload carries nothing worth drawing.


def bar_chart(payload: dict, palette: Palette) -> str:
    """Ranked values as horizontal bars. The workhorse: any "N of M", any
    ranked list, any before/after belongs here rather than in prose."""
    rows = [
        (_text(r.get("label"), 60), _number(r.get("value")))
        for r in _rows(payload)
    ]
    rows = [(label, value) for label, value in rows if label and value is not None]
    if not rows:
        return ""
    rows = rows[:8]
    top = max(value for _, value in rows) or 1.0

    row_h, gap, label_w, pad = 34, 10, 150, 12
    width = 640
    height = pad * 2 + len(rows) * row_h + (len(rows) - 1) * gap
    bar_max = width - label_w - pad * 2 - 56

    title = _text(payload.get("title"), 80) or "chart"
    parts = [
        f'<svg viewBox="0 0 {width} {height}" role="img" aria-label="{title}" '
        f'xmlns="http://www.w3.org/2000/svg">',
        f"<title>{title}</title>",
        f'<defs><linearGradient id="svbar" x1="0" y1="0" x2="1" y2="0">'
        f'<stop offset="0" stop-color="{palette.accent}"/>'
        f'<stop offset="1" stop-color="{palette.accent_soft}"/></linearGradient></defs>',
        f'<rect width="{width}" height="{height}" rx="20" fill="{palette.ground}"/>',
    ]
    y = pad
    for label, value in rows:
        bar = max(6, round(bar_max * (value / top)))
        text_y = y + row_h / 2 + 4
        clean = f"{value:g}" if value % 1 else str(int(value))
        parts += [
            f'<text x="{pad + 4}" y="{text_y}" fill="{palette.ink}" '
            f'font-family="system-ui,-apple-system,Segoe UI,sans-serif" '
            f'font-size="13">{label}</text>',
            f'<rect x="{label_w}" y="{y + 6}" width="{bar}" height="{row_h - 12}" '
            f'rx="11" fill="url(#svbar)"/>',
            f'<text x="{label_w + bar + 10}" y="{text_y}" fill="{palette.muted}" '
            f'font-family="system-ui,-apple-system,Segoe UI,sans-serif" '
            f'font-size="12.5">{clean}</text>',
        ]
        y += row_h + gap
    parts.append("</svg>")
    return _figure("".join(parts), payload.get("caption"), title)


def step_diagram(payload: dict, palette: Palette) -> str:
    """A numbered flow. What most pages write as a paragraph and a reader skips."""
    steps = [_text(s, 44) for s in (payload.get("steps") or []) if _text(s, 44)]
    if len(steps) < 2:
        return ""
    steps = steps[:5]

    box_w, box_h, gap, pad = 168, 96, 26, 16
    width = pad * 2 + len(steps) * box_w + (len(steps) - 1) * gap
    height = pad * 2 + box_h
    title = _text(payload.get("title"), 80) or "how it works"

    parts = [
        f'<svg viewBox="0 0 {width} {height}" role="img" aria-label="{title}" '
        f'xmlns="http://www.w3.org/2000/svg">',
        f"<title>{title}</title>",
    ]
    x = pad
    for i, step in enumerate(steps, 1):
        parts += [
            f'<rect x="{x}" y="{pad}" width="{box_w}" height="{box_h}" rx="18" '
            f'fill="{palette.surface}" stroke="{palette.ground}"/>',
            f'<circle cx="{x + 24}" cy="{pad + 26}" r="13" fill="{palette.accent}"/>',
            f'<text x="{x + 24}" y="{pad + 31}" text-anchor="middle" fill="#ffffff" '
            f'font-family="system-ui,-apple-system,Segoe UI,sans-serif" '
            f'font-size="13" font-weight="600">{i}</text>',
        ]
        # Two lines, because a step name that wraps is a step name that fits.
        words, line, lines = step.split(" "), "", []
        for word in words:
            if len(line) + len(word) + 1 > 20 and line:
                lines.append(line)
                line = word
            else:
                line = f"{line} {word}".strip()
        if line:
            lines.append(line)
        for j, text_line in enumerate(lines[:2]):
            parts.append(
                f'<text x="{x + 16}" y="{pad + 62 + j * 17}" fill="{palette.ink}" '
                f'font-family="system-ui,-apple-system,Segoe UI,sans-serif" '
                f'font-size="13">{text_line}</text>'
            )
        if i < len(steps):
            arrow_x = x + box_w + gap / 2
            parts.append(
                f'<path d="M{arrow_x - 6} {pad + box_h / 2} h12 m-5 -5 l5 5 l-5 5" '
                f'stroke="{palette.muted}" stroke-width="1.5" fill="none" '
                f'stroke-linecap="round" stroke-linejoin="round"/>'
            )
        x += box_w + gap
    parts.append("</svg>")
    return _figure("".join(parts), payload.get("caption"), title)


def stat_band(payload: dict, palette: Palette) -> str:
    """Two to four numbers the page already claims, given room to be read.

    Deliberately HTML rather than SVG: these are numbers a reader quotes and a
    machine should be able to lift, so they are real text in a real list. It
    does **not** count as imagery, and should not — a row of figures is
    typography, and calling it a picture is how the imagery rule gets gamed.
    """
    stats = []
    for row in _rows(payload, "stats"):
        value = _text(row.get("value"), 16)
        label = _text(row.get("label"), 48)
        if value and label:
            stats.append((value, label))
    if len(stats) < 2:
        return ""
    items = "".join(
        f'<li class="sv-stat"><b>{value}</b><span>{label}</span></li>'
        for value, label in stats[:4]
    )
    return f'<ul class="sv-stats sv-rise">{items}</ul>'


def device_frame(payload: dict, palette: Palette) -> str:
    """A browser shell around the page's own words.

    The one primitive that depicts the product rather than arguing about it,
    and it needs no screenshot: the founder's own headline set inside a window
    chrome reads as the thing itself, and stays text a crawler can read.
    """
    heading = _text(payload.get("heading"), 60)
    if not heading:
        return ""
    lines = [_text(line, 56) for line in (payload.get("lines") or [])][:3]
    width, height = 640, 300
    title = _text(payload.get("title"), 80) or "the product"

    parts = [
        f'<svg viewBox="0 0 {width} {height}" role="img" aria-label="{title}" '
        f'xmlns="http://www.w3.org/2000/svg">',
        f"<title>{title}</title>",
        f'<rect width="{width}" height="{height}" rx="20" fill="{palette.surface}" '
        f'stroke="{palette.ground}"/>',
        f'<rect width="{width}" height="40" rx="20" fill="{palette.ground}"/>',
        f'<rect y="26" width="{width}" height="14" fill="{palette.ground}"/>',
    ]
    for i, cx in enumerate((22, 42, 62)):
        parts.append(f'<circle cx="{cx}" cy="20" r="5" fill="{palette.muted}" opacity="{0.35 + i * 0.12:.2f}"/>')
    parts.append(
        f'<text x="28" y="104" fill="{palette.ink}" '
        f'font-family="system-ui,-apple-system,Segoe UI,sans-serif" '
        f'font-size="26" font-weight="600">{heading}</text>'
    )
    for j, line in enumerate(lines):
        parts.append(
            f'<text x="28" y="{140 + j * 24}" fill="{palette.muted}" '
            f'font-family="system-ui,-apple-system,Segoe UI,sans-serif" '
            f'font-size="14">{line}</text>'
        )
    action = _text(payload.get("action"), 24)
    if action:
        parts += [
            f'<rect x="28" y="{150 + len(lines) * 24}" width="176" height="44" rx="13" '
            f'fill="{palette.accent}"/>',
            f'<text x="116" y="{178 + len(lines) * 24}" text-anchor="middle" fill="#ffffff" '
            f'font-family="system-ui,-apple-system,Segoe UI,sans-serif" '
            f'font-size="14" font-weight="600">{action}</text>',
        ]
    parts.append("</svg>")
    return _figure("".join(parts), payload.get("caption"), title)


PRIMITIVES = {
    "bar_chart": bar_chart,
    "step_diagram": step_diagram,
    "stat_band": stat_band,
    "device_frame": device_frame,
}


# ── the catalogue the model is given ─────────────────────────────────────────

VISUAL_CATALOGUE = """\
GRAPHICS — draw with these, never with hand-written SVG or an <img>.

Write a marker where the graphic belongs and nothing else; it is replaced with
finished artwork in the page's own colours. Every value must come from the
page's real words: a chart of numbers the page does not claim is a fabrication,
and it is checked for.

  <!--saibyl:bar_chart {"title":"Where the hours go","rows":[
      {"label":"Chasing invoices","value":9},{"label":"Actual work","value":4}],
      "caption":"From the survey quoted above."}-->

  <!--saibyl:step_diagram {"title":"How it works","steps":[
      "Connect your inbox","We draft the chase","You approve","It sends"]}-->

  <!--saibyl:stat_band {"stats":[{"value":"3 min","label":"to first draft"},
      {"value":"$0","label":"until you send one"}]}-->

  <!--saibyl:device_frame {"heading":"Your headline here",
      "lines":["The sub-line the page already uses"],"action":"Start free"}-->

Rules:
- Use at most three graphics on the page, and only where one carries an
  argument the prose is making badly. A page of charts is not a designed page.
- `bar_chart` needs 2-8 rows with real numbers. `step_diagram` needs 2-5 steps.
  `stat_band` needs 2-4 figures. Anything short of that draws nothing.
- Do not invent a number, a step or a claim to fill one in. If the page does
  not supply the content, leave the graphic out."""


# ── substitution ─────────────────────────────────────────────────────────────

#: `<!--saibyl:name {json}-->`, with whitespace and newlines tolerated because
#: a model will pretty-print the payload about half the time.
_MARKER = re.compile(r"<!--\s*saibyl:([a-z_]+)\s*(\{.*?\})\s*-->", re.DOTALL)


def render_visuals(html: str, *, palette: Palette | None = None) -> tuple[str, list[str]]:
    """Replace every marker with finished artwork. Returns `(html, drawn)`.

    **A marker that cannot be drawn is left exactly where it is**, which
    renders as an HTML comment: invisible to the reader, harmless to the
    layout, and still in the source where the next round can see it. The
    alternative — substituting an apology, or dropping the surrounding
    markup — would put a defect on the founder's page to report a defect in
    ours.
    """
    if not html or "saibyl:" not in html:
        return html or "", []

    palette = palette or Palette()
    drawn: list[str] = []

    def one(match: re.Match) -> str:
        name = match.group(1)
        primitive = PRIMITIVES.get(name)
        if primitive is None:
            logger.info("visuals_unknown_primitive", name=name)
            return match.group(0)
        try:
            payload = json.loads(match.group(2))
        except json.JSONDecodeError:
            logger.info("visuals_bad_payload", name=name)
            return match.group(0)
        if not isinstance(payload, dict):
            return match.group(0)
        try:
            svg = primitive(payload, palette)
        except Exception:  # noqa: BLE001 - a broken graphic must not break a page
            logger.warning("visuals_primitive_raised", name=name, exc_info=True)
            return match.group(0)
        if not svg:
            logger.info("visuals_empty_payload", name=name)
            return match.group(0)
        drawn.append(name)
        return svg

    rendered = _MARKER.sub(one, html)
    if drawn and _STYLE_ID not in rendered:
        style = _shared_style(palette)
        if "</head>" in rendered:
            rendered = rendered.replace("</head>", f"{style}</head>", 1)
        else:
            rendered = style + rendered
    logger.info("visuals_rendered", drawn=drawn)
    return rendered, drawn
