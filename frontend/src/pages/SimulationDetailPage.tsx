import { useEffect, useState, useCallback } from 'react';
import { useParams, Link } from 'react-router-dom';
import { motion } from 'framer-motion';
import api from '@/lib/api';
import { PLATFORM_NAMES, TERMINAL_STATUSES, ACTIVE_STATUSES, IDLE_STATUSES } from '@/lib/constants';
import StatusBadge from '@/components/StatusBadge';

interface Simulation {
  id: string;
  name: string;
  status: string;
  prediction_goal: string;
  platforms: string[];
  max_rounds: number;
  is_ab_test: boolean;
  agent_count: number;
  persona_pack_ids: string[];
  created_at: string;
  completed_at: string | null;
  project_id: string;
  error_message: string | null;
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

  // Accuracy scoring state
  const [actualSentiment, setActualSentiment] = useState('');
  const [actualNotes, setActualNotes] = useState('');
  const [scoringLoading, setScoringLoading] = useState(false);
  const [accuracyResult, setAccuracyResult] = useState<{ accuracy_score: number; predicted_sentiment: number; actual_sentiment: number; analysis: string } | null>(null);

  // Interview panel state
  const [agents, setAgents] = useState<Record<string, unknown>[]>([]);
  const [selectedAgentId, setSelectedAgentId] = useState('');
  const [interviewPrompt, setInterviewPrompt] = useState('');
  const [interviewLoading, setInterviewLoading] = useState(false);
  const [interviewResponses, setInterviewResponses] = useState<{ agent: string; persona: string; response: string; sentiment: number }[]>([]);

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
          agent_ids: agents.slice(0, 5).map((a: any) => a.id),
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
    } catch (err: any) {
      const msg = err.response?.data?.detail || 'Interview failed';
      setInterviewResponses((prev) => [...prev, { agent: 'System', persona: 'error', response: msg, sentiment: 0 }]);
    } finally {
      setInterviewLoading(false);
    }
  };

  const handleScoreAccuracy = async () => {
    if (!id) return;
    setScoringLoading(true);
    try {
      const { data } = await api.post('/accuracy/score', {
        simulation_id: id,
        actual_sentiment: actualSentiment ? parseFloat(actualSentiment) : null,
        notes: actualNotes || null,
      });
      setAccuracyResult(data);
    } catch { /* ignore */ } finally {
      setScoringLoading(false);
    }
  };

  // Poll while running or preparing
  useEffect(() => {
    if (!sim || !['running', 'preparing'].includes(sim.status)) return;
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
    // Auto-start
    setRunning(true);
    setRunStatus('Starting simulation...');
    api.post(`/simulations/${id}/start`).then(() => {
      setRunStatus('Simulation running...');
      loadSim();
    }).catch(() => {
      setRunning(false);
      setRunStatus('');
    });
  }, [sim?.status, id, eventCount]); // eslint-disable-line react-hooks/exhaustive-deps

  // One-click: prepare + wait for ready + start + poll
  async function handleRunNow() {
    if (!id) return;
    setRunning(true);
    setError('');
    setRunStatus('Preparing agents...');
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
          setError('Agent preparation failed. Make sure you have at least one persona pack selected.');
          setRunning(false);
          setRunStatus('');
          return;
        }
      }
      if (!ready) {
        setError('Agent preparation timed out.');
        setRunning(false);
        setRunStatus('');
        return;
      }

      setRunStatus('Starting simulation...');
      await api.post(`/simulations/${id}/start`);
      setRunStatus('Simulation running — polling for updates...');
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
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to run simulation');
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
  if (!sim) return <div className="p-8 text-center text-saibyl-negative">Simulation not found.</div>;

  const stats = [
    { value: sim.agent_count ?? 0, label: 'Agents', color: '#5B5FEE' },
    { value: eventCount, label: 'Events', color: '#00D4FF' },
    { value: sim.max_rounds, label: 'Rounds', color: '#A78BFA' },
    { value: sim.platforms?.length ?? 0, label: 'Platforms', color: '#10B981' },
  ];

  const isIdle = IDLE_STATUSES.includes(sim.status);
  const isRunning = ACTIVE_STATUSES.includes(sim.status);
  const isDone = ['complete', 'completed', 'stopped'].includes(sim.status);

  return (
    <div className="p-8 max-w-4xl mx-auto">
      {/* Header */}
      <div className="flex items-start justify-between mb-6">
        <div>
          <h1 className="text-h1 text-saibyl-white">{sim.name}</h1>
          <p className="text-small mt-1 max-w-lg">{sim.prediction_goal}</p>
        </div>
        <StatusBadge status={sim.status} />
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
          <p className="text-saibyl-negative font-medium mb-1">Simulation failed</p>
          <p className="text-saibyl-muted font-mono text-[12px]">{sim.error_message}</p>
        </div>
      )}

      {/* Stats */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 mb-6">
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

      {/* Primary Action */}
      <div className="glass rounded-2xl p-6 mb-6">
        {isIdle && !running && (
          <div className="flex items-center justify-between">
            <div>
              <p className="text-[15px] font-medium text-saibyl-platinum">Ready to run</p>
              <p className="text-[12px] text-saibyl-muted mt-0.5">This will prepare agents and start the simulation on {(sim.platforms || []).map((p) => PLATFORM_NAMES[p] || p).join(' + ')}.</p>
            </div>
            <button
              onClick={handleRunNow}
              className="relative px-8 py-3 rounded-xl text-white font-semibold text-sm overflow-hidden transition-all hover:scale-[1.02]"
            >
              <div className="absolute inset-0 bg-gradient-to-r from-[#5B5FEE] to-[#00D4FF]" />
              <div className="absolute inset-0 animate-glow-pulse rounded-xl" />
              <span className="relative">Run Simulation →</span>
            </button>
          </div>
        )}

        {(running || isRunning) && (
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-4">
              <div className="animate-spin rounded-full h-6 w-6 border-b-2 border-saibyl-indigo" />
              <div>
                <p className="text-[15px] font-medium text-saibyl-platinum">
                  {runStatus || `Simulation ${sim.status}...`}
                </p>
                <p className="text-[12px] text-saibyl-muted mt-0.5">This may take a few minutes depending on agent count and rounds.</p>
              </div>
            </div>
            <button onClick={handleStop} className="glass glass-hover px-4 py-2 rounded-lg text-saibyl-negative text-sm font-medium">
              Stop
            </button>
          </div>
        )}

        {isDone && (
          <div className="flex items-center justify-between">
            <div>
              <p className="text-[15px] font-medium text-saibyl-positive">Simulation {sim.status}</p>
              <p className="text-[12px] text-saibyl-muted mt-0.5">
                {sim.completed_at ? `Completed ${new Date(sim.completed_at).toLocaleString()}` : 'Results available'}
              </p>
            </div>
            <div className="flex gap-3">
              <Link
                to={`/app/simulations/${id}/report`}
                className="relative px-6 py-2.5 rounded-xl text-white font-medium text-sm overflow-hidden transition-all hover:scale-[1.02]"
              >
                <div className="absolute inset-0 bg-gradient-to-r from-[#5B5FEE] to-[#00D4FF]" />
                <span className="relative">View Report →</span>
              </Link>
              <Link
                to={`/app/simulations/${id}/run`}
                className="glass glass-hover px-5 py-2.5 rounded-xl text-saibyl-platinum text-sm font-medium"
              >
                Live View
              </Link>
            </div>
          </div>
        )}
      </div>

      {/* Live Event Feed */}
      {events.length > 0 && (
        <div className="glass rounded-2xl p-6 mb-6">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-[11px] font-mono text-saibyl-muted uppercase tracking-widest">
              Live Feed — {events.length} events
            </h2>
            {(isRunning || running) && (
              <span className="flex items-center gap-1.5 text-[11px] text-saibyl-positive">
                <span className="w-1.5 h-1.5 rounded-full bg-saibyl-positive animate-pulse" />
                Updating...
              </span>
            )}
          </div>
          <div className="space-y-2 max-h-[500px] overflow-y-auto">
            {events.slice().reverse().map((evt, i) => {
              const content = String(evt.content || '');
              const sentiment = Number((evt.metadata as Record<string, unknown>)?.sentiment || 0);
              const sentColor = sentiment > 0.2 ? 'border-saibyl-positive/30' : sentiment < -0.2 ? 'border-saibyl-negative/30' : 'border-white/[0.04]';
              return (
                <div key={i} className={`p-3 rounded-lg bg-white/[0.02] border-l-2 ${sentColor}`}>
                  <div className="flex items-center gap-2 mb-1">
                    <span className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-saibyl-indigo/15 text-saibyl-indigo">{String(evt.platform)}</span>
                    <span className="text-[10px] font-mono text-saibyl-muted">R{String(evt.round_number)}</span>
                    <span className="text-[11px] text-saibyl-muted ml-auto">
                      sentiment: <span className={sentiment > 0.2 ? 'text-saibyl-positive' : sentiment < -0.2 ? 'text-saibyl-negative' : 'text-saibyl-muted'}>{sentiment.toFixed(2)}</span>
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
            Agent Interviews {isRunning && <span className="text-saibyl-positive ml-2">Live</span>}
          </h2>
          <div className="flex gap-3 mb-4">
            <select
              value={selectedAgentId}
              onChange={(e) => setSelectedAgentId(e.target.value)}
              className="flex-shrink-0 w-48 rounded-lg px-3 py-2 text-[13px] bg-[#0B1120] border border-white/[0.08] text-saibyl-platinum focus:outline-none focus:ring-2 focus:ring-saibyl-indigo/50"
              style={{ colorScheme: 'dark' }}
            >
              <option value="">All agents (top 5)</option>
              {agents.map((a: any) => (
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
              placeholder="Ask agents a question..."
              className="flex-1 rounded-lg px-4 py-2 text-[13px] bg-[#0B1120] border border-white/[0.08] text-saibyl-platinum placeholder-saibyl-muted/50 focus:outline-none focus:ring-2 focus:ring-saibyl-indigo/50"
            />
            <button
              onClick={handleInterview}
              disabled={interviewLoading || !interviewPrompt.trim()}
              className="px-5 py-2 rounded-lg bg-saibyl-indigo text-white text-[13px] font-medium hover:bg-[#4B4FDE] disabled:opacity-50 transition-all"
            >
              {interviewLoading ? 'Asking...' : 'Ask'}
            </button>
          </div>
          {interviewResponses.length > 0 && (
            <div className="space-y-3 max-h-[400px] overflow-y-auto">
              {interviewResponses.map((r, i) => (
                <div key={i} className="p-3 rounded-lg bg-white/[0.02] border border-white/[0.04]">
                  <div className="flex items-center gap-2 mb-1.5">
                    <span className="text-[12px] font-medium text-saibyl-platinum">{r.agent}</span>
                    <span className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-saibyl-indigo/15 text-saibyl-indigo">{r.persona}</span>
                    <span className="text-[10px] font-mono text-saibyl-muted ml-auto">
                      sentiment: <span className={r.sentiment > 0.2 ? 'text-saibyl-positive' : r.sentiment < -0.2 ? 'text-saibyl-negative' : 'text-saibyl-muted'}>{r.sentiment.toFixed(2)}</span>
                    </span>
                  </div>
                  <p className="text-[13px] text-saibyl-platinum/80 leading-relaxed">{r.response}</p>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Prediction Analysis */}
      {isDone && (
        <div className="glass rounded-2xl p-6 mb-6">
          <h2 className="text-[11px] font-mono text-saibyl-muted uppercase tracking-widest mb-4">Prediction Analysis</h2>
          {!accuracyResult ? (
            <div className="space-y-4">
              <div className="flex items-center justify-between">
                <p className="text-[13px] text-saibyl-muted">Analyze the simulation's predicted sentiment and outcomes.</p>
                <button
                  onClick={handleScoreAccuracy}
                  disabled={scoringLoading}
                  className="px-6 py-2.5 rounded-xl bg-saibyl-indigo text-white text-[13px] font-medium hover:bg-[#4B4FDE] disabled:opacity-50 transition-all shrink-0"
                >
                  {scoringLoading ? 'Analyzing...' : 'Analyze Predictions'}
                </button>
              </div>
              <details className="text-[12px] text-saibyl-muted">
                <summary className="cursor-pointer hover:text-saibyl-platinum transition-colors">Have real-world data to compare? (optional)</summary>
                <div className="grid grid-cols-2 gap-4 mt-3">
                  <div>
                    <label className="block text-[12px] text-saibyl-muted mb-1">Actual Sentiment (-1 to 1)</label>
                    <input
                      type="number"
                      step="0.1"
                      min="-1"
                      max="1"
                      value={actualSentiment}
                      onChange={(e) => setActualSentiment(e.target.value)}
                      placeholder="e.g. -0.3"
                      className="w-full rounded-lg px-3 py-2 text-[13px] bg-[#0B1120] border border-white/[0.08] text-saibyl-platinum focus:outline-none focus:ring-2 focus:ring-saibyl-indigo/50"
                    />
                  </div>
                  <div>
                    <label className="block text-[12px] text-saibyl-muted mb-1">Notes on actual outcome</label>
                    <input
                      type="text"
                      value={actualNotes}
                      onChange={(e) => setActualNotes(e.target.value)}
                      placeholder="What actually happened?"
                      className="w-full rounded-lg px-3 py-2 text-[13px] bg-[#0B1120] border border-white/[0.08] text-saibyl-platinum placeholder-saibyl-muted/50 focus:outline-none focus:ring-2 focus:ring-saibyl-indigo/50"
                    />
                  </div>
                </div>
              </details>
            </div>
          ) : (
            <div className="space-y-4">
              <div className="grid grid-cols-3 gap-4">
                <div className="text-center p-4 rounded-xl bg-white/[0.02] border border-white/[0.04]">
                  <div className="text-2xl font-display font-bold text-saibyl-indigo">{(accuracyResult.accuracy_score * 100).toFixed(1)}%</div>
                  <div className="text-[11px] text-saibyl-muted mt-1">Accuracy Score</div>
                </div>
                <div className="text-center p-4 rounded-xl bg-white/[0.02] border border-white/[0.04]">
                  <div className="text-2xl font-display font-bold text-saibyl-cyan">{accuracyResult.predicted_sentiment.toFixed(3)}</div>
                  <div className="text-[11px] text-saibyl-muted mt-1">Predicted Sentiment</div>
                </div>
                <div className="text-center p-4 rounded-xl bg-white/[0.02] border border-white/[0.04]">
                  <div className="text-2xl font-display font-bold text-saibyl-positive">{accuracyResult.actual_sentiment.toFixed(3)}</div>
                  <div className="text-[11px] text-saibyl-muted mt-1">Actual Sentiment</div>
                </div>
              </div>
              <div className="p-4 rounded-xl bg-white/[0.02] border border-white/[0.04]">
                <h3 className="text-[12px] font-medium text-saibyl-platinum mb-2">Analysis</h3>
                <p className="text-[13px] text-saibyl-muted leading-relaxed whitespace-pre-wrap">{accuracyResult.analysis}</p>
              </div>
              <button onClick={() => setAccuracyResult(null)} className="text-[12px] text-saibyl-indigo hover:underline">Re-score with different data</button>
            </div>
          )}
        </div>
      )}

      {/* Details */}
      <div className="glass rounded-2xl p-6">
        <h2 className="text-[11px] font-mono text-saibyl-muted uppercase tracking-widest mb-4">Details</h2>
        <dl className="space-y-3">
          {[
            ['Created', new Date(sim.created_at).toLocaleString()],
            ['Platforms', (sim.platforms || []).map((p) => PLATFORM_NAMES[p] || p).join(', ') || 'N/A'],
            ['Persona Packs', (sim.persona_pack_ids || []).length > 0 ? sim.persona_pack_ids.join(', ') : 'None'],
            ['Agents', String(sim.agent_count ?? 0)],
            ['Max Rounds', String(sim.max_rounds)],
            ['A/B Testing', sim.is_ab_test ? 'Enabled' : 'Disabled'],
          ].map(([label, value]) => (
            <div key={label} className="flex items-center gap-4 py-1.5 border-b border-white/[0.03] last:border-0">
              <dt className="w-28 text-saibyl-muted text-[12px]">{label}</dt>
              <dd className="text-saibyl-platinum text-[13px]">{value}</dd>
            </div>
          ))}
        </dl>
      </div>
    </div>
  );
}
