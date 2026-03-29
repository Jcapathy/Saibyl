import { useEffect, useState } from 'react';
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
  event_count: number;
  created_at: string;
  project_id: string;
  project_name?: string;
}

export default function SimulationDetailPage() {
  const { id } = useParams<{ id: string }>();
  const [sim, setSim] = useState<Simulation | null>(null);
  const [loading, setLoading] = useState(true);
  const [actionLoading, setActionLoading] = useState('');

  useEffect(() => {
    api.get(`/simulations/${id}`)
      .then((res) => setSim(res.data))
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [id]);

  const doAction = async (action: string) => {
    setActionLoading(action);
    try {
      await api.post(`/simulations/${id}/${action}`);
      const res = await api.get(`/simulations/${id}`);
      setSim(res.data);
    } catch {
      // handle error
    } finally {
      setActionLoading('');
    }
  };

  if (loading) {
    return (
      <div className="p-6 max-w-4xl mx-auto space-y-4">
        <div className="h-8 w-64 rounded-xl bg-saibyl-deep animate-pulse" />
        <div className="grid grid-cols-4 gap-4">
          {[...Array(4)].map((_, i) => <div key={i} className="h-24 rounded-2xl bg-saibyl-deep animate-pulse" />)}
        </div>
      </div>
    );
  }
  if (!sim) return <div className="p-8 text-center text-saibyl-negative">Simulation not found.</div>;

  const stats = [
    { value: sim.agent_count ?? 0, label: 'Agents',    color: '#5B5FEE' },
    { value: sim.event_count ?? 0, label: 'Events',    color: '#00D4FF' },
    { value: sim.max_rounds,       label: 'Rounds',    color: '#A78BFA' },
    { value: sim.platforms?.length ?? 0, label: 'Platforms', color: '#10B981' },
  ];

  return (
    <div className="p-6 max-w-4xl mx-auto">
      {/* Header */}
      <div className="flex items-start justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold text-saibyl-platinum">{sim.name}</h1>
          {sim.prediction_goal && (
            <p className="text-saibyl-muted mt-1 text-sm max-w-lg">{sim.prediction_goal}</p>
          )}
        </div>
        <StatusBadge status={sim.status} />
      </div>

      {/* Stat Cards */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 mb-6">
        {stats.map((s, i) => (
          <motion.div
            key={s.label}
            initial={{ opacity: 0, y: 16 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.35, delay: i * 0.06 }}
            className="bg-saibyl-deep rounded-2xl p-4 text-center border border-white/[0.05] hover:border-white/[0.1] transition-colors"
          >
            <div className="text-2xl font-bold" style={{ color: s.color }}>{s.value}</div>
            <div className="text-xs text-saibyl-muted mt-1">{s.label}</div>
          </motion.div>
        ))}
      </div>

      {/* Actions */}
      <div className="flex flex-wrap gap-3 mb-6">
        {(sim.status === 'draft' || sim.status === 'failed') && (
          <button
            onClick={() => doAction('prepare')}
            disabled={!!actionLoading}
            className="bg-saibyl-indigo/20 border border-saibyl-indigo/30 text-saibyl-indigo px-4 py-2 rounded-xl text-sm font-medium hover:bg-saibyl-indigo/30 disabled:opacity-50 transition"
          >
            {actionLoading === 'prepare' ? 'Preparing...' : 'Prepare'}
          </button>
        )}
        {sim.status === 'ready' && (
          <button
            onClick={() => doAction('start')}
            disabled={!!actionLoading}
            className="bg-saibyl-positive/20 border border-saibyl-positive/30 text-saibyl-positive px-4 py-2 rounded-xl text-sm font-medium hover:bg-saibyl-positive/30 disabled:opacity-50 transition"
          >
            {actionLoading === 'start' ? 'Starting...' : '▶ Start'}
          </button>
        )}
        {sim.status === 'running' && (
          <>
            <button
              onClick={() => doAction('stop')}
              disabled={!!actionLoading}
              className="bg-saibyl-negative/20 border border-saibyl-negative/30 text-saibyl-negative px-4 py-2 rounded-xl text-sm font-medium hover:bg-saibyl-negative/30 disabled:opacity-50 transition"
            >
              {actionLoading === 'stop' ? 'Stopping...' : '■ Stop'}
            </button>
            <Link
              to={`/app/simulations/${id}/run`}
              className="bg-saibyl-indigo text-white px-4 py-2 rounded-xl text-sm font-medium hover:bg-[#4B4FDE] hover:shadow-[0_0_20px_rgba(91,95,238,0.3)] transition-all"
            >
              Live View →
            </Link>
          </>
        )}
        {sim.status === 'completed' && (
          <Link
            to={`/app/simulations/${id}/report`}
            className="bg-saibyl-indigo text-white px-4 py-2 rounded-xl text-sm font-medium hover:bg-[#4B4FDE] hover:shadow-[0_0_20px_rgba(91,95,238,0.3)] transition-all"
          >
            View Report →
          </Link>
        )}
        {sim.is_ab_test && sim.status === 'completed' && (
          <Link
            to={`/app/simulations/${id}/compare`}
            className="border border-saibyl-indigo/30 text-saibyl-indigo px-4 py-2 rounded-xl text-sm font-medium hover:bg-saibyl-elevated transition"
          >
            A/B Comparison
          </Link>
        )}
      </div>

      {/* Details */}
      <div className="bg-saibyl-deep rounded-2xl p-6 border border-white/[0.05]">
        <h2 className="text-[11px] font-semibold text-saibyl-muted uppercase tracking-widest mb-4">Details</h2>
        <dl className="space-y-3">
          <div className="flex">
            <dt className="w-32 text-saibyl-muted text-[12px]">Created</dt>
            <dd className="text-saibyl-platinum font-mono text-[12px]">{new Date(sim.created_at).toLocaleString()}</dd>
          </div>
          <div className="flex items-start">
            <dt className="w-32 text-saibyl-muted text-[12px] pt-0.5">Platforms</dt>
            <dd className="flex flex-wrap gap-1.5">
              {sim.platforms?.length ? sim.platforms.map((p) => (
                <span key={p} className="px-2 py-0.5 rounded-md bg-saibyl-indigo/10 text-saibyl-indigo border border-saibyl-indigo/15 font-mono text-[10px]">{p}</span>
              )) : <span className="text-saibyl-muted text-[12px]">N/A</span>}
            </dd>
          </div>
          <div className="flex">
            <dt className="w-32 text-saibyl-muted text-[12px]">A/B Testing</dt>
            <dd className={`text-[12px] font-medium ${sim.is_ab_test ? 'text-saibyl-positive' : 'text-saibyl-muted'}`}>
              {sim.is_ab_test ? 'Enabled' : 'Disabled'}
            </dd>
          </div>
        </dl>
      </div>
    </div>
  );
}
