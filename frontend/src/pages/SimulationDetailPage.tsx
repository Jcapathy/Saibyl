import { useEffect, useState, useCallback } from 'react';
import { useParams, Link } from 'react-router-dom';
import { motion } from 'framer-motion';
import { AlertTriangle } from 'lucide-react';
import api from '@/lib/api';
import { PLATFORM_NAMES, TERMINAL_STATUSES, ACTIVE_STATUSES, IDLE_STATUSES } from '@/lib/constants';
import { isFinished } from '@/lib/status';
import StatusBadge from '@/components/StatusBadge';
import RunConfigurator, { type RunShape } from '@/components/RunConfigurator';
import VariantSetup from '@/components/marketing/VariantSetup';
import { getErrorMessage } from '../lib/errors';
import type { SimulationAgent } from '../lib/types';
import type { Simulation } from '@/types';

/**
 * Narrow the stored `depth` to the three values the pricing API accepts.
 *
 * The column is `TEXT NOT NULL DEFAULT 'standard'` with no CHECK constraint, so
 * it is always present but not guaranteed to be one of them. Falling back to
 * the column's own default keeps the quote on this page priced the same way the
 * run was.
 */
function toDepth(value: string): RunShape['depth'] {
  return value === 'brief' || value === 'deep' ? value : 'standard';
}

/**
 * What this run's state is called on screen.
 *
 * Never the raw column value. The database holds both `complete` and
 * `completed` — see `lib/status.ts` — so rendering `sim.status` directly is why
 * the same finished run read "COMPLETED" on one load and "COMPLETE" on the
 * next. `isFinished` collapses the two, and everything else is given a word a
 * founder already knows rather than the engine's own vocabulary.
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

/**
 * Redeem the quote the configurator stashed for this simulation, once.
 *
 * A quote is single-use server-side, so replaying one on a retry would fail the
 * start with "already used" rather than falling back to a fresh price. Removing
 * it here means a retry re-prices against the stored shape instead — the same
 * cost, arrived at honestly.
 */
function takeQuoteId(simulationId: string): string | undefined {
  const key = `saibyl_quote_${simulationId}`;
  const quoteId = sessionStorage.getItem(key);
  if (quoteId) sessionStorage.removeItem(key);
  return quoteId ?? undefined;
}

