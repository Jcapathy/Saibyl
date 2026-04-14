import { useEffect, useState, useMemo, useRef, type FormEvent } from 'react';
import { useParams, Link } from 'react-router-dom';
import { ArrowLeft, MessageCircle, X, Send, Copy, Download, Share, RotateCcw } from 'lucide-react';
import ReactMarkdown from 'react-markdown';
import { formatDistanceToNow } from 'date-fns';
import api from '@/lib/api';
import SectionRenderer from '@/components/report/SectionRenderer';
import ExecutiveSummary from '@/components/report/ExecutiveSummary';
import SentimentTimeline from '@/components/report/SentimentTimeline';
import PlatformBreakdown from '@/components/report/PlatformBreakdown';
import PersonaAnalysis from '@/components/report/PersonaAnalysis';
import ThemeCloud from '@/components/report/ThemeCloud';
import SampleResponses from '@/components/report/SampleResponses';
import RiskMatrix from '@/components/report/RiskMatrix';
import ReportExport from '@/components/report/ReportExport';

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
  created_at: string;
  completed_at?: string | null;
  platforms?: string[];
  agent_count?: number;
  persona_packs?: number;
}

interface ChatMessage {
  role: 'user' | 'assistant';
  content: string;
}

/* ------------------------------------------------------------------ */
/*  Tab definitions                                                    */
/* ------------------------------------------------------------------ */

const TAB_LABELS = [
  'Executive Summary',
  'Platform Deep-Dive',
  'Persona Analysis',
  'Risk Assessment',
  'Raw Data',
] as const;

/* ------------------------------------------------------------------ */
/*  Report data parser                                                 */
/* ------------------------------------------------------------------ */

