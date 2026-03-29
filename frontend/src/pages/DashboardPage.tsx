import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import api from '@/lib/api';

interface Simulation {
  id: string;
  name: string;
  status: string;
  created_at: string;
}

interface BillingStatus {
  plan: string;
  simulations_used: number;
  simulations_limit: number;
  agents_used: number;
  agents_limit: number;
}

const statusColor: Record<string, string> = {
  draft: 'bg-gray-200 text-saibyl-platinum',
  preparing: 'bg-yellow-100 text-yellow-800',
  ready: 'bg-blue-100 text-blue-800',
  running: 'bg-green-100 text-green-800',
  completed: 'bg-emerald-100 text-emerald-800',
  failed: 'bg-red-100 text-red-800',
};

export default function DashboardPage() {
  const [sims, setSims] = useState<Simulation[]>([]);
  const [billing, setBilling] = useState<BillingStatus | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    Promise.all([
      api.get('/simulations', { params: { limit: 5 } }),
      api.get('/billing/status'),
    ])
      .then(([simRes, billRes]) => {
        setSims(simRes.data.items || simRes.data);
        setBilling(billRes.data);
      })
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  if (loading) {
    return <div className="p-8 text-center text-saibyl-muted">Loading dashboard...</div>;
  }

  const usagePct = billing
    ? Math.round((billing.simulations_used / Math.max(billing.simulations_limit, 1)) * 100)
    : 0;

  return (
    <div className="p-6 max-w-5xl mx-auto space-y-8 bg-saibyl-void">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold text-saibyl-platinum">Dashboard</h1>
        <Link
          to="/app/simulations/new"
          className="bg-saibyl-indigo text-white px-4 py-2 rounded-lg hover:bg-[#4B4FDE] transition"
        >
          + New Simulation
        </Link>
      </div>

      {/* Usage */}
      {billing && (
        <div className="bg-saibyl-deep rounded-2xl p-6 border border-saibyl-border">
          <h2 className="text-lg font-semibold text-saibyl-platinum mb-3">Usage ({billing.plan} plan)</h2>
          <div className="mb-2 text-sm text-saibyl-muted">
            Simulations: {billing.simulations_used} / {billing.simulations_limit}
          </div>
          <div className="w-full bg-saibyl-surface rounded-full h-3 mb-4">
            <div
              className="bg-saibyl-indigo h-3 rounded-full transition-all"
              style={{ width: `${Math.min(usagePct, 100)}%` }}
            />
          </div>
          <div className="text-sm text-saibyl-muted">
            Agents: {billing.agents_used} / {billing.agents_limit}
          </div>
        </div>
      )}

      {/* Recent Simulations */}
      <div className="bg-saibyl-deep rounded-2xl p-6 border border-saibyl-border">
        <h2 className="text-lg font-semibold text-saibyl-platinum mb-4">Recent Simulations</h2>
        {sims.length === 0 ? (
          <p className="text-saibyl-muted">No simulations yet. Create your first one!</p>
        ) : (
          <ul className="divide-y divide-saibyl-border">
            {sims.map((sim) => (
              <li key={sim.id} className="py-3 flex items-center justify-between">
                <Link to={`/app/simulations/${sim.id}`} className="text-saibyl-indigo hover:underline font-medium">
                  {sim.name}
                </Link>
                <span className={`text-xs px-2 py-1 rounded-full ${statusColor[sim.status] || 'bg-saibyl-deep'}`}>
                  {sim.status}
                </span>
              </li>
            ))}
          </ul>
        )}
        {sims.length > 0 && (
          <Link to="/app/simulations" className="block mt-4 text-sm text-saibyl-indigo hover:underline">
            View all simulations
          </Link>
        )}
      </div>
    </div>
  );
}
