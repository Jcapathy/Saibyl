# PUBLIC INTERFACE
# ─────────────────────────────────────────────────────────
# DocumentSection, ReportDocumentInput
# build_report_html(doc: ReportDocumentInput) -> str
# load_artifact(schema_version, artifact) -> tuple[SimulationAnalysis | None, str]
# platform_label(key: str) -> str
# SUPPORTED_SCHEMA_VERSION, PLATFORM_NAMES, COHORT_NAMES
# ─────────────────────────────────────────────────────────
"""The exported report, composed as a document rather than a styled web page.

Everything here is pure: rows in, HTML out, no database and no renderer. That is
what makes the honesty rules testable — the four below are properties of a
string this module returns, checked in `tests/test_report_document.py`, not
promises about a PDF nobody opened.

**1. An unmeasured value is absent, not zero.** `analysis_data.mean_interval`
returns `Interval(mean=0, lower=0, upper=0, n=0)` when nothing was measured, so
every read here drops `n == 0` before it can be drawn. The previous exporter
shipped a heatmap with `"sentiment": 0.0` hardcoded for every cell; a chart that
reads "neutral" where the truth is "not measured" is worse than no chart,
because the reader cannot tell the difference and has no reason to ask.

**2. Every figure traces to the artifact.** The only source of a number in this
document is a validated `SimulationAnalysis`. Nothing is scraped from the report
markdown, derived from event counts, or recomputed — if a field is not in
`analysis_schema`, it cannot appear on the page.

**3. Confidence intervals travel with their means.** There is no code path that
formats a mean without its band: `vector_charts.IntervalRow` carries all four of
mean, lower, upper and n, and the text formatters print all four. This document
gets forwarded to investors, and a point estimate quoted alone is the misreading
the product exists to prevent.

**4. Ordering is not ranking.** When `scoreboard.winner_variant_key` is None the
document says so in words, prints no ordinal column, and emphasises no row. A
marketer acts on the top row; an ordering drawn from overlapping bands launders
sampling noise into a launch decision.

And a fifth, matching the viewer: an artifact whose `schema_version` is outside
the supported range renders **nothing** measured. Rendering the fields a newer
artifact happens to share is how a reader ends up seeing a Founder-lens run
without its adversarial disclosure.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime

import structlog
from pydantic import ValidationError

from app.services.export.markdown_lite import escape_html as _h
from app.services.export.markdown_lite import markdown_to_html
from app.services.export.print_stylesheet import build_stylesheet
from app.services.export.vector_charts import (
    IntervalRow,
    StanceSegment,
    format_plain,
    format_signed,
    interval_rows_svg,
    sentiment_arc_svg,
    stance_bar_svg,
)
from app.services.intelligence.analysis_schema import (
    SCHEMA_VERSION,
    Interval,
    SimulationAnalysis,
    VariantScoreboard,
)

logger = structlog.get_logger()

# Mirrors `frontend/src/lib/analysis.ts`. The viewer refuses an unknown version;
# so does the document. Two renderers of the same artifact disagreeing about
# what they will render is how a disclosure goes missing from one of them.
SUPPORTED_SCHEMA_VERSION = SCHEMA_VERSION

PLATFORM_NAMES: dict[str, str] = {
    "twitter_x": "X (Twitter)",
    "reddit": "Reddit",
    "instagram": "Instagram",
    "tiktok": "TikTok",
    "youtube": "YouTube",
    "facebook": "Facebook",
    "threads": "Threads",
    "linkedin": "LinkedIn",
    "news_comments": "News comments",
    "hacker_news": "Hacker News",
    "discord": "Discord",
    "custom": "Custom",
}

COHORT_NAMES: dict[str, str] = {
    "buyer": "Buyers",
    "adversarial": "Incumbent-aligned (synthetic)",
}


@dataclass(frozen=True)
class DocumentSection:
    """One narrative section of the report, as stored markdown."""

    title: str
    content: str


@dataclass(frozen=True)
class ReportDocumentInput:
    """Everything the document needs, already read out of the database."""

    org_name: str
    simulation_name: str
    report_title: str
    prediction_goal: str
    generated_at: datetime
    report_id: str
    simulation_id: str

    platforms: list[str] = field(default_factory=list)
    max_rounds: int | None = None
    variants: int = 1
    agent_count: int | None = None
    run_started: str | None = None

    schema_version: int | None = None
    artifact: dict | None = None
    sections: list[DocumentSection] = field(default_factory=list)


@dataclass
class _Section:
    anchor: str
    number: str | None
    title: str
    body: str
    flow: bool = False


# ── artifact gate ────────────────────────────────────────────────────


def load_artifact(
    schema_version: int | None, artifact: dict | None
) -> tuple[SimulationAnalysis | None, str]:
    """Validate the stored artifact, or explain in one sentence why there is none.

    The returned sentence is printed in the document. "No charts" without a
    reason invites the reader to assume the run was flat; the three reasons a
    run has no measured figures are genuinely different and a reader deciding
    whether to trust this document needs to know which one applies.
    """
    if artifact is None or schema_version is None:
        return None, (
            "This run has not been analysed, so this document contains no "
            "measured figures. Nothing here is estimated from the narrative text."
        )
    if not isinstance(schema_version, int) or not (
        1 <= schema_version <= SUPPORTED_SCHEMA_VERSION
    ):
        return None, (
            f"This run's analysis was written in artifact format "
            f"{schema_version}; this build of Saibyl reads formats 1 to "
            f"{SUPPORTED_SCHEMA_VERSION}. Rather than render the fields the two "
            f"formats happen to share, the measured sections are omitted "
            f"entirely — a partially-read artifact can drop a disclosure "
            f"without saying so."
        )
    try:
        return SimulationAnalysis.model_validate(artifact), ""
    except ValidationError as exc:
        logger.warning(
            "export_artifact_invalid",
            schema_version=schema_version,
            errors=len(exc.errors()),
        )
        return None, (
            "This run's analysis artifact did not validate against the "
            "measurement schema, so no measured figures are shown. This is a "
            "fault to report, not a property of the run."
        )


def _measured(interval: Interval | None) -> bool:
    """An interval is only drawable when at least one agent produced it."""
    return interval is not None and interval.n > 0


def _interval_sentence(interval: Interval, digits: int = 2) -> str:
    """A mean and its band in prose. There is no bare-mean formatter."""
    return (
        f"{format_signed(interval.mean, digits)} "
        f"(95% CI {format_signed(interval.lower, digits)} to "
        f"{format_signed(interval.upper, digits)}, {interval.n} "
        f"agent{'' if interval.n == 1 else 's'})"
    )


# ── small builders ───────────────────────────────────────────────────


class _Figures:
    """Figure numbering, so captions and cross-references cannot drift."""

    def __init__(self) -> None:
        self.count = 0

    def render(self, title: str, svg: str, caption: str) -> str:
        if not svg:
            return ""
        self.count += 1
        return (
            "<figure>"
            f'<div class="fig-title"><span class="fig-num">Figure '
            f"{self.count}.</span> {_h(title)}</div>"
            f"{svg}"
            f"<figcaption>{caption}</figcaption>"
            "</figure>"
        )


def _callout(head: str, body_html: str, *, warn: bool = False) -> str:
    cls = "callout warn" if warn else "callout"
    return (
        f'<div class="{cls}"><div class="callout-head">{_h(head)}</div>'
        f"{body_html}</div>"
    )


def _metric(label: str, value: str, sub: str) -> str:
    return (
        f'<td><div class="m-label">{_h(label)}</div>'
        f'<div class="m-value">{_h(value)}</div>'
        f'<div class="m-sub">{_h(sub)}</div></td>'
    )


def _kv_table(rows: list[tuple[str, str]]) -> str:
    body = "".join(
        f'<tr><td class="k">{_h(k)}</td><td>{_h(v)}</td></tr>' for k, v in rows if v
    )
    return f'<table class="kv"><tbody>{body}</tbody></table>' if body else ""


def platform_label(key: str) -> str:
    return PLATFORM_NAMES.get(key, key.replace("_", " ").title())


# ── section builders ─────────────────────────────────────────────────


def _cover(doc: ReportDocumentInput, analysis: SimulationAnalysis | None) -> str:
    facts: list[tuple[str, str]] = [
        ("Client", doc.org_name),
        ("Prepared", doc.generated_at.strftime("%d %B %Y")),
        ("Platforms", ", ".join(platform_label(p) for p in doc.platforms) or "—"),
        ("Rounds", str(doc.max_rounds) if doc.max_rounds else "—"),
    ]
    if doc.agent_count:
        facts.append(("Agents", f"{doc.agent_count:,}"))
    if doc.variants and doc.variants > 1:
        facts.append(("Message arenas", str(doc.variants)))
    facts.append(("Report reference", doc.report_id[:8].upper()))

    pairs = [f'<td><span class="k">{_h(k)}</span>{_h(v)}</td>' for k, v in facts]
    rows = ""
    for index in range(0, len(pairs), 2):
        rows += "<tr>" + "".join(pairs[index : index + 2]) + "</tr>"

    provenance = ""
    if analysis:
        quality = analysis.quality
        provenance = (
            '<p class="provenance">Every figure in this document is measured '
            "from what the simulated agents wrote. "
            f"{quality.events_measured:,} of {quality.events_total:,} events "
            f"were scored ({quality.coverage_pct:.1f}% coverage) across "
            f"{quality.agents_active} active agents and {quality.rounds} "
            "rounds. Confidence intervals are computed across agents, not "
            f"events. Overall confidence: {_h(quality.confidence)}.</p>"
        )

    disclosure = ""
    if analysis and analysis.adversarial.enabled:
        disclosure = _callout(
            "Synthetic adversarial cohort", f"<p>{_h(analysis.adversarial.disclosure)}</p>"
        )

    return f"""
