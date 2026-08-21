import { useEffect, useMemo, useRef, useState, type FormEvent } from 'react';
import { Link, useParams } from 'react-router-dom';
import { AxiosError } from 'axios';
import { ArrowLeft, Copy, Download, MessageCircle, RotateCcw, Send, X } from 'lucide-react';
import ReactMarkdown from 'react-markdown';
import { formatDistanceToNow } from 'date-fns';
import api from '@/lib/api';
import { getErrorMessage } from '@/lib/errors';
import { cleanContent, stripDuplicateTitle } from '@/lib/utils';
import { REPORT_TERMINAL_STATUSES } from '@/lib/constants';
import { isFinished } from '@/lib/status';
import {
  isSupportedSchema,
  withSchemaDefaults,
  SUPPORTED_SCHEMA_VERSION,
  type AnalysisResponse,
  type SimulationAnalysis,
} from '@/lib/analysis';
import SectionRenderer from '@/components/report/SectionRenderer';
import ReportExport from '@/components/report/ReportExport';
import WhatNext from '@/components/billing/WhatNext';
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
import type { Simulation, SimulationReport } from '@/types';

/* ------------------------------------------------------------------ */
/*  Types                                                              */
/* ------------------------------------------------------------------ */

interface ChatMessage {
  role: 'user' | 'assistant';
  content: string;
}

/**
 * `POST /reports/{id}/chat` → 409, when there is no report to answer from yet.
 *
 * The body is `{ detail: { … } }` — an object, not the `detail: string` every
 * other error on this API uses, so `getErrorMessage` cannot read it and would
 * surface "Request failed with status code 409" instead of the sentence the
 * server wrote. Parsed explicitly for that reason.
 */
interface ReportNotReady {
  code: 'report_not_ready';
  report_id: string;
  status: string;
  message: string;
}

function asReportNotReady(err: unknown): ReportNotReady | null {
  if (!(err instanceof AxiosError) || err.response?.status !== 409) return null;
  const detail = err.response.data?.detail;
  if (!detail || typeof detail !== 'object' || detail.code !== 'report_not_ready') return null;
  return detail as ReportNotReady;
}

/**
 * How many times a report with an *unrecognised* status may be re-fetched.
 *
 * The status-based test below covers every value the backend writes. This bound
 * only applies to the emptiness fallback, which fires when the status is
 * something this build has never heard of — and an unrecognised status is not a
 * licence to poll forever. At the 5s interval this is two minutes.
 */
const UNKNOWN_STATUS_POLL_LIMIT = 24;

const TAB_LABELS = [
  'What happened',
  'What they pushed back on',
  'Who said what',
  // Sits next to the pushback tab because that is where the founder already is
  // when they decide to do something about it. Appended rather than inserted:
  // `activeTab` is an index, and renumbering the existing tabs would silently
  // change what any bookmarked or linked position points at.
  'The write-up',
  'The raw numbers',
  'Answer them back',
] as const;

const INOCULATE_TAB = 5;

/* ------------------------------------------------------------------ */
/*  Helpers                                                            */
/* ------------------------------------------------------------------ */

function statusColor(status: string): string {
  // Green like every other "Finished" pill in the app — one status, one idiom.
  if (isFinished(status)) {
    return 'bg-saibyl-green/10 text-saibyl-positive border-saibyl-green/40';
  }
  switch (status.toLowerCase()) {
    case 'running':
    case 'analyzing':
      return 'bg-saibyl-gold/15 text-saibyl-gold border-saibyl-gold/30';
    case 'failed':
      return 'bg-saibyl-negative/15 text-saibyl-negative border-saibyl-negative/30';
    default:
      return 'bg-saibyl-muted/15 text-saibyl-muted border-saibyl-muted/30';
  }
}

/**
 * What this run's state is called on screen.
 *
 * Never `simulation.status` raw. The database holds both `complete` and
 * `completed` — see `lib/status.ts` — so rendering the column directly is why a
 * founder saw the same finished run labelled "COMPLETED" on one load and
 * "COMPLETE" on the next.
 */