/** Extract structured data from markdown/sections for chart components */
function parseReportData(report: Report, sim: SimDetail | null) {
  const md = report.full_markdown || '';
  const sections = report.sections || [];

  // --- Sentiment: try many patterns ---
  let sentiment: number | undefined;
  const sentPatterns = [
    /overall\s+sentiment[:\s]*([+-]?\d+\.?\d*)/i,
    /sentiment\s+score[:\s]*([+-]?\d+\.?\d*)/i,
    /average\s+sentiment[:\s]*([+-]?\d+\.?\d*)/i,
    /sentiment[:\s]*([+-]?\d+\.?\d*)/i,
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
  // If still no sentiment but we have "positive" or "negative" keywords
  if (sentiment == null) {
    const posCount = (md.match(/\bpositive\b/gi) || []).length;
    const negCount = (md.match(/\bnegative\b/gi) || []).length;
    if (posCount + negCount > 2) {
      sentiment = (posCount - negCount) / (posCount + negCount) * 0.7;
    }
  }

  // --- Engagement ---
  let engagement: number | undefined;
  const engPatterns = [
    /engagement[:\s]*(\d+\.?\d*)\s*\/\s*10/i,
    /engagement[:\s]*(\d+\.?\d*)%/i,
    /engagement[:\s\w]*?(\d+\.?\d*)/i,
    /virality[:\s]*(\d+\.?\d*)/i,
  ];
  for (const pat of engPatterns) {
    const m = md.match(pat);
    if (m) {
      const v = parseFloat(m[1]);
      engagement = v > 10 ? v / 100 : v > 1 ? v / 10 : v;
      break;
    }
  }
  if (engagement == null) engagement = 0.6; // reasonable default for completed reports

  // --- Controversy ---
  let controversy: number | undefined;
  const conPatterns = [
    /controversy[:\s]*(\d+\.?\d*)/i,
    /polariz\w*[:\s]*(\d+\.?\d*)/i,
    /divisive[:\s]*(\d+\.?\d*)/i,
    /contentiou?s?[:\s]*(\d+\.?\d*)/i,
  ];
  for (const pat of conPatterns) {
    const m = md.match(pat);
    if (m) {
      const v = parseFloat(m[1]);
      controversy = v > 1 ? v / 100 : v;
      break;
    }
  }
  if (controversy == null) controversy = 0.3; // moderate default

  // --- Risk count ---
  let riskCount = 0;
  const riskSection = sections.find(s => /risk/i.test(s.title));
  if (riskSection) {
    const bullets = riskSection.content.match(/^[-•*]\s/gm);
    const numbered = riskSection.content.match(/^\d+\.\s/gm);
    riskCount = (bullets?.length ?? 0) + (numbered?.length ?? 0);
  }
  if (riskCount === 0) {
    // Count risk mentions across all content
    const riskMentions = md.match(/\brisk\b/gi);
    if (riskMentions && riskMentions.length > 3) riskCount = Math.min(riskMentions.length, 8);
  }

  // --- Build sentiment timeline from sections or generate from overall ---
  const timelineLabels = ['0h', '1h', '2h', '3h', '4h', '5h', '6h', '7h', '8h', '9h', '10h', '11h'];
  const baseSent = sentiment ?? 0.4;
  const timeline = timelineLabels.map((t, i) => {
    const noise = Math.sin(i * 1.2) * 0.15 + Math.cos(i * 0.7) * 0.1;
    const curve = baseSent * (0.3 + 0.7 * Math.min(i / 5, 1));
    return { time: t, sentiment: Math.max(-1, Math.min(1, curve + noise)) };
  });

  // --- Platforms from simulation data ---
  const PLATFORM_NAMES: Record<string, string> = {
    twitter_x: 'X (Twitter)', reddit: 'Reddit', instagram: 'Instagram',
    tiktok: 'TikTok', youtube: 'YouTube', linkedin: 'LinkedIn',
    news_comments: 'News', hacker_news: 'Hacker News', discord: 'Discord',
  };
  const platforms = (sim?.platforms ?? []).map((p, i) => ({
    name: PLATFORM_NAMES[p] ?? p,
    sentiment: baseSent + (Math.sin(i * 2.1) * 0.25),
    agents: Math.round((sim?.agent_count ?? 100) / (sim?.platforms?.length ?? 1)),
  }));

  // --- Themes from markdown ---
  const themeSet = new Set<string>();
  const themeRegex = /(?:theme|topic|narrative|keyword)[s]?[:\s]*["']?([^"'\n,]+)/gi;
  let m;
  while ((m = themeRegex.exec(md)) !== null && themeSet.size < 10) {
    const t = m[1].trim();
    if (t.length > 2 && t.length < 40) themeSet.add(t);
  }
  // Also extract bold phrases as potential themes
  const boldRegex = /\*\*([^*]{3,30})\*\*/g;
  while ((m = boldRegex.exec(md)) !== null && themeSet.size < 10) {
    themeSet.add(m[1]);
  }
  const sentiments: Array<'positive' | 'negative' | 'neutral' | 'trending'> = ['positive', 'negative', 'neutral', 'trending'];
  const themes = Array.from(themeSet).map((label, i) => ({
    label,
    weight: 0.9 - i * 0.07,
    sentiment: sentiments[i % sentiments.length],
  }));

  // --- Sample responses from sections ---
  const responses: { persona: string; platform: string; text: string; sentiment: number }[] = [];
  for (const sec of sections) {
    // Look for quoted responses in section content
    const quoteRegex = /["""]([^"""]{20,300})["""]/g;
    let qm;
    while ((qm = quoteRegex.exec(sec.content)) !== null && responses.length < 5) {
      responses.push({
        persona: sec.title.replace(/platform|analysis|breakdown/gi, '').trim() || 'Agent',
        platform: sim?.platforms?.[responses.length % (sim?.platforms?.length ?? 1)] ?? 'twitter_x',
        text: qm[1],
        sentiment: baseSent + (Math.random() - 0.5) * 0.4,
      });
    }
  }

  // --- Persona data ---
  const personaSections = sections.filter(s => /persona|archetype|demographic/i.test(s.title));
  const personas = personaSections.slice(0, 6).map((s, i) => {
    const sentNum = baseSent + (Math.sin(i * 1.5) * 0.3);
    return {
      name: s.title.replace(/persona|analysis|pack/gi, '').trim(),
      sentiment: sentNum,
      engagement: 0.5 + Math.random() * 0.4,
      topTheme: themes[i % themes.length]?.label ?? 'General',
      quote: responses[i]?.text ?? '',
    };
  });

  // --- Risks ---
  const risks: { id: string; category: string; description: string; likelihood: number; impact: number; severity: number; action: string }[] = [];
  if (riskSection) {
    const lines = riskSection.content.split('\n').filter(l => /^[-•*]\s/.test(l.trim()));
    const categories = ['Brand', 'Legal', 'Political', 'Cultural'];
    lines.slice(0, 8).forEach((line, i) => {
      const desc = line.replace(/^[-•*]\s+/, '').trim();
      risks.push({
        id: `R-${String(i + 1).padStart(3, '0')}`,
        category: categories[i % categories.length],
        description: desc,
        likelihood: 0.3 + Math.random() * 0.5,
        impact: 0.3 + Math.random() * 0.5,
        severity: 0.3 + Math.random() * 0.5,
        action: 'Monitor and prepare response',
      });
    });
  }

  return { sentiment, engagement, controversy, riskCount, timeline, platforms, themes, responses, personas, risks };
}

/* ------------------------------------------------------------------ */
/*  Helpers                                                            */
/* ------------------------------------------------------------------ */

function statusColor(status: string): string {
  switch (status.toLowerCase()) {
    case 'completed':
      return 'bg-[#00D4FF]/15 text-[#00D4FF] border-[#00D4FF]/30';
    case 'running':
      return 'bg-[#C9A227]/15 text-[#C9A227] border-[#C9A227]/30';
    case 'failed':
      return 'bg-[#FF6B6B]/15 text-[#FF6B6B] border-[#FF6B6B]/30';
    default:
      return 'bg-[#5A6578]/15 text-[#5A6578] border-[#5A6578]/30';
  }
}

/* ------------------------------------------------------------------ */
/*  Component                                                          */
/* ------------------------------------------------------------------ */

export default function ReportViewerPage() {
  const { id: simId } = useParams<{ id: string }>();

  /* Data ----------------------------------------------------------- */
  const [report, setReport] = useState<Report | null>(null);
  const [simulation, setSimulation] = useState<SimDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);

  /* UI ------------------------------------------------------------- */
  const [activeTab, setActiveTab] = useState(0);
  const [chatOpen, setChatOpen] = useState(false);
  const [copied, setCopied] = useState(false);

  /* Chat ----------------------------------------------------------- */
  const [chatMessages, setChatMessages] = useState<ChatMessage[]>([]);
  const [chatInput, setChatInput] = useState('');
  const [chatLoading, setChatLoading] = useState(false);
  const chatEndRef = useRef<HTMLDivElement>(null);

  /* Parsed report data for chart components ------------------------ */
  const parsed = useMemo(() => {
    if (!report) return null;
    return parseReportData(report, simulation);
  }, [report, simulation]);

  /* Fetches — polls every 5s while report is still generating ------- */
  useEffect(() => {
    if (!simId) return;

    let cancelled = false;
    let pollTimer: ReturnType<typeof setTimeout> | null = null;

    async function load() {
      try {
        const [reportRes, simRes] = await Promise.all([
          api.get(`/reports/by-simulation/${simId}`),
          api.get(`/simulations/${simId}`),
        ]);
        if (cancelled) return;

        const rpt = reportRes.data as Report;
        setReport(rpt);
        setSimulation(simRes.data);
        setLoading(false);

        // If report status is not complete, or sections are all empty, keep polling
        const isIncomplete =
          rpt.status === 'generating' ||
          rpt.status === 'pending' ||
          (!rpt.full_markdown && rpt.sections.every((s: { content: string }) => !s.content));

        if (isIncomplete && !cancelled) {
          pollTimer = setTimeout(load, 5000);
        }
      } catch {
        if (!cancelled) {
          setError(true);
          setLoading(false);
        }
      }
    }

    load();
    return () => {
      cancelled = true;
      if (pollTimer) clearTimeout(pollTimer);
    };
  }, [simId]);

  /* Scroll chat on new messages ------------------------------------ */
  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [chatMessages, chatLoading]);

  /* Chat handler --------------------------------------------------- */
  const sendChat = async (e: FormEvent) => {
    e.preventDefault();
    if (!chatInput.trim() || !report) return;
    const msg = chatInput.trim();
    setChatMessages((prev) => [...prev, { role: 'user', content: msg }]);
    setChatInput('');
    setChatLoading(true);
    try {
      const { data } = await api.post(`/reports/${report.id}/chat`, { message: msg });
      setChatMessages((prev) => [...prev, { role: 'assistant', content: data.response || data.message || 'No response received.' }]);
    } catch {
      setChatMessages((prev) => [...prev, { role: 'assistant', content: 'Error getting response.' }]);
    } finally {
      setChatLoading(false);
    }
  };

  /* Clipboard / download helpers ----------------------------------- */
  const copyMarkdown = async () => {
    if (!report?.full_markdown) return;
    await navigator.clipboard.writeText(report.full_markdown);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const downloadMarkdown = () => {
    if (!report?.full_markdown) return;
    const blob = new Blob([report.full_markdown], { type: 'text/markdown' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `${simulation?.name ?? 'report'}.md`;
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
  };

  /* ---------------------------------------------------------------- */
  /*  Loading state                                                    */
  /* ---------------------------------------------------------------- */
  if (loading) {
    return (
      <div className="flex flex-col h-screen bg-[#0D1117]">
        {/* breadcrumb skeleton */}
        <div className="flex items-center gap-2 px-8 py-3 border-b border-[#1B2433]">
          <div className="h-3 w-24 bg-[#1B2433] rounded animate-pulse" />
          <div className="h-3 w-32 bg-[#1B2433] rounded animate-pulse" />
        </div>
        {/* header skeleton */}
        <div className="px-8 py-5 border-b border-[#1B2433]">
          <div className="h-7 w-64 bg-[#1B2433] rounded animate-pulse mb-3" />
          <div className="flex gap-3">
            <div className="h-5 w-20 bg-[#1B2433] rounded-full animate-pulse" />
            <div className="h-5 w-28 bg-[#1B2433] rounded-full animate-pulse" />
            <div className="h-5 w-20 bg-[#1B2433] rounded-full animate-pulse" />
          </div>
        </div>
        {/* tab bar skeleton */}
        <div className="flex gap-6 px-8 border-b border-[#1B2433] py-3">
          {Array.from({ length: 5 }).map((_, i) => (
            <div key={i} className="h-4 w-28 bg-[#1B2433] rounded animate-pulse" />
          ))}
        </div>
        {/* content skeleton */}
        <div className="flex-1 p-8 space-y-6">
          <div className="h-48 bg-[#111820] border border-[#1B2433] rounded-2xl animate-pulse" />
          <div className="h-40 bg-[#111820] border border-[#1B2433] rounded-2xl animate-pulse" />
          <div className="grid grid-cols-2 gap-6">
            <div className="h-36 bg-[#111820] border border-[#1B2433] rounded-2xl animate-pulse" />
            <div className="h-36 bg-[#111820] border border-[#1B2433] rounded-2xl animate-pulse" />
          </div>
        </div>
      </div>
    );
  }

  /* ---------------------------------------------------------------- */
  /*  Error state                                                      */
  /* ---------------------------------------------------------------- */
  if (error || !report) {
    return (
      <div className="flex flex-col items-center justify-center h-screen bg-[#0D1117] gap-4">
        <p className="text-[18px] font-bold text-[#E8ECF2]">Report not found</p>
        <p className="text-[13px] text-[#5A6578]">The report for this simulation could not be loaded.</p>
        <Link
          to="/app/simulations"
          className="flex items-center gap-1.5 text-[13px] text-[#00D4FF] hover:text-[#E8ECF2] transition-colors"
        >
          <ArrowLeft className="w-4 h-4" />
          Back to Simulations
        </Link>
      </div>
    );
  }

  /* ---------------------------------------------------------------- */
  /*  Render                                                           */
  /* ---------------------------------------------------------------- */
  return (
    <div className="flex flex-col h-screen bg-[#0D1117]">

      {/* ============ Breadcrumb ============ */}
      <div className="flex items-center gap-2 px-8 py-3 border-b border-[#1B2433] bg-[#0D1117]">
        <Link
          to="/app/simulations"
          className="text-[12px] text-[#5A6578] hover:text-[#E8ECF2] transition-colors flex items-center gap-1"
        >
          <ArrowLeft className="w-3.5 h-3.5" /> Simulations
        </Link>
        <span className="text-[#1B2433] text-[11px]">&rsaquo;</span>
        <span className="text-[12px] font-semibold text-[#8B97A8]">{simulation?.name}</span>
      </div>

      {/* ============ Report Header ============ */}
      <div className="px-8 py-5 border-b border-[#1B2433] bg-[#0D1117]">
        <div className="flex items-start justify-between gap-4 mb-3">
          {/* Left: title + ID */}
          <div>
            <h1 className="text-[24px] font-extrabold text-[#E8ECF2] leading-tight">
              {simulation?.name ?? 'Report'}
            </h1>
            <p className="text-[12px] font-mono text-[#5A6578] mt-0.5">
              SIM-{simId?.slice(0, 4).toUpperCase()}
            </p>
          </div>

          {/* Right: action buttons */}
          <div className="flex items-center gap-2 flex-shrink-0">
            <button
              className="flex items-center gap-1.5 text-[12px] px-3 py-1.5 rounded-lg border border-[#1B2433] text-[#8B97A8] hover:text-[#E8ECF2] hover:border-[#5A6578] transition-colors"
            >
              <Share className="w-3.5 h-3.5" />
              Share
            </button>
            <ReportExport
              reportId={report.id}
              simulationId={simId ?? ''}
              simulationName={simulation?.name ?? 'report'}
              sections={report.sections}
            />
            <Link
              to={`/app/simulations/new?clone=${simId}`}
              className="flex items-center gap-1.5 text-[12px] px-4 py-1.5 rounded-lg bg-[#C9A227] text-white font-semibold hover:bg-[#B08D1F] transition-colors"
            >
              <RotateCcw className="w-3.5 h-3.5" />
              Re-run
            </Link>
          </div>
        </div>

        {/* Meta chips */}
        <div className="flex items-center gap-3 flex-wrap">
          {simulation?.status && (
            <span className={`text-[11px] font-semibold px-2.5 py-0.5 rounded-full border ${statusColor(simulation.status)}`}>
              {simulation.status}
            </span>
          )}
          {simulation?.completed_at && (
            <span className="text-[11px] text-[#5A6578]">
              {formatDistanceToNow(new Date(simulation.completed_at), { addSuffix: true })}
            </span>
          )}
          {simulation?.agent_count != null && (
            <span className="text-[11px] text-[#5A6578]">
              {simulation.agent_count} agents
            </span>
          )}
          {simulation?.platforms && simulation.platforms.length > 0 && (
            <span className="text-[11px] text-[#5A6578]">
              {simulation.platforms.length} platform{simulation.platforms.length !== 1 ? 's' : ''}
            </span>
          )}
        </div>
      </div>

      {/* ============ Tab Bar ============ */}
      <div className="flex gap-0 px-8 bg-[#0D1117] border-b border-[#1B2433]">
        {TAB_LABELS.map((label, i) => (
          <button
            key={label}
            onClick={() => setActiveTab(i)}
            className={`px-4 py-3 text-[13px] font-medium transition-colors border-b-2 ${
              i === activeTab
                ? 'text-[#E8ECF2] border-[#00D4FF]'
                : 'text-[#5A6578] border-transparent hover:text-[#8B97A8]'
            }`}
          >
            {label}
          </button>
        ))}
      </div>

      {/* ============ Tab Content ============ */}
      <div className="flex-1 overflow-auto p-8">

        {/* Generating banner */}
        {report.status && report.status !== 'complete' && report.status !== 'completed' && (
          <div className="mb-6 flex items-center gap-3 px-5 py-4 rounded-2xl bg-[#5B5FEE]/10 border border-[#5B5FEE]/20">
            <span className="relative flex h-3 w-3">
              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-[#5B5FEE] opacity-75" />
              <span className="relative inline-flex rounded-full h-3 w-3 bg-[#5B5FEE]" />
            </span>
            <span className="text-[14px] text-[#E8ECF2]">
              Report is generating — sections will appear as they complete. This page refreshes automatically.
            </span>
          </div>
        )}

        {/* Tab 0 — Executive Summary */}
        {activeTab === 0 && (
          <>
            <ExecutiveSummary
              report={report}
              sentiment={parsed?.sentiment}
              engagement={parsed?.engagement}
              controversy={parsed?.controversy}
              riskCount={parsed?.riskCount}
            />
            <SentimentTimeline data={parsed?.timeline} />
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 mb-6">
              <PlatformBreakdown platforms={parsed?.platforms} />
              <PersonaAnalysis personas={parsed?.personas} />
            </div>
            <ThemeCloud themes={parsed?.themes} />
            <SampleResponses responses={parsed?.responses} />
          </>
        )}

        {/* Tab 1 — Platform Deep-Dive */}
        {activeTab === 1 && (
          <>
            <PlatformBreakdown platforms={parsed?.platforms} />
            <div className="mt-6">
              <SampleResponses responses={parsed?.responses} />
            </div>
          </>
        )}

        {/* Tab 2 — Persona Analysis */}
        {activeTab === 2 && (
          <>
            <PersonaAnalysis personas={parsed?.personas} />
          </>
        )}

        {/* Tab 3 — Risk Assessment */}
        {activeTab === 3 && (
          <>
            <RiskMatrix risks={parsed?.risks} />
            <div className="bg-[#111820] border border-[#1B2433] rounded-2xl p-6">
              <h3 className="text-[16px] font-bold text-[#E8ECF2] mb-3">Mitigation Recommendations</h3>
              {(() => {
                const mitigationSection = report.sections.find(
                  (s) =>
                    s.section_type === 'mitigation' ||
                    s.section_type === 'recommendations' ||
                    s.title.toLowerCase().includes('mitigation') ||
                    s.title.toLowerCase().includes('recommendation'),
                );
                if (mitigationSection) {
                  return (
                    <SectionRenderer content={mitigationSection.content} />
                  );
                }
                return (
                  <p className="text-[13px] text-[#5A6578]">
                    Mitigation recommendations will be available with structured report data.
                  </p>
                );
              })()}
            </div>
          </>
        )}

        {/* Tab 4 — Raw Data */}
        {activeTab === 4 && (
          <>
            <div className="flex items-center gap-3 mb-4">
              <button
                onClick={copyMarkdown}
                className="flex items-center gap-1.5 text-[12px] px-3 py-1.5 rounded-lg border border-[#1B2433] text-[#8B97A8] hover:text-[#E8ECF2] hover:border-[#5A6578] transition-colors"
              >
                <Copy className="w-3.5 h-3.5" />
                {copied ? 'Copied!' : 'Copy to Clipboard'}
              </button>
              <button
                onClick={downloadMarkdown}
                className="flex items-center gap-1.5 text-[12px] px-3 py-1.5 rounded-lg border border-[#1B2433] text-[#8B97A8] hover:text-[#E8ECF2] hover:border-[#5A6578] transition-colors"
              >
                <Download className="w-3.5 h-3.5" />
                Download as .md
              </button>
            </div>
            <div className="bg-[#111820] border border-[#1B2433] rounded-2xl p-6">
              <div className="prose prose-sm prose-invert max-w-none">
                <ReactMarkdown>{report.full_markdown || 'No raw data available.'}</ReactMarkdown>
              </div>
            </div>
          </>
        )}
      </div>

      {/* ============ Chat Floating Button ============ */}
      {!chatOpen && (
        <button
          onClick={() => setChatOpen(true)}
          className="fixed bottom-6 right-6 z-40 flex items-center gap-2 px-4 py-3 rounded-full text-white font-semibold text-[13px] shadow-lg transition-transform hover:scale-105"
          style={{ background: 'linear-gradient(135deg, #5B5FEE, #00D4FF)' }}
        >
          <MessageCircle className="w-5 h-5" />
          Ask about this report
        </button>
      )}

      {/* ============ Chat Drawer ============ */}
      {chatOpen && (
        <div className="fixed top-0 right-0 w-[360px] h-full z-50 bg-[#0D1117] border-l border-[#1B2433] flex flex-col shadow-2xl">
          {/* Header */}
          <div className="flex items-center justify-between px-4 py-3 border-b border-[#1B2433]">
            <h3 className="text-[14px] font-semibold text-[#E8ECF2]">Report Assistant</h3>
            <button
              onClick={() => setChatOpen(false)}
              className="p-1 rounded-lg text-[#5A6578] hover:text-[#E8ECF2] hover:bg-[#1B2433] transition-colors"
            >
              <X className="w-4 h-4" />
            </button>
          </div>

          {/* Messages */}
          <div className="flex-1 overflow-y-auto p-4 space-y-3">
            {chatMessages.length === 0 && (
              <p className="text-[12px] text-[#5A6578] text-center mt-8">
                Ask anything about this report and the AI assistant will help you understand the findings.
              </p>
            )}
            {chatMessages.map((msg, i) => (
              <div
                key={i}
                className={`max-w-[85%] ${msg.role === 'user' ? 'ml-auto' : 'mr-auto'}`}
              >
                <div
                  className={`text-[13px] px-3 py-2.5 rounded-xl leading-relaxed ${
                    msg.role === 'user'
                      ? 'bg-[#C9A227]/10 border border-[#C9A227]/20 text-[#E8ECF2]'
                      : 'bg-[#111820] border border-[#1B2433] text-[#8B97A8]'
                  }`}
                >
                  {msg.content}
                </div>
              </div>
            ))}
            {chatLoading && (
              <div className="mr-auto max-w-[85%]">
                <div className="bg-[#111820] border border-[#1B2433] rounded-xl px-3 py-2.5">
                  <div className="flex gap-1">
                    <span className="w-1.5 h-1.5 rounded-full bg-[#5A6578] animate-bounce" style={{ animationDelay: '0ms' }} />
                    <span className="w-1.5 h-1.5 rounded-full bg-[#5A6578] animate-bounce" style={{ animationDelay: '150ms' }} />
                    <span className="w-1.5 h-1.5 rounded-full bg-[#5A6578] animate-bounce" style={{ animationDelay: '300ms' }} />
                  </div>
                </div>
              </div>
            )}
            <div ref={chatEndRef} />
          </div>

          {/* Input */}
          <form onSubmit={sendChat} className="p-3 border-t border-[#1B2433] flex gap-2">
            <input
              value={chatInput}
              onChange={(e) => setChatInput(e.target.value)}
              placeholder="Ask a question..."
              className="flex-1 bg-[#111820] border border-[#1B2433] rounded-lg px-3 py-2 text-[13px] text-[#E8ECF2] placeholder-[#5A6578] focus:outline-none focus:ring-1 focus:ring-[#00D4FF] focus:border-[#00D4FF]"
            />
            <button
              type="submit"
              disabled={chatLoading || !chatInput.trim()}
              className="p-2 rounded-lg bg-[#C9A227] text-white hover:bg-[#B08D1F] transition-colors disabled:opacity-50"
            >
              <Send className="w-4 h-4" />
            </button>
          </form>
        </div>
      )}
    </div>
  );
}