<div class="cover">
  <div class="wordmark">SAIBYL</div>
  <hr class="top-rule">
  <div class="doc-kind">Predictive intelligence report</div>
  <h1>{_h(doc.simulation_name)}</h1>
  <div class="subtitle">{_h(doc.report_title)}</div>
  <hr class="cover-rule">
  <table class="facts"><tbody>{rows}</tbody></table>
  {provenance}
  {disclosure}
  <div class="colophon">Confidential — prepared by Saibyl · Saido Labs LLC</div>
</div>
"""


def _contents(sections: list[_Section]) -> str:
    items = ""
    for section in sections:
        number = (
            f'<span class="toc-num">{_h(section.number)}</span>'
            if section.number
            else '<span class="toc-num"></span>'
        )
        lead = ' class="lead-in"' if section.number is None else ""
        items += (
            f"<li{lead}>{number}"
            f'<a href="#{_h(section.anchor)}">{_h(section.title)}</a></li>'
        )
    return (
        '<section class="doc-section" id="contents">'
        '<h2 class="section-title">Contents</h2>'
        f'<ul class="toc">{items}</ul>'
        "</section>"
    )


def _executive_summary(
    doc: ReportDocumentInput,
    analysis: SimulationAnalysis | None,
    absence_reason: str,
    narrative: DocumentSection | None,
) -> str:
    parts: list[str] = []

    if analysis is None:
        parts.append(f'<div class="note">{_h(absence_reason)}</div>')
    else:
        headline = analysis.headline
        quality = analysis.quality

        # The lede states the claim the run supports, in words, with its band.
        if analysis.scoreboard is not None:
            verdict = analysis.scoreboard.verdict or (
                "This test did not separate its variants."
            )
            parts.append(f'<p class="lede">{_h(verdict)}</p>')
        elif _measured(headline.valence):
            direction = (
                "negative" if headline.valence.mean < 0
                else "positive" if headline.valence.mean > 0
                else "neutral"
            )
            parts.append(
                f'<p class="lede">Across {quality.agents_active} active agents '
                f"and {quality.rounds} rounds, the measured response is "
                f"{direction} at {_h(_interval_sentence(headline.valence))}. "
                "Read the interval, not the mean.</p>"
            )

        metrics: list[str] = []
        if _measured(headline.valence):
            metrics.append(
                _metric(
                    "Overall valence",
                    format_signed(headline.valence.mean),
                    f"95% CI {format_signed(headline.valence.lower)} to "
                    f"{format_signed(headline.valence.upper)} · n={headline.valence.n}"
                    + (" · one agent is an anecdote" if headline.valence.n == 1 else ""),
                )
            )
        stance = headline.stance
        if any(
            value > 0
            for value in (
                stance.support_pct, stance.oppose_pct,
                stance.undecided_pct, stance.off_topic_pct,
            )
        ):
            metrics.append(
                _metric(
                    "Opposed",
                    f"{stance.oppose_pct:.0f}%",
                    f"{stance.support_pct:.0f}% support · share of measured events",
                )
            )
        metrics.append(
            _metric(
                "Trajectory",
                headline.trajectory.capitalize(),
                f"{format_signed(headline.trajectory_delta)} first round to last; "
                "reported flat unless the intervals separate",
            )
        )
        metrics.append(
            _metric(
                "Measurement coverage",
                f"{quality.coverage_pct:.0f}%",
                f"{quality.events_measured:,} of {quality.events_total:,} events "
                f"· confidence {quality.confidence}",
            )
        )
        # Four to a row keeps the strip on one line at this measure.
        rows = ""
        for index in range(0, len(metrics), 4):
            rows += "<tr>" + "".join(metrics[index : index + 4]) + "</tr>"
        parts.append(f'<table class="metrics"><tbody>{rows}</tbody></table>')

        if quality.caveats:
            bullets = "".join(f"<li>{_h(c)}</li>" for c in quality.caveats)
            parts.append(
                _callout(
                    "What this run can and cannot show", f"<ul>{bullets}</ul>", warn=True
                )
            )

        if analysis.scoreboard is not None:
            parts.append(_scoreboard_verdict_callout(analysis.scoreboard))

    if narrative and narrative.content.strip():
        parts.append(markdown_to_html(narrative.content, heading_base=3))

    if not parts:
        parts.append(
            '<div class="note">The report has not produced an executive summary '
            "for this run.</div>"
        )
    return "".join(parts)


def _scoreboard_verdict_callout(scoreboard: VariantScoreboard) -> str:
    """The verdict, and — when there is no winner — the refusal, in words.

    Deliberately loud in both directions. A named winner and an unresolved test
    are different results, and a document that presents them in the same voice
    lets a reader take the top row as the answer either way.
    """
    if scoreboard.winner_variant_key:
        winner = next(
            (
                v for v in scoreboard.variants
                if v.variant_key == scoreboard.winner_variant_key
            ),
            None,
        )
        name = (winner.label or winner.variant_key) if winner else scoreboard.winner_variant_key
        body = f"<p><strong>Winner: {_h(name)}.</strong> {_h(scoreboard.verdict)}</p>"
        if scoreboard.paired is not None:
            paired = scoreboard.paired
            body += (
                f"<p>Decided by a paired comparison of the top two arenas: "
                f"{paired.shared_agents} agents saw both, "
                f"{paired.discordant_agents} behaved differently between them, "
                f"and the mean per-agent difference is "
                f"{format_signed(paired.mean_difference)} "
                f"(95% CI {format_signed(paired.lower)} to "
                f"{format_signed(paired.upper)}).</p>"
            )
        if (
            scoreboard.unpaired_winner_variant_key
            != scoreboard.winner_variant_key
        ):
            body += (
                "<p>The previous, unpaired rule would have reached a different "
                "answer here. That is a documented change in how a winner is "
                "chosen, not the product changing its mind.</p>"
            )
        return _callout("Verdict", body)

    body = (
        f"<p><strong>No winner.</strong> {_h(scoreboard.verdict)}</p>"
        "<p>The arenas below appear in display order. That order is not a "
        "ranking: where the intervals overlap, this run does not establish "
        "that one message outperformed another, and acting on the top row "
        "would be acting on sampling noise.</p>"
    )
    if scoreboard.paired is not None:
        paired = scoreboard.paired
        body += (
            f"<p>The paired comparison of the top two arenas had "
            f"{paired.shared_agents} shared agents, of whom "
            f"{paired.discordant_agents} behaved differently between them — "
            f"a mean per-agent difference of "
            f"{format_signed(paired.mean_difference)} "
            f"(95% CI {format_signed(paired.lower)} to "
            f"{format_signed(paired.upper)}), which includes zero.</p>"
        )
    return _callout("Verdict", body, warn=True)


def _scope_section(
    doc: ReportDocumentInput, analysis: SimulationAnalysis | None
) -> str:
    parts: list[str] = []
    parts.append("<h3>Question put to the swarm</h3>")
    parts.append(f"<blockquote>{_h(doc.prediction_goal or '—')}</blockquote>")

    parts.append("<h3>Run parameters</h3>")
    rows: list[tuple[str, str]] = [
        ("Simulation", doc.simulation_name),
        ("Platforms", ", ".join(platform_label(p) for p in doc.platforms) or "—"),
        ("Rounds", str(doc.max_rounds) if doc.max_rounds else "—"),
        ("Agents generated", f"{doc.agent_count:,}" if doc.agent_count else "—"),
        ("Message arenas", str(doc.variants or 1)),
        ("Run started", doc.run_started or "—"),
        ("Simulation reference", doc.simulation_id),
    ]
    if analysis:
        quality = analysis.quality
        rows.extend(
            [
                (
                    "Events measured",
                    f"{quality.events_measured:,} of {quality.events_total:,} "
                    f"({quality.coverage_pct:.1f}%)",
                ),
                ("Agents active", f"{quality.agents_active} of {quality.agents_total}"),
                ("Measurement model", quality.measurement_model or "—"),
                ("Mean interval width", format_plain(quality.mean_ci_width)),
                ("Stated confidence", quality.confidence),
                ("Artifact format", str(analysis.schema_version)),
            ]
        )
    parts.append(_kv_table(rows))

    if analysis and analysis.adversarial.enabled:
        adversarial = analysis.adversarial
        body = f"<p>{_h(adversarial.disclosure)}</p>"
        if adversarial.roles:
            roles = ", ".join(
                f"{key.replace('_', ' ')} ({value})"
                for key, value in sorted(adversarial.roles.items())
            )
            body += f"<p><strong>Roles:</strong> {_h(roles)}</p>"
        if adversarial.archetypes:
            body += (
                "<p><strong>Archetypes:</strong> "
                f"{_h(', '.join(adversarial.archetypes))}</p>"
            )
        parts.append("<h3>Adversarial cohort disclosure</h3>")
        parts.append(_callout("Required disclosure", body, warn=True))

    return "".join(parts)


def _measured_response_section(
    analysis: SimulationAnalysis, figures: _Figures
) -> str:
    parts: list[str] = []

    arc_rows = [
        IntervalRow(
            label=str(point.round_number),
            mean=point.valence.mean,
            lower=point.valence.lower,
            upper=point.valence.upper,
            n=point.valence.n,
        )
        for point in analysis.sentiment_timeline
        if _measured(point.valence)
    ]
    if len(arc_rows) >= 2:
        parts.append(
            figures.render(
                "Measured valence by round",
                sentiment_arc_svg(arc_rows),
                "Columns are the mean valence of the round; whiskers are the 95% "
                "confidence interval across agents. Solid columns are positive, "
                "hatched columns negative, so the sign survives a greyscale "
                "print. A round that produced no measurable opinion is absent "
                "from the axis rather than drawn at zero.",
            )
        )

    platform_rows = [
        IntervalRow(
            label=platform_label(slice_.platform),
            mean=slice_.valence.mean,
            lower=slice_.valence.lower,
            upper=slice_.valence.upper,
            n=slice_.valence.n,
        )
        for slice_ in analysis.by_platform
        if _measured(slice_.valence)
    ]
    if len(platform_rows) >= 2:
        parts.append(
            figures.render(
                "Measured valence by platform",
                interval_rows_svg(platform_rows),
                "Ordered most negative first. Where two bands overlap, this run "
                "does not resolve a difference between those platforms and the "
                "ordering should not be read as one.",
            )
        )

    archetype_rows = [
        IntervalRow(
            label=slice_.archetype,
            mean=slice_.valence.mean,
            lower=slice_.valence.lower,
            upper=slice_.valence.upper,
            n=slice_.valence.n,
        )
        for slice_ in analysis.by_archetype
        if _measured(slice_.valence)
    ]
    if len(archetype_rows) >= 2:
        parts.append(
            figures.render(
                "Measured valence by archetype",
                interval_rows_svg(archetype_rows),
                "Which kind of person reacted how. Archetypes whose agents "
                "produced no measurable opinion are omitted.",
            )
        )

    cohort_rows = [
        IntervalRow(
            label=COHORT_NAMES.get(slice_.cohort, slice_.cohort),
            mean=slice_.valence.mean,
            lower=slice_.valence.lower,
            upper=slice_.valence.upper,
            n=slice_.valence.n,
            note=f"{slice_.agent_count} of {slice_.agents_total} allocated agents spoke",
        )
        for slice_ in analysis.by_cohort
        if _measured(slice_.valence)
    ]
    if len(cohort_rows) >= 2:
        parts.append(
            figures.render(
                "Buyers against the incumbent-aligned cohort",
                interval_rows_svg(cohort_rows),
                "How much of the headline came from agents constructed to argue "
                "against adopting the subject. Both cohorts are synthetic; the "
                "split exists so the headline can be read either way.",
            )
        )

    stance = analysis.headline.stance
    segments = [
        StanceSegment("Support", stance.support_pct),
        StanceSegment("Undecided", stance.undecided_pct),
        StanceSegment("Oppose", stance.oppose_pct),
        StanceSegment("Off-topic", stance.off_topic_pct),
    ]
    if any(segment.pct > 0 for segment in segments):
        parts.append(
            figures.render(
                "Stance composition of measured events",
                stance_bar_svg(segments),
                "Share of measured, content-bearing events taking each position. "
                "This describes the sample rather than estimating a population, "
                "so it carries no interval. Off-topic events are shown rather "
                "than dropped: a swarm that never engaged is a different result "
                "from one that disagreed.",
            )
        )

    drawn = [part for part in parts if part]
    if not drawn:
        return (
            '<div class="note">This run produced no slice with a measurable '
            "opinion, so there are no figures in this section. Charts are only "
            "drawn from measured data.</div>"
        )
    return "".join(drawn)


def _scoreboard_section(analysis: SimulationAnalysis, figures: _Figures) -> str:
    scoreboard = analysis.scoreboard
    if scoreboard is None:
        return ""

    rows = [variant for variant in scoreboard.variants if _measured(variant.objective_rate)]
    if not rows:
        return (
            '<div class="note">No arena produced a measurable objective rate, '
            "so there is no scoreboard to show.</div>"
        )

    parts: list[str] = []
    objective = scoreboard.objective or "any committing action"
    parts.append(
        f"<p>Every arena received the same swarm, agent for agent. The metric is "
        f"the share of an arena's active agents whose measured intent was "
        f"<strong>{_h(objective)}</strong>, taken over agents rather than events "
        f"so one talkative agent cannot carry a variant.</p>"
    )
    parts.append(_scoreboard_verdict_callout(scoreboard))

    forest = [
        IntervalRow(
            label=variant.label or variant.variant_key,
            mean=variant.objective_rate.mean,
            lower=variant.objective_rate.lower,
            upper=variant.objective_rate.upper,
            n=variant.objective_rate.n,
            emphasis=bool(
                scoreboard.winner_variant_key
                and variant.variant_key == scoreboard.winner_variant_key
            ),
        )
        for variant in rows
    ]
    caption = (
        "Objective rate per arena with its 95% interval. "
        + (
            "The filled marker is the variant the paired comparison named."
            if scoreboard.winner_variant_key
            else "No marker is emphasised: this test named no winner, and the "
            "order shown is display order rather than a ranking."
        )
    )
    parts.append(
        figures.render(
            "Objective rate by message arena",
            interval_rows_svg(
                forest, domain=(0.0, 1.0), signed=False,
                axis_label="Share of active agents taking the objective action",
            ),
            caption,
        )
    )

    show_virality = any(variant.virality.score is not None for variant in rows)
    header = (
        "<tr><th>Arena</th>"
        '<th class="num">Objective rate</th>'
        '<th class="num">95% CI</th>'
        '<th class="num">Agents</th>'
        '<th class="num">Valence</th>'
        '<th class="num">95% CI</th>'
        + ('<th class="num">Virality</th>' if show_virality else "")
        + "<th>Notes</th></tr>"
    )
    body = ""
    for variant in rows:
        name = variant.label or variant.variant_key
        if scoreboard.winner_variant_key == variant.variant_key:
            name = f"{name} — winner"
        notes: list[str] = []
        if variant.viral_but_off_message:
            notes.append("travels but off-message")
        if variant.converts_but_wont_travel:
            notes.append("converts but will not travel")
        valence_cells = (
            f'<td class="num">{format_signed(variant.valence.mean)}</td>'
            f'<td class="num">{format_signed(variant.valence.lower)} to '
            f"{format_signed(variant.valence.upper)}</td>"
            if _measured(variant.valence)
            else '<td class="num"></td><td class="num"></td>'
        )
        virality_cell = ""
        if show_virality:
            score = variant.virality.score
            virality_cell = (
                f'<td class="num">{format_plain(score, 0)} '
                f"({variant.virality.components_used}/"
                f"{variant.virality.components_total})</td>"
                if score is not None
                else '<td class="num"></td>'
            )
        body += (
            f'<tr><td class="rowhead">{_h(name)}</td>'
            f'<td class="num">{format_plain(variant.objective_rate.mean * 100, 1)}%</td>'
            f'<td class="num">{format_plain(variant.objective_rate.lower * 100, 1)}% to '
            f"{format_plain(variant.objective_rate.upper * 100, 1)}%</td>"
            f'<td class="num">{variant.objective_rate.n}</td>'
            f"{valence_cells}{virality_cell}"
            f"<td>{_h('; '.join(notes))}</td></tr>"
        )
    parts.append(f'<table class="data"><thead>{header}</thead><tbody>{body}</tbody></table>')

    footnotes = [
        "Blank cells are unmeasured, not zero.",
        "Objective rate is a proportion over agents; the interval is computed "
        "across agents, so a small arena reports a visibly wider band.",
    ]
    if show_virality:
        footnotes.append(
            "Virality is an index out of 100 with the number of components that "
            "contributed shown in brackets; a component that could not be "
            "measured is dropped and the remaining weights renormalised, never "
            "counted as zero. It is a separate axis from the objective metric "
            "and is never blended into it."
        )
    parts.append(
        '<p class="provenance">' + " ".join(_h(f) for f in footnotes) + "</p>"
    )
    return "".join(parts)


def _objections_section(analysis: SimulationAnalysis) -> str:
    objections = analysis.objections[:10]
    if not objections:
        return ""

    parts: list[str] = [
        "<p>Ranked by load-bearing weight — reach × intensity × cohort spread — "
        "rather than by how often an objection was repeated. The two are usually "
        "different objections, and only the first predicts a lost deal.</p>"
    ]

    header = (
        "<tr><th>Objection</th>"
        '<th class="num">Weight</th>'
        '<th class="num">Agents</th>'
        '<th class="num">First seen</th>'
        "<th>Originating cohort</th>"
        "<th>Crossed into buyers</th></tr>"
    )
    body = ""
    for objection in objections:
        first_seen = (
            f"R{objection.first_round_seen}"
            if objection.first_round_seen is not None
            else ""
        )
        crossed = (
            "yes" if objection.crossed_into_buyers
            else "no" if objection.originated_adversarial
            else ""
        )
        body += (
            f'<tr><td class="rowhead">{_h(objection.label)}</td>'
            f'<td class="num">{objection.load_bearing_score:.1f}</td>'
            f'<td class="num">{objection.agent_count}</td>'
            f'<td class="num">{first_seen}</td>'
            f"<td>{_h(objection.originating_cohort or '')}</td>"
            f"<td>{crossed}</td></tr>"
        )
    parts.append(
        f'<table class="data"><thead>{header}</thead><tbody>{body}</tbody></table>'
    )
    parts.append(
        '<p class="provenance">An empty cell is a value this run did not '
        "measure. &ldquo;Crossed into buyers&rdquo; is only meaningful for an "
        "objection that started in the incumbent-aligned cohort, so it is blank "
        "for the rest.</p>"
    )

    quoted = [o for o in objections[:4] if o.quotes]
    if quoted:
        parts.append("<h3>Verbatim</h3>")
        parts.append(
            "<p>Agent output, unedited. Every objection above resolves to the "
            "events that produced it; these are the first two of each.</p>"
        )
        for objection in quoted:
            parts.append(f"<h4>{_h(objection.label)}</h4>")
            if objection.summary:
                parts.append(f"<p>{_h(objection.summary)}</p>")
            for quote in objection.quotes[:2]:
                attribution = " · ".join(
                    part
                    for part in (
                        f"@{quote.agent_username}" if quote.agent_username else "",
                        quote.archetype or "",
                        platform_label(quote.platform) if quote.platform else "",
                        f"round {quote.round_number}"
                        if quote.round_number is not None
                        else "",
                    )
                    if part
                )
                parts.append(
                    f"<blockquote>&ldquo;{_h(quote.text)}&rdquo;"
                    f'<span class="attribution">{_h(attribution)}</span></blockquote>'
                )
    return "".join(parts)


def _flashpoints_section(analysis: SimulationAnalysis) -> str:
    flashpoints = analysis.flashpoints[:8]
    if not flashpoints:
        return ""
    header = (
        "<tr><th>Round</th>"
        '<th class="num">Before</th>'
        '<th class="num">After</th>'
        '<th class="num">Shift</th>'
        "<th>Status</th><th>What moved</th></tr>"
    )
    body = ""
    for flash in flashpoints:
        status = (
            "measured shift" if flash.significant else "inside the bands"
        )
        body += (
            f'<tr><td class="rowhead">R{flash.round_number}</td>'
            f'<td class="num">{format_signed(flash.valence_before)}</td>'
            f'<td class="num">{format_signed(flash.valence_after)}</td>'
            f'<td class="num">{format_signed(flash.delta)}</td>'
            f"<td>{status}</td>"
            f"<td>{_h(flash.description or ', '.join(flash.objection_keys))}</td></tr>"
        )
    return (
        "<p>Round-to-round moves large enough to be worth naming. A shift is "
        "only called <em>measured</em> when the intervals on either side of it "
        "separate; the rest are directional and are labelled as such rather "
        "than narrated into a story.</p>"
        f'<table class="data"><thead>{header}</thead><tbody>{body}</tbody></table>'
    )


def _methodology_section(
    doc: ReportDocumentInput, analysis: SimulationAnalysis | None, absence_reason: str
) -> str:
    parts: list[str] = []
    parts.append("<h3>Where the numbers come from</h3>")
    parts.append(
        "<p>Every figure in this document is read from one artifact: the "
        "measurement record built from what the simulated agents actually "
        "wrote. Nothing is scraped from the report narrative, inferred from "
        "event counts, or recomputed at print time. A number that has no field "
        "in that artifact does not appear on these pages.</p>"
    )
    parts.append("<h3>How to read an interval</h3>")
    parts.append(
        "<p>Confidence intervals are computed across <em>agents</em>, not "
        "events. A run of 25 agents that produced 400 events has 25 independent "
        "observations, not 400 — one agent posting ten times is one opinion "
        "repeated. A small swarm therefore reports a visibly wide band rather "
        "than manufacturing precision out of its own verbosity. Where two bands "
        "overlap, the difference between them is not resolved by this run, "
        "whatever order they appear in.</p>"
    )
    parts.append("<h3>What is deliberately missing</h3>")
    parts.append(
        "<p>Blank cells and absent rows are unmeasured values. They are left "
        "blank rather than filled with a zero or a dash that could be read as "
        "data. A round with no measurable opinion is absent from the timeline "
        "rather than interpolated, and a mean is never printed without the band "
        "around it.</p>"
    )
    if analysis is None:
        parts.append(f'<div class="note">{_h(absence_reason)}</div>')

    parts.append("<h3>Scope</h3>")
    parts.append(
        "<p>Every agent in this run is synthetic. This document reports what a "
        "constructed swarm did in a simulation; it is evidence about a message, "
        "not a survey of a population.</p>"
    )
    rows = [
        ("Document generated", doc.generated_at.strftime("%d %B %Y at %H:%M UTC")),
        ("Report reference", doc.report_id),
        ("Simulation reference", doc.simulation_id),
        (
            "Artifact format",
            f"{analysis.schema_version} (this build reads 1–{SUPPORTED_SCHEMA_VERSION})"
            if analysis
            else f"not read (this build reads 1–{SUPPORTED_SCHEMA_VERSION})",
        ),
        (
            "Arenas included",
            "all arenas in the run" if (doc.variants or 1) > 1 else "single arena",
        ),
    ]
    parts.append(_kv_table(rows))
    return "".join(parts)


# ── entry point ──────────────────────────────────────────────────────


def _match(sections: list[DocumentSection], pattern: str) -> DocumentSection | None:
    expression = re.compile(pattern, re.IGNORECASE)
    for section in sections:
        if expression.search(section.title or ""):
            return section
    return None


def build_report_html(doc: ReportDocumentInput) -> str:
    """Compose the whole document. Pure — no database, no renderer."""
    analysis, absence_reason = load_artifact(doc.schema_version, doc.artifact)
    figures = _Figures()

    narrative = list(doc.sections)
    exec_section = _match(narrative, r"executive|summary|overview") or (
        narrative[0] if narrative else None
    )
    conclusion = _match(narrative, r"strategic.*implication|recommended.*action|conclusion")
    detailed = [
        section
        for section in narrative
        if section is not exec_section and section is not conclusion
    ]

    sections: list[_Section] = [
        _Section(
            anchor="executive-summary",
            number=None,
            title="Executive summary",
            body=_executive_summary(doc, analysis, absence_reason, exec_section),
        )
    ]
    # `_contents` and the body are generated from this one list, so the contents
    # page cannot list a section the document does not contain, or miss one it
    # does. Section titles stay short enough to sit on one line in the running
    # head — a running head that wraps is a header that eats into the text block.

    numbered: list[tuple[str, str]] = []

    def add(anchor: str, title: str, body: str) -> None:
        if not body.strip():
            return
        numbered.append((anchor, title))
        sections.append(
            _Section(anchor=anchor, number=str(len(numbered)), title=title, body=body)
        )

    add("scope", "Scope and method", _scope_section(doc, analysis))

    if analysis is not None:
        add(
            "measured-response",
            "Measured response",
            _measured_response_section(analysis, figures),
        )
        add(
            "scoreboard",
            "Message arena scoreboard",
            _scoreboard_section(analysis, figures),
        )
        add("objections", "Objections", _objections_section(analysis))
        add("flashpoints", "Turning points", _flashpoints_section(analysis))
    else:
        add(
            "measured-response",
            "Measured response",
            f'<div class="note">{_h(absence_reason)}</div>',
        )

    if detailed:
        body = ""
        for section in detailed:
            title = (section.title or "").strip()
            if title:
                body += f"<h3>{_h(title)}</h3>"
            body += markdown_to_html(section.content, heading_base=4)
        add("findings", "Detailed findings", body)

    if conclusion and conclusion.content.strip():
        add(
            "implications",
            "Strategic implications",
            markdown_to_html(conclusion.content, heading_base=3),
        )

    add(
        "methodology",
        "How to read this document",
        _methodology_section(doc, analysis, absence_reason),
    )

    body_html = ""
    for section in sections:
        heading_number = (
            f'<span class="num">Section {section.number}</span>'
            if section.number
            else ""
        )
        body_html += (
            f'<section class="doc-section" id="{_h(section.anchor)}">'
            f'<h2 class="section-title">{heading_number}'
            f'<span class="name">{_h(section.title)}</span></h2>'
            f"{section.body}</section>"
        )

    client_line = " · ".join(
        part for part in (doc.org_name, doc.simulation_name) if part
    )
    stylesheet = build_stylesheet(client_line)

    return (
        "<!DOCTYPE html>\n"
        '<html lang="en"><head><meta charset="utf-8">'
        f"<title>{_h(doc.report_title)} — {_h(doc.simulation_name)}</title>"
        f"<style>{stylesheet}</style></head><body>"
        f"{_cover(doc, analysis)}"
        f"{_contents(sections)}"
        f"{body_html}"
        "</body></html>"
    )
