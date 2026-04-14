# PUBLIC INTERFACE
# ─────────────────────────────────────────────────────────
# render_sentiment_chart(timeline: list[float], headline: str | None) -> bytes  (PNG)
# render_heatmap(data: list[dict]) -> bytes  (PNG)
# render_persona_distribution(data: dict[str, int]) -> bytes  (PNG)
# render_platform_activity(data: dict[str, int]) -> bytes  (PNG)
# ─────────────────────────────────────────────────────────
from __future__ import annotations

import io

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

# ── Brand color system (matches frontend CHART_COLORS) ──
SUBJECT_A = "#6C63FF"   # Purple — Primary entity
SUBJECT_B = "#00D4FF"   # Cyan — Secondary entity
NEUTRAL   = "#D4A84B"   # Gold — Moderate / Undecided
POSITIVE  = "#34D399"   # Green — Positive movement
NEGATIVE  = "#F87171"   # Red — Negative movement

# Legacy aliases for backward compat (used in pdf_exporter title styling)
PRIMARY = "#1A3A5C"
LIGHT_BG = "#F0F4FA"

# Ordered palette for multi-series charts
PALETTE = [SUBJECT_A, SUBJECT_B, NEUTRAL, POSITIVE, NEGATIVE, "#818CF8"]

# Per-platform colors (matches frontend PLATFORM_COLORS)
PLATFORM_COLORS: dict[str, str] = {
    "twitter_x":     SUBJECT_A,
    "reddit":        NEGATIVE,
    "linkedin":      NEUTRAL,
    "instagram":     SUBJECT_B,
    "hacker_news":   "#818CF8",
    "discord":       "#A78BFA",
    "news_comments": POSITIVE,
    "custom":        "#94A3B8",
}


def _sentiment_bar_color(v: float) -> str:
    """Return bar color based on sentiment value — matches frontend sentimentBarColor()."""
    if v >= 0.2:
        return POSITIVE
    if v >= -0.2:
        return NEUTRAL
    return NEGATIVE


def _find_inflection(timeline: list[float]) -> int | None:
    """Find the index of the largest single-step sentiment change."""
    if len(timeline) < 3:
        return None
    max_delta = 0.0
    max_idx = -1
    for i in range(1, len(timeline)):
        delta = abs(timeline[i] - timeline[i - 1])
        if delta > max_delta:
            max_delta = delta
            max_idx = i
    return max_idx if max_delta > 0.1 else None


def render_sentiment_chart(timeline: list[float], headline: str | None = None) -> bytes:
    """Render sentiment over time as a bar chart with inflection annotation."""
    fig, ax = plt.subplots(figsize=(8, 3.5))
    rounds = list(range(1, len(timeline) + 1))

    # Per-bar coloring based on sentiment value
    bar_colors = [_sentiment_bar_color(v) for v in timeline]
    bars = ax.bar(rounds, timeline, color=bar_colors, edgecolor="none", width=0.7)

    # Zero line
    ax.axhline(y=0, color="#999", linestyle="--", linewidth=0.5)

    # Inflection annotation
    inflection_idx = _find_inflection(timeline)
    if inflection_idx is not None:
        x = rounds[inflection_idx]
        y = timeline[inflection_idx]
        prev = timeline[inflection_idx - 1]
        delta = y - prev
        sign = "+" if delta > 0 else ""
        arrow = "↑" if delta > 0 else "↓"
        ax.annotate(
            f"Inflection {arrow} {sign}{delta:.2f}",
            xy=(x, y),
            xytext=(x, y + (0.2 if y >= 0 else -0.2)),
            fontsize=8,
            fontweight="bold",
            color=NEGATIVE,
            ha="center",
            arrowprops=dict(arrowstyle="->", color=NEGATIVE, lw=1.2),
        )
        # Highlight the inflection bar with an outline
        bars[inflection_idx].set_edgecolor(NEGATIVE)
        bars[inflection_idx].set_linewidth(2)

    ax.set_xlabel("Round", fontsize=10)
    ax.set_ylabel("Avg Sentiment", fontsize=10)

    # Use headline as title if provided, otherwise generic title
    title = headline or "Sentiment Over Time"
    ax.set_title(title, fontsize=11, color=PRIMARY, fontweight="bold", loc="left")

    ax.set_ylim(-1.1, 1.1)
    ax.set_facecolor(LIGHT_BG)
    fig.tight_layout()
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=150, bbox_inches="tight")
    plt.close(fig)
    buf.seek(0)
    return buf.read()


