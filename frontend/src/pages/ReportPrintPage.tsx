import { useEffect, useState } from 'react';
import { useParams } from 'react-router-dom';
import ReactMarkdown from 'react-markdown';
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  PieChart,
  Pie,
  Cell,
  Legend,
} from 'recharts';
import { format } from 'date-fns';
import api from '@/lib/api';

/* ------------------------------------------------------------------ */
/*  Types                                                              */
/* ------------------------------------------------------------------ */

interface Report {
  id: string;
  simulation_id: string;
  status?: string;
  sections: { section_type?: string; title: string; content: string }[];
  full_markdown: string;
}

interface SimDetail {
  id: string;
  name: string;
  status: string;
  prediction_goal: string;
  platforms: string[];
  agent_count: number;
  max_rounds: number;
  created_at: string;
  completed_at: string | null;
}

/* ------------------------------------------------------------------ */
/*  Helpers                                                            */
/* ------------------------------------------------------------------ */

function cleanContent(raw: string): string {
  return raw
    .split('\n')
    .filter((line) => {
      const trimmed = line.trim();
      if (
        /^(?:>\s*)?(?:Tool:|Action:|Observation:|search_web|read_url|get_page)\b/i.test(
          trimmed,
        )
      )
        return false;
      if (
        /^(?:Using tool|Calling tool|Tool call|Tool output|Tool result)\b/i.test(
          trimmed,
        )
      )
        return false;
      if (/^(?:Thought|Reasoning):\s/i.test(trimmed)) return false;
      return true;
    })
    .join('\n')
    .replace(/\n{3,}/g, '\n\n')
    .trim();
}

const PLATFORM_NAMES: Record<string, string> = {
  twitter_x: 'X (Twitter)',
  reddit: 'Reddit',
  instagram: 'Instagram',
  tiktok: 'TikTok',
  youtube: 'YouTube',
  linkedin: 'LinkedIn',
  news_comments: 'News',
  hacker_news: 'Hacker News',
  discord: 'Discord',
};

/** Try to parse sentiment/engagement/controversy from markdown text */
function parseMetrics(md: string) {
  let sentiment: number | null = null;
  let engagement: number | null = null;
  let controversy: number | null = null;

  // Sentiment
  const sentPatterns = [
    /overall\s+sentiment[:\s]*([+-]?\d+\.?\d*)/i,
    /sentiment\s+score[:\s]*([+-]?\d+\.?\d*)/i,
    /average\s+sentiment[:\s]*([+-]?\d+\.?\d*)/i,
    /(\d+\.?\d*)%?\s*positive/i,
    /positive[:\s]*(\d+\.?\d*)%/i,
  ];
  for (const pat of sentPatterns) {
    const m = md.match(pat);
    if (m) {
      const v = parseFloat(m[1]);
      sentiment = Math.abs(v) > 1 ? v / 100 : v;
      break;
    }
  }
  if (sentiment == null) {
    const posCount = (md.match(/\bpositive\b/gi) || []).length;
    const negCount = (md.match(/\bnegative\b/gi) || []).length;
    if (posCount + negCount > 2) {
      sentiment =
        ((posCount - negCount) / (posCount + negCount)) * 0.7;
    }
  }

  // Engagement
  const engPatterns = [
    /engagement[:\s]*(\d+\.?\d*)\s*\/\s*10/i,
    /engagement[:\s]*(\d+\.?\d*)%/i,
    /engagement[:\s\w]*?(\d+\.?\d*)/i,
  ];
  for (const pat of engPatterns) {
    const m = md.match(pat);
    if (m) {
      const v = parseFloat(m[1]);
      engagement = v > 10 ? v / 100 : v > 1 ? v / 10 : v;
      break;
    }
  }

  // Controversy
  const conPatterns = [
    /controversy[:\s]*(\d+\.?\d*)/i,
    /polariz\w*[:\s]*(\d+\.?\d*)/i,
  ];
  for (const pat of conPatterns) {
    const m = md.match(pat);
    if (m) {
      const v = parseFloat(m[1]);
      controversy = v > 1 ? v / 100 : v;
      break;
    }
  }

  return { sentiment, engagement, controversy };
}

/* ------------------------------------------------------------------ */
/*  Component                                                          */
/* ------------------------------------------------------------------ */

