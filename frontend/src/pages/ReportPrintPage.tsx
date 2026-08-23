import { useEffect, useState } from 'react';
import { useParams } from 'react-router-dom';
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  ErrorBar,
  Legend,
  Pie,
  PieChart,
  ReferenceLine,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import { format } from 'date-fns';
import api from '@/lib/api';
import SectionRenderer from '@/components/report/SectionRenderer';
import { groupLabel } from '@/lib/groups';
import { PRINT_PIE_COLORS, PRINT_PLATFORM_COLORS } from '@/lib/constants';
import { cleanContent, stripDuplicateTitle } from '@/lib/utils';
import { PageHeader } from '@/components/design';
import {
  TRAJECTORY_COPY,
  formatSigned,
  isSupportedSchema,
  withSchemaDefaults,
  type AnalysisResponse,
  type SimulationAnalysis,
} from '@/lib/analysis';
import type { Simulation, SimulationReport } from '@/types';

/* ------------------------------------------------------------------ */
/*  Types                                                              */
/* ------------------------------------------------------------------ */

const PLATFORM_NAMES: Record<string, string> = {
  twitter_x: 'X (Twitter)',
  reddit: 'Reddit',
  instagram: 'Instagram',
  tiktok: 'TikTok',
  youtube: 'YouTube',
  facebook: 'Facebook',
  threads: 'Threads',
  linkedin: 'LinkedIn',
  news_comments: 'News',
  hacker_news: 'Hacker News',
  discord: 'Discord',
  custom: 'Custom',
};

/**
 * The document's four colours, and they are the design system's own.
 *
 * Until 2026-08-23 they were neutral greys — `#1a1a1a`, `#666`, `#e0e0e0` —
 * with a dozen more (`#333`, `#444`, `#555`, `#999`) spelled inline beside
 * them, so the exported PDF was the one Saibyl artefact printed in a palette
 * nothing else in the product uses. These are `tailwind.config.js`'s
 * `saibyl-ink`, `saibyl-muted` and the hairline, which is what the reader sees
 * on screen five seconds before they hit print.
 *
 * Nothing else about this page changed with them. It carries no wash, no
 * gradient, no glass and no motion: none of those print, and several of them
 * come out of a laser printer as a grey slab. `@media print` below turns
 * colour rendering on precisely so these four survive the trip.
 */
const INK = '#14294a';
const MUTED = '#60718e';
const RULE = '#dbe3ef';
const BRAND = '#8b73ee';

/* ------------------------------------------------------------------ */
/*  Component                                                          */
/* ------------------------------------------------------------------ */

/**
 * The print / PDF view, rebuilt on the `simulation_analysis` artifact.
 *
 * This page previously carried its own copy of the report viewer's markdown
 * scraping, plus its own fabrications: platform sentiment was
 * `baseSent + Math.sin(i * 2.1) * 0.2` and the sentiment distribution pie was a
 * "plausible population split" derived from one scraped scalar. Both are gone.
 *
 * The exported document is where a fabricated number does the most damage — it
 * leaves the product, gets forwarded, and is quoted back months later with no
 * way to check it. So this page renders the artifact or it renders nothing, and
 * it states its own measurement coverage on the page.
 *
 * The V1 section structure (Source Material → Executive Summary → Data &
 * Analysis → Detailed Findings → Strategic Implications) is preserved; only the
 * charts inside it changed.
 *
 * ---
 *
 * **On 2026-08-23 this page was brought onto the design system's palette and
 * no further.** It is read on paper, and most of what the system is made of
 * does not survive the trip: a radial wash prints as a smudge, `backdrop-filter`
 * prints as nothing, a soft blue shadow prints as a grey slab, and an entrance
 * animation prints as whatever frame the browser happened to be on. So there
 * is no `Ground` here, no `Card`, no `sb-hero`, no `Deal` and no `Rise`.
 *
 * Two things did change, and both are about ink:
 *
 * 1. The four colour constants and the dozen loose hex literals beside them
 *    became `saibyl-ink`, `saibyl-muted` and the system hairline. This
 *    document had been printing in a neutral-grey palette used nowhere else
 *    in the product.
 * 2. The cover heading composes `PageHeader` — static, and the only primitive
 *    in the folder that is. See the comment at its render site for exactly
 *    what that does and does not bring with it.
 */
