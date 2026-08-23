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
import Room from '@/components/room/Room';
import QualityNotice from '@/components/analysis/QualityNotice';
import AdversarialNotice from '@/components/analysis/AdversarialNotice';
import SentimentArc from '@/components/analysis/SentimentArc';
import GroupBreakdown from '@/components/analysis/GroupBreakdown';
import ObjectionMap from '@/components/analysis/ObjectionMap';
import FlashpointList from '@/components/analysis/FlashpointList';
import VariantScoreboardPanel from '@/components/analysis/VariantScoreboard';
import EvidenceDrawer from '@/components/analysis/EvidenceDrawer';
import Panel from '@/components/analysis/Panel';
import InoculationWorkbench from '@/components/founder/InoculationWorkbench';
import {
  Action,
  Card,
  Ground,
  Notice,
  PageHeader,
  Rise,
  dealDelayMs,
} from '@/components/design';
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
      /* Cyan, the system's colour for "this is happening right now" — the same
         one `sb-note-live` wears. It was `saibyl-gold`, a legacy dark-theme
         alias that resolves to the blue accent, so a run in progress was
         wearing the colour the app reserves for things you press. */
      return 'bg-saibyl-cyan/[0.12] text-[#127f8a] border-saibyl-cyan/40';
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
 *
 * ---
 *
 * **Restyled onto the shared design system on 2026-08-23.** `design/Report.dc.html`
 * is this page's artboard, and the gap between it and what shipped was not a
 * matter of taste:
 *
 * 1. The root painted `bg-saibyl-void` — a flat `#f8fbff` panel laid over the
 *    radial wash — so canvas rule 1 was switched off on the page the room is
 *    reported on. `Ground` re-lays it.
 * 2. Every colour was a legacy dark-theme alias (`saibyl-void`, `saibyl-gold`,
 *    `saibyl-platinum`, `saibyl-gold-hover`). Those names still resolve to
 *    light values, which is exactly why nobody noticed the page had never been
 *    converted.
 * 3. The heading was a hand-rolled `<h1>` with no eyebrow and no accent
 *    phrase. The artboard opens with a dotted mono line, a title and one
 *    Playfair italic sentence; `PageHeader` is that, and it pulses its dot
 *    while the write-up is still being put together.
 * 4. Three states — the write-up failed, the write-up is still coming, nothing
 *    has been measured — were all said in the same grey body text as
 *    everything else. They are `Notice` blocks now, in the tone the state
 *    actually has.
 * 5. `disabled` is gone. Where a control is mid-flight the control is replaced
 *    by what is happening, which stops the double submit the grey rectangle
 *    used to and leaves no third rendering.
 *
 * The page also stopped nesting its own scroll container. `AppLayout`'s
 * `<main>` already scrolls; a second `h-screen`/`overflow-auto` inside it gave
 * the report two scrollbars and pinned a header that the artboard scrolls
 * away. The tab bar is `sticky` instead, which keeps it reachable without
 * spending the viewport on chrome.
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
    /* `chatLoading` joins the guard for the same reason `regenerating` guards
       the write-up: the `disabled` attribute that used to hold this line is
       gone, and a second question posted while the first is still in flight
       appends both to the transcript out of order. Cheaper than a report, but
       the same defect. */
    if (!chatInput.trim() || !report || chatNotReady || chatLoading) return;
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
    /* The guard the `disabled` attribute used to be, and it has to live here
       rather than on the button.
       Removing `disabled` from a control that spends money is only safe once
       the handler itself refuses to re-enter: `POST /reports/generate` starts a
       paid write-up, and a double click landing inside one render is a second
       one. Reading `regenerating` from state is enough because React batches
       within an event and these clicks are separate events — the flag is set
       before the first `await` and stays set until `finally`. */
    if (regenerating) return;
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
      <Ground className="min-h-full">
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
        <div className="p-8 space-y-6">
          <div className="grid grid-cols-1 sm:grid-cols-4 gap-4">
            {Array.from({ length: 4 }).map((_, i) => (
              <div
                key={i}
                className="h-28 bg-white border border-saibyl-border rounded-2xl animate-pulse"
              />
            ))}
          </div>
          <div className="h-64 bg-white border border-saibyl-border rounded-2xl animate-pulse" />
        </div>
      </Ground>
    );
  }

  if (error || !report) {
    return (
      <Ground className="min-h-full flex items-center justify-center p-8">
        <Rise className="w-full max-w-lg">
          {/*
            The reason, the cost, and the button that fixes it — in the one
            rendering the founder's standing rule allows. It used to be an
            18px bold line, a grey paragraph and a flat blue rectangle, which
            is three registers saying one thing.

            The button itself was the fix this screen was missing entirely: it
            said the write-up "has not been started again" and then offered no
            way to start it — a dead end at the worst possible moment, because
            a founder reaches it having already spent the credits the run
            charged. On the free tier that is the entire grant, so "go back to
            your runs" was the whole remedy for a paid run with no report.
          */}
          <Notice
            tone="blocked"
            title="There is nothing written up for this run"
            action={
              regenerating ? (
                /* No `disabled`, and no second POST either: while it is
                   running the control is replaced by what is happening. */
                <span className="text-[12.5px] font-extrabold text-saibyl-violet">
                  Writing it up again…
                </span>
              ) : (
                <Action onClick={regenerateReport}>
                  <RotateCcw className="w-3.5 h-3.5" />
                  Write it up again
                </Action>
              )
            }
          >
            The run itself is safe &mdash; everyone in the room has already been
            read and measured. It is only the write-up that did not finish, and
            writing it again costs nothing: nobody goes back in the room.
          </Notice>

          {regenerateError && (
            <p className="mt-3 text-[12px] text-saibyl-negative">{regenerateError}</p>
          )}

          <Link
            to="/app/simulations"
            className="mt-5 inline-flex items-center gap-1.5 text-[13px] text-saibyl-muted hover:text-saibyl-ink transition-colors"
          >
            <ArrowLeft className="w-4 h-4" />
            Back to your runs
          </Link>
        </Rise>
      </Ground>
    );
  }

  /* A violet block, not a dashed grey box inside a white card. This reports a
     state — nothing to draw from — and the canvas says a state is said in
     colour. The `action` is deliberately absent: there is no button anywhere
     in the product that scores a finished run on demand, and inventing one
     here would be a dead end wearing a way out. */
  const measurementMissing = (
    <Notice tone="blocked" title="Nothing here has been measured yet">
      {analysisError ||
        'Nobody has scored what was said in this run, so there are no figures to show.'}
      <br />
      <br />
      No number on this page is worked back out of the written report. If the
      scoring has not happened, the charts stay empty rather than being filled
      in with something plausible.
    </Notice>
  );

  /* The write-up is still on its way — which is the one condition under which
     the eyebrow's dot is allowed to pulse. `live` on a settled page is
     decoration, and decoration that claims to be a state stops meaning
     anything the second time somebody sees it. */
  const writeUpPending = Boolean(
    report.status && !REPORT_TERMINAL_STATUSES.includes(report.status),
  );

  return (
    <Ground className="min-h-full pb-24">
      {/* Breadcrumb + heading, in the scroll flow rather than pinned above it.
          The artboard scrolls its header away and keeps the room in view; the
          old fixed band spent a fifth of the viewport on chrome. */}
      <Rise className="px-8 pt-6">
        <div className="flex items-center gap-2 mb-5">
          <Link
            to="/app/simulations"
            className="text-[12px] text-saibyl-muted hover:text-saibyl-ink transition-colors flex items-center gap-1"
          >
            <ArrowLeft className="w-3.5 h-3.5" /> Your runs
          </Link>
          <span className="text-saibyl-border text-[11px]">&rsaquo;</span>
          <span className="text-[12px] font-semibold text-saibyl-silver">{simulation?.name}</span>
        </div>

        <div className="flex flex-wrap items-start justify-between gap-4">
          <PageHeader
            /* Not the room's own line — `Room` already deals
               "The room · N buyers · M rounds" over the stage below, and two
               of those on one screen is the same fact said twice. */
            eyebrow="Your report"
            live={writeUpPending}
            title={simulation?.name ?? 'Report'}
            phrase="They argued about it, and this is what they kept coming back to."
            className="flex-1 min-w-0"
          >
            <p>
              Everything on this page was read off what people in the room
              actually wrote. Nothing is worked back out of the write-up, so a
              figure that was never measured stays missing rather than turning
              into a plausible number.
            </p>
            {/* No `SIM-{first four characters of the id}` line. It read as a
                reference number and was not one — four characters off the front
                of a UUID identify nothing and collide between runs, and a
                founder reported three different runs all showing the same
                "SIM-1111". The run's own question is real and is what tells
                one report from another. */}
            {simulation?.prediction_goal && (
              <p className="mt-2 text-saibyl-ink">{simulation.prediction_goal}</p>
            )}
          </PageHeader>

          <div className="flex items-center gap-2 flex-shrink-0">
            <ReportExport
              reportId={report.id}
              simulationId={simId ?? ''}
              simulationName={simulation?.name ?? 'report'}
              sections={report.sections}
            />
            {/* `quiet`. The one gradient on this screen is the ask-pill, which
                is the thing a founder is actually here to press; four buyers'
                worth of blue rectangles is how a screen stops saying which
                one matters. */}
            <Action as={Link} to={`/app/simulations/new?clone=${simId}`} kind="quiet">
              <RotateCcw className="w-3.5 h-3.5" />
              Run this again
            </Action>
          </div>
        </div>

        <div className="flex items-center gap-3 flex-wrap mt-5">
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
      </Rise>

      {/* Tabs. Sticky rather than pinned: the heading above scrolls away, and
          the bar stays reachable from anywhere in a long report. The paper
          tint and blur are the same surface `sb-stage` is drawn on, so the
          content passing underneath stays visible without smearing. */}
      <Rise
        delayMs={dealDelayMs(1)}
        className="sticky top-0 z-20 mt-6 border-b border-saibyl-border bg-saibyl-paper/85 backdrop-blur-[18px]"
      >
        <div className="flex gap-0 px-8 overflow-x-auto">
          {TAB_LABELS.map((label, i) => (
            <button
              key={label}
              type="button"
              onClick={() => setActiveTab(i)}
              className={`px-4 py-3 text-[13px] font-medium transition-colors border-b-2 whitespace-nowrap ${
                i === activeTab
                  ? 'text-saibyl-ink border-saibyl-blue'
                  : 'text-saibyl-muted border-transparent hover:text-saibyl-ink'
              }`}
            >
              {label}
            </button>
          ))}
        </div>
      </Rise>

      {/* Content */}
      <div className="px-8 pt-6">
        {report.status === 'failed' && (
          /* Was a rose-tinted slab with a flat blue rectangle inside it and a
              `disabled` attribute on the one control that fixes the problem.
              The state is "something is missing and here is what supplies it",
              which is what `blocked` says in the system's own colour. */
          <Notice
            tone="blocked"
            title="The written-up version failed and is not coming"
            className="mb-6"
            action={
              regenerating ? (
                <span className="text-[12.5px] font-extrabold text-saibyl-violet">
                  Starting…
                </span>
              ) : (
                <Action onClick={regenerateReport} kind="quiet">
                  <RotateCcw className="w-3.5 h-3.5" />
                  Write it up again
                </Action>
              )
            }
          >
            Everything measured below is unaffected &mdash; it is scored from
            what people actually said, not from the write-up.
            {regenerateError && (
              <span className="block mt-2 text-saibyl-negative">{regenerateError}</span>
            )}
          </Notice>
        )}

        {writeUpPending && (
          /* Cyan, because something is genuinely happening. The old block was
              violet with a hand-rolled ping ring, which is the colour the
              system reserves for "blocked" — the two most different states on
              the page were wearing the same one. */
          <Notice
            tone="live"
            title="The written-up version is still being put together"
            className="mb-6"
          >
            Everything measured below is already complete and does not wait on it.
          </Notice>
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
              {/* The room, where the table of numbers used to be.
                  `design/canvas.json`, annotation `the-room`: the landing
                  page's hero is a room of buyers orbiting a pitch, and inside
                  the app — where the founder paid for it — that same room had
                  always been four stat tiles. `Room` renders those same four,
                  from the same two props, around the thing they measured.
                  It draws nothing it was not given and returns null on a run
                  that carried nothing measurable. */}
              <Room
                pitchName={simulation?.name ?? ''}
                groups={analysis.by_archetype}
                objections={analysis.objections}
                headline={analysis.headline}
                quality={analysis.quality}
              />
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
              /* A tab with nothing in it is a dead end unless it offers the
                 way out, and the way out already existed: writing it up is
                 free and puts nobody back in the room. */
              <Notice
                tone="blocked"
                title="Nobody has written this up yet"
                action={
                  regenerating ? (
                    <span className="text-[12.5px] font-extrabold text-saibyl-violet">
                      Starting…
                    </span>
                  ) : (
                    <Action onClick={regenerateReport} kind="quiet">
                      <RotateCcw className="w-3.5 h-3.5" />
                      Write it up
                    </Action>
                  )
                }
              >
                Everything measured in the other tabs is already complete
                &mdash; the write-up is prose over the top of it, and it costs
                nothing to produce.
              </Notice>
            )}
            {report.sections.map((section) => (
              /* `meaning`. Each section is a claim a founder has to weigh, and
                 there are few enough of them that depth still means something. */
              <Card carries="meaning" key={section.title} className="p-6">
                <h2 className="text-[16px] font-bold text-saibyl-ink mb-4">
                  {section.title}
                </h2>
                <SectionRenderer
                  content={stripDuplicateTitle(section.title, cleanContent(section.content))}
                  className="text-saibyl-silver leading-[1.75]"
                />
              </Card>
            ))}
          </div>
        )}

        {/* Tab 4 — Raw data */}
        {activeTab === 4 && (
          <>
            <div className="flex items-center gap-3 mb-4">
              <Action onClick={copyMarkdown} kind="quiet">
                <Copy className="w-3.5 h-3.5" />
                {copied ? 'Copied!' : 'Copy markdown'}
              </Action>
              <Action onClick={downloadMarkdown} kind="quiet">
                <Download className="w-3.5 h-3.5" />
                Download .md
              </Action>
            </div>
            <Card carries="meaning" className="p-6 mb-6">
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
            </Card>
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
        /* The one primary on this screen. It was a hand-rolled copy of
           `sb-action`'s gradient in an inline `style`, which is how a second
           set of the system's numbers gets into the codebase — the class now
           owns it, and the radius is the only thing this call site decides. */
        <Action
          onClick={() => setChatOpen(true)}
          className="fixed bottom-6 right-6 z-40 rounded-full gap-2 px-4 py-3 text-[13px]"
        >
          <MessageCircle className="w-5 h-5" />
          Ask about this run
        </Action>
      )}

      {chatOpen && (
        <div className="fixed top-0 right-0 w-[360px] h-full z-50 bg-saibyl-paper border-l border-saibyl-border flex flex-col shadow-2xl">
          <div className="flex items-center justify-between px-4 py-3 border-b border-saibyl-border">
            <h3 className="text-[14px] font-semibold text-saibyl-ink">Ask about this</h3>
            <button
              type="button"
              onClick={() => setChatOpen(false)}
              className="p-1 rounded-lg text-saibyl-muted hover:text-saibyl-ink hover:bg-white transition-colors"
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
                      ? 'bg-saibyl-blue/[0.08] border border-saibyl-blue/25 text-saibyl-ink'
                      : 'bg-white border border-saibyl-border text-saibyl-silver'
                  }`}
                >
                  {msg.content}
                </div>
              </div>
            ))}
            {chatLoading && (
              <div className="mr-auto max-w-[85%]">
                <div className="bg-white border border-saibyl-border rounded-xl px-3 py-2.5">
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
              which depends entirely on the status it reported. Two states, two
              tones: `blocked` when the write-up is not coming and there is a
              button that changes that, `live` while it is still on its way. */}
          {chatNotReady && (
            <Notice
              tone={chatNotReady.status === 'failed' ? 'blocked' : 'live'}
              title={chatNotReady.message}
              className="mx-3 mb-2 px-3 py-3"
              action={
                chatNotReady.status === 'failed' ? (
                  regenerating ? (
                    <span className="text-[12.5px] font-extrabold text-saibyl-violet">
                      Starting…
                    </span>
                  ) : (
                    <Action onClick={regenerateReport} kind="quiet">
                      <RotateCcw className="w-3.5 h-3.5" />
                      Write it up again
                    </Action>
                  )
                ) : undefined
              }
            >
              {chatNotReady.status === 'failed' ? (
                <>
                  It is not still coming &mdash; we have stopped waiting for it.
                  Everything measured on this page is unaffected; only the
                  written-up version is missing. Write it again and there will
                  be something here to answer from.
                  {regenerateError && (
                    <span className="block mt-2 text-saibyl-negative">{regenerateError}</span>
                  )}
                </>
              ) : (
                'Still being written — this unlocks on its own when it lands.'
              )}
            </Notice>
          )}

          {/* No `disabled` on either control.

              The input is `readOnly` while there is nothing to answer from —
              still focusable, still selectable, and its placeholder says why,
              with the reason and the button that fixes it in the `Notice`
              directly above it. `sendChat` already refuses an empty message
              and refuses to send at all while `chatNotReady` is set, so the
              guard lives where the decision is rather than in an attribute
              that greys a rectangle.

              While an answer is in flight the send control is replaced by the
              same three dots the transcript is showing, which is what stops a
              second submit. */}
          <form onSubmit={sendChat} className="p-3 border-t border-saibyl-border flex gap-2">
            <input
              value={chatInput}
              onChange={(e) => setChatInput(e.target.value)}
              readOnly={!!chatNotReady}
              placeholder={
                chatNotReady ? 'Nothing to ask about yet…' : 'e.g. Why did they hate the price?'
              }
              className="flex-1 bg-white border border-saibyl-border rounded-lg px-3 py-2 text-[13px] text-saibyl-ink placeholder-saibyl-muted focus:outline-none focus:ring-1 focus:ring-saibyl-blue focus:border-saibyl-blue read-only:text-saibyl-muted"
            />
            {chatLoading ? (
              <span className="flex items-center gap-1 px-2 rounded-lg border border-saibyl-border bg-white">
                {[0, 150, 300].map((delay) => (
                  <span
                    key={delay}
                    className="w-1.5 h-1.5 rounded-full bg-saibyl-muted animate-bounce"
                    style={{ animationDelay: `${delay}ms` }}
                  />
                ))}
              </span>
            ) : (
              <Action type="submit" className="px-2 py-2 rounded-lg" aria-label="Send">
                <Send className="w-4 h-4" />
              </Action>
            )}
          </form>
        </div>
      )}
    </Ground>
  );
}