def render_heatmap(data: list[dict]) -> bytes:
    """Render persona x platform heatmap as PNG.
    data: list of {"persona_type": str, "platform": str, "intensity": float, "sentiment": float}
    """
    if not data:
        return _empty_chart("No heatmap data")

    personas = sorted({d["persona_type"] for d in data})
    platforms = sorted({d["platform"] for d in data})

    grid = np.zeros((len(personas), len(platforms)))
    for d in data:
        pi = personas.index(d["persona_type"])
        pj = platforms.index(d["platform"])
        grid[pi][pj] = d["intensity"]

    fig, ax = plt.subplots(figsize=(max(6, len(platforms) * 1.2), max(4, len(personas) * 0.6)))

    # Custom colormap using brand colors: Gold (low) → Purple (high)
    from matplotlib.colors import LinearSegmentedColormap
    brand_cmap = LinearSegmentedColormap.from_list("brand", [NEUTRAL, SUBJECT_A], N=256)

    im = ax.imshow(grid, cmap=brand_cmap, aspect="auto", vmin=0, vmax=1)
    ax.set_xticks(range(len(platforms)))
    ax.set_xticklabels(platforms, rotation=45, ha="right", fontsize=8)
    ax.set_yticks(range(len(personas)))
    ax.set_yticklabels(personas, fontsize=8)
    ax.set_title("Activity Heatmap (Persona × Platform)", fontsize=12, color=PRIMARY, fontweight="bold", loc="left")
    fig.colorbar(im, ax=ax, shrink=0.8, label="Activity Intensity")
    fig.tight_layout()
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=150, bbox_inches="tight")
    plt.close(fig)
    buf.seek(0)
    return buf.read()


def render_persona_distribution(data: dict[str, int]) -> bytes:
    """Render persona type distribution as horizontal bar chart."""
    if not data:
        return _empty_chart("No persona data")

    labels = list(data.keys())
    values = list(data.values())

    # Cycle through brand palette
    bar_colors = [PALETTE[i % len(PALETTE)] for i in range(len(labels))]

    fig, ax = plt.subplots(figsize=(8, max(3, len(labels) * 0.4)))
    bars = ax.barh(labels, values, color=bar_colors)
    ax.set_xlabel("Count", fontsize=10)
    ax.set_title("Persona Distribution", fontsize=12, color=PRIMARY, fontweight="bold", loc="left")
    ax.set_facecolor(LIGHT_BG)

    for bar, val in zip(bars, values):
        ax.text(bar.get_width() + 0.5, bar.get_y() + bar.get_height() / 2,
                str(val), va="center", fontsize=8)

    fig.tight_layout()
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=150, bbox_inches="tight")
    plt.close(fig)
    buf.seek(0)
    return buf.read()


def render_platform_activity(data: dict[str, int]) -> bytes:
    """Render platform activity as bar chart."""
    if not data:
        return _empty_chart("No platform data")

    labels = list(data.keys())
    values = list(data.values())

    # Use per-platform brand colors, falling back to palette cycling
    bar_colors = [PLATFORM_COLORS.get(label, PALETTE[i % len(PALETTE)]) for i, label in enumerate(labels)]

    fig, ax = plt.subplots(figsize=(max(5, len(labels) * 1.5), 4))
    ax.bar(labels, values, color=bar_colors)
    ax.set_ylabel("Events", fontsize=10)
    ax.set_title("Platform Activity", fontsize=12, color=PRIMARY, fontweight="bold", loc="left")
    ax.set_facecolor(LIGHT_BG)
    fig.tight_layout()
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=150, bbox_inches="tight")
    plt.close(fig)
    buf.seek(0)
    return buf.read()


def _empty_chart(message: str) -> bytes:
    """Render a placeholder chart."""
    fig, ax = plt.subplots(figsize=(6, 3))
    ax.text(0.5, 0.5, message, ha="center", va="center", fontsize=14, color="#999")
    ax.set_axis_off()
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=100)
    plt.close(fig)
    buf.seek(0)
    return buf.read()