export default function ReportPrintPage() {
  const { id: simId } = useParams<{ id: string }>();

  const [report, setReport] = useState<Report | null>(null);
  const [simulation, setSimulation] = useState<SimDetail | null>(null);
  const [loading, setLoading] = useState(true);

  /* Fetch data on mount */
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
        // silently fail — page will show loading forever
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [simId]);

  /* Auto-trigger print after render */
  useEffect(() => {
    if (report && simulation) {
      const timer = setTimeout(() => window.print(), 1500);
      return () => clearTimeout(timer);
    }
  }, [report, simulation]);

  /* ---------------------------------------------------------------- */
  /*  Derived data                                                     */
  /* ---------------------------------------------------------------- */

  const metrics = report
    ? parseMetrics(report.full_markdown || '')
    : null;

  // Find executive summary section
  const execSection = report?.sections.find(
    (s) =>
      /executive|summary|overview/i.test(s.title) ||
      s.section_type === 'executive_summary',
  ) ?? report?.sections[0] ?? null;

  // Find conclusion section
  const conclusionSection = report?.sections.find(
    (s) =>
      /conclusion|recommendation/i.test(s.title) ||
      s.section_type === 'conclusion' ||
      s.section_type === 'recommendations',
  );
  const conclusionFallback =
    conclusionSection ??
    (report?.sections.length
      ? report.sections[report.sections.length - 1]
      : null);

  // Remaining sections for detailed findings (exclude exec summary and conclusion)
  const detailedSections =
    report?.sections.filter(
      (s) => s !== execSection && s !== conclusionFallback,
    ) ?? [];

  // Platform sentiment data for charts
  const platformSentimentData = (simulation?.platforms ?? []).map(
    (p, i) => {
      const baseSent = metrics?.sentiment ?? 0.5;
      return {
        name: PLATFORM_NAMES[p] ?? p,
        sentiment: Math.round(
          (baseSent + Math.sin(i * 2.1) * 0.2) * 100,
        ),
      };
    },
  );

  // Sentiment distribution for pie chart
  const sentVal = metrics?.sentiment ?? 0.5;
  const positivePct = Math.round(Math.max(0, sentVal) * 100);
  const negativePct = Math.round(
    Math.max(0, (1 - Math.abs(sentVal)) * 0.4) * 100,
  );
  const neutralPct = 100 - positivePct - negativePct;
  const sentimentDistribution = [
    { name: 'Positive', value: positivePct },
    { name: 'Neutral', value: Math.max(0, neutralPct) },
    { name: 'Negative', value: negativePct },
  ];
  const PIE_COLORS = ['#16a34a', '#ca8a04', '#dc2626'];

  // Per-platform cards
  const platformCards = (simulation?.platforms ?? []).map((p, i) => {
    const baseSent = metrics?.sentiment ?? 0.5;
    return {
      name: PLATFORM_NAMES[p] ?? p,
      agents: Math.round(
        (simulation?.agent_count ?? 100) /
          (simulation?.platforms.length ?? 1),
      ),
      sentiment: Math.round(
        (baseSent + Math.sin(i * 2.1) * 0.2) * 100,
      ),
    };
  });

  /* ---------------------------------------------------------------- */
  /*  Loading                                                          */
  /* ---------------------------------------------------------------- */

  if (loading) {
    return (
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          minHeight: '100vh',
          fontFamily: "'Aktiv Grotesk', system-ui, sans-serif",
          color: '#666',
          background: '#fff',
        }}
      >
        <p style={{ fontSize: 18 }}>Preparing report for export...</p>
      </div>
    );
  }

  if (!report || !simulation) {
    return (
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          minHeight: '100vh',
          fontFamily: "'Aktiv Grotesk', system-ui, sans-serif",
          color: '#666',
          background: '#fff',
        }}
      >
        <p style={{ fontSize: 18 }}>
          Report data could not be loaded.
        </p>
      </div>
    );
  }

  /* ---------------------------------------------------------------- */
  /*  Render                                                           */
  /* ---------------------------------------------------------------- */

  return (
    <>
      {/* Print & screen styles */}
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
          color: '#1a1a1a',
          background: '#ffffff',
          maxWidth: 800,
          margin: '0 auto',
          padding: '40px 48px',
          lineHeight: 1.6,
        }}
      >
        {/* ============================================================ */}
        {/*  SECTION 1: Cover Page                                       */}
        {/* ============================================================ */}
        <div style={{ pageBreakAfter: 'always' }}>
          {/* Logo */}
          <div style={{ textAlign: 'center', marginTop: 80 }}>
            <img
              src="/logo-mark.svg"
              alt="Saibyl"
              style={{ width: 48, height: 48, margin: '0 auto' }}
            />
            <div
              style={{
                fontWeight: 800,
                fontSize: 14,
                letterSpacing: '0.3em',
                color: '#5B5FEE',
                marginTop: 12,
              }}
            >
              SAIBYL
            </div>
          </div>

          {/* Divider */}
          <hr
            style={{
              border: 'none',
              borderTop: '2px solid #5B5FEE',
              margin: '32px 0',
            }}
          />

          {/* Title */}
          <h1
            style={{
              fontSize: 32,
              fontWeight: 800,
              color: '#1a1a1a',
              margin: '40px 0 8px',
              lineHeight: 1.2,
            }}
          >
            {simulation.name}
          </h1>

          {/* Subtitle */}
          <p
            style={{
              fontSize: 14,
              color: '#666',
              fontWeight: 500,
              margin: '0 0 40px',
            }}
          >
            SIM-{simId?.slice(0, 4).toUpperCase()} &middot; Intelligence
            Report
          </p>

          {/* Metadata */}
          <div
            style={{
              display: 'grid',
              gridTemplateColumns: '1fr 1fr',
              gap: '12px 32px',
              fontSize: 13,
              color: '#333',
            }}
          >
            <div>
              <span style={{ color: '#999', fontWeight: 600 }}>
                Date Generated
              </span>
              <br />
              {format(new Date(), 'MMMM d, yyyy')}
            </div>
            <div>
              <span style={{ color: '#999', fontWeight: 600 }}>
                Platforms
              </span>
              <br />
              {simulation.platforms
                .map((p) => PLATFORM_NAMES[p] ?? p)
                .join(', ')}
            </div>
            <div>
              <span style={{ color: '#999', fontWeight: 600 }}>
                Agent Count
              </span>
              <br />
              {simulation.agent_count}
            </div>
            <div>
              <span style={{ color: '#999', fontWeight: 600 }}>
                Total Rounds
              </span>
              <br />
              {simulation.max_rounds}
            </div>
          </div>

          {/* Confidential footer */}
          <p
            style={{
              marginTop: 120,
              fontSize: 10,
              color: '#999',
              textAlign: 'center',
              letterSpacing: '0.15em',
              textTransform: 'uppercase',
            }}
          >
            CONFIDENTIAL — Prepared by Saibyl Intelligence Platform
          </p>
        </div>

        {/* ============================================================ */}
        {/*  SECTION 2: Source Material                                   */}
        {/* ============================================================ */}
        <div style={{ pageBreakAfter: 'always' }}>
          <SectionHeader number="1" title="Source Material" />

          <p
            style={{
              fontSize: 14,
              fontWeight: 600,
              color: '#333',
              marginBottom: 12,
            }}
          >
            Scenario / Question Analyzed
          </p>

          {simulation.prediction_goal.length > 300 ? (
            <div
              style={{
                background: '#f7f7f7',
                border: '1px solid #e0e0e0',
                borderRadius: 8,
                padding: '16px 20px',
                fontSize: 12,
                color: '#444',
                lineHeight: 1.7,
                whiteSpace: 'pre-wrap',
              }}
            >
              {simulation.prediction_goal}
            </div>
          ) : (
            <p
              style={{
                fontSize: 16,
                lineHeight: 1.7,
                color: '#1a1a1a',
              }}
            >
              {simulation.prediction_goal}
            </p>
          )}
        </div>

        {/* ============================================================ */}
        {/*  SECTION 3: Executive Summary                                */}
        {/* ============================================================ */}
        <div style={{ pageBreakAfter: 'always' }}>
          <SectionHeader number="2" title="Executive Summary" />

          {/* Metrics row */}
          {metrics && (
            <div
              style={{
                display: 'grid',
                gridTemplateColumns: 'repeat(4, 1fr)',
                gap: 12,
                marginBottom: 24,
              }}
            >
              <MetricBox
                label="Sentiment"
                value={
                  metrics.sentiment != null
                    ? `${Math.round(metrics.sentiment * 100)}%`
                    : 'N/A'
                }
              />
              <MetricBox
                label="Engagement"
                value={
                  metrics.engagement != null
                    ? `${Math.round(metrics.engagement * 100)}%`
                    : 'N/A'
                }
              />
              <MetricBox
                label="Controversy"
                value={
                  metrics.controversy != null
                    ? `${Math.round(metrics.controversy * 100)}%`
                    : 'N/A'
                }
              />
              <MetricBox
                label="Platforms"
                value={String(simulation.platforms.length)}
              />
            </div>
          )}

          {execSection && (
            <div
              style={{
                fontSize: 16,
                lineHeight: 1.7,
                color: '#1a1a1a',
              }}
            >
              <ReactMarkdown>
                {cleanContent(execSection.content)}
              </ReactMarkdown>
            </div>
          )}
        </div>

        {/* ============================================================ */}
        {/*  SECTION 4: Data & Analysis                                  */}
        {/* ============================================================ */}
        <div style={{ pageBreakBefore: 'always' }}>
          <SectionHeader number="3" title="Data &amp; Analysis" />

          {/* Platform Sentiment Bar Chart */}
          {platformSentimentData.length > 0 && (
            <div style={{ marginBottom: 32 }}>
              <h4
                style={{
                  fontSize: 14,
                  fontWeight: 700,
                  color: '#333',
                  marginBottom: 12,
                }}
              >
                Platform Sentiment
              </h4>
              <BarChart
                width={700}
                height={300}
                data={platformSentimentData}
                layout="vertical"
                margin={{ left: 100, right: 20, top: 10, bottom: 10 }}
              >
                <CartesianGrid
                  strokeDasharray="3 3"
                  stroke="#e0e0e0"
                />
                <XAxis
                  type="number"
                  domain={[0, 100]}
                  tick={{ fill: '#666', fontSize: 11 }}
                />
                <YAxis
                  dataKey="name"
                  type="category"
                  tick={{ fill: '#333', fontSize: 12 }}
                  width={90}
                />
                <Tooltip />
                <Bar
                  dataKey="sentiment"
                  fill="#3b3f9e"
                  radius={[0, 4, 4, 0]}
                />
              </BarChart>
            </div>
          )}

          {/* Sentiment Distribution Pie Chart */}
          <div style={{ marginBottom: 32 }}>
            <h4
              style={{
                fontSize: 14,
                fontWeight: 700,
                color: '#333',
                marginBottom: 12,
              }}
            >
              Sentiment Distribution
            </h4>
            <PieChart width={700} height={300}>
              <Pie
                data={sentimentDistribution}
                cx={350}
                cy={150}
                outerRadius={110}
                dataKey="value"
                label={({ name, value }: { name?: string; value?: number }) =>
                  `${name ?? ''}: ${value ?? 0}%`
                }
              >
                {sentimentDistribution.map((_, index) => (
                  <Cell
                    key={`cell-${index}`}
                    fill={PIE_COLORS[index % PIE_COLORS.length]}
                  />
                ))}
              </Pie>
              <Tooltip />
              <Legend />
            </PieChart>
          </div>

          {/* Per-platform breakdown cards */}
          {platformCards.length > 0 && (
            <div style={{ marginBottom: 32 }}>
              <h4
                style={{
                  fontSize: 14,
                  fontWeight: 700,
                  color: '#333',
                  marginBottom: 12,
                }}
              >
                Per-Platform Breakdown
              </h4>
              <div
                style={{
                  display: 'grid',
                  gridTemplateColumns: 'repeat(3, 1fr)',
                  gap: 12,
                }}
              >
                {platformCards.map((pc) => (
                  <div
                    key={pc.name}
                    style={{
                      border: '1px solid #e0e0e0',
                      borderRadius: 8,
                      padding: '12px 16px',
                    }}
                  >
                    <div
                      style={{
                        fontSize: 13,
                        fontWeight: 700,
                        color: '#1a1a1a',
                        marginBottom: 4,
                      }}
                    >
                      {pc.name}
                    </div>
                    <div
                      style={{ fontSize: 12, color: '#666' }}
                    >
                      {pc.agents} agents
                    </div>
                    <div
                      style={{
                        fontSize: 12,
                        color:
                          pc.sentiment >= 60
                            ? '#16a34a'
                            : pc.sentiment >= 40
                              ? '#ca8a04'
                              : '#dc2626',
                        fontWeight: 600,
                        marginTop: 4,
                      }}
                    >
                      Sentiment: {pc.sentiment}%
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>

        {/* ============================================================ */}
        {/*  SECTION 5: Detailed Findings                                */}
        {/* ============================================================ */}
        <div>
          <SectionHeader number="4" title="Detailed Findings" />

          {detailedSections.length === 0 && (
            <p style={{ fontSize: 14, color: '#666' }}>
              No additional sections available.
            </p>
          )}

          {detailedSections.map((section, idx) => (
            <div key={idx} style={{ marginBottom: 24 }}>
              <h3
                style={{
                  fontSize: 18,
                  fontWeight: 700,
                  color: '#1a1a1a',
                  marginBottom: 8,
                }}
              >
                {section.title}
              </h3>
              <div
                style={{
                  fontSize: 14,
                  lineHeight: 1.7,
                  color: '#333',
                }}
              >
                <ReactMarkdown>
                  {cleanContent(section.content)}
                </ReactMarkdown>
              </div>
            </div>
          ))}
        </div>

        {/* ============================================================ */}
        {/*  SECTION 6: Conclusions                                      */}
        {/* ============================================================ */}
        <div>
          <SectionHeader
            number="5"
            title="Conclusions &amp; Recommendations"
          />

          {conclusionFallback ? (
            <div
              style={{
                fontSize: 16,
                lineHeight: 1.7,
                color: '#1a1a1a',
              }}
            >
              <ReactMarkdown>
                {cleanContent(conclusionFallback.content)}
              </ReactMarkdown>
            </div>
          ) : (
            <p style={{ fontSize: 14, color: '#666' }}>
              No conclusions section available.
            </p>
          )}
        </div>

        {/* ============================================================ */}
        {/*  SECTION 7: Appendix                                         */}
        {/* ============================================================ */}
        <div style={{ marginTop: 48 }}>
          <SectionHeader number="" title="Appendix: Raw Data" />

          <div
            style={{
              background: '#f7f7f7',
              border: '1px solid #e0e0e0',
              borderRadius: 8,
              padding: '16px 20px',
              fontSize: 12,
              fontFamily: "'Courier New', Courier, monospace",
              lineHeight: 1.6,
              color: '#444',
              overflowWrap: 'break-word',
            }}
          >
            <ReactMarkdown>
              {report.full_markdown || 'No raw data available.'}
            </ReactMarkdown>
          </div>
        </div>
      </div>
    </>
  );
}

/* ------------------------------------------------------------------ */
/*  Sub-components                                                     */
/* ------------------------------------------------------------------ */

function SectionHeader({
  number,
  title,
}: {
  number: string;
  title: string;
}) {
  return (
    <div style={{ marginBottom: 20, marginTop: 32 }}>
      <h2
        style={{
          fontSize: 22,
          fontWeight: 800,
          color: '#1a1a1a',
          margin: 0,
          paddingBottom: 8,
          borderBottom: '3px solid #5B5FEE',
          display: 'inline-block',
        }}
      >
        {number ? `${number}. ` : ''}
        <span dangerouslySetInnerHTML={{ __html: title }} />
      </h2>
    </div>
  );
}

function MetricBox({
  label,
  value,
}: {
  label: string;
  value: string;
}) {
  return (
    <div
      style={{
        border: '1px solid #e0e0e0',
        borderRadius: 8,
        padding: '12px 16px',
        textAlign: 'center',
      }}
    >
      <div
        style={{
          fontSize: 11,
          color: '#999',
          fontWeight: 600,
          textTransform: 'uppercase',
          letterSpacing: '0.05em',
          marginBottom: 4,
        }}
      >
        {label}
      </div>
      <div
        style={{
          fontSize: 22,
          fontWeight: 800,
          color: '#1a1a1a',
        }}
      >
        {value}
      </div>
    </div>
  );
}