function runStateWord(status: string): string {
  if (isFinished(status)) return 'Finished';
  switch (status) {
    case 'stopped':
      return 'Stopped';
    case 'failed':
      return 'Failed';
    case 'preparing':
      return 'Building the room';
    case 'running':
      return 'Running';
    case 'analyzing':
      return 'Working out what happened';
    case 'ready':
      return 'Ready to start';
    case 'draft':
      return 'Not started yet';
    default:
      return status;
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

  const [report, setReport] = useState<SimulationReport | null>(null);
  const [simulation, setSimulation] = useState<Simulation | null>(null);
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
  const [chatNotReady, setChatNotReady] = useState<ReportNotReady | null>(null);
  const [regenerating, setRegenerating] = useState(false);
  const [regenerateError, setRegenerateError] = useState('');
  const chatEndRef = useRef<HTMLDivElement>(null);

  /* Re-fetching the report is what drives the "still generating" banner, so it
     is restarted and halted from more than one place: the fetch itself, and a
     409 from the chat endpoint that reports a status the page had not seen yet.
     The ref is the halt — a poll that has been told the report failed must not
     schedule another tick, whichever of the two learned it first. */
  const [pollNonce, setPollNonce] = useState(0);
  const pollHalted = useRef(false);

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
    let unknownStatusPolls = 0;

    async function load() {
      if (pollHalted.current) return;
      try {
        const [reportRes, simRes] = await Promise.all([
          api.get(`/reports/by-simulation/${simId}`),
          api.get(`/simulations/${simId}`),
        ]);
        if (cancelled) return;

        const rpt = reportRes.data as SimulationReport;
        setReport(rpt);
        setSimulation(simRes.data);
        setLoading(false);

        // A terminal status ends the poll outright. Testing only for emptiness
        // is what made a failed report poll forever: a failure leaves no
        // markdown and no section content, so "still empty" looked identical to
        // "still writing" and the request repeated every five seconds for as
        // long as the tab stayed open.
        const terminal = REPORT_TERMINAL_STATUSES.includes(rpt.status ?? '');
        const explicitlyWriting = rpt.status === 'generating' || rpt.status === 'pending';
        // The emptiness fallback, reached only when the status is absent or is
        // a value this build does not know. It is bounded for the same reason
        // the terminal check exists: "empty" is not evidence of progress, and
        // an unrecognised status must not be able to poll indefinitely either.
        const maybeWriting =
          !terminal &&
          !explicitlyWriting &&
          !rpt.full_markdown &&
          rpt.sections.every((s) => !s.content);
        if (maybeWriting) unknownStatusPolls += 1;

        const stillWriting =
          !terminal &&
          (explicitlyWriting ||
            (maybeWriting && unknownStatusPolls < UNKNOWN_STATUS_POLL_LIMIT));
        if (stillWriting && !cancelled && !pollHalted.current) {
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
          // how a chart ends up quietly missing a series. Only ever reached now
          // when the artifact is *newer* than this build — an older one renders,
          // because the schema is additive.
          setAnalysisError(
            `These figures were written by a newer version of Saibyl (format ${payload.schema_version}; this page reads up to ${SUPPORTED_SCHEMA_VERSION}). We are showing nothing rather than the parts we recognise. Reload the page to pick up the current version.`,
          );
          return;
        }
        setAnalysis(withSchemaDefaults(payload.artifact));
      } catch (err) {
        if (!cancelled) {
          setAnalysisError(
            getErrorMessage(
              err,
              'Nobody has scored what was said in this run, so there are no figures for it.',
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
  }, [simId, pollNonce]);

  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [chatMessages, chatLoading]);

  /* The report arrived while the chat was locked out. Clearing here rather than
     leaving the panel up means the lockout ends by itself, without the reader
     having to work out that reloading would fix it. */
  useEffect(() => {
    if (chatNotReady && REPORT_TERMINAL_STATUSES.includes(report?.status ?? '')) {
      if (report?.status !== 'failed') setChatNotReady(null);
    }
  }, [report?.status, chatNotReady]);

  const sendChat = async (e: FormEvent) => {
    e.preventDefault();
    if (!chatInput.trim() || !report || chatNotReady) return;
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
          content: data.answer || data.response || data.message || 'We got no answer back. Try asking again.',
        },
      ]);
    } catch (err) {
      const notReady = asReportNotReady(err);
      if (notReady) {
        // Not an answer, so it is not pushed into the transcript as one. The
        // panel below renders the server's own `message`, then branches on the
        // status it reports.
        setChatNotReady(notReady);
        if (notReady.status === 'failed') {
          // Stop polling. A failed report is not going to arrive, and this is
          // the second of the two places that can learn so — the fetch reads
          // the same status, but only whichever one learns it first stops the
          // timer.
          pollHalted.current = true;
        } else {
          // pending / generating: it is still coming. Restart the poll in case
          // this page loaded after it had already stopped.
          pollHalted.current = false;
          setPollNonce((n) => n + 1);
        }
        return;
      }
      setChatMessages((prev) => [
        ...prev,
        {
          role: 'assistant',
          content: getErrorMessage(err, 'Something went wrong answering that. Try again.'),
        },
      ]);
    } finally {
      setChatLoading(false);
    }
  };

  /**
   * Write it up again, from the scores that already exist.
   *
   * Everything measured on this page is independent of the prose and unaffected
   * by its failure, so this redoes the write-up only — it does not put anybody
   * back in the room, and costs nothing near what that would.
   */
  const regenerateReport = async () => {
    if (!simId) return;
    setRegenerating(true);
    setRegenerateError('');
    try {
      await api.post('/reports/generate', { simulation_id: simId });
      setChatNotReady(null);
      pollHalted.current = false;
      setPollNonce((n) => n + 1);
    } catch (err) {
      setRegenerateError(getErrorMessage(err, 'We could not start writing it again.'));
    } finally {
      setRegenerating(false);
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
        <p className="text-[18px] font-bold text-saibyl-platinum">
          There is nothing written up for this run
        </p>
        <p className="text-[13px] text-saibyl-muted max-w-md text-center leading-relaxed">
          The run itself is safe — everyone in the room has already been read and
          measured. It is only the write-up that did not finish, and writing it
          again costs nothing: nobody goes back in the room.
        </p>
        {/*
          The button this screen was missing.

          It said the write-up "has not been started again" and then offered no
          way to start it — a dead end at the worst possible moment, because a
          founder reaches it having already spent the credits the run charged.
          On the free tier that is the entire grant, so "go back to your runs"
          was the whole remedy for a paid run with no report.

          `regenerateReport` already existed and is free; it was simply never
          reachable from the failure it exists for.
        */}
        <button
          type="button"
          onClick={regenerateReport}
          className="inline-flex items-center gap-1.5 px-5 py-2 rounded-xl bg-saibyl-blue text-white font-semibold text-[13px] hover:bg-saibyl-gold-hover transition-colors"
        >
          {regenerating ? 'Writing it up again…' : 'Write it up again'}
        </button>
        {regenerateError && (
          <p className="text-[12px] text-saibyl-negative">{regenerateError}</p>
        )}
        <Link
          to="/app/simulations"
          className="flex items-center gap-1.5 text-[13px] text-saibyl-muted hover:text-saibyl-ink transition-colors"
        >
          <ArrowLeft className="w-4 h-4" />
          Back to your runs
        </Link>
      </div>
    );
  }

  const measurementMissing = (
    <Panel title="Nothing here has been measured yet">
      <NoData>
        {analysisError ||
          'Nobody has scored what was said in this run, so there are no figures to show.'}
        <br />
        <br />
        No number on this page is worked back out of the written report. If the
        scoring has not happened, the charts stay empty rather than being filled
        in with something plausible.
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
          <ArrowLeft className="w-3.5 h-3.5" /> Your runs
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
            {/* No `SIM-{first four characters of the id}` line. It read as a
                reference number and was not one — four characters off the front
                of a UUID identify nothing and collide between runs, and a
                founder reported three different runs all showing the same
                "SIM-1111". The run's own question is real and is what tells
                one report from another. */}
            {simulation?.prediction_goal && (
              <p className="text-[12px] text-saibyl-muted mt-1 max-w-2xl leading-relaxed">
                {simulation.prediction_goal}
              </p>
            )}
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
              Run this again
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
              {/* Never the raw column value. It holds both `complete` and
                  `completed`, which is how the same run read differently
                  between two loads. */}
              {runStateWord(simulation.status)}
            </span>
          )}
          {simulation?.completed_at && (
            <span className="text-[11px] text-saibyl-muted">
              finished{' '}
              {formatDistanceToNow(new Date(simulation.completed_at), { addSuffix: true })}
            </span>
          )}
          {analysis && (
            <>
              <span className="text-[11px] text-saibyl-muted">
                {analysis.quality.agents_active} of {analysis.quality.agents_total} people
                said something
              </span>
              <span className="text-[11px] text-saibyl-muted">
                {analysis.quality.events_measured.toLocaleString()} posts and replies we
                could read
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
      {/* pb-24 keeps the floating ask-pill off the last row of content. */}
      <div className="flex-1 overflow-auto p-8 pb-24">
        {report.status === 'failed' && (
          <div className="mb-6 px-5 py-4 rounded-2xl bg-saibyl-negative/10 border border-saibyl-negative/20">
            <div className="flex items-center gap-3">
              <span className="inline-flex h-3 w-3 rounded-full bg-saibyl-negative shrink-0" />
              <span className="text-[14px] text-saibyl-platinum">
                The written-up version failed and is not coming. Everything measured below is
                unaffected — it is scored from what people actually said, not from the
                write-up.
              </span>
            </div>
            <button
              onClick={regenerateReport}
              disabled={regenerating}
              className="mt-3 ml-6 flex items-center gap-1.5 text-[12px] px-3 py-1.5 rounded-lg bg-saibyl-gold text-saibyl-void font-semibold hover:bg-saibyl-gold-hover disabled:opacity-50 transition-colors"
            >
              <RotateCcw className="w-3.5 h-3.5" />
              {regenerating ? 'Starting…' : 'Write it up again'}
            </button>
            {regenerateError && (
              <p className="mt-2 ml-6 text-[12px] text-saibyl-negative">{regenerateError}</p>
            )}
          </div>
        )}

        {report.status &&
          !REPORT_TERMINAL_STATUSES.includes(report.status) && (
            <div className="mb-6 flex items-center gap-3 px-5 py-4 rounded-2xl bg-saibyl-insight-violet/10 border border-saibyl-insight-violet/20">
              <span className="relative flex h-3 w-3">
                <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-saibyl-insight-violet opacity-75" />
                <span className="relative inline-flex rounded-full h-3 w-3 bg-saibyl-insight-violet" />
              </span>
              <span className="text-[14px] text-saibyl-platinum">
                The written-up version is still being put together. Everything measured below
                is already complete and does not wait on it.
              </span>
            </div>
          )}

        {/* Tab 0 — Findings */}
        {activeTab === 0 &&
          (analysis ? (
            <>
              {/* When several messages were tested, which one won comes first
                  and the overall figures are demoted — those average every
                  message into one number, which describes none of them.
                  Reversing this order would put a meaningless figure at the top
                  of the page. */}
              {analysis.scoreboard ? (
                <>
                  <VariantScoreboardPanel
                    scoreboard={analysis.scoreboard}
                    // The panel's callback carries only ids; the drawer also
                    // wants a heading. Supplied here rather than making `label`
                    // optional, because an untitled drawer is how a reader
                    // loses track of which message they opened.
                    onDrillDown={(ids) => drillDown(ids, 'What people said about this message')}
                  />
                  <p className="text-[11px] text-saibyl-muted mb-3">
                    The figures below mix every message together. They tell you about
                    your audience, not about any one thing you wrote.
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
              {/* Last on the page a founder actually reads, after the evidence
                  rather than before it: the two questions this run raised and
                  could not answer, priced. */}
              <WhatNext productId={simulation?.project_id} />
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
                  and no table of buyer types makes that legible. */}
              {analysis.by_cohort.length > 0 && (
                <div className="mb-6">
                  <GroupBreakdown
                    title="Your buyers, against the people who already have something else"
                    slices={analysis.by_cohort}
                    objectionLabels={objectionLabels}
                  />
                </div>
              )}
              <div className="grid grid-cols-1 xl:grid-cols-2 gap-6">
                <GroupBreakdown
                  title="Where they were"
                  slices={analysis.by_platform}
                  objectionLabels={objectionLabels}
                />
                <GroupBreakdown
                  title="What kind of buyer they were"
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
              <Panel title="The write-up">
                <NoData>Nobody has written this up yet.</NoData>
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
              <div className="prose prose-sm max-w-none">
                <ReactMarkdown>
                  {report.full_markdown ||
                    report.sections
                      .map(
                        (s) => `## ${s.title}\n\n${stripDuplicateTitle(s.title, s.content)}`,
                      )
                      .join('\n\n---\n\n') ||
                    'There is nothing written up to show here yet.'}
                </ReactMarkdown>
              </div>
            </div>
            {analysis && (
              <Panel
                title="The exact numbers behind every chart"
                note="Every figure on this page was read straight out of this. Nothing is worked out in your browser."
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
          style={{ background: 'linear-gradient(135deg, #286cf0, #5268e9)' }}
        >
          <MessageCircle className="w-5 h-5" />
          Ask about this run
        </button>
      )}

      {chatOpen && (
        <div className="fixed top-0 right-0 w-[360px] h-full z-50 bg-saibyl-void border-l border-saibyl-border flex flex-col shadow-2xl">
          <div className="flex items-center justify-between px-4 py-3 border-b border-saibyl-border">
            <h3 className="text-[14px] font-semibold text-saibyl-platinum">Ask about this</h3>
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
                Ask anything about what happened in this run.
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

          {/* The server's own sentence, verbatim, then what happens next —
              which depends entirely on the status it reported. */}
          {chatNotReady && (
            <div
              className={`mx-3 mb-2 px-3 py-3 rounded-xl border ${
                chatNotReady.status === 'failed'
                  ? 'bg-saibyl-negative/10 border-saibyl-negative/25'
                  : 'bg-saibyl-insight-violet/10 border-saibyl-insight-violet/25'
              }`}
            >
              <p className="text-[12px] text-saibyl-platinum leading-relaxed">
                {chatNotReady.message}
              </p>
              {chatNotReady.status === 'failed' ? (
                <>
                  <p className="text-[11px] text-saibyl-muted mt-1.5 leading-relaxed">
                    It is not still coming — we have stopped waiting for it. Everything
                    measured on this page is unaffected; only the written-up version is
                    missing. Write it again and there will be something here to answer
                    from.
                  </p>
                  <button
                    onClick={regenerateReport}
                    disabled={regenerating}
                    className="mt-2.5 flex items-center gap-1.5 text-[12px] px-3 py-1.5 rounded-lg bg-saibyl-gold text-saibyl-void font-semibold hover:bg-saibyl-gold-hover disabled:opacity-50 transition-colors"
                  >
                    <RotateCcw className="w-3.5 h-3.5" />
                    {regenerating ? 'Starting…' : 'Write it up again'}
                  </button>
                  {regenerateError && (
                    <p className="mt-2 text-[12px] text-saibyl-negative">{regenerateError}</p>
                  )}
                </>
              ) : (
                <p className="flex items-center gap-2 text-[11px] text-saibyl-muted mt-1.5">
                  <span className="relative flex h-2 w-2">
                    <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-saibyl-insight-violet opacity-75" />
                    <span className="relative inline-flex rounded-full h-2 w-2 bg-saibyl-insight-violet" />
                  </span>
                  Still being written — this unlocks on its own when it lands.
                </p>
              )}
            </div>
          )}

          <form onSubmit={sendChat} className="p-3 border-t border-saibyl-border flex gap-2">
            <input
              value={chatInput}
              onChange={(e) => setChatInput(e.target.value)}
              disabled={!!chatNotReady}
              placeholder={
                chatNotReady ? 'Nothing to ask about yet…' : 'e.g. Why did they hate the price?'
              }
              className="flex-1 bg-saibyl-surface border border-saibyl-border rounded-lg px-3 py-2 text-[13px] text-saibyl-platinum placeholder-saibyl-muted focus:outline-none focus:ring-1 focus:ring-saibyl-gold focus:border-saibyl-gold disabled:opacity-50"
            />
            <button
              type="submit"
              disabled={chatLoading || !chatInput.trim() || !!chatNotReady}
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
