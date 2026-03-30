import { useEffect, useState, useCallback } from 'react';
import { useParams, Link } from 'react-router-dom';
import { motion } from 'framer-motion';
import api from '@/lib/api';
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

const PLATFORM_NAMES: Record<string, string> = {
  twitter_x: 'Twitter / X',
  reddit: 'Reddit',
  linkedin: 'LinkedIn',
  instagram: 'Instagram',
  hacker_news: 'Hacker News',
  discord: 'Discord',
  news_comments: 'News Comments',
  custom: 'Custom',
};

export default function SimulationDetailPage() {
  const { id } = useParams<{ id: string }>();
  const [sim, setSim] = useState<Simulation | null>(null);
  const [loading, setLoading] = useState(true);
  const [running, setRunning] = useState(false);
  const [runStatus, setRunStatus] = useState('');
  const [error, setError] = useState('');
  const [eventCount, setEventCount] = useState(0);
  const [events, setEvents] = useState<Record<string, unknown>[]>([]);

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

  // Poll while running or preparing
  useEffect(() => {
    if (!sim || !['running', 'preparing'].includes(sim.status)) return;
    const interval = setInterval(loadSim, 4000);
    return () => clearInterval(interval);
  }, [sim?.status, loadSim]);

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
          setError('Agent preparation failed. Make sure you have documents uploaded and an ontology generated, or select persona packs.');
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
          if (['complete', 'completed', 'failed', 'stopped'].includes(r.data.status)) {
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

  const isIdle = ['draft', 'ready', 'failed'].includes(sim.status);
  const isRunning = ['preparing', 'running'].includes(sim.status);
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

      {/* Details */}
      <div className="glass rounded-2xl p-6">
        <h2 className="text-[11px] font-mono text-saibyl-muted uppercase tracking-widest mb-4">Details</h2>
        <dl className="space-y-3">
          {[
            ['Created', new Date(sim.created_at).toLocaleString()],
            ['Platforms', (sim.platforms || []).map((p) => PLATFORM_NAMES[p] || p).join(', ') || 'N/A'],
            ['Persona Packs', (sim.persona_pack_ids || []).length > 0 ? sim.persona_pack_ids.join(', ') : 'None (ontology-based)'],
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