export default function ReportPrintPage() {
  const { id: simId } = useParams<{ id: string }>();

  const [report, setReport] = useState<SimulationReport | null>(null);
  const [simulation, setSimulation] = useState<Simulation | null>(null);
  const [analysis, setAnalysis] = useState<SimulationAnalysis | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!simId) return;
    let cancelled = false;

    (async () => {
      try {
        const [reportRes, simRes] = await Promise.all([
          api.get(`/reports/by-simulation/${simId}`),
          api.get(`/simulations/${simId}`),
        ]);
        if (cancelled) return;
        setReport(reportRes.data as SimulationReport);
        setSimulation(simRes.data as Simulation);
      } catch {
        // Falls through to the "could not be loaded" state below.
      }

      try {
        const res = await api.get(`/simulations/${simId}/analysis`);
        if (cancelled) return;
        const payload = res.data as AnalysisResponse;
        if (isSupportedSchema(payload.schema_version)) {
          setAnalysis(withSchemaDefaults(payload.artifact));
        }
      } catch {
        // An unanalysed run prints without charts and says so.
      }

      if (!cancelled) setLoading(false);
    })();

    return () => {
      cancelled = true;
    };
  }, [simId]);

  useEffect(() => {
    if (simulation?.name) {
      document.title = `${simulation.name} — Saibyl Report`;
      return () => {
        document.title = 'Saibyl — Find out what buyers will object to, before you launch';
      };
    }
  }, [simulation?.name]);

  /* Print once the artifact has had its chance to arrive, so the PDF is never
     missing charts that were one tick from rendering. */
  useEffect(() => {
    if (!loading && report && simulation) {
      const timer = setTimeout(() => window.print(), 1500);
      return () => clearTimeout(timer);
    }
  }, [loading, report, simulation]);

  /* ---------------------------------------------------------------- */

  if (loading) {
    return (
      <div style={centeredStyle}>
        <p style={{ fontSize: 18 }}>Getting this ready to print…</p>
      </div>
    );
  }

  if (!report || !simulation) {
    return (
      <div style={centeredStyle}>
        <p style={{ fontSize: 18 }}>We could not load this run.</p>
      </div>
    );
  }

  // Matched on title alone. The route embeds only `title` and `content` in
  // each section, and `section_type` is not a column on `report_sections` at
  // all — the clauses that tested it could never fire.
  const execSection =
    report.sections.find((s) => /executive|summary|overview/i.test(s.title)) ??
    report.sections[0] ??
    null;

  const conclusionSection =
    report.sections.find((s) =>
      /strategic.*implication|recommended.*action|conclusion/i.test(s.title),
    ) ?? null;

  const detailedSections = report.sections.filter(
    (s) => s !== execSection && s !== conclusionSection,
  );

  /* Chart data — read straight off the artifact, never derived here. */
  const arcData =
    analysis?.sentiment_timeline.map((point) => ({
      round: `R${point.round_number}`,
      mean: point.valence.mean,
      // ErrorBar takes offsets from the value, not absolute bounds.
      error: [
        point.valence.mean - point.valence.lower,
        point.valence.upper - point.valence.mean,
      ] as [number, number],
      agents: point.valence.n,
    })) ?? [];

  const platformData =
    analysis?.by_platform.map((slice) => ({
      key: slice.platform,
      name: PLATFORM_NAMES[slice.platform] ?? slice.platform,
      mean: slice.valence.mean,
      error: [
        slice.valence.mean - slice.valence.lower,
        slice.valence.upper - slice.valence.mean,
      ] as [number, number],
      agents: slice.valence.n,
    })) ?? [];

  /* The stance split is measured, not modelled. The old pie mapped one scraped
     scalar onto an invented positive/neutral/negative population. */
  const stanceData = analysis
    ? [
        { name: 'For it', value: Math.round(analysis.headline.stance.support_pct) },
        { name: 'Undecided', value: Math.round(analysis.headline.stance.undecided_pct) },
        { name: 'Against it', value: Math.round(analysis.headline.stance.oppose_pct) },
        { name: 'Talking about something else', value: Math.round(analysis.headline.stance.off_topic_pct) },
      ].filter((slice) => slice.value > 0)
    : [];

  const stanceColors = [...PRINT_PIE_COLORS, '#94a3b8'];

  return (
    <>
      <style
        dangerouslySetInnerHTML={{
          __html: `
            @page { size: letter; margin: 0.9in; }

            @media print {
              body { margin: 0; background: #fff !important; }
              .no-print { display: none !important; }

              /* The page margin above owns the paper's edges. The screen
                 padding has to come off, or it is added *inside* that margin
                 and the text block drifts a further half-inch in on every
                 side. */
              .print-page { padding: 0 !important; max-width: none !important; box-shadow: none !important; }

              /* Nothing atomic splits across a sheet. A chart cut in half at a
                 page boundary is the defect that makes a printed report look
                 like a screenshot, and the browser will do it by default. */
              .print-figure,
              .print-avoid-break,
              figure,
              table,
              blockquote,
              .recharts-wrapper { break-inside: avoid; page-break-inside: avoid; }

              /* A heading is never the last thing on a sheet. */
              h1, h2, h3, h4 { break-after: avoid; page-break-after: avoid; break-inside: avoid; }

              p, li { orphans: 3; widows: 3; }

              /* Long tables repeat their header on each sheet they span. */
              thead { display: table-header-group; }
              tr { break-inside: avoid; page-break-inside: avoid; }

              /* Print in the colours as drawn rather than the browser's
                 economy rendering — the charts are already legible in
                 greyscale, but a half-dropped fill is legible as neither. */
              * { -webkit-print-color-adjust: exact; print-color-adjust: exact; }
            }

            @media screen {
              body { background: #f8fbff; }
              .print-page { max-width: 800px; margin: 0 auto; background: white; box-shadow: 0 12px 30px rgba(52,96,164,0.12); }
            }
          `,
        }}
      />

      <div
        className="print-page"
        style={{
          fontFamily: "Manrope, system-ui, sans-serif",
          color: INK,
          background: '#ffffff',
          maxWidth: 800,
          margin: '0 auto',
          padding: '40px 48px',
          lineHeight: 1.6,
        }}
      >
        {/* ================= Cover ================= */}
        <div style={{ pageBreakAfter: 'always' }}>
          <div style={{ textAlign: 'center', marginTop: 60 }}>
            <img src="/logo-mark.svg" alt="Saibyl" style={{ width: 96, height: 96, margin: '0 auto' }} />
            <div
              style={{
                fontWeight: 800,
                fontSize: 28,
                letterSpacing: '0.35em',
                color: BRAND,
                marginTop: 16,
              }}
            >
              SAIBYL
            </div>
          </div>

          <hr style={{ border: 'none', borderTop: `2px solid ${BRAND}`, margin: '32px 0' }} />

          {/* The one thing on this page composed from `components/design`, and
              the choice is narrow on purpose.

              `PageHeader` renders a heading, an explanation and one Playfair
              italic line — three static elements. It emits no animation class,
              no gradient and no shadow, and its two colours (`saibyl-ink`,
              `saibyl-violet`) are already this document's own INK and BRAND.
              Its 2rem heading is the 32px this cover already used. So it costs
              the printed page nothing and gives it canvas rule 4, which a
              document that leaves the product and gets forwarded is the last
              place that should be missing it.

              `eyebrow` is deliberately not passed. `Eyebrow`'s dot is drawn
              with a `box-shadow` glow, and a glow on paper is a fuzzy grey
              ring and wasted toner. Everything else on this page stays
              hand-rolled and inline-styled for the same reason: no `Ground`
              (a radial wash is wrong on paper), no `Card` (`sb-stage` is
              glass), no `Deal`/`Rise`, no `sb-hero`.

              No `SIM-{first four characters of the id}` line either. It read
              as a reference number and was not one — four characters off the
              front of a UUID identify nothing and collide between runs, and a
              founder reported three different runs all showing the same
              "SIM-1111". On a document that gets forwarded, a fake identifier
              is worse than none: someone will quote it back. */}
          <PageHeader
            title={simulation.name}
            phrase="They argued about it before your customers ever could."
            className="mt-10 mb-10"
          >
            <p>
              Who was in the room, what they kept coming back to, and the
              sentences behind every number in this document.
            </p>
          </PageHeader>

          <div
            style={{
              display: 'grid',
              gridTemplateColumns: '1fr 1fr',
              gap: '12px 32px',
              fontSize: 13,
              color: INK,
            }}
          >
            <Field label="Printed" value={format(new Date(), 'MMMM d, yyyy')} />
            <Field
              label="Platforms"
              value={simulation.platforms.map((p) => PLATFORM_NAMES[p] ?? p).join(', ')}
            />
            <Field
              label="People in the room"
              value={simulation.agent_count?.toString() ?? 'not recorded'}
            />
            <Field label="Rounds" value={String(simulation.max_rounds)} />
          </div>

          {/* Measurement provenance belongs on the cover of an exported
              document: it is the first thing a reader forwarding this to a
              board should be able to see. */}
          {analysis && (
            <p
              style={{
                marginTop: 32,
                fontSize: 11,
                color: MUTED,
                lineHeight: 1.7,
                borderLeft: `3px solid ${RULE}`,
                paddingLeft: 12,
              }}
            >
              Every figure in this document was measured from what people in the
              room actually wrote — none of it is estimated.{' '}
              {analysis.quality.events_measured.toLocaleString()} of the{' '}
              {analysis.quality.events_total.toLocaleString()} posts and replies could
              be read and scored ({analysis.quality.coverage_pct.toFixed(1)}%), across{' '}
              {analysis.quality.agents_active} people who said something and{' '}
              {analysis.quality.rounds} rounds. Ranges are worked out across people, so
              somebody posting ten times counts as one opinion rather than ten.
            </p>
          )}

          {/* On the cover page, alongside the measurement statement. PRD §4
              requires the people built to argue against you to be labelled
              synthetic in every report and export, and a printed report is the
              artefact most likely to be forwarded to someone who never saw the
              run being set up. The sentence is composed on the server so this
              page, the viewer, the PDF and the JSON export cannot disagree —
              which is also why it is the one string here not rewritten. */}
          {analysis?.adversarial?.enabled && (
            <p
              style={{
                marginTop: 16,
                fontSize: 11,
                color: MUTED,
                lineHeight: 1.7,
                borderLeft: '3px solid #286cf0',
                paddingLeft: 12,
              }}
            >
              {analysis.adversarial.disclosure}
            </p>
          )}

          <p
            style={{
              marginTop: analysis ? 60 : 120,
              fontSize: 10,
              color: MUTED,
              textAlign: 'center',
              letterSpacing: '0.15em',
              textTransform: 'uppercase',
            }}
          >
            CONFIDENTIAL — Prepared by Saibyl · Saido Labs LLC
          </p>
        </div>

        {/* ================= 1. Source Material ================= */}
        <div style={{ pageBreakAfter: 'always' }}>
          <SectionHeader number="1" title="What went in" />

          <p style={{ fontSize: 14, fontWeight: 600, color: INK, marginBottom: 8 }}>
            What we asked
          </p>
          {simulation.prediction_goal.length > 300 ? (
            <div style={quoteBlockStyle}>{simulation.prediction_goal}</div>
          ) : (
            <p style={{ fontSize: 16, lineHeight: 1.7, marginBottom: 20 }}>
              {simulation.prediction_goal}
            </p>
          )}

          {report.source_documents && report.source_documents.length > 0 && (
            <>
              <p style={{ fontSize: 14, fontWeight: 600, color: INK, marginBottom: 8 }}>
                What you gave us to read
              </p>
              {report.source_documents.map((doc) => (
                <div key={doc.filename} style={{ ...quoteBlockStyle, marginBottom: 12 }}>
                  <p
                    style={{
                      fontSize: 11,
                      fontWeight: 600,
                      color: MUTED,
                      textTransform: 'uppercase',
                      letterSpacing: '0.05em',
                      marginBottom: 8,
                    }}
                  >
                    {doc.filename} ({doc.file_type.toUpperCase()}
                    {doc.word_count > 0 ? ` — ${doc.word_count.toLocaleString()} words` : ''})
                  </p>
                  <div style={{ fontSize: 12, color: INK, lineHeight: 1.7, whiteSpace: 'pre-wrap' }}>
                    {doc.text}
                  </div>
                </div>
              ))}
            </>
          )}

          <p style={{ fontSize: 14, fontWeight: 600, color: INK, margin: '20px 0 8px' }}>
            How this run was set up
          </p>
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
            <tbody>
              {[
                ['People in the room', simulation.agent_count?.toString() ?? 'not recorded'],
                ['Rounds', String(simulation.max_rounds)],
                ['Platforms', simulation.platforms.map((p) => PLATFORM_NAMES[p] ?? p).join(', ')],
                ...(simulation.persona_pack_ids?.length
                  ? [['Groups of buyers', simulation.persona_pack_ids.join(', ')]]
                  : []),
                ...(analysis
                  ? [
                      [
                        'Posts and replies we could read',
                        `${analysis.quality.events_measured.toLocaleString()} of ${analysis.quality.events_total.toLocaleString()} (${analysis.quality.coverage_pct.toFixed(1)}%)`,
                      ],
                      ['Scored by', analysis.quality.measurement_model || 'not recorded'],
                    ]
                  : []),
                [
                  'Date run',
                  new Date(simulation.created_at).toLocaleDateString('en-US', {
                    year: 'numeric',
                    month: 'long',
                    day: 'numeric',
                  }),
                ],
              ].map(([label, value]) => (
                <tr key={label}>
                  <td style={{ ...cellStyle, fontWeight: 600, color: MUTED, width: '35%' }}>
                    {label}
                  </td>
                  <td style={cellStyle}>{value}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        {/* ================= 2. Executive Summary ================= */}
        <div style={{ pageBreakAfter: 'always' }}>
          <SectionHeader number="2" title="The short version" />

          {analysis ? (
            <>
              <div
                className="print-avoid-break"
                style={{
                  display: 'grid',
                  gridTemplateColumns: 'repeat(4, 1fr)',
                  gap: 12,
                  marginBottom: 16,
                }}
              >
                <MetricBox
                  label="How the room felt"
                  value={
                    analysis.headline.valence.n > 0
                      ? formatSigned(analysis.headline.valence.mean)
                      : '—'
                  }
                  sub={
                    analysis.headline.valence.n > 1
                      ? `somewhere between ${formatSigned(analysis.headline.valence.lower)} and ${formatSigned(analysis.headline.valence.upper)}`
                      : 'too few people to read'
                  }
                />
                <MetricBox
                  label="Against it"
                  value={`${analysis.headline.stance.oppose_pct.toFixed(0)}%`}
                  sub={`${analysis.headline.stance.support_pct.toFixed(0)}% were for it`}
                />
                <MetricBox
                  label="Which way it moved"
                  value={
                    analysis.headline.trajectory === 'flat'
                      ? 'Held steady'
                      : formatSigned(analysis.headline.trajectory_delta)
                  }
                  sub={TRAJECTORY_COPY[analysis.headline.trajectory]}
                />
                <MetricBox
                  label="People we could read"
                  value={String(analysis.headline.valence.n)}
                  sub={`of ${analysis.quality.agents_total} in the room`}
                />
              </div>

              {analysis.quality.caveats.length > 0 && (
                <div
                  className="print-avoid-break"
                  style={{
                    border: `1px solid ${RULE}`,
                    borderRadius: 8,
                    padding: '12px 16px',
                    marginBottom: 24,
                    fontSize: 11,
                    color: MUTED,
                    lineHeight: 1.7,
                  }}
                >
                  <strong style={{ color: INK }}>What this run can and cannot tell you</strong>
                  <ul style={{ margin: '6px 0 0', paddingLeft: 18 }}>
                    {analysis.quality.caveats.map((caveat) => (
                      <li key={caveat}>{caveat}</li>
                    ))}
                  </ul>
                </div>
              )}
            </>
          ) : (
            <p style={{ ...noticeStyle, marginBottom: 24 }}>
              Nobody has scored what was said in this run, so there are no figures
              here. Nothing in this document is estimated from the written text.
            </p>
          )}

          {execSection && (
            <div style={{ fontSize: 16, lineHeight: 1.7 }}>
              <SectionRenderer content={cleanContent(execSection.content)} printMode />
            </div>
          )}
        </div>

        {/* ================= 3. Data & Analysis ================= */}
        <div style={{ pageBreakBefore: 'always' }}>
          <SectionHeader number="3" title="The numbers" />

          {!analysis && (
            <p style={noticeStyle}>
              Nothing in this run has been scored, so there are no charts. Charts are
              only ever drawn from things that were actually measured.
            </p>
          )}

          {analysis && arcData.length > 0 && (
            <div className="print-figure" style={{ marginBottom: 32 }}>
              <ChartTitle>How the room felt, round by round</ChartTitle>
              <ChartNote>
                Each bar is how the room felt that round, on a scale where +1 is loved
                it and −1 is hated it. The whisker is the range the real figure is
                likely to sit in. Rounds where nobody said anything we could read are
                left out rather than guessed at.
              </ChartNote>
              <BarChart
                width={700}
                height={280}
                data={arcData}
                margin={{ left: 10, right: 20, top: 10, bottom: 10 }}
              >
                <CartesianGrid strokeDasharray="3 3" stroke={RULE} />
                <XAxis dataKey="round" tick={{ fill: INK, fontSize: 12 }} />
                <YAxis domain={[-1, 1]} tick={{ fill: MUTED, fontSize: 11 }} />
                <ReferenceLine y={0} stroke="#999" />
                <Tooltip
                  // Recharts hands these back as ValueType/ReactNode, which
                  // includes undefined — narrowing the parameter to `number`
                  // or `string` is what `tsc -b` rejects. Coerce at the
                  // boundary instead, and render nothing rather than "NaN"
                  // when a point genuinely has no value.
                  formatter={(value) =>
                    typeof value === 'number' ? formatSigned(value) : '—'
                  }
                  labelFormatter={(label) => {
                    const round = String(label ?? '');
                    const point = arcData.find((d) => String(d.round) === round);
                    return `${round} — ${point?.agents ?? 0} people`;
                  }}
                />
                <Bar dataKey="mean" radius={[3, 3, 0, 0]}>
                  {arcData.map((entry) => (
                    <Cell
                      key={entry.round}
                      fill={entry.mean >= 0 ? PRINT_PIE_COLORS[0] : PRINT_PIE_COLORS[2]}
                    />
                  ))}
                  <ErrorBar dataKey="error" width={6} strokeWidth={1.5} stroke="#555" />
                </Bar>
              </BarChart>
            </div>
          )}

          {analysis && platformData.length > 0 && (
            <div className="print-figure" style={{ marginBottom: 32 }}>
              <ChartTitle>How the room felt, by platform</ChartTitle>
              <ChartNote>
                Worst first. Where the whiskers overlap, this run cannot tell those
                platforms apart.
              </ChartNote>
              <BarChart
                width={700}
                height={280}
                data={platformData}
                layout="vertical"
                margin={{ left: 100, right: 20, top: 10, bottom: 10 }}
              >
                <CartesianGrid strokeDasharray="3 3" stroke={RULE} />
                <XAxis type="number" domain={[-1, 1]} tick={{ fill: MUTED, fontSize: 11 }} />
                <YAxis
                  dataKey="name"
                  type="category"
                  tick={{ fill: INK, fontSize: 12 }}
                  width={90}
                />
                <ReferenceLine x={0} stroke="#999" />
                <Tooltip
                  // See the arc chart above: Recharts' callback types are
                  // wider than the data, so coerce here rather than annotate.
                  formatter={(value) =>
                    typeof value === 'number' ? formatSigned(value) : '—'
                  }
                  labelFormatter={(label) => {
                    const name = String(label ?? '');
                    const row = platformData.find((d) => String(d.name) === name);
                    return `${name} — ${row?.agents ?? 0} people`;
                  }}
                />
                <Bar dataKey="mean" radius={[0, 3, 3, 0]}>
                  {platformData.map((entry) => (
                    <Cell key={entry.key} fill={PRINT_PLATFORM_COLORS[entry.key] ?? '#64748b'} />
                  ))}
                  <ErrorBar dataKey="error" width={6} strokeWidth={1.5} stroke="#555" />
                </Bar>
              </BarChart>
            </div>
          )}

          {analysis && stanceData.length > 0 && (
            <div className="print-figure" style={{ marginBottom: 32 }}>
              <ChartTitle>For, against and undecided</ChartTitle>
              <ChartNote>
                How much of what was said took each position. Anything off the subject
                is shown rather than dropped — a room that never engaged is a very
                different result from one that disagreed.
              </ChartNote>
              <PieChart width={700} height={280}>
                <Pie
                  data={stanceData}
                  cx={350}
                  cy={140}
                  outerRadius={100}
                  dataKey="value"
                  label={({ name, value }: { name?: string; value?: number }) =>
                    (value ?? 0) >= 3 ? `${name ?? ''}: ${value ?? 0}%` : ''
                  }
                >
                  {stanceData.map((entry, index) => (
                    <Cell key={entry.name} fill={stanceColors[index % stanceColors.length]} />
                  ))}
                </Pie>
                <Tooltip />
                <Legend />
              </PieChart>
            </div>
          )}

          {analysis && analysis.objections.length > 0 && (
            <div className="print-figure" style={{ marginBottom: 32 }}>
              <ChartTitle>What they pushed back on, worst first</ChartTitle>
              <ChartNote>
                Weight is how far it spread, how strongly it was meant and how many
                kinds of buyer raised it — not how often it came up. Quotes are word
                for word.
              </ChartNote>
              <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12 }}>
                <thead>
                  <tr>
                    {['What they said', 'Weight', 'People', 'First came up', 'Started with'].map(
                      (heading) => (
                        <th
                          key={heading}
                          style={{
                            textAlign: 'left',
                            padding: '6px 8px',
                            borderBottom: `2px solid ${RULE}`,
                            color: MUTED,
                            fontSize: 11,
                            textTransform: 'uppercase',
                            letterSpacing: '0.05em',
                          }}
                        >
                          {heading}
                        </th>
                      ),
                    )}
                  </tr>
                </thead>
                <tbody>
                  {analysis.objections.slice(0, 10).map((objection) => (
                    <tr key={objection.key}>
                      <td style={{ ...cellStyle, fontWeight: 600 }}>{objection.label}</td>
                      <td style={cellStyle}>{objection.load_bearing_score.toFixed(1)}</td>
                      <td style={cellStyle}>{objection.agent_count}</td>
                      <td style={cellStyle}>R{objection.first_round_seen ?? '—'}</td>
                      {/* The label, never the raw key. This document gets
                          forwarded, and "adversarial" in a table cell is a word
                          the reader has to be taught. */}
                      <td style={cellStyle}>
                        {objection.originating_cohort
                          ? groupLabel(objection.originating_cohort)
                          : '—'}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>

              {analysis.objections.slice(0, 3).map((objection) =>
                objection.quotes.length > 0 ? (
                  <div key={objection.key} style={{ marginTop: 16 }}>
                    <p style={{ fontSize: 12, fontWeight: 700, marginBottom: 4 }}>
                      {objection.label}
                    </p>
                    {objection.quotes.slice(0, 2).map((quote) => (
                      <blockquote
                        key={quote.event_id}
                        style={{
                          borderLeft: `3px solid ${BRAND}`,
                          paddingLeft: 12,
                          margin: '6px 0',
                          fontSize: 12,
                          color: INK,
                          fontStyle: 'italic',
                        }}
                      >
                        “{quote.text}”
                        <span style={{ display: 'block', fontStyle: 'normal', fontSize: 10, color: MUTED, marginTop: 2 }}>
                          @{quote.agent_username}
                          {quote.archetype ? ` · ${quote.archetype}` : ''}
                          {quote.round_number != null ? ` · round ${quote.round_number}` : ''}
                        </span>
                      </blockquote>
                    ))}
                  </div>
                ) : null,
              )}
            </div>
          )}

          {analysis && analysis.flashpoints.length > 0 && (
            <div className="print-figure" style={{ marginBottom: 32 }}>
              <ChartTitle>Where the mood turned</ChartTitle>
              <ChartNote>
                Moments where the room moved noticeably between one round and the
                next. A move is only called real when the ranges around the two
                figures do not overlap.
              </ChartNote>
              <ul style={{ margin: 0, paddingLeft: 18, fontSize: 12, lineHeight: 1.8 }}>
                {analysis.flashpoints.slice(0, 6).map((flash) => (
                  <li key={`${flash.round_number}-${flash.delta}`}>
                    <strong>Round {flash.round_number}:</strong>{' '}
                    {formatSigned(flash.valence_before)} → {formatSigned(flash.valence_after)}{' '}
                    ({flash.significant ? 'a real move' : 'too small to be sure'})
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>

        {/* ================= 4. Detailed Findings ================= */}
        <div>
          <SectionHeader number="4" title="In detail" />
          {detailedSections.length === 0 && (
            <p style={{ fontSize: 14, color: MUTED }}>Nothing more was written up.</p>
          )}
          {detailedSections.map((section) => (
            <div key={section.title} style={{ marginBottom: 24 }}>
              <h3 style={{ fontSize: 18, fontWeight: 700, marginBottom: 8 }}>{section.title}</h3>
              <div style={{ fontSize: 14, lineHeight: 1.7, color: INK }}>
                <SectionRenderer
                  content={stripDuplicateTitle(section.title, cleanContent(section.content))}
                  printMode
                />
              </div>
            </div>
          ))}
        </div>

        {/* ================= 5. Strategic Implications ================= */}
        <div>
          <SectionHeader number="5" title="What to do about it" />
          {conclusionSection?.content ? (
            <div style={{ fontSize: 16, lineHeight: 1.7 }}>
              <SectionRenderer
                content={stripDuplicateTitle(
                  conclusionSection.title,
                  cleanContent(conclusionSection.content),
                )}
                printMode
              />
            </div>
          ) : (
            <p style={{ fontSize: 14, color: MUTED }}>
              This appears once the write-up finishes.
            </p>
          )}
        </div>
      </div>
    </>
  );
}

/* ------------------------------------------------------------------ */
/*  Sub-components and shared styles                                   */
/* ------------------------------------------------------------------ */

const centeredStyle: React.CSSProperties = {
  display: 'flex',
  alignItems: 'center',
  justifyContent: 'center',
  minHeight: '100vh',
  fontFamily: "Manrope, system-ui, sans-serif",
  color: MUTED,
  background: '#fff',
};

const quoteBlockStyle: React.CSSProperties = {
  background: '#f4f8fd',
  border: `1px solid ${RULE}`,
  borderRadius: 8,
  padding: '16px 20px',
  fontSize: 12,
  color: INK,
  lineHeight: 1.7,
  whiteSpace: 'pre-wrap',
  marginBottom: 20,
};

const cellStyle: React.CSSProperties = {
  padding: '6px 8px',
  borderBottom: `1px solid ${RULE}`,
  color: INK,
  verticalAlign: 'top',
};

const noticeStyle: React.CSSProperties = {
  fontSize: 13,
  color: MUTED,
  lineHeight: 1.7,
  border: `1px dashed ${RULE}`,
  borderRadius: 8,
  padding: '12px 16px',
};

function Field({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <span style={{ color: MUTED, fontWeight: 600 }}>{label}</span>
      <br />
      {value}
    </div>
  );
}

function ChartTitle({ children }: { children: React.ReactNode }) {
  return (
    <h4 style={{ fontSize: 14, fontWeight: 700, color: INK, marginBottom: 4 }}>{children}</h4>
  );
}

function ChartNote({ children }: { children: React.ReactNode }) {
  return (
    <p style={{ fontSize: 11, color: MUTED, marginBottom: 12, lineHeight: 1.6 }}>{children}</p>
  );
}

function SectionHeader({ number, title }: { number: string; title: string }) {
  return (
    <div style={{ marginBottom: 20, marginTop: 32 }}>
      <h2
        style={{
          fontSize: 22,
          fontWeight: 800,
          margin: 0,
          paddingBottom: 8,
          borderBottom: `3px solid ${BRAND}`,
          display: 'inline-block',
        }}
      >
        {number ? `${number}. ` : ''}
        <span dangerouslySetInnerHTML={{ __html: title }} />
      </h2>
    </div>
  );
}

function MetricBox({ label, value, sub }: { label: string; value: string; sub?: string }) {
  return (
    <div style={{ border: `1px solid ${RULE}`, borderRadius: 8, padding: '12px 14px', textAlign: 'center' }}>
      <div
        style={{
          fontSize: 10,
          color: MUTED,
          fontWeight: 600,
          textTransform: 'uppercase',
          letterSpacing: '0.05em',
          marginBottom: 4,
        }}
      >
        {label}
      </div>
      <div style={{ fontSize: 20, fontWeight: 800 }}>{value}</div>
      {sub && <div style={{ fontSize: 10, color: MUTED, marginTop: 4 }}>{sub}</div>}
    </div>
  );
}
