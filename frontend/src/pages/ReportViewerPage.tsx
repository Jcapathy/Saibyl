import { useEffect, useMemo, useRef, useState, type FormEvent } from 'react';
import { Link, useParams } from 'react-router-dom';
import { ArrowLeft, Copy, Download, MessageCircle, RotateCcw, Send, X } from 'lucide-react';
import ReactMarkdown from 'react-markdown';
import { formatDistanceToNow } from 'date-fns';
import api from '@/lib/api';
import { getErrorMessage } from '@/lib/errors';
import { cleanContent, stripDuplicateTitle } from '@/lib/utils';
import {
  isSupportedSchema,
  type AnalysisResponse,
  type SimulationAnalysis,
} from '@/lib/analysis';
import SectionRenderer from '@/components/report/SectionRenderer';
import ReportExport from '@/components/report/ReportExport';
import HeadlineStats from '@/components/analysis/HeadlineStats';
import QualityNotice from '@/components/analysis/QualityNotice';
import AdversarialNotice from '@/components/analysis/AdversarialNotice';
import SentimentArc from '@/components/analysis/SentimentArc';
import GroupBreakdown from '@/components/analysis/GroupBreakdown';
import ObjectionMap from '@/components/analysis/ObjectionMap';
import FlashpointList from '@/components/analysis/FlashpointList';
import VariantScoreboardPanel from '@/components/analysis/VariantScoreboard';
import EvidenceDrawer from '@/components/analysis/EvidenceDrawer';
import Panel, { NoData } from '@/components/analysis/Panel';
import InoculationWorkbench from '@/components/founder/InoculationWorkbench';

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
  /** Set when this run is an inoculation re-simulation of another. */
  parent_simulation_id?: string | null;
}

interface ChatMessage {
  role: 'user' | 'assistant';
  content: string;
}

const TAB_LABELS = [
  'Findings',
  'Objections',
  'Audience',
  // Sits next to Objections because that is where the founder already is when
  // they decide to do something about one. Appended rather than inserted:
  // `activeTab` is an index, and renumbering the existing tabs would silently
  // change what any bookmarked or linked position points at.
  'Narrative',
  'Raw data',
  'Inoculate',
] as const;

const INOCULATE_TAB = 5;

/* ------------------------------------------------------------------ */
/*  Helpers                                                            */
/* ------------------------------------------------------------------ */

function statusColor(status: string): string {
  switch (status.toLowerCase()) {
    case 'complete':
    case 'completed':
      return 'bg-saibyl-signal-blue/15 text-saibyl-signal-blue border-saibyl-signal-blue/30';
    case 'running':
    case 'analyzing':
      return 'bg-saibyl-gold/15 text-saibyl-gold border-saibyl-gold/30';
    case 'failed':
      return 'bg-saibyl-negative/15 text-saibyl-negative border-saibyl-negative/30';
    default:
      return 'bg-saibyl-muted/15 text-saibyl-muted border-saibyl-muted/30';
  }
}

/* ------------------------------------------------------------------ */
/*  Component                                                          */
/* ------------------------------------------------------------------ */

/**
 * The report viewer, rebuilt on the `simulation_analysis` artifact.
 *
 * Everything numeric on this page comes from `analysis`. The previous version
 * regex-scraped one sentiment scalar out of the report markdown and then
 * generated the timeline, the per-platform sentiment, the persona metrics and
 * the risk matrix from it with `Math.sin()` and `Math.random()` — risk
 * likelihood was `0.3 + Math.random() * 0.5`. All of that parsing is gone, and
 * with it the possibility of its return: there is no code path here that
 * derives a metric from prose.
 *
 * Prose and measurement are also now visibly separate. The narrative sits in
 * its own tab, and the charts never depend on it having been written.
 */