export default function SimulationDetailPage() {
  const { id } = useParams<{ id: string }>();
  const [sim, setSim] = useState<Simulation | null>(null);
  const [loading, setLoading] = useState(true);
  const [running, setRunning] = useState(false);
  const [runStatus, setRunStatus] = useState('');
  const [error, setError] = useState('');
  const [eventCount, setEventCount] = useState(0);
  const [events, setEvents] = useState<Record<string, unknown>[]>([]);

  /* How many variants are stored carrying copy, as `VariantSetup` last read or
     wrote them. Null means "not yet known" and is never treated as zero: an
     unanswered question and an answer of none are different, and only one of
     them justifies blocking a run. */
  const [variantsWithCopy, setVariantsWithCopy] = useState<number | null>(null);
  const [variantResetting, setVariantResetting] = useState(false);
  const [variantSetupKey, setVariantSetupKey] = useState(0);

  // Accuracy scoring state
  const [actualSentiment, setActualSentiment] = useState('');
  const [actualNotes, setActualNotes] = useState('');
  const [scoringLoading, setScoringLoading] = useState(false);
  const [scoringError, setScoringError] = useState('');
  const [accuracyResult, setAccuracyResult] = useState<{ accuracy_score: number; predicted_sentiment: number; actual_sentiment: number; analysis: string } | null>(null);

  // Interview panel state
  const [agents, setAgents] = useState<SimulationAgent[]>([]);
  const [selectedAgentId, setSelectedAgentId] = useState('');
  const [interviewPrompt, setInterviewPrompt] = useState('');
  const [interviewLoading, setInterviewLoading] = useState(false);
  const [interviewResponses, setInterviewResponses] = useState<{ agent: string; persona: string; response: string; sentiment: number }[]>([]);

  /* The run was priced per arena — `variants` on the row is what the quote
     signed for — but the engine executes one arena per variant row that has
     copy. A 4-variant run with no copy was billed four arenas and ran one, so
     `/start` now refuses it with a 409. Mirrored here so the refusal is visible
     before the click rather than as an error after it. */
  const configuredVariants = sim?.variants ?? 1;
  const variantsUnknown = configuredVariants > 1 && variantsWithCopy === null;
  const variantShortfall =
    configuredVariants > 1 &&
    variantsWithCopy !== null &&
    variantsWithCopy < configuredVariants;
  /* What this run would actually execute, and therefore what it should be
     quoted at. Never `configuredVariants`: quoting the selected count is how
     the price reads 4x on a run the server will refuse. */
  const arenasThatWouldRun = Math.max(1, variantsWithCopy ?? configuredVariants);

  const loadSim = useCallback(() => {
    api.get(`/simulations/${id}`).then((r) => {
      setSim(r.data);
      // Load latest events
      api.get(`/simulations/${id}/events`, { params: { limit: 50, offset: 0 } }).then((r2) => {
        const data = Array.isArray(r2.data) ? r2.data : [];
        setEvents(data);
        setEventCount(data.length);
      }).catch(() => {});
    }).catch(() => {}).finally(() => setLoading(false));
  }, [id]);

  useEffect(() => { loadSim(); }, [loadSim]);

  // Load agents for interview panel
  useEffect(() => {
    if (!id) return;
    api.get(`/simulations/${id}/agents`).then((r) => {
      setAgents(Array.isArray(r.data) ? r.data : []);
    }).catch(() => {});
  }, [id]);

  const handleInterview = async () => {
    if (!id || !interviewPrompt.trim()) return;
    setInterviewLoading(true);
    try {
      if (selectedAgentId) {
        const { data } = await api.post(`/simulations/${id}/interview`, { agent_id: selectedAgentId, prompt: interviewPrompt });
        setInterviewResponses((prev) => [...prev, {
          agent: data.agent_username,
          persona: data.persona_type,
          response: data.response,
          sentiment: data.sentiment_score,
        }]);
      } else {
        // Interview all agents
        const { data } = await api.post(`/simulations/${id}/interview/batch`, {
          agent_ids: agents.slice(0, 5).map((a) => a.id),
          prompt: interviewPrompt,
        });
        for (const r of data) {
          setInterviewResponses((prev) => [...prev, {
            agent: r.agent_username,
            persona: r.persona_type,
            response: r.response,
            sentiment: r.sentiment_score,
          }]);
        }
      }
      setInterviewPrompt('');
    } catch (err) {
      const msg = getErrorMessage(err, 'We could not ask that. Nothing was charged.');
      setInterviewResponses((prev) => [...prev, { agent: 'System', persona: 'error', response: msg, sentiment: 0 }]);
    } finally {
      setInterviewLoading(false);
    }
  };

  /**
   * Score what this run predicted against what actually happened.
   *
   * The failure used to be swallowed whole by an empty `catch`, and that is the
   * entire reason this control read as broken: `POST /accuracy/score`
   * **rejects a request with no `actual_sentiment`** with a
   * 400, the rejection was discarded, and the button flipped back to its idle
   * label having said nothing. A founder who pressed it without filling in the
   * number — which the old copy called "optional" — got silence every time.
   *
   * The request is unchanged. What changed is that the server's own sentence is
   * now rendered instead of dropped.
   */
  /* A number between -1 and 1, actually typed. `parseFloat('')` is NaN and
     `Number('')` is 0 - and 0 is a legitimate score meaning "nobody cared",
     so an empty field must not become one. */
  const parsedSentiment = actualSentiment.trim() === ''
    ? null
    : Number(actualSentiment);
  const hasSentiment =
    parsedSentiment !== null &&
    Number.isFinite(parsedSentiment) &&
    parsedSentiment >= -1 &&
    parsedSentiment <= 1;

  const handleScoreAccuracy = async () => {
    if (!id) return;
    // The control is not rendered without a number, so this is unreachable
    // from the UI. It is here because the request 400s without one, and a
    // second caller added later should be refused here rather than by the
    // server returning a sentence written for an API client.
    if (!hasSentiment) return;
    setScoringLoading(true);
    setScoringError('');
    try {
      const { data } = await api.post('/accuracy/score', {
        simulation_id: id,
        actual_sentiment: parsedSentiment,
        notes: actualNotes || null,
      });
      setAccuracyResult(data);
    } catch (err) {
      setScoringError(
        getErrorMessage(
          err,
          'We could not score this run against what you told us. Nothing was saved.',
        ),
      );
    } finally {
      setScoringLoading(false);
    }
  };

  // Poll for as long as the run is in flight. This reads the shared status set
  // rather than its own list: the local copy omitted `analyzing`, so polling
  // stopped the moment measurement began and the page sat on a stale status
  // until the user reloaded it.
  useEffect(() => {
    if (!sim || !ACTIVE_STATUSES.includes(sim.status)) return;
    const interval = setInterval(loadSim, 4000);
    return () => clearInterval(interval);
  }, [sim?.status, loadSim]);

  // Clear local running state when sim reaches a terminal status
  useEffect(() => {
    if (sim && TERMINAL_STATUSES.includes(sim.status)) {
      setRunning(false);
      setRunStatus('');
    }
  }, [sim?.status]);

  // Auto-start simulation when prepare finishes (from wizard flow)
  useEffect(() => {
    if (!sim || !id || sim.status !== 'ready') return;
    // Check if events exist — if so, this sim already ran, don't re-start
    if (eventCount > 0) return;
    // A multi-variant run does not auto-start until the variant rows have been
    // read. Firing before then either 409s on a run the user never got to fix,
    // or — worse, if the guard were skipped — charges for arenas that never
    // execute. Waiting costs one render; the alternative costs money.
    if (variantsUnknown || variantShortfall) return;
    // Auto-start
    setRunning(true);
    setRunStatus('Starting…');
    api.post(`/simulations/${id}/start`, { quote_id: takeQuoteId(id) }).then(() => {
      setRunStatus('Running…');
      loadSim();
    }).catch((err) => {
      setRunning(false);
      setRunStatus('');
      // Previously swallowed. A 409 from the missing-copy guard is the server
      // explaining, in a sentence written to be read, why nothing happened —
      // dropping it left the page sitting on "ready" with no explanation.
      setError(getErrorMessage(err, 'We could not start this run.'));
    });
  }, [sim?.status, id, eventCount, variantsUnknown, variantShortfall]); // eslint-disable-line react-hooks/exhaustive-deps

  // One-click: prepare + wait for ready + start + poll
  async function handleRunNow() {
    if (!id || variantShortfall) return;
    setRunning(true);
    setError('');
    setRunStatus('Building the room…');
    try {
      await api.post(`/simulations/${id}/prepare`);

      // Wait for prepare to finish (poll for ready/failed)
      let ready = false;
      for (let i = 0; i < 60; i++) {
        await new Promise((r) => setTimeout(r, 3000));
        const r = await api.get(`/simulations/${id}`);
        setSim(r.data);
        if (r.data.status === 'ready') { ready = true; break; }
        if (r.data.status === 'failed') {
          setError('We could not build the room. Check that you picked at least one group of buyers.');
          setRunning(false);
          setRunStatus('');
          return;
        }
      }
      if (!ready) {
        setError('Building the room took too long, so we stopped waiting. Nothing was charged.');
        setRunning(false);
        setRunStatus('');
        return;
      }

      setRunStatus('Starting…');
      await api.post(`/simulations/${id}/start`, { quote_id: takeQuoteId(id) });
      setRunStatus('Running — checking for new reactions…');
      // Poll until complete
      const poll = setInterval(async () => {
        try {
          const r = await api.get(`/simulations/${id}`);
          setSim(r.data);
          if (TERMINAL_STATUSES.includes(r.data.status)) {
            clearInterval(poll);
            setRunning(false);
            setRunStatus('');
          }
        } catch { /* keep polling */ }
      }, 4000);
      setTimeout(() => { clearInterval(poll); setRunning(false); setRunStatus(''); }, 300000);
    } catch (err) {
      setError(getErrorMessage(err, 'We could not start this run.'));
      setRunning(false);
      setRunStatus('');
    }
  }

  async function handleStop() {
    try {
      await api.post(`/simulations/${id}/stop`);
      loadSim();
    } catch { /* ignore */ }
  }

  /**
   * The escape hatch the 409 names: drop back to testing one message.
   *
   * An *empty* list, not a list of one — the API rejects exactly one message
   * with a 400, because one message is not a comparison. So "delete all but
   * one" is a different and unavailable operation, and offering it as the fix
   * would replace one refusal with another.
   */
  async function handleResetToSingleArena() {
    if (!id) return;
    setVariantResetting(true);
    setError('');
    try {
      await api.put(`/variants/${id}`, { variants: [] });
      setVariantsWithCopy(0);
      setVariantSetupKey((key) => key + 1);
      loadSim();
    } catch (err) {
      setError(getErrorMessage(err, 'Could not switch this run back to a single message'));
    } finally {
      setVariantResetting(false);
    }
  }

  if (loading) {
    return (
      <div className="p-8 max-w-4xl mx-auto space-y-4">
        <div className="h-8 w-64 rounded-xl bg-saibyl-deep animate-pulse" />
        <div className="grid grid-cols-4 gap-4">
          {[...Array(4)].map((_, i) => <div key={i} className="h-24 rounded-2xl bg-saibyl-deep animate-pulse" />)}
        </div>
      </div>
    );
  }
  if (!sim) return <div className="p-8 text-center text-saibyl-negative">We could not find this run.</div>;

  /*
    Three figures, and every one of them is a real property of the run.

    There used to be a fourth reading "Events", and it was wrong on every run.
    `GET /simulations/{id}/events` returns a *page* — this page asks for 50 —
    with no total in the body and no count header, so `eventCount` was the size
    of the first page and never the run's total. Worse, the fetch swallows its
    own failure, so a request that never landed left the initial `0` on screen:
    a founder looking at a finished 100-person run was shown "0 Events" and had
    no way to tell that from a run where nobody spoke.

    The honest total does exist — `analysis.quality.events_total`, on the report
    — so it is shown there, on a page that has actually fetched it, instead of
    being guessed at here.

    `agent_count` is null until the room has been built, so it renders as a dash
    rather than a zero for the same reason.
  */
  const stats: Array<{ value: string; label: string; color: string }> = [
    {
      value: sim.agent_count == null ? '—' : String(sim.agent_count),
      label: 'People in the room',
      color: '#286cf0', // all three stat numerals one color — landing stat-band rule
    },
    { value: String(sim.max_rounds), label: 'Rounds', color: '#286cf0' },
    { value: String(sim.platforms?.length ?? 0), label: 'Platforms', color: '#286cf0' },
  ];

  const isIdle = IDLE_STATUSES.includes(sim.status);
  const isRunning = ACTIVE_STATUSES.includes(sim.status);
  // `isFinished` rather than a hand-written list: the database holds both
  // `complete` and `completed`, and comparing strings here is how the same run
  // reads as finished on one page and unfinished on another.
  const isDone = isFinished(sim.status) || sim.status === 'stopped';

  return (
    <div className="p-8 max-w-4xl mx-auto">
      {/* Header */}
      <div className="flex items-start justify-between mb-6">
        <div>
          <h1 className="text-h1 text-saibyl-white">{sim.name}</h1>
          <p className="text-small mt-1 max-w-lg">{sim.prediction_goal}</p>
        </div>
        {/* Handed the collapsed spelling, so the badge cannot read "COMPLETED"
            on one load and "COMPLETE" on the next depending on which of the two
            values the row happens to hold. */}
        <StatusBadge status={isFinished(sim.status) ? 'complete' : sim.status} />
      </div>

      {/* Error */}
      {error && (
        <div className="mb-4 px-4 py-3 rounded-xl bg-saibyl-negative/10 border border-saibyl-negative/20 text-saibyl-negative text-sm">
          {error}
          <button onClick={() => setError('')} className="ml-3 underline">dismiss</button>
        </div>
      )}

      {/* Server error from failed simulation */}
      {sim.status === 'failed' && sim.error_message && (
        <div className="mb-4 px-4 py-3 rounded-xl bg-saibyl-negative/10 border border-saibyl-negative/20 text-sm">
          <p className="text-saibyl-negative font-medium mb-1">This run failed</p>
          <p className="text-saibyl-muted font-mono text-[12px]">{sim.error_message}</p>
        </div>
      )}

      {/* Stats */}
      <div
        className={`grid grid-cols-1 sm:grid-cols-3 gap-4 ${
          sim.agent_count == null ? 'mb-3' : 'mb-6'
        }`}
      >
        {stats.map((s, i) => (
          <motion.div
            key={s.label}
            initial={{ opacity: 0, y: 16 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.35, delay: i * 0.06 }}
            className="glass rounded-2xl p-4 text-center"
          >
            <div className="text-2xl font-display font-bold" style={{ color: s.color }}>{s.value}</div>
            <div className="text-[11px] text-saibyl-muted mt-1">{s.label}</div>
          </motion.div>
        ))}
      </div>

      {/* The dash above, said in words. A reader should not have to work out
          what an em-dash in a number slot means. */}
      {sim.agent_count == null && (
        <p className="text-[12px] text-saibyl-muted mb-6">
          Nobody has been put in the room yet — that happens when you start the run.
        </p>
      )}

      {/* The messages being tested — only while the run can still be changed.
          Once it starts they freeze, because the whole claim of the comparison
          is that the only thing that differed was the wording. */}
      {isIdle && !running && (
        <div className="glass rounded-2xl p-6 mb-6">
          <p className="text-[15px] font-medium text-saibyl-platinum mb-1">
            Test more than one message
          </p>
          <p className="text-[12px] text-saibyl-muted mb-4">
            Write two or more versions and the same people react to each one, in
            separate rooms that never see each other. Whatever differs in the
            results is down to your wording rather than to who happened to be
            listening. Leave this empty to test a single message.
          </p>
          <VariantSetup
            key={variantSetupKey}
            simulationId={id!}
            onSavedChange={setVariantsWithCopy}
          />
        </div>
      )}

      {/* Primary Action */}
      <div className="glass rounded-2xl p-6 mb-6">
        {isIdle && !running && (
          <div className="space-y-5">
            <div className="flex items-center justify-between gap-4">
              <div>
                <p className="text-[15px] font-medium text-saibyl-platinum">Ready to go</p>
                <p className="text-[12px] text-saibyl-muted mt-0.5">
                  We&rsquo;ll build the room and put your message in front of it on{' '}
                  {(sim.platforms || []).map((p) => PLATFORM_NAMES[p] || p).join(' + ')}.
                </p>
              </div>
              {/* Never a greyed rectangle explained only by a hover title — that
                  is no explanation at all on a touch screen and invisible in a
                  screenshot. When the run genuinely cannot start, the button is
                  not rendered and the block below says why in a sentence and
                  carries the way out. */}
              {!variantShortfall && (
                <button
                  onClick={handleRunNow}
                  className="px-8 py-3 rounded-xl bg-saibyl-blue text-white font-semibold text-sm transition-all hover:bg-saibyl-gold-hover hover:-translate-y-0.5 hover:shadow-[0_10px_24px_rgba(40,108,240,0.20)] shrink-0"
                >
                  Start the run →
                </button>
              )}
            </div>

            {variantShortfall && variantsWithCopy !== null && (
              <div className="rounded-2xl border border-saibyl-warning/30 bg-saibyl-warning/[0.08] p-4">
                <p className="flex items-center gap-2 text-[13px] font-semibold text-saibyl-warning">
                  <AlertTriangle className="w-4 h-4 shrink-0" />
                  This run can&rsquo;t start yet
                </p>
                <p className="text-[12px] text-saibyl-silver mt-1.5 leading-relaxed">
                  You set this up to test {configuredVariants} different messages, but only{' '}
                  {variantsWithCopy} of them {variantsWithCopy === 1 ? 'has' : 'have'} anything
                  written. Each message is a whole run of its own — the same people react to
                  each one — so starting now would charge you for{' '}
                  {configuredVariants - variantsWithCopy} run
                  {configuredVariants - variantsWithCopy === 1 ? '' : 's'} that would never
                  happen.
                </p>
                <p className="text-[12px] text-saibyl-silver mt-2 leading-relaxed">
                  Write the missing ones above and save, or:
                </p>
                <button
                  onClick={handleResetToSingleArena}
                  disabled={variantResetting}
                  className="mt-3 px-4 py-2 rounded-lg text-[12px] font-medium bg-saibyl-gold text-saibyl-void hover:bg-saibyl-gold-hover disabled:opacity-50 transition-colors"
                >
                  {variantResetting
                    ? 'Switching…'
                    : 'Just test one message instead'}
                </button>
              </div>
            )}

            {/*
              Priced from the messages that would actually run, not from the
              number the configurator sold. Quoting the selected count leaves
              the price reading 4x on a run the server refuses, which is the
              same disagreement between price shown and price charged that the
              guard exists to prevent.

              Not rendered before the room exists: `agent_count` is null until
              the prepare pass has built it, and substituting a zero would quote
              a run of nobody.
            */}
            {sim.agent_count != null && (
              <RunConfigurator
                shape={{
                  agent_count: sim.agent_count,
                  rounds: sim.max_rounds,
                  platforms: Math.max(sim.platforms?.length ?? 1, 1),
                  variants: arenasThatWouldRun,
                  depth: toDepth(sim.depth),
                }}
                platformCount={sim.platforms?.length ?? 1}
                onChange={() => {}}
                readOnly
              />
            )}
          </div>
        )}

        {(running || isRunning) && (
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-4">
              <div className="animate-spin rounded-full h-6 w-6 border-b-2 border-saibyl-gold" />
              <div>
                <p className="text-[15px] font-medium text-saibyl-platinum">
                  {runStatus || `${runStateWord(sim.status)}…`}
                </p>
                <p className="text-[12px] text-saibyl-muted mt-0.5">
                  This takes a few minutes — longer with more people and more rounds.
                  You can leave this page; it keeps going.
                </p>
              </div>
            </div>
            <button onClick={handleStop} className="glass glass-hover px-4 py-2 rounded-lg text-saibyl-negative text-sm font-medium">
              Stop it
            </button>
          </div>
        )}

        {isDone && (
          <div className="flex items-center justify-between gap-4">
            <div>
              {/* Never `sim.status` raw — the column holds both `complete` and
                  `completed`, which is how this line read differently between
                  two loads of the same finished run. */}
              <p className="text-[15px] font-medium text-saibyl-positive">
                {runStateWord(sim.status)}
              </p>
              <p className="text-[12px] text-saibyl-muted mt-0.5">
                {sim.completed_at
                  ? `Finished ${new Date(sim.completed_at).toLocaleString()}. Everything they said is written up for you.`
                  : 'Everything they said is written up for you.'}
              </p>
            </div>
            {/* The one gold button on this page. It is what a founder came here
                for, and nothing else on the screen is allowed to compete with
                it — the panel further down that scores a run against real-world
                results is deliberately quieter, because reading the write-up
                comes first and the scoring needs a number you can only have
                after you have launched. */}
            <Link
              to={`/app/simulations/${id}/report`}
              className="px-6 py-2.5 rounded-xl bg-saibyl-blue text-white font-semibold text-sm hover:bg-saibyl-gold-hover transition-all hover:-translate-y-0.5 shrink-0"
            >
              Read what they said →
            </Link>
          </div>
        )}
      </div>

      {/* Live Event Feed */}
      {events.length > 0 && (
        <div className="glass rounded-2xl p-6 mb-6">
          <div className="flex items-center justify-between mb-4">
            {/* "the latest N", not "N" — this list is one page of at most 50,
                so calling the number a total would be a count we never asked
                the server for. */}
            <h2 className="text-[11px] font-mono text-saibyl-muted uppercase tracking-widest">
              The latest {events.length} things they said
            </h2>
            {(isRunning || running) && (
              <span className="flex items-center gap-1.5 text-[11px] text-saibyl-positive">
                <span className="w-1.5 h-1.5 rounded-full bg-saibyl-positive animate-pulse" />
                Still coming in…
              </span>
            )}
          </div>
          <div className="space-y-2 max-h-[500px] overflow-y-auto">
            {events.slice().reverse().map((evt, i) => {
              const content = String(evt.content || '');
              const sentiment = Number((evt.metadata as Record<string, unknown>)?.sentiment || 0);
              const sentColor = sentiment > 0.2 ? 'border-saibyl-positive/30' : sentiment < -0.2 ? 'border-saibyl-negative/30' : 'border-saibyl-border';
              return (
                <div key={i} className={`p-3 rounded-lg bg-[#14294a]/[0.02] border-l-2 ${sentColor}`}>
                  <div className="flex items-center gap-2 mb-1">
                    <span className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-saibyl-gold/15 text-saibyl-gold">{String(evt.platform)}</span>
                    <span className="text-[10px] font-mono text-saibyl-muted">R{String(evt.round_number)}</span>
                    <span className="text-[11px] text-saibyl-muted ml-auto">
                      how they took it: <span className={sentiment > 0.2 ? 'text-saibyl-positive' : sentiment < -0.2 ? 'text-saibyl-negative' : 'text-saibyl-muted'}>{sentiment.toFixed(2)}</span>
                    </span>
                  </div>
                  <p className="text-[13px] text-saibyl-platinum leading-relaxed">{content}</p>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* Agent Interview Panel */}
      {agents.length > 0 && (
        <div className="glass rounded-2xl p-6 mb-6">
          <h2 className="text-[11px] font-mono text-saibyl-muted uppercase tracking-widest mb-4">
            Ask them a question {isRunning && <span className="text-saibyl-positive ml-2">Live</span>}
          </h2>
          <div className="flex gap-3 mb-4">
            <select
              value={selectedAgentId}
              onChange={(e) => setSelectedAgentId(e.target.value)}
              className="flex-shrink-0 w-48 rounded-xl px-3 py-2 text-[13px] bg-white border border-saibyl-border-light text-saibyl-ink focus:outline-none focus:border-saibyl-blue focus:ring-2 focus:ring-saibyl-blue/20"
              style={{ colorScheme: 'light' }}
            >
              <option value="">Ask the first five</option>
              {agents.map((a) => (
                <option key={a.id} value={a.id}>
                  {a.profile?.display_name || a.username} — {a.profile?.persona_type || 'agent'}
                </option>
              ))}
            </select>
            <input
              type="text"
              value={interviewPrompt}
              onChange={(e) => setInterviewPrompt(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && handleInterview()}
              placeholder="e.g. What would make you buy this?"
              className="flex-1 rounded-xl px-4 py-2 text-[13px] bg-white border border-saibyl-border-light text-saibyl-ink placeholder:text-saibyl-muted/70 focus:outline-none focus:border-saibyl-blue focus:ring-2 focus:ring-saibyl-blue/20"
            />
            <button
              onClick={handleInterview}
              disabled={interviewLoading || !interviewPrompt.trim()}
              className="px-5 py-2 rounded-lg bg-saibyl-gold text-white text-[13px] font-medium hover:bg-saibyl-gold-hover disabled:opacity-50 transition-all"
            >
              {interviewLoading ? 'Asking…' : 'Ask'}
            </button>
          </div>
          {interviewResponses.length > 0 && (
            <div className="space-y-3 max-h-[400px] overflow-y-auto">
              {interviewResponses.map((r, i) => (
                <div key={i} className="p-3 rounded-lg bg-saibyl-elevated border border-saibyl-border">
                  <div className="flex items-center gap-2 mb-1.5">
                    <span className="text-[12px] font-medium text-saibyl-platinum">{r.agent}</span>
                    <span className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-saibyl-gold/15 text-saibyl-gold">{r.persona}</span>
                    <span className="text-[10px] font-mono text-saibyl-muted ml-auto">
                      how they took it: <span className={r.sentiment > 0.2 ? 'text-saibyl-positive' : r.sentiment < -0.2 ? 'text-saibyl-negative' : 'text-saibyl-muted'}>{r.sentiment.toFixed(2)}</span>
                    </span>
                  </div>
                  <p className="text-[13px] text-saibyl-platinum/80 leading-relaxed">{r.response}</p>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/*
        Scoring this run against reality.

        Two things were wrong here and both came from the same mistake — the
        screen described a capability the server does not have. `POST
        /accuracy/score` does exactly one thing: it compares what this run
        predicted against a figure *you* report, and it refuses outright
        (HTTP 400) if that figure is missing. It cannot "analyse predictions"
        on its own.

        So the heading no longer promises that, the number is no longer hidden
        behind a disclosure triangle labelled "(optional)" — it is required,
        and calling it optional is what made the button look broken — and the
        button is no longer gold. Reading the write-up is the thing a founder
        came here for; this is for weeks later, after they have launched.
      */}
      {isDone && (
        <div className="glass rounded-2xl p-6 mb-6">
          <h2 className="text-[11px] font-mono text-saibyl-muted uppercase tracking-widest mb-1">
            Already launched?
          </h2>
          {!accuracyResult ? (
            <div className="space-y-4">
              <p className="text-[13px] text-saibyl-muted leading-relaxed max-w-2xl">
                Tell us how it actually went and we&rsquo;ll show you how close this run
                came. You need to have put the thing in front of real people first —
                there is nothing to compare against until then.
              </p>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                <div>
                  <label className="block text-[12px] text-saibyl-silver mb-1.5">
                    How did people actually take it?
                  </label>
                  <input
                    type="number"
                    step="0.1"
                    min="-1"
                    max="1"
                    value={actualSentiment}
                    onChange={(e) => setActualSentiment(e.target.value)}
                    placeholder="e.g. 0.4"
                    className="w-full rounded-xl px-3 py-2 text-[13px] bg-white border border-saibyl-border-light text-saibyl-ink placeholder:text-saibyl-muted/70 focus:outline-none focus:border-saibyl-blue focus:ring-2 focus:ring-saibyl-blue/20"
                  />
                  <p className="text-[11px] text-saibyl-muted/80 mt-1.5 leading-relaxed">
                    Your own read, as a number from &minus;1 to 1. &minus;1 is everyone
                    hated it, 0 is nobody cared either way, 1 is everyone loved it. A
                    rough judgement is fine — we need it to have anything to compare
                    against.
                  </p>
                </div>
                <div>
                  <label className="block text-[12px] text-saibyl-silver mb-1.5">
                    What actually happened?
                  </label>
                  <input
                    type="text"
                    value={actualNotes}
                    onChange={(e) => setActualNotes(e.target.value)}
                    placeholder="e.g. 40 signups, but three people asked about the price"
                    className="w-full rounded-xl px-3 py-2 text-[13px] bg-white border border-saibyl-border-light text-saibyl-ink placeholder:text-saibyl-muted/70 focus:outline-none focus:border-saibyl-blue focus:ring-2 focus:ring-saibyl-blue/20"
                  />
                  <p className="text-[11px] text-saibyl-muted/80 mt-1.5 leading-relaxed">
                    Optional. Anything you write here goes into the write-up of what
                    the run got right and wrong.
                  </p>
                </div>
              </div>

              {/*
                It does not fire without the number.

                It used to. The endpoint 400s without `actual_sentiment`, the
                page sent `null` whenever the field was blank, and the failure
                was swallowed - so the founder pressed a button, nothing
                happened, and nothing said why. Twenty-two seconds of staring
                at an unchanged panel was the reported experience.

                Not disabled, either: a grey rectangle is the same silence with
                a different colour. When there is no number the control is
                replaced by the sentence explaining what it needs, which is the
                same rule the rail runs on.
              */}
              {!hasSentiment ? (
                <p className="text-[12.5px] text-saibyl-muted leading-relaxed">
                  Put in how it actually went, above, and this can compare the
                  two. Without that number there is nothing to score the run
                  against.
                </p>
              ) : (
              <button
                onClick={handleScoreAccuracy}
                className="px-5 py-2 rounded-xl border border-saibyl-gold/40 text-saibyl-gold text-[13px] font-medium hover:bg-saibyl-gold/10 transition-colors"
              >
                {scoringLoading ? 'Working it out…' : 'Score this run against what happened'}
              </button>
              )}

              {/* The server's own sentence. This used to be discarded, which is
                  why pressing the button appeared to do nothing at all. */}
              {scoringError && (
                <p className="text-[12px] text-saibyl-negative leading-relaxed">
                  {scoringError}
                </p>
              )}
            </div>
          ) : (
            <div className="space-y-4">
              <div className="grid grid-cols-3 gap-4">
                <div className="text-center p-4 rounded-xl bg-saibyl-elevated border border-saibyl-border">
                  <div className="text-2xl font-display font-bold text-saibyl-gold">{(accuracyResult.accuracy_score * 100).toFixed(1)}%</div>
                  <div className="text-[11px] text-saibyl-muted mt-1">How close we got</div>
                </div>
                <div className="text-center p-4 rounded-xl bg-saibyl-elevated border border-saibyl-border">
                  <div className="text-2xl font-display font-bold text-saibyl-blue">{accuracyResult.predicted_sentiment.toFixed(3)}</div>
                  <div className="text-[11px] text-saibyl-muted mt-1">What we said would happen</div>
                </div>
                <div className="text-center p-4 rounded-xl bg-saibyl-elevated border border-saibyl-border">
                  <div className="text-2xl font-display font-bold text-saibyl-positive">{accuracyResult.actual_sentiment.toFixed(3)}</div>
                  <div className="text-[11px] text-saibyl-muted mt-1">What you told us happened</div>
                </div>
              </div>
              <div className="p-4 rounded-xl bg-saibyl-elevated border border-saibyl-border">
                <h3 className="text-[12px] font-medium text-saibyl-platinum mb-2">What we got right and wrong</h3>
                <p className="text-[13px] text-saibyl-muted leading-relaxed whitespace-pre-wrap">{accuracyResult.analysis}</p>
              </div>
              <button onClick={() => { setAccuracyResult(null); setScoringError(''); }} className="text-[12px] text-saibyl-gold hover:underline">Try that again with different numbers</button>
            </div>
          )}
        </div>
      )}

      {/* Details */}
      <div className="glass rounded-2xl p-6">
        <h2 className="text-[11px] font-mono text-saibyl-muted uppercase tracking-widest mb-4">How this run was set up</h2>
        <dl className="space-y-3">
          {[
            ['Set up', new Date(sim.created_at).toLocaleString()],
            ['Platforms', (sim.platforms || []).map((p) => PLATFORM_NAMES[p] || p).join(', ') || 'None picked'],
            ['Groups of buyers', (sim.persona_pack_ids || []).length > 0 ? sim.persona_pack_ids.join(', ') : 'None saved — worked out fresh for this run'],
            // A dash, not a zero. `agent_count` is null until the room has been
            // built, and "0" would state that the run had nobody in it.
            ['People in the room', sim.agent_count == null ? 'Not built yet' : String(sim.agent_count)],
            ['Rounds', String(sim.max_rounds)],
            ['Messages tested', String(sim.variants ?? 1)],
          ].map(([label, value]) => (
            <div key={label} className="flex items-start gap-4 py-1.5 border-b border-saibyl-border last:border-0">
              <dt className="w-40 shrink-0 text-saibyl-muted text-[12px]">{label}</dt>
              <dd className="text-saibyl-platinum text-[13px]">{value}</dd>
            </div>
          ))}
        </dl>
      </div>
    </div>
  );
}
