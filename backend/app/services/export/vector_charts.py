# PUBLIC INTERFACE
# ─────────────────────────────────────────────────────────
# FIGURE_WIDTH_PT
# IntervalRow, StanceSegment
# format_signed(value, digits) -> str
# format_interval(mean, lower, upper, n) -> str
# sentiment_arc_svg(points) -> str
# interval_rows_svg(rows, *, domain, axis_label, zero_rule) -> str
# stance_bar_svg(segments) -> str
# ─────────────────────────────────────────────────────────
"""Charts drawn as vector SVG, sized for an 8.5×11 page and legible in greyscale.

Three properties this module exists to guarantee, none of which a screenshot of a
web chart can provide:

**Vector, not raster.** The figures are emitted as SVG and embedded in the flow,
so they are resolution-independent: the type inside a chart is the same type as
the type around it, at the same weight, and it stays sharp at 600 dpi. The
previous exporter rendered matplotlib PNGs at 150 dpi and scaled them to fit,
which is why axis labels arrived soft.

**Never colour-only.** This is a document people print, and a meaningful number of
them print it in greyscale. Every distinction here is carried by at least two of:
luminance (the palette is neutral, so a colour print and a greyscale print are
the same image), texture (diagonal hatching, drawn as real line geometry rather
than a `<pattern>` fill so it survives any renderer), and a direct label on the
mark itself. No reader has to consult a legend to read a value.

**A mean is never drawn without its interval.** Every estimate here is plotted as
a point with its 95% band. There is no entry point to this module that accepts a
bare mean, which is the structural version of the rule rather than a convention
somebody has to remember.

Unmeasured is absent, not zero. `Interval(mean=0, lower=0, upper=0, n=0)` is what
`analysis_data.mean_interval` returns when nothing was measured, and callers drop
those rows before they reach here — a zero-height bar reads as "the swarm was
neutral", which is a different and false claim.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

# US Letter at the document's 0.9in side margins: 8.5in − 1.8in = 6.7in.
FIGURE_WIDTH_PT = 482.0

# A neutral ink scale. Chosen so a colour print and a greyscale print are the
# same image — there is no hue anywhere in a figure carrying meaning.
INK = "#14181d"
INK_MID = "#5a6570"
INK_SOFT = "#909aa4"
RULE = "#b9c2ca"
GRID = "#e2e7eb"
FILL_DARK = "#2b343d"
FILL_MID = "#828d98"
FILL_LIGHT = "#e6eaee"

SANS = "Liberation Sans, DejaVu Sans, Helvetica, Arial, sans-serif"

MINUS = "−"  # A real minus sign. A hyphen at 7pt reads as a dash.


@dataclass(frozen=True)
class IntervalRow:
    """One estimate: a label, a mean, its 95% band, and the n behind it."""

    label: str
    mean: float
    lower: float
    upper: float
    n: int
    note: str = ""
    emphasis: bool = False


@dataclass(frozen=True)
class StanceSegment:
    label: str
    pct: float


# ── formatting ───────────────────────────────────────────────────────


def format_signed(value: float, digits: int = 2) -> str:
    text = f"{abs(value):.{digits}f}"
    if value < 0:
        return f"{MINUS}{text}"
    return f"+{text}"


def format_plain(value: float, digits: int = 2) -> str:
    text = f"{abs(value):.{digits}f}"
    return f"{MINUS}{text}" if value < 0 else text


def format_interval(mean: float, lower: float, upper: float, n: int, digits: int = 2) -> str:
    """A mean and its band in the one format the whole document uses."""
    return (
        f"{format_signed(mean, digits)} "
        f"[{format_signed(lower, digits)}, {format_signed(upper, digits)}] "
        f"n={n}"
    )


def _esc(text: object) -> str:
    return (
        str(text)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def _n(value: float) -> str:
    """Round coordinates so the SVG stays small and diff-stable."""
    return f"{value:.2f}".rstrip("0").rstrip(".") or "0"


# ── geometry helpers ─────────────────────────────────────────────────


def _clip(
    x0: float, y0: float, x1: float, y1: float,
    xmin: float, ymin: float, xmax: float, ymax: float,
) -> tuple[float, float, float, float] | None:
    """Liang–Barsky clip of a segment to a rectangle."""
    dx, dy = x1 - x0, y1 - y0
    t0, t1 = 0.0, 1.0
    for p, q in ((-dx, x0 - xmin), (dx, xmax - x0), (-dy, y0 - ymin), (dy, ymax - y0)):
        if p == 0:
            if q < 0:
                return None
        else:
            r = q / p
            if p < 0:
                if r > t1:
                    return None
                t0 = max(t0, r)
            else:
                if r < t0:
                    return None
                t1 = min(t1, r)
    return (x0 + t0 * dx, y0 + t0 * dy, x0 + t1 * dx, y0 + t1 * dy)


def _hatch(
    x: float, y: float, w: float, h: float,
    *, spacing: float = 3.2, angle_deg: float = 45.0,
    stroke: str = INK, width: float = 0.6,
) -> str:
    """Diagonal hatching for a rectangle, as clipped line geometry.

    Drawn as explicit `<line>` elements rather than an SVG `<pattern>` fill.
    Patterns are the part of the SVG specification renderers disagree about, and
    a texture that silently does not render takes the greyscale distinction with
    it — leaving a chart that is once again colour-only.
    """
    if w <= 0 or h <= 0:
        return ""
    theta = math.radians(angle_deg)
    dx, dy = math.cos(theta), math.sin(theta)
    # Normal to the hatch direction; offsets are measured along it.
    nx, ny = -dy, dx
    corners = ((x, y), (x + w, y), (x, y + h), (x + w, y + h))
    projections = [px * nx + py * ny for px, py in corners]
    start = math.floor(min(projections) / spacing) * spacing
    end = max(projections)
    span = math.hypot(w, h) + spacing
    # Each candidate line is generated around the rectangle's centre, not around
    # the origin. Generating around the origin produced segments that were the
    # right length but hundreds of points away from any rectangle not sitting at
    # the top-left of the canvas, so every one of them clipped to nothing and
    # the hatching silently vanished.
    centre = (x + w / 2) * dx + (y + h / 2) * dy

    parts: list[str] = []
    offset = start
    while offset <= end:
        px = nx * offset + dx * centre
        py = ny * offset + dy * centre
        segment = _clip(
            px - dx * span, py - dy * span, px + dx * span, py + dy * span,
            x, y, x + w, y + h,
        )
        if segment:
            x0, y0, x1, y1 = segment
            parts.append(
                f'<line x1="{_n(x0)}" y1="{_n(y0)}" x2="{_n(x1)}" y2="{_n(y1)}"/>'
            )
        offset += spacing
    if not parts:
        return ""
    return (
        f'<g stroke="{stroke}" stroke-width="{width}" stroke-linecap="butt">'
        f'{"".join(parts)}</g>'
    )


def _text(
    x: float, y: float, content: str,
    *, size: float = 7.0, anchor: str = "start",
    fill: str = INK, weight: str = "normal", style: str = "normal",
) -> str:
    return (
        f'<text x="{_n(x)}" y="{_n(y)}" font-family="{SANS}" font-size="{_n(size)}" '
        f'text-anchor="{anchor}" fill="{fill}" font-weight="{weight}" '
        f'font-style="{style}">{_esc(content)}</text>'
    )


def _svg(width: float, height: float, body: str, title: str) -> str:
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{_n(width)}pt" '
        f'height="{_n(height)}pt" viewBox="0 0 {_n(width)} {_n(height)}" '
        f'role="img" aria-label="{_esc(title)}">'
        f"<title>{_esc(title)}</title>{body}</svg>"
    )


# ── figures ──────────────────────────────────────────────────────────


def sentiment_arc_svg(rows: list[IntervalRow]) -> str:
    """Mean valence per round as columns, each with its 95% band.

    Rows are positioned by round number rather than by list index, so a round
    that produced no measurable opinion appears as a gap. Plotting by index
    would close the gap and turn an absence into a smooth arc — the exact
    move the measurement layer was built to stop.
    """
    if not rows:
        return ""

    numbers: list[int] = []
    for row in rows:
        try:
            numbers.append(int(str(row.label)))
        except (TypeError, ValueError):
            numbers.append(len(numbers) + 1)

    width = FIGURE_WIDTH_PT
    pad_l, pad_r, pad_t, pad_b = 34.0, 10.0, 20.0, 26.0
    plot_w = width - pad_l - pad_r
    plot_h = 128.0
    height = plot_h + pad_t + pad_b

    lo, hi = min(numbers), max(numbers)
    slots = max(1, hi - lo + 1)
    band = plot_w / slots
    bar_w = min(24.0, max(4.0, band * 0.5))

    def y_of(value: float) -> float:
        clamped = max(-1.0, min(1.0, value))
        return pad_t + (1.0 - clamped) / 2.0 * plot_h

    def x_of(number: int) -> float:
        return pad_l + (number - lo + 0.5) * band

    parts: list[str] = []

    for tick in (1.0, 0.5, 0.0, -0.5, -1.0):
        y = y_of(tick)
        colour = INK_MID if tick == 0.0 else GRID
        dash = "" if tick == 0.0 else ' stroke-dasharray="2 2"'
        parts.append(
            f'<line x1="{_n(pad_l)}" y1="{_n(y)}" x2="{_n(pad_l + plot_w)}" '
            f'y2="{_n(y)}" stroke="{colour}" stroke-width="0.6"{dash}/>'
        )
        label = "0" if tick == 0.0 else format_signed(tick, 1)
        parts.append(
            _text(pad_l - 5, y + 2.4, label, size=6.5, anchor="end", fill=INK_SOFT)
        )

    label_values = len(rows) <= 14
    label_ticks = max(1, math.ceil(slots / 18))

    for row, number in zip(rows, numbers):
        cx = x_of(number)
        top = y_of(max(row.mean, 0.0))
        bottom = y_of(min(row.mean, 0.0))
        bar_h = max(0.6, bottom - top)
        bx = cx - bar_w / 2

        if row.mean >= 0:
            parts.append(
                f'<rect x="{_n(bx)}" y="{_n(top)}" width="{_n(bar_w)}" '
                f'height="{_n(bar_h)}" fill="{FILL_DARK}"/>'
            )
        else:
            # Negative bars are hollow with hatching: sign is carried by
            # texture, not by hue, so it survives a greyscale print.
            parts.append(
                f'<rect x="{_n(bx)}" y="{_n(top)}" width="{_n(bar_w)}" '
                f'height="{_n(bar_h)}" fill="#ffffff" stroke="{INK}" stroke-width="0.7"/>'
            )
            parts.append(_hatch(bx, top, bar_w, bar_h, spacing=3.0, stroke=INK_MID))

        upper_y, lower_y = y_of(row.upper), y_of(row.lower)
        cap = min(5.0, bar_w * 0.4)
        parts.append(
            f'<line x1="{_n(cx)}" y1="{_n(upper_y)}" x2="{_n(cx)}" y2="{_n(lower_y)}" '
            f'stroke="{INK}" stroke-width="0.9"/>'
            f'<line x1="{_n(cx - cap)}" y1="{_n(upper_y)}" x2="{_n(cx + cap)}" '
            f'y2="{_n(upper_y)}" stroke="{INK}" stroke-width="0.9"/>'
            f'<line x1="{_n(cx - cap)}" y1="{_n(lower_y)}" x2="{_n(cx + cap)}" '
            f'y2="{_n(lower_y)}" stroke="{INK}" stroke-width="0.9"/>'
        )

        if label_values:
            label_y = upper_y - 4 if row.mean >= 0 else lower_y + 8
            parts.append(
                _text(cx, label_y, format_signed(row.mean), size=6.4,
                      anchor="middle", weight="bold")
            )

        if (number - lo) % label_ticks == 0:
            parts.append(
                _text(cx, pad_t + plot_h + 12, f"R{number}", size=6.6,
                      anchor="middle", fill=INK_MID)
            )

    parts.append(
        f'<line x1="{_n(pad_l)}" y1="{_n(pad_t + plot_h)}" x2="{_n(pad_l + plot_w)}" '
        f'y2="{_n(pad_t + plot_h)}" stroke="{RULE}" stroke-width="0.6"/>'
    )
    parts.append(
        _text(pad_l, pad_t + plot_h + 22, "Round", size=6.6, fill=INK_MID)
    )
    parts.append(
        _text(pad_l, 10, "Mean sentiment, −1 to +1, with 95% interval",
              size=6.6, fill=INK_MID)
    )

    return _svg(FIGURE_WIDTH_PT, height, "".join(parts), "Mean sentiment by round")


def interval_rows_svg(
    rows: list[IntervalRow],
    *,
    domain: tuple[float, float] = (-1.0, 1.0),
    axis_label: str = "Mean sentiment, −1 to +1",
    signed: bool = True,
    digits: int = 2,
) -> str:
    """A dot-and-whisker row per estimate, with the figures printed alongside.

    The right form for point estimates that carry intervals: the reader compares
    bands, and overlapping bands are visibly overlapping rather than two bars of
    slightly different length. The numbers are printed on the figure so it can be
    read without the surrounding table.
    """
    if not rows:
        return ""

    width = FIGURE_WIDTH_PT
    label_w = 104.0
    stats_w = 132.0
    gap = 10.0
    plot_x = label_w + gap
    plot_w = width - label_w - stats_w - gap * 2
    # A row with a footnote needs a second line of space, or the note lands on
    # the next row's shading and reads as belonging to it.
    has_notes = any(row.note for row in rows)
    row_h = 21.0 if has_notes else 15.0
    pad_t, pad_b = 16.0, 18.0
    height = pad_t + row_h * len(rows) + pad_b

    lo, hi = domain
    span = (hi - lo) or 1.0

    def x_of(value: float) -> float:
        clamped = max(lo, min(hi, value))
        return plot_x + (clamped - lo) / span * plot_w

    fmt = format_signed if signed else format_plain
    # Banding first, so the gridlines and marks sit on top of it rather than
    # being washed out by a translucent rectangle drawn over them.
    parts: list[str] = [
        f'<rect x="0" y="{_n(pad_t + row_h * index)}" width="{_n(width)}" '
        f'height="{_n(row_h)}" fill="{FILL_LIGHT}"/>'
        for index in range(len(rows))
        if index % 2 == 1
    ]

    # A signed scale gets its midpoints; a rate scale gets thirds. Five ticks on
    # 0–1 round to "0.2" and "0.8" at one decimal, which is wrong on the page.
    ticks = [lo, lo / 2, 0.0, hi / 2, hi] if lo < 0 < hi else [
        lo, lo + span / 2, hi
    ]
    for tick in ticks:
        x = x_of(tick)
        is_zero = abs(tick) < 1e-9 and lo < 0 < hi
        stroke = INK_MID if is_zero else GRID
        dash = "" if is_zero else ' stroke-dasharray="2 2"'
        parts.append(
            f'<line x1="{_n(x)}" y1="{_n(pad_t - 4)}" x2="{_n(x)}" '
            f'y2="{_n(pad_t + row_h * len(rows))}" '
            f'stroke="{stroke}" stroke-width="0.6"{dash}/>'
        )
        label = "0" if is_zero else fmt(tick, 1)
        parts.append(
            _text(x, pad_t - 8, label, size=6.2, anchor="middle", fill=INK_SOFT)
        )

    for index, row in enumerate(rows):
        top = pad_t + row_h * index
        cy = top + (8.0 if has_notes else row_h / 2)
        parts.append(
            _text(0, cy + 2.4, row.label, size=7.2,
                  weight="bold" if row.emphasis else "normal")
        )

        x_lo, x_hi, x_mid = x_of(row.lower), x_of(row.upper), x_of(row.mean)
        parts.append(
            f'<line x1="{_n(x_lo)}" y1="{_n(cy)}" x2="{_n(x_hi)}" y2="{_n(cy)}" '
            f'stroke="{INK_MID}" stroke-width="0.9"/>'
            f'<line x1="{_n(x_lo)}" y1="{_n(cy - 3)}" x2="{_n(x_lo)}" y2="{_n(cy + 3)}" '
            f'stroke="{INK_MID}" stroke-width="0.9"/>'
            f'<line x1="{_n(x_hi)}" y1="{_n(cy - 3)}" x2="{_n(x_hi)}" y2="{_n(cy + 3)}" '
            f'stroke="{INK_MID}" stroke-width="0.9"/>'
        )
        # A filled square for an emphasised row, an open circle otherwise:
        # shape, not colour, carries the distinction.
        if row.emphasis:
            parts.append(
                f'<rect x="{_n(x_mid - 3)}" y="{_n(cy - 3)}" width="6" height="6" '
                f'fill="{INK}"/>'
            )
        else:
            parts.append(
                f'<circle cx="{_n(x_mid)}" cy="{_n(cy)}" r="2.8" fill="#ffffff" '
                f'stroke="{INK}" stroke-width="1.1"/>'
            )

        stats = f"{fmt(row.mean, digits)} [{fmt(row.lower, digits)}, {fmt(row.upper, digits)}]  n={row.n}"
        parts.append(_text(width, cy + 2.4, stats, size=6.6, anchor="end", fill=INK))
        if row.note:
            parts.append(
                _text(width, top + row_h - 3.5, row.note, size=5.8, anchor="end",
                      fill=INK_SOFT, style="italic")
            )

    parts.append(
        _text(plot_x, height - 5, axis_label, size=6.4, fill=INK_MID)
    )
    return _svg(FIGURE_WIDTH_PT, height, "".join(parts), axis_label)


def stance_bar_svg(segments: list[StanceSegment]) -> str:
    """Composition of measured events as one 100% bar.

    A stacked bar rather than a pie: four wedges at 8pt are unreadable on paper,
    and a pie cannot be compared against another pie. Each band is filled at a
    different luminance *and* given its own texture, and labelled in place, so
    the legend is a convenience rather than a requirement.
    """
    visible = [s for s in segments if s.pct > 0]
    if not visible:
        return ""

    width = FIGURE_WIDTH_PT
    bar_h = 26.0
    height = bar_h + 34.0
    total = sum(s.pct for s in visible) or 100.0

    styles = [
        (FILL_DARK, None, "#ffffff"),
        ("#ffffff", 45.0, INK),
        (FILL_MID, None, "#ffffff"),
        (FILL_LIGHT, -45.0, INK),
    ]

    parts: list[str] = []
    x = 0.0
    legend: list[tuple[str, float, tuple]] = []
    for index, segment in enumerate(visible):
        seg_w = segment.pct / total * width
        fill, hatch_angle, label_fill = styles[index % len(styles)]
        parts.append(
            f'<rect x="{_n(x)}" y="0" width="{_n(seg_w)}" height="{_n(bar_h)}" '
            f'fill="{fill}" stroke="{INK}" stroke-width="0.5"/>'
        )
        if hatch_angle is not None:
            parts.append(
                _hatch(x, 0, seg_w, bar_h, spacing=3.4, angle_deg=hatch_angle,
                       stroke=INK_MID, width=0.55)
            )
        if seg_w > 34:
            parts.append(
                _text(x + seg_w / 2, bar_h / 2 + 3, f"{segment.pct:.0f}%", size=8.0,
                      anchor="middle", fill=label_fill, weight="bold")
            )
        legend.append((segment.label, segment.pct, (fill, hatch_angle)))
        x += seg_w

    lx = 0.0
    for label, pct, (fill, hatch_angle) in legend:
        parts.append(
            f'<rect x="{_n(lx)}" y="{_n(bar_h + 10)}" width="8" height="8" '
            f'fill="{fill}" stroke="{INK}" stroke-width="0.5"/>'
        )
        if hatch_angle is not None:
            parts.append(
                _hatch(lx, bar_h + 10, 8, 8, spacing=2.6, angle_deg=hatch_angle,
                       stroke=INK_MID, width=0.5)
            )
        caption = f"{label} {pct:.0f}%"
        parts.append(_text(lx + 11, bar_h + 17, caption, size=6.8, fill=INK))
        lx += 11 + len(caption) * 3.5 + 14

    return _svg(width, height, "".join(parts), "Stance composition of measured events")