export default function ReportViewerPage() {
  const { id: simId } = useParams<{ id: string }>();

  const [report, setReport] = useState<Report | null>(null);
  const [simulation, setSimulation] = useState<SimDetail | null>(null);
  const [analysis, setAnalysis] = useState<SimulationAnalysis | null>(null);
  const [analysisError, setAnalysisError] = useState('');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);

  const [activeTab, setActiveTab] = useState(0);
  const [copied, setCopied] = useState(false);
  const [evidence, setEvidence] = useState<{ ids: string[]; label: string } | null>(null);

  const [chatOpen, setChatOpen] = useState(false);
  const [chatMessages, setChatMessages] = useState<ChatMessage[]>([]);
  const [chatInput, setChatInput] = useState('');
  const [chatLoading, setChatLoading] = useState(false);
  const chatEndRef = useRef<HTMLDivElement>(null);

  /* Objection key -> label, so a chip can name what it points at. */
  const objectionLabels = useMemo(() => {
    const map: Record<string, string> = {};
    analysis?.objections.forEach((o) => {
      map[o.key] = o.label;
    });
    return map;
  }, [analysis]);

  /* Fetch. Polls while the report is still being written. The analysis is
     fetched alongside but independently: it exists before the prose does, so
     the charts render as soon as the run has been measured. */
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

        const incomplete =
          rpt.status === 'generating' ||
          rpt.status === 'pending' ||
          (!rpt.full_markdown && rpt.sections.every((s) => !s.content));
        if (incomplete && !cancelled) {
          pollTimer = setTimeout(load, 5000);
        }
      } catch {
        if (!cancelled) {
          setError(true);
          setLoading(false);
        }
      }
    }

    async function loadAnalysis() {
      try {
        const res = await api.get(`/simulations/${simId}/analysis`);
        if (cancelled) return;
        const payload = res.data as AnalysisResponse;
        if (!isSupportedSchema(payload.schema_version)) {
          // Refuse rather than render a version this client does not know. A
          // partially-understood artifact would silently drop fields, which is
          // how a chart ends up quietly missing a series.
          setAnalysisError(
            `This analysis uses schema version ${payload.schema_version}; this app renders version 1. Reload to pick up the current build.`,
          );
          return;
        }
        setAnalysis(payload.artifact);
      } catch (err) {
        if (!cancelled) {
          setAnalysisError(
            getErrorMessage(
              err,
              'This run has not been analysed, so it has no measured figures.',
            ),
          );
        }
      }
    }

    load();
    loadAnalysis();
    return () => {
      cancelled = true;
      if (pollTimer) clearTimeout(pollTimer);
    };
  }, [simId]);

  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [chatMessages, chatLoading]);

  const sendChat = async (e: FormEvent) => {
    e.preventDefault();
    if (!chatInput.trim() || !report) return;
    const msg = chatInput.trim();
    setChatMessages((prev) => [...prev, { role: 'user', content: msg }]);
    setChatInput('');
    setChatLoading(true);
    try {
      const { data } = await api.post(`/reports/${report.id}/chat`, { message: msg });
      setChatMessages((prev) => [
        ...prev,
        {
          role: 'assistant',
          content: data.answer || data.response || data.message || 'No response received.',
        },
      ]);
    } catch (err) {
      setChatMessages((prev) => [
        ...prev,
        { role: 'assistant', content: getErrorMessage(err, 'Error getting response.') },
      ]);
    } finally {
      setChatLoading(false);
    }
  };

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

  const drillDown = (ids: string[], label: string) => setEvidence({ ids, label });

  /* ---------------------------------------------------------------- */

  if (loading) {
    return (
      <div className="flex flex-col h-screen bg-saibyl-void">
        <div className="flex items-center gap-2 px-8 py-3 border-b border-saibyl-border">
          <div className="h-3 w-24 bg-saibyl-border rounded animate-pulse" />
          <div className="h-3 w-32 bg-saibyl-border rounded animate-pulse" />
        </div>
        <div className="px-8 py-5 border-b border-saibyl-border">
          <div className="h-7 w-64 bg-saibyl-border rounded animate-pulse mb-3" />
          <div className="flex gap-3">
            <div className="h-5 w-20 bg-saibyl-border rounded-full animate-pulse" />
            <div className="h-5 w-28 bg-saibyl-border rounded-full animate-pulse" />
          </div>
        </div>
        <div className="flex-1 p-8 space-y-6">
          <div className="grid grid-cols-1 sm:grid-cols-4 gap-4">
            {Array.from({ length: 4 }).map((_, i) => (
              <div
                key={i}
                className="h-28 bg-saibyl-surface border border-saibyl-border rounded-2xl animate-pulse"
              />
            ))}
          </div>
          <div className="h-64 bg-saibyl-surface border border-saibyl-border rounded-2xl animate-pulse" />
        </div>
      </div>
    );
  }

  if (error || !report) {
    return (
      <div className="flex flex-col items-center justify-center h-screen bg-saibyl-void gap-4">
        <p className="text-[18px] font-bold text-saibyl-platinum">Report not found</p>
        <p className="text-[13px] text-saibyl-muted">
          The report for this simulation could not be loaded.
        </p>
        <Link
          to="/app/simulations"
          className="flex items-center gap-1.5 text-[13px] text-saibyl-signal-blue hover:text-saibyl-platinum transition-colors"
        >
          <ArrowLeft className="w-4 h-4" />
          Back to Simulations
        </Link>
      </div>
    );
  }

  const measurementMissing = (
    <Panel title="No measured figures">
      <NoData>
        {analysisError ||
          'This run has not been analysed, so there are no measured figures to show.'}
        <br />
        <br />
        Nothing on this page is estimated from the report text. If the
        measurement pass has not run, the charts stay empty rather than being
        filled in.
      </NoData>
    </Panel>
  );

  return (
    <div className="flex flex-col h-screen bg-saibyl-void">
      {/* Breadcrumb */}
      <div className="flex items-center gap-2 px-8 py-3 border-b border-saibyl-border">
        <Link
          to="/app/simulations"
          className="text-[12px] text-saibyl-muted hover:text-saibyl-platinum transition-colors flex items-center gap-1"
        >
          <ArrowLeft className="w-3.5 h-3.5" /> Simulations
        </Link>
        <span className="text-saibyl-border text-[11px]">&rsaquo;</span>
        <span className="text-[12px] font-semibold text-saibyl-silver">{simulation?.name}</span>
      </div>

      {/* Header */}
      <div className="px-8 py-5 border-b border-saibyl-border">
        <div className="flex items-start justify-between gap-4 mb-3">
          <div>
            <h1 className="text-[24px] font-extrabold text-saibyl-platinum leading-tight">
              {simulation?.name ?? 'Report'}
            </h1>
            <p className="text-[12px] font-mono text-saibyl-muted mt-0.5">
              SIM-{simId?.slice(0, 4).toUpperCase()}
            </p>
          </div>
          <div className="flex items-center gap-2 flex-shrink-0">
            <ReportExport
              reportId={report.id}
              simulationId={simId ?? ''}
              simulationName={simulation?.name ?? 'report'}
              sections={report.sections}
            />
            <Link
              to={`/app/simulations/new?clone=${simId}`}
              className="flex items-center gap-1.5 text-[12px] px-4 py-1.5 rounded-lg bg-saibyl-gold text-saibyl-void font-semibold hover:bg-saibyl-gold-hover transition-colors"
            >
              <RotateCcw className="w-3.5 h-3.5" />
              Re-run
            </Link>
          </div>
        </div>

        <div className="flex items-center gap-3 flex-wrap">
          {simulation?.status && (
            <span
              className={`text-[11px] font-semibold px-2.5 py-0.5 rounded-full border ${statusColor(
                simulation.status,
              )}`}
            >
              {simulation.status}
            </span>
          )}
          {simulation?.completed_at && (
            <span className="text-[11px] text-saibyl-muted">
              {formatDistanceToNow(new Date(simulation.completed_at), { addSuffix: true })}
            </span>
          )}
          {analysis && (
            <>
              <span className="text-[11px] text-saibyl-muted">
                {analysis.quality.agents_active} of {analysis.quality.agents_total} agents
                active
              </span>
              <span className="text-[11px] text-saibyl-muted">
                {analysis.quality.events_measured.toLocaleString()} events measured
              </span>
            </>
          )}
        </div>
      </div>

      {/* Tabs */}
      <div className="flex gap-0 px-8 border-b border-saibyl-border overflow-x-auto">
        {TAB_LABELS.map((label, i) => (
          <button
            key={label}
            onClick={() => setActiveTab(i)}
            className={`px-4 py-3 text-[13px] font-medium transition-colors border-b-2 whitespace-nowrap ${
              i === activeTab
                ? 'text-saibyl-platinum border-saibyl-gold'
                : 'text-saibyl-muted border-transparent hover:text-saibyl-silver'
            }`}
          >
            {label}
          </button>
        ))}
      </div>

      {/* Content */}
      <div className="flex-1 overflow-auto p-8">
        {report.status && report.status !== 'complete' && report.status !== 'completed' && (
          <div className="mb-6 flex items-center gap-3 px-5 py-4 rounded-2xl bg-saibyl-insight-violet/10 border border-saibyl-insight-violet/20">
            <span className="relative flex h-3 w-3">
              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-saibyl-insight-violet opacity-75" />
              <span className="relative inline-flex rounded-full h-3 w-3 bg-saibyl-insight-violet" />
            </span>
            <span className="text-[14px] text-saibyl-platinum">
              The written report is still generating. The measured findings below are complete
              and do not depend on it.
            </span>
          </div>
        )}

        {/* Tab 0 — Findings */}
        {activeTab === 0 &&
          (analysis ? (
            <>
              {/* On a multi-variant run the scoreboard comes first and the
                  headline is demoted, because the headline aggregates every
                  arena into one number — the average of several competing
                  messages, describing none of them. Reversing this order would
                  put a meaningless figure at the top of a matched-swarm test. */}
              {analysis.scoreboard ? (
                <>
                  <VariantScoreboardPanel
                    scoreboard={analysis.scoreboard}
                    onDrillDown={drillDown}
                  />
                  <p className="text-[11px] text-saibyl-muted mb-3">
                    The figures below pool every variant. On a matched-swarm test
                    they describe the audience, not any one message.
                  </p>
                </>
              ) : null}
              <HeadlineStats headline={analysis.headline} quality={analysis.quality} />
              {/* Above the quality notice, not below it. The headline mixes
                  both cohorts, so a reader who has just looked at a negative
                  number needs to know a share of the swarm was constructed to
                  produce one before they scroll on. */}
              <AdversarialNotice adversarial={analysis.adversarial} />
              <QualityNotice quality={analysis.quality} />
              <div className="mb-6">
                <SentimentArc
                  timeline={analysis.sentiment_timeline}
                  flashpoints={analysis.flashpoints}
                  onDrillDown={drillDown}
                />
              </div>
              <FlashpointList
                flashpoints={analysis.flashpoints}
                objectionLabels={objectionLabels}
                onDrillDown={drillDown}
              />
            </>
          ) : (
            measurementMissing
          ))}

        {/* Tab 1 — Objections */}
        {activeTab === 1 &&
          (analysis ? (
            <ObjectionMap objections={analysis.objections} onDrillDown={drillDown} />
          ) : (
            measurementMissing
          ))}

        {/* Tab 2 — Audience */}
        {activeTab === 2 &&
          (analysis ? (
            <>
              <AdversarialNotice adversarial={analysis.adversarial} />
              {/* Full width and first. A −0.4 headline means something
                  different depending on which side of the room produced it,
                  and no archetype table makes that legible. */}
              {analysis.by_cohort.length > 0 && (
                <div className="mb-6">
                  <GroupBreakdown
                    title="Buyers vs. incumbent-aligned"
                    slices={analysis.by_cohort}
                    objectionLabels={objectionLabels}
                  />
                </div>
              )}
              <div className="grid grid-cols-1 xl:grid-cols-2 gap-6">
                <GroupBreakdown
                  title="By platform"
                  slices={analysis.by_platform}
                  objectionLabels={objectionLabels}
                />
                <GroupBreakdown
                  title="By archetype"
                  slices={analysis.by_archetype}
                  objectionLabels={objectionLabels}
                />
              </div>
            </>
          ) : (
            measurementMissing
          ))}

        {/* Tab 3 — Narrative */}
        {activeTab === 3 && (
          <div className="space-y-6">
            {report.sections.length === 0 && (
              <Panel title="Narrative">
                <NoData>The written report has not been generated yet.</NoData>
              </Panel>
            )}
            {report.sections.map((section) => (
              <div
                key={section.title}
                className="bg-saibyl-surface border border-saibyl-border rounded-2xl p-6"
              >
                <h2 className="text-[16px] font-bold text-saibyl-platinum mb-4">
                  {section.title}
                </h2>
                <SectionRenderer
                  content={stripDuplicateTitle(section.title, cleanContent(section.content))}
                  className="text-saibyl-silver leading-[1.75]"
                />
              </div>
            ))}
          </div>
        )}

        {/* Tab 4 — Raw data */}
        {activeTab === 4 && (
          <>
            <div className="flex items-center gap-3 mb-4">
              <button
                onClick={copyMarkdown}
                className="flex items-center gap-1.5 text-[12px] px-3 py-1.5 rounded-lg border border-saibyl-border text-saibyl-silver hover:text-saibyl-platinum hover:border-saibyl-border-light transition-colors"
              >
                <Copy className="w-3.5 h-3.5" />
                {copied ? 'Copied!' : 'Copy markdown'}
              </button>
              <button
                onClick={downloadMarkdown}
                className="flex items-center gap-1.5 text-[12px] px-3 py-1.5 rounded-lg border border-saibyl-border text-saibyl-silver hover:text-saibyl-platinum hover:border-saibyl-border-light transition-colors"
              >
                <Download className="w-3.5 h-3.5" />
                Download .md
              </button>
            </div>
            <div className="bg-saibyl-surface border border-saibyl-border rounded-2xl p-6 mb-6">
              <div className="prose prose-sm prose-invert max-w-none">
                <ReactMarkdown>
                  {report.full_markdown ||
                    report.sections
                      .map(
                        (s) => `## ${s.title}\n\n${stripDuplicateTitle(s.title, s.content)}`,
                      )
                      .join('\n\n---\n\n') ||
                    'No raw data available.'}
                </ReactMarkdown>
              </div>
            </div>
            {analysis && (
              <Panel
                title="Analysis artifact"
                note="The exact object every figure above was read from. Nothing is derived on the client."
              >
                <pre className="text-[10px] text-saibyl-muted overflow-auto max-h-96 leading-relaxed">
                  {JSON.stringify(analysis, null, 2)}
                </pre>
              </Panel>
            )}
          </>
        )}

        {/* Tab 5 — Inoculate */}
        {activeTab === INOCULATE_TAB &&
          (simId ? (
            <InoculationWorkbench
              simulationId={simId}
              parentSimulationId={simulation?.parent_simulation_id}
              objections={analysis?.objections ?? []}
            />
          ) : null)}
      </div>

      {evidence && simId && (
        <EvidenceDrawer
          simulationId={simId}
          eventIds={evidence.ids}
          label={evidence.label}
          onClose={() => setEvidence(null)}
        />
      )}

      {!chatOpen && (
        <button
          onClick={() => setChatOpen(true)}
          className="fixed bottom-6 right-6 z-40 flex items-center gap-2 px-4 py-3 rounded-full text-white font-semibold text-[13px] shadow-lg transition-transform hover:scale-105"
          style={{ background: 'linear-gradient(135deg, #8B5CF6, #2563EB)' }}
        >
          <MessageCircle className="w-5 h-5" />
          Ask about this report
        </button>
      )}

      {chatOpen && (
        <div className="fixed top-0 right-0 w-[360px] h-full z-50 bg-saibyl-void border-l border-saibyl-border flex flex-col shadow-2xl">
          <div className="flex items-center justify-between px-4 py-3 border-b border-saibyl-border">
            <h3 className="text-[14px] font-semibold text-saibyl-platinum">Report Assistant</h3>
            <button
              onClick={() => setChatOpen(false)}
              className="p-1 rounded-lg text-saibyl-muted hover:text-saibyl-platinum hover:bg-saibyl-surface transition-colors"
            >
              <X className="w-4 h-4" />
            </button>
          </div>

          <div className="flex-1 overflow-y-auto p-4 space-y-3">
            {chatMessages.length === 0 && (
              <p className="text-[12px] text-saibyl-muted text-center mt-8">
                Ask anything about this report.
              </p>
            )}
            {chatMessages.map((msg, i) => (
              <div key={i} className={`max-w-[85%] ${msg.role === 'user' ? 'ml-auto' : 'mr-auto'}`}>
                <div
                  className={`text-[13px] px-3 py-2.5 rounded-xl leading-relaxed ${
                    msg.role === 'user'
                      ? 'bg-saibyl-gold/10 border border-saibyl-gold/20 text-saibyl-platinum'
                      : 'bg-saibyl-surface border border-saibyl-border text-saibyl-silver'
                  }`}
                >
                  {msg.content}
                </div>
              </div>
            ))}
            {chatLoading && (
              <div className="mr-auto max-w-[85%]">
                <div className="bg-saibyl-surface border border-saibyl-border rounded-xl px-3 py-2.5">
                  <div className="flex gap-1">
                    {[0, 150, 300].map((delay) => (
                      <span
                        key={delay}
                        className="w-1.5 h-1.5 rounded-full bg-saibyl-muted animate-bounce"
                        style={{ animationDelay: `${delay}ms` }}
                      />
                    ))}
                  </div>
                </div>
              </div>
            )}
            <div ref={chatEndRef} />
          </div>

          <form onSubmit={sendChat} className="p-3 border-t border-saibyl-border flex gap-2">
            <input
              value={chatInput}
              onChange={(e) => setChatInput(e.target.value)}
              placeholder="Ask a question..."
              className="flex-1 bg-saibyl-surface border border-saibyl-border rounded-lg px-3 py-2 text-[13px] text-saibyl-platinum placeholder-saibyl-muted focus:outline-none focus:ring-1 focus:ring-saibyl-gold focus:border-saibyl-gold"
            />
            <button
              type="submit"
              disabled={chatLoading || !chatInput.trim()}
              className="p-2 rounded-lg bg-saibyl-gold text-saibyl-void hover:bg-saibyl-gold-hover transition-colors disabled:opacity-50"
            >
              <Send className="w-4 h-4" />
            </button>
          </form>
        </div>
      )}
    </div>
  );
}
