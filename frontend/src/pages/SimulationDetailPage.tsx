import { useEffect, useState } from 'react';
import { useParams, Link } from 'react-router-dom';
import api from '@/lib/api';

interface Simulation {
  id: string;
  name: string;
  status: string;
  prediction_goal: string;
  platforms: string[];
  rounds: number;
  ab_enabled: boolean;
  agent_count: number;
  event_count: number;
  created_at: string;
  project_id: string;
  project_name?: string;
}

const statusColor: Record<string, string> = {
  draft: 'bg-gray-200 text-saibyl-platinum',
  preparing: 'bg-yellow-100 text-yellow-800',
  ready: 'bg-blue-100 text-blue-800',
  running: 'bg-green-100 text-green-800',
  completed: 'bg-emerald-100 text-emerald-800',
  failed: 'bg-red-100 text-red-800',
};

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

  if (loading) return <div className="p-8 text-center text-saibyl-muted">Loading simulation...</div>;
  if (!sim) return <div className="p-8 text-center text-red-500">Simulation not found.</div>;

  return (
    <div className="p-6 max-w-4xl mx-auto bg-saibyl-void">
      <div className="flex items-start justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold text-saibyl-platinum">{sim.name}</h1>
          <p className="text-saibyl-muted mt-1">{sim.prediction_goal}</p>
        </div>
        <span className={`text-sm px-3 py-1 rounded-full ${statusColor[sim.status] || 'bg-saibyl-deep'}`}>
          {sim.status}
        </span>
      </div>

      {/* Info Grid */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 mb-6">
        <div className="bg-saibyl-deep rounded-2xl p-4 text-center border border-saibyl-border">
          <div className="text-2xl font-bold text-saibyl-indigo">{sim.agent_count ?? 0}</div>
          <div className="text-xs text-saibyl-muted mt-1">Agents</div>
        </div>
        <div className="bg-saibyl-deep rounded-2xl p-4 text-center border border-saibyl-border">
          <div className="text-2xl font-bold text-saibyl-indigo">{sim.event_count ?? 0}</div>
          <div className="text-xs text-saibyl-muted mt-1">Events</div>
        </div>
        <div className="bg-saibyl-deep rounded-2xl p-4 text-center border border-saibyl-border">
          <div className="text-2xl font-bold text-saibyl-indigo">{sim.rounds}</div>
          <div className="text-xs text-saibyl-muted mt-1">Rounds</div>
        </div>
        <div className="bg-saibyl-deep rounded-2xl p-4 text-center border border-saibyl-border">
          <div className="text-2xl font-bold text-saibyl-indigo">{sim.platforms?.length ?? 0}</div>
          <div className="text-xs text-saibyl-muted mt-1">Platforms</div>
        </div>
      </div>

      {/* Actions */}
      <div className="flex flex-wrap gap-3 mb-6">
        {(sim.status === 'draft' || sim.status === 'failed') && (
          <button
            onClick={() => doAction('prepare')}
            disabled={!!actionLoading}
            className="bg-yellow-500 text-white px-4 py-2 rounded-lg hover:bg-yellow-600 disabled:opacity-50 transition"
          >
            {actionLoading === 'prepare' ? 'Preparing...' : 'Prepare'}
          </button>
        )}
        {sim.status === 'ready' && (
          <button
            onClick={() => doAction('start')}
            disabled={!!actionLoading}
            className="bg-green-600 text-white px-4 py-2 rounded-lg hover:bg-green-700 disabled:opacity-50 transition"
          >
            {actionLoading === 'start' ? 'Starting...' : 'Start'}
          </button>
        )}
        {sim.status === 'running' && (
          <>
            <button
              onClick={() => doAction('stop')}
              disabled={!!actionLoading}
              className="bg-red-600 text-white px-4 py-2 rounded-lg hover:bg-red-700 disabled:opacity-50 transition"
            >
              {actionLoading === 'stop' ? 'Stopping...' : 'Stop'}
            </button>
            <Link
              to={`/app/simulations/${id}/run`}
              className="bg-saibyl-indigo text-white px-4 py-2 rounded-lg hover:bg-[#4B4FDE] transition"
            >
              Live View
            </Link>
          </>
        )}
        {sim.status === 'completed' && (
          <Link
            to={`/app/simulations/${id}/report`}
            className="bg-saibyl-indigo text-white px-4 py-2 rounded-lg hover:bg-[#4B4FDE] transition"
          >
            View Report
          </Link>
        )}
        {sim.ab_enabled && sim.status === 'completed' && (
          <Link
            to={`/app/simulations/${id}/compare`}
            className="border border-saibyl-border-active text-saibyl-indigo px-4 py-2 rounded-lg hover:bg-saibyl-elevated transition"
          >
            A/B Comparison
          </Link>
        )}
      </div>

      {/* Details */}
      <div className="bg-saibyl-deep rounded-2xl p-6 border border-saibyl-border">
        <h2 className="text-lg font-semibold text-saibyl-platinum mb-3">Details</h2>
        <dl className="text-sm space-y-2">
          <div className="flex"><dt className="w-32 text-saibyl-muted">Created:</dt><dd className="text-saibyl-platinum">{new Date(sim.created_at).toLocaleString()}</dd></div>
          <div className="flex"><dt className="w-32 text-saibyl-muted">Platforms:</dt><dd className="text-saibyl-platinum">{sim.platforms?.join(', ') || 'N/A'}</dd></div>
          <div className="flex"><dt className="w-32 text-saibyl-muted">A/B Testing:</dt><dd className="text-saibyl-platinum">{sim.ab_enabled ? 'Enabled' : 'Disabled'}</dd></div>
        </dl>
      </div>
    </div>
  );
}
