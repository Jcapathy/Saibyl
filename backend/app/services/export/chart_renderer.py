# PUBLIC INTERFACE
# ─────────────────────────────────────────────────────────
# render_sentiment_arc_png(rows, title) -> bytes  (PNG)
# render_interval_rows_png(rows, title, domain, signed, axis_label) -> bytes  (PNG)
# ─────────────────────────────────────────────────────────
"""Raster charts for the PowerPoint export.

The PDF draws its own vector figures (`vector_charts`) because a document is
typeset. A `.pptx` cannot embed SVG — `python-pptx` takes raster or nothing — so
this module exists solely to give the deck the same figures at slide resolution.

It shares three rules with the vector renderer, deliberately:

* **Every entry point takes an interval**, never a bare mean. There is no
  function here that can draw a point estimate without its band.
* **Nothing is distinguished by hue alone.** The palette is a neutral ink scale
  plus texture, so a slide printed as a greyscale handout — which is what
  happens to every deck eventually — loses no information.
* **Unmeasured rows never arrive.** Callers drop `n == 0` before calling. The
  previous version of this file had a `render_heatmap` whose caller passed
  `"sentiment": 0.0` for every cell; both are gone.
"""
from __future__ import annotations

import io
from dataclasses import dataclass

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

INK = "#14181d"
INK_MID = "#5a6570"
INK_SOFT = "#909aa4"
GRID = "#e2e7eb"
FILL_DARK = "#2b343d"
PAPER = "#ffffff"

MINUS = "−"


@dataclass(frozen=True)
class ChartRow:
    """A label, a mean, its 95% band, and the agent count behind it."""

    label: str
    mean: float
    lower: float
    upper: float
    n: int


def _signed(value: float, digits: int = 2) -> str:
    text = f"{abs(value):.{digits}f}"
    return f"{MINUS}{text}" if value < 0 else f"+{text}"


def _plain(value: float, digits: int = 2) -> str:
    text = f"{abs(value):.{digits}f}"
    return f"{MINUS}{text}" if value < 0 else text


def _save(fig) -> bytes:
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=200, bbox_inches="tight", facecolor=PAPER)
    plt.close(fig)
    buf.seek(0)
    return buf.read()


def render_sentiment_arc_png(
    rows: list[ChartRow], title: str = "Measured sentiment by round"
) -> bytes:
    """Mean valence per round as columns with 95% whiskers.

    Positive columns are solid, negative columns hatched: the sign is carried by
    texture as well as position, so it survives a greyscale handout.
    """
    if not rows:
        raise ValueError("render_sentiment_arc_png needs at least one measured row")

    fig, ax = plt.subplots(figsize=(10, 4.2))
    x = list(range(len(rows)))
    means = [row.mean for row in rows]
    lower_err = [max(0.0, row.mean - row.lower) for row in rows]
    upper_err = [max(0.0, row.upper - row.mean) for row in rows]

    bars = ax.bar(x, means, width=0.62, color=FILL_DARK, edgecolor=INK, linewidth=0.8)
    for bar, row in zip(bars, rows):
        if row.mean < 0:
            bar.set_facecolor(PAPER)
            bar.set_hatch("////")
            bar.set_edgecolor(INK)

    ax.errorbar(
        x, means, yerr=[lower_err, upper_err],
        fmt="none", ecolor=INK, elinewidth=1.1, capsize=4, capthick=1.1,
    )
    ax.axhline(0, color=INK_MID, linewidth=0.8)
    ax.set_ylim(-1.15, 1.15)
    ax.set_xticks(x)
    ax.set_xticklabels([f"R{row.label}" for row in rows], fontsize=9, color=INK_MID)
    ax.set_ylabel("Mean sentiment", fontsize=9, color=INK_MID)
    ax.set_title(title, fontsize=12, color=INK, fontweight="bold", loc="left")
    ax.yaxis.grid(True, color=GRID, linewidth=0.6, linestyle=(0, (2, 2)))
    ax.set_axisbelow(True)
    for spine in ("top", "right"):
        ax.spines[spine].set_visible(False)

    if len(rows) <= 14:
        for xi, row in zip(x, rows):
            offset = 0.06 if row.mean >= 0 else -0.06
            ax.text(
                xi, row.upper + offset if row.mean >= 0 else row.lower + offset,
                _signed(row.mean), ha="center",
                va="bottom" if row.mean >= 0 else "top",
                fontsize=8, fontweight="bold", color=INK,
            )

    ax.text(
        0.0, -0.18,
        "Whiskers are the 95% confidence interval across agents. "
        "Rounds with no measurable opinion are absent, not zero.",
        transform=ax.transAxes, fontsize=8, color=INK_SOFT,
    )
    fig.tight_layout()
    return _save(fig)


def render_interval_rows_png(
    rows: list[ChartRow],
    title: str,
    *,
    domain: tuple[float, float] = (-1.0, 1.0),
    signed: bool = True,
    axis_label: str = "Mean sentiment",
) -> bytes:
    """A dot-and-whisker row per estimate, with the figures printed alongside."""
    if not rows:
        raise ValueError("render_interval_rows_png needs at least one measured row")

    fmt = _signed if signed else _plain
    height = max(2.4, 0.46 * len(rows) + 1.2)
    fig, ax = plt.subplots(figsize=(10, height))

    y = list(range(len(rows)))[::-1]
    for yi, row in zip(y, rows):
        ax.plot([row.lower, row.upper], [yi, yi], color=INK_MID, linewidth=1.3)
        ax.plot([row.lower, row.lower], [yi - 0.16, yi + 0.16], color=INK_MID, linewidth=1.3)
        ax.plot([row.upper, row.upper], [yi - 0.16, yi + 0.16], color=INK_MID, linewidth=1.3)
        ax.plot(
            [row.mean], [yi], marker="o", markersize=7,
            markerfacecolor=PAPER, markeredgecolor=INK, markeredgewidth=1.6,
        )
        ax.text(
            domain[1], yi,
            f"  {fmt(row.mean)} [{fmt(row.lower)}, {fmt(row.upper)}]  n={row.n}",
            va="center", ha="left", fontsize=8, color=INK,
        )

    if domain[0] < 0 < domain[1]:
        ax.axvline(0, color=INK_MID, linewidth=0.8)
    ax.set_yticks(y)
    ax.set_yticklabels([row.label for row in rows], fontsize=9, color=INK)
    ax.set_xlim(*domain)
    ax.set_xlabel(axis_label, fontsize=9, color=INK_MID)
    ax.set_title(title, fontsize=12, color=INK, fontweight="bold", loc="left")
    ax.xaxis.grid(True, color=GRID, linewidth=0.6, linestyle=(0, (2, 2)))
    ax.set_axisbelow(True)
    for spine in ("top", "right", "left"):
        ax.spines[spine].set_visible(False)
    fig.tight_layout()
    return _save(fig)
