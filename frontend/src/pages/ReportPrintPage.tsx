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
import { PRINT_PIE_COLORS, PRINT_PLATFORM_COLORS } from '@/lib/constants';
import { cleanContent, stripDuplicateTitle } from '@/lib/utils';
import {
  formatSigned,
  isSupportedSchema,
  withSchemaDefaults,
  type AnalysisResponse,
  type SimulationAnalysis,
} from '@/lib/analysis';

/* ------------------------------------------------------------------ */
/*  Types                                                              */
/* ------------------------------------------------------------------ */

interface SourceDocument {
  filename: string;
  file_type: string;
  word_count: number;
  text: string;
}

interface Report {
  id: string;
  simulation_id: string;
  status?: string;
  sections: { section_type?: string; title: string; content: string }[];
  full_markdown: string;
  source_documents?: SourceDocument[];
}

interface SimDetail {
  id: string;
  name: string;
  status: string;
  prediction_goal: string;
  platforms: string[];
  agent_count: number;
  max_rounds: number;
  persona_pack_ids?: string[];
  description?: string;
  created_at: string;
  completed_at: string | null;
}

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

const INK = '#1a1a1a';
const MUTED = '#666';
const RULE = '#e0e0e0';
const BRAND = '#8B5CF6';

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
 */
export default function ReportPrintPage() {
  const { id: simId } = useParams<{ id: string }>();

  const [report, setReport] = useState<Report | null>(null);
  const [simulation, setSimulation] = useState<SimDetail | null>(null);
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
        setReport(reportRes.data as Report);
        setSimulation(simRes.data as SimDetail);
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
        document.title = 'Saibyl — Know the Conversation Before It Happens';
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
        <p style={{ fontSize: 18 }}>Preparing report for export...</p>
      </div>
    );
  }

  if (!report || !simulation) {
    return (
      <div style={centeredStyle}>
        <p style={{ fontSize: 18 }}>Report data could not be loaded.</p>
      </div>
    );
  }

  const execSection =
    report.sections.find(
      (s) =>
        /executive|summary|overview/i.test(s.title) ||
        s.section_type === 'executive_summary',
    ) ??
    report.sections[0] ??
    null;

  const conclusionSection =
    report.sections.find(
      (s) =>
        /strategic.*implication|recommended.*action|conclusion/i.test(s.title) ||
        s.section_type === 'conclusion' ||
        s.section_type === 'recommendations',
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
        { name: 'Support', value: Math.round(analysis.headline.stance.support_pct) },
        { name: 'Undecided', value: Math.round(analysis.headline.stance.undecided_pct) },
        { name: 'Oppose', value: Math.round(analysis.headline.stance.oppose_pct) },
        { name: 'Off-topic', value: Math.round(analysis.headline.stance.off_topic_pct) },
      ].filter((slice) => slice.value > 0)
    : [];

  const stanceColors = [...PRINT_PIE_COLORS, '#94a3b8'];

  return (
    <>
      <style
        dangerouslySetInnerHTML={{
          __html: `
            @media print {
              body { margin: 0; background: #fff !important; }
              @page { margin: 1in 0.75in; size: letter; }
              .no-print { display: none !important; }
            }
            @media screen {
              body { background: #f5f5f5; }
              .print-page { max-width: 800px; margin: 0 auto; background: white; box-shadow: 0 2px 20px rgba(0,0,0,0.1); }
            }
          `,
        }}
      />

      <div
        className="print-page"
        style={{
          fontFamily: "'Aktiv Grotesk', system-ui, sans-serif",
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

          <h1 style={{ fontSize: 32, fontWeight: 800, margin: '40px 0 8px', lineHeight: 1.2 }}>
            {simulation.name}
          </h1>
          <p style={{ fontSize: 14, color: MUTED, fontWeight: 500, margin: '0 0 40px' }}>
            SIM-{simId?.slice(0, 4).toUpperCase()} &middot; Intelligence Report
          </p>

          <div
            style={{
              display: 'grid',
              gridTemplateColumns: '1fr 1fr',
              gap: '12px 32px',
              fontSize: 13,
              color: '#333',
            }}
          >
            <Field label="Date Generated" value={format(new Date(), 'MMMM d, yyyy')} />
            <Field
              label="Platforms"
              value={simulation.platforms.map((p) => PLATFORM_NAMES[p] ?? p).join(', ')}
            />
            <Field label="Agents" value={String(simulation.agent_count)} />
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
              Every figure in this document is measured from what the simulated
              agents wrote. {analysis.quality.events_measured.toLocaleString()} of{' '}
              {analysis.quality.events_total.toLocaleString()} events were scored (
              {analysis.quality.coverage_pct.toFixed(1)}% coverage) across{' '}
              {analysis.quality.agents_active} active agents and{' '}
              {analysis.quality.rounds} rounds. Confidence intervals are computed
              across agents. Overall confidence: {analysis.quality.confidence}.
            </p>
          )}

          {/* On the cover page, alongside the measurement statement. PRD §4
              requires adversarial agents to be labelled synthetic in every
              report and export, and a printed report is the artefact most
              likely to be forwarded to someone who never saw the run being
              configured. The sentence is composed on the server so this page,
              the viewer, the PDF and the JSON export cannot disagree. */}
          {analysis?.adversarial?.enabled && (
            <p
              style={{
                marginTop: 16,
                fontSize: 11,
                color: MUTED,
                lineHeight: 1.7,
                borderLeft: '3px solid #C9A227',
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
              color: '#999',
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
          <SectionHeader number="1" title="Source Material" />

          <p style={{ fontSize: 14, fontWeight: 600, color: '#333', marginBottom: 8 }}>
            Scenario / Question Analyzed
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
              <p style={{ fontSize: 14, fontWeight: 600, color: '#333', marginBottom: 8 }}>
                Input Article / Document
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
                  <div style={{ fontSize: 12, color: '#444', lineHeight: 1.7, whiteSpace: 'pre-wrap' }}>
                    {doc.text}
                  </div>
                </div>
              ))}
            </>
          )}

          <p style={{ fontSize: 14, fontWeight: 600, color: '#333', margin: '20px 0 8px' }}>
            Simulation Parameters
          </p>
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
            <tbody>
              {[
                ['Agents generated', String(simulation.agent_count)],
                ['Rounds', String(simulation.max_rounds)],
                ['Platforms', simulation.platforms.map((p) => PLATFORM_NAMES[p] ?? p).join(', ')],
                ...(simulation.persona_pack_ids?.length
                  ? [['Persona packs', simulation.persona_pack_ids.join(', ')]]
                  : []),
                ...(analysis
                  ? [
                      [
                        'Events measured',
                        `${analysis.quality.events_measured.toLocaleString()} of ${analysis.quality.events_total.toLocaleString()} (${analysis.quality.coverage_pct.toFixed(1)}%)`,
                      ],
                      ['Measurement model', analysis.quality.measurement_model || '—'],
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
                  <td style={{ ...cellStyle, fontWeight: 600, color: '#555', width: '35%' }}>
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
          <SectionHeader number="2" title="Executive Summary" />

          {analysis ? (
            <>
              <div
                style={{
                  display: 'grid',
                  gridTemplateColumns: 'repeat(4, 1fr)',
                  gap: 12,
                  marginBottom: 16,
                }}
              >
                <MetricBox
                  label="Overall sentiment"
                  value={
                    analysis.headline.valence.n > 0
                      ? formatSigned(analysis.headline.valence.mean)
                      : 'N/A'
                  }
                  sub={
                    analysis.headline.valence.n > 1
                      ? `95% CI ${formatSigned(analysis.headline.valence.lower)} to ${formatSigned(analysis.headline.valence.upper)}`
                      : 'not resolvable'
                  }
                />
                <MetricBox
                  label="Opposed"
                  value={`${analysis.headline.stance.oppose_pct.toFixed(0)}%`}
                  sub={`${analysis.headline.stance.support_pct.toFixed(0)}% support`}
                />
                <MetricBox
                  label="Trajectory"
                  value={
                    analysis.headline.trajectory === 'flat'
                      ? 'Flat'
                      : formatSigned(analysis.headline.trajectory_delta)
                  }
                  sub={analysis.headline.trajectory}
                />
                <MetricBox
                  label="Agents measured"
                  value={String(analysis.headline.valence.n)}
                  sub={`of ${analysis.quality.agents_total} generated`}
                />
              </div>

              {analysis.quality.caveats.length > 0 && (
                <div
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
                  <strong style={{ color: '#333' }}>What this run can and cannot show</strong>
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
              This run has not been analysed, so no measured figures are included.
              Nothing in this document is estimated from the narrative text.
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
          <SectionHeader number="3" title="Data &amp; Analysis" />

          {!analysis && (
            <p style={noticeStyle}>
              No analysis artifact exists for this run, so there are no charts.
              Charts are only drawn from measured data.
            </p>
          )}

          {analysis && arcData.length > 0 && (
            <div style={{ marginBottom: 32 }}>
              <ChartTitle>Sentiment by round</ChartTitle>
              <ChartNote>
                Bars are the mean valence per round; whiskers are the 95% confidence
                interval computed across agents. Rounds with no measurable opinion
                are omitted rather than interpolated.
              </ChartNote>
              <BarChart
                width={700}
                height={280}
                data={arcData}
                margin={{ left: 10, right: 20, top: 10, bottom: 10 }}
              >
                <CartesianGrid strokeDasharray="3 3" stroke={RULE} />
                <XAxis dataKey="round" tick={{ fill: '#333', fontSize: 12 }} />
                <YAxis domain={[-1, 1]} tick={{ fill: MUTED, fontSize: 11 }} />
                <ReferenceLine y={0} stroke="#999" />
                <Tooltip
                  formatter={(value: number) => formatSigned(value)}
                  labelFormatter={(label: string) => {
                    const point = arcData.find((d) => d.round === label);
                    return `${label} — ${point?.agents ?? 0} agents`;
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
            <div style={{ marginBottom: 32 }}>
              <ChartTitle>Sentiment by platform</ChartTitle>
              <ChartNote>
                Ordered most negative first. Where whiskers overlap, this run does
                not resolve a difference between those platforms.
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
                  tick={{ fill: '#333', fontSize: 12 }}
                  width={90}
                />
                <ReferenceLine x={0} stroke="#999" />
                <Tooltip
                  formatter={(value: number) => formatSigned(value)}
                  labelFormatter={(label: string) => {
                    const row = platformData.find((d) => d.name === label);
                    return `${label} — ${row?.agents ?? 0} agents`;
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
            <div style={{ marginBottom: 32 }}>
              <ChartTitle>Stance distribution</ChartTitle>
              <ChartNote>
                Share of measured events taking each position on the subject.
                Off-topic events are shown rather than dropped — a swarm that
                never engaged is a different result from one that disagreed.
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
            <div style={{ marginBottom: 32 }}>
              <ChartTitle>Objections, ranked by load-bearing weight</ChartTitle>
              <ChartNote>
                Weight is reach × intensity × cohort spread — not how often an
                objection was repeated. Quotes are verbatim agent output.
              </ChartNote>
              <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12 }}>
                <thead>
                  <tr>
                    {['Objection', 'Weight', 'Agents', 'First seen', 'Originating cohort'].map(
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
                      <td style={cellStyle}>{objection.originating_cohort ?? '—'}</td>
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
                          color: '#444',
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
            <div style={{ marginBottom: 32 }}>
              <ChartTitle>Flashpoints</ChartTitle>
              <ChartNote>
                Round-to-round shifts larger than 0.15. Only shifts whose intervals
                separate are marked as measured; the rest are directional.
              </ChartNote>
              <ul style={{ margin: 0, paddingLeft: 18, fontSize: 12, lineHeight: 1.8 }}>
                {analysis.flashpoints.slice(0, 6).map((flash) => (
                  <li key={`${flash.round_number}-${flash.delta}`}>
                    <strong>Round {flash.round_number}:</strong>{' '}
                    {formatSigned(flash.valence_before)} → {formatSigned(flash.valence_after)}{' '}
                    ({flash.significant ? 'measured shift' : 'within the bands'})
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>

        {/* ================= 4. Detailed Findings ================= */}
        <div>
          <SectionHeader number="4" title="Detailed Findings" />
          {detailedSections.length === 0 && (
            <p style={{ fontSize: 14, color: MUTED }}>No additional sections available.</p>
          )}
          {detailedSections.map((section) => (
            <div key={section.title} style={{ marginBottom: 24 }}>
              <h3 style={{ fontSize: 18, fontWeight: 700, marginBottom: 8 }}>{section.title}</h3>
              <div style={{ fontSize: 14, lineHeight: 1.7, color: '#333' }}>
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
          <SectionHeader number="5" title="Strategic Implications &amp; Recommended Actions" />
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
              Strategic implications will appear once the report generation completes.
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
  fontFamily: "'Aktiv Grotesk', system-ui, sans-serif",
  color: MUTED,
  background: '#fff',
};

const quoteBlockStyle: React.CSSProperties = {
  background: '#f7f7f7',
  border: `1px solid ${RULE}`,
  borderRadius: 8,
  padding: '16px 20px',
  fontSize: 12,
  color: '#444',
  lineHeight: 1.7,
  whiteSpace: 'pre-wrap',
  marginBottom: 20,
};

const cellStyle: React.CSSProperties = {
  padding: '6px 8px',
  borderBottom: '1px solid #eee',
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
      <span style={{ color: '#999', fontWeight: 600 }}>{label}</span>
      <br />
      {value}
    </div>
  );
}

function ChartTitle({ children }: { children: React.ReactNode }) {
  return (
    <h4 style={{ fontSize: 14, fontWeight: 700, color: '#333', marginBottom: 4 }}>{children}</h4>
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
          color: '#999',
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
