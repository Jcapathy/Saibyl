# PUBLIC INTERFACE
# ─────────────────────────────────────────────────────────
# render_sentiment_chart(timeline: list[float]) -> bytes  (PNG)
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

PRIMARY = "#1A3A5C"
SECONDARY = "#2E6DA4"
ACCENT = "#C8970A"
LIGHT_BG = "#F0F4FA"


def render_sentiment_chart(timeline: list[float]) -> bytes:
    """Render sentiment over time as a line chart PNG."""
    fig, ax = plt.subplots(figsize=(8, 3))
    rounds = list(range(1, len(timeline) + 1))
    ax.plot(rounds, timeline, color=SECONDARY, linewidth=2, marker="o", markersize=4)
    ax.axhline(y=0, color="#ccc", linestyle="--", linewidth=0.5)
    ax.set_xlabel("Round", fontsize=10)
    ax.set_ylabel("Avg Sentiment", fontsize=10)
    ax.set_title("Sentiment Over Time", fontsize=12, color=PRIMARY)
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
    im = ax.imshow(grid, cmap="YlOrRd", aspect="auto", vmin=0, vmax=1)
    ax.set_xticks(range(len(platforms)))
    ax.set_xticklabels(platforms, rotation=45, ha="right", fontsize=8)
    ax.set_yticks(range(len(personas)))
    ax.set_yticklabels(personas, fontsize=8)
    ax.set_title("Activity Heatmap (Persona × Platform)", fontsize=12, color=PRIMARY)
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

    fig, ax = plt.subplots(figsize=(8, max(3, len(labels) * 0.4)))
    bars = ax.barh(labels, values, color=SECONDARY)
    ax.set_xlabel("Count", fontsize=10)
    ax.set_title("Persona Distribution", fontsize=12, color=PRIMARY)
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

    fig, ax = plt.subplots(figsize=(max(5, len(labels) * 1.5), 4))
    ax.bar(labels, values, color=[SECONDARY, ACCENT, PRIMARY, "#6C757D", "#28A745"][:len(labels)])
    ax.set_ylabel("Events", fontsize=10)
    ax.set_title("Platform Activity", fontsize=12, color=PRIMARY)
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
