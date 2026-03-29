# PUBLIC INTERFACE
# ─────────────────────────────────────────────────────────
# export_report_pptx(report_id: UUID) -> bytes
# ─────────────────────────────────────────────────────────
from __future__ import annotations

import io
from datetime import UTC, datetime
from uuid import UUID

import structlog
from pptx import Presentation
from pptx.util import Inches, Pt

from app.core.database import get_supabase_admin
from app.services.export.chart_renderer import (
    render_persona_distribution,
    render_platform_activity,
    render_sentiment_chart,
)
from app.services.intelligence.react_tools import simulation_analytics

logger = structlog.get_logger()

# Design system
PRIMARY = "1A3A5C"
SECONDARY = "2E6DA4"
ACCENT = "C8970A"
TITLE_SIZE = Pt(36)
SUBTITLE_SIZE = Pt(18)
BODY_SIZE = Pt(14)


def _add_title_slide(prs: Presentation, title: str, subtitle: str) -> None:
    layout = prs.slide_layouts[0]  # Title slide
    slide = prs.slides.add_slide(layout)
    slide.shapes.title.text = title
    slide.placeholders[1].text = subtitle


def _add_content_slide(prs: Presentation, title: str, bullets: list[str]) -> None:
    layout = prs.slide_layouts[1]  # Title + Content
    slide = prs.slides.add_slide(layout)
    slide.shapes.title.text = title
    tf = slide.placeholders[1].text_frame
    tf.clear()
    for i, bullet in enumerate(bullets):
        if i == 0:
            tf.paragraphs[0].text = bullet
            tf.paragraphs[0].font.size = BODY_SIZE
        else:
            p = tf.add_paragraph()
            p.text = bullet
            p.font.size = BODY_SIZE


def _add_chart_slide(prs: Presentation, title: str, chart_png: bytes) -> None:
    layout = prs.slide_layouts[5]  # Blank
    slide = prs.slides.add_slide(layout)

    tx_box = slide.shapes.add_textbox(Inches(0.5), Inches(0.3), Inches(9), Inches(0.8))
    tx_box.text_frame.paragraphs[0].text = title
    tx_box.text_frame.paragraphs[0].font.size = Pt(24)
    tx_box.text_frame.paragraphs[0].font.bold = True

    img_stream = io.BytesIO(chart_png)
    slide.shapes.add_picture(img_stream, Inches(1), Inches(1.3), Inches(8), Inches(5))


async def export_report_pptx(report_id: UUID) -> bytes:
    """Generate PowerPoint from a completed report."""
    admin = get_supabase_admin()

    report = admin.table("reports").select("*").eq(
        "id", str(report_id)
    ).single().execute().data

    sim = admin.table("simulations").select("*").eq(
        "id", report["simulation_id"]
    ).single().execute().data

    sections = admin.table("report_sections").select("*").eq(
        "report_id", str(report_id)
    ).order("section_index").execute().data

    prs = Presentation()
    prs.slide_width = Inches(13.33)
    prs.slide_height = Inches(7.5)

    # 1. Title slide
    _add_title_slide(
        prs,
        report.get("title", "Intelligence Report"),
        f"{sim['name']}\n{datetime.now(UTC).strftime('%B %d, %Y')}",
    )

    # 2. Executive summary
    markdown = report.get("markdown_content", "")
    summary_lines = []
    if "## Executive Summary" in markdown:
        summary_text = markdown.split("## Executive Summary")[1].split("##")[0].strip()
        summary_lines = [line.strip() for line in summary_text.split("\n") if line.strip()][:5]
    if summary_lines:
        _add_content_slide(prs, "Executive Summary", summary_lines)

    # 3. One slide per section
    for s in sections:
        content = s.get("content") or ""
        bullets = [line.strip() for line in content.split("\n") if line.strip()][:5]
        if bullets:
            _add_content_slide(prs, s["title"], bullets)

    # 4. Statistics slide
    agents = admin.table("simulation_agents").select(
        "id", count="exact"
    ).eq("simulation_id", report["simulation_id"]).execute()
    events = admin.table("simulation_events").select(
        "id", count="exact"
    ).eq("simulation_id", report["simulation_id"]).execute()

    _add_content_slide(prs, "Simulation Statistics", [
        f"Agents: {agents.count or 0}",
        f"Total Events: {events.count or 0}",
        f"Platforms: {', '.join(sim.get('platforms') or [])}",
        f"Max Rounds: {sim.get('max_rounds', 'N/A')}",
        f"A/B Test: {'Yes' if sim.get('is_ab_test') else 'No'}",
    ])

    # 5. Charts
    try:
        # Persona distribution chart
        persona_data = await simulation_analytics(
            UUID(report["simulation_id"]), "persona_breakdown"
        )
        pbreakdown = persona_data.data.get("persona_events", {})
        if pbreakdown:
            chart = render_persona_distribution(pbreakdown)
            _add_chart_slide(prs, "Persona Distribution", chart)

        # Sentiment chart
        sentiment_data = await simulation_analytics(
            UUID(report["simulation_id"]), "sentiment_over_time"
        )
        curve = sentiment_data.data.get("sentiment_curve", {})
        if curve:
            timeline = [curve[k] for k in sorted(curve, key=int)]
            chart = render_sentiment_chart(timeline)
            _add_chart_slide(prs, "Sentiment Over Time", chart)

        # Platform activity chart
        platform_data = await simulation_analytics(
            UUID(report["simulation_id"]), "platform_comparison"
        )
        pdata = platform_data.data.get("platform_events", {})
        if pdata:
            chart = render_platform_activity(pdata)
            _add_chart_slide(prs, "Platform Activity", chart)
    except Exception as e:
        logger.warning("pptx_chart_error", error=str(e))

    # 6. Methodology
    _add_content_slide(prs, "Methodology", [
        f"Prediction Goal: {sim.get('prediction_goal', 'N/A')}",
        f"Platforms: {', '.join(sim.get('platforms') or [])}",
        f"Max Rounds: {sim.get('max_rounds', 'N/A')}",
        "Generated by Saibyl — Swarm Intelligence Prediction Platform",
    ])

    # Serialize
    buf = io.BytesIO()
    prs.save(buf)
    buf.seek(0)
    result = buf.read()
    logger.info("pptx_exported", report_id=str(report_id), size=len(result))
    return result
