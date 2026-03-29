import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { motion } from 'framer-motion';
import api from '@/lib/api';
import StatusBadge from '@/components/StatusBadge';

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

function Skeleton({ className }: { className: string }) {
  return <div className={`animate-pulse rounded-xl bg-saibyl-deep ${className}`} />;
}

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

  const simPct   = billing ? Math.round((billing.simulations_used / Math.max(billing.simulations_limit, 1)) * 100) : 0;
  const agentPct = billing ? Math.round((billing.agents_used / Math.max(billing.agents_limit, 1)) * 100) : 0;

  return (
    <div className="p-6 max-w-5xl mx-auto space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold text-saibyl-platinum">Dashboard</h1>
        <Link
          to="/app/simulations/new"
          className="relative inline-flex items-center gap-2 px-4 py-2 rounded-xl text-white font-medium text-sm overflow-hidden transition-all hover:scale-[1.02] hover:shadow-[0_0_20px_rgba(91,95,238,0.25)]"
        >
          <div className="absolute inset-0 bg-gradient-to-r from-saibyl-indigo to-[#4B8BEE]" />
          <span className="relative">+ New Simulation</span>
        </Link>
      </div>

      {loading ? (
        <div className="space-y-4">
          <div className="grid grid-cols-2 gap-4">
            <Skeleton className="h-32" />
            <Skeleton className="h-32" />
          </div>
          <Skeleton className="h-48" />
        </div>
      ) : (
        <>
          {/* Usage cards */}
          {billing && (
            <motion.div
              initial={{ opacity: 0, y: 16 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.35 }}
              className="grid grid-cols-1 sm:grid-cols-2 gap-4"
            >
              {/* Simulations usage */}
              <div className="bg-saibyl-deep rounded-2xl p-5 border border-white/[0.05]">
                <div className="flex items-center justify-between mb-3">
                  <div>
                    <p className="text-[11px] font-mono tracking-widest uppercase text-saibyl-muted">Simulations</p>
                    <p className="text-2xl font-bold text-saibyl-platinum mt-0.5">
                      {billing.simulations_used}
                      <span className="text-sm font-normal text-saibyl-muted ml-1">/ {billing.simulations_limit}</span>
                    </p>
                  </div>
                  <div className="w-10 h-10 rounded-xl bg-saibyl-indigo/10 flex items-center justify-center">
                    <svg className="w-5 h-5 text-saibyl-indigo" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M9.75 3.104v5.714a2.25 2.25 0 01-.659 1.591L5 14.5M9.75 3.104c-.251.023-.501.05-.75.082m.75-.082a24.301 24.301 0 014.5 0m0 0v5.714c0 .597.237 1.17.659 1.591L19.8 15.3M14.25 3.104c.251.023.501.05.75.082M19.8 15.3l-1.57.393A9.065 9.065 0 0112 15a9.065 9.065 0 00-6.23-.693L5 14.5" />
                    </svg>
                  </div>
                </div>
                <div className="w-full h-1.5 bg-white/[0.05] rounded-full overflow-hidden">
                  <motion.div
                    initial={{ width: 0 }}
                    animate={{ width: `${Math.min(simPct, 100)}%` }}
                    transition={{ duration: 0.8, ease: 'easeOut', delay: 0.2 }}
                    className="h-full rounded-full"
                    style={{ background: 'linear-gradient(90deg, #5B5FEE, #00D4FF)' }}
                  />
                </div>
                <p className="text-[11px] text-saibyl-muted mt-1.5">{simPct}% used</p>
              </div>

              {/* Agents usage */}
              <div className="bg-saibyl-deep rounded-2xl p-5 border border-white/[0.05]">
                <div className="flex items-center justify-between mb-3">
                  <div>
                    <p className="text-[11px] font-mono tracking-widest uppercase text-saibyl-muted">Agents</p>
                    <p className="text-2xl font-bold text-saibyl-platinum mt-0.5">
                      {billing.agents_used.toLocaleString()}
                      <span className="text-sm font-normal text-saibyl-muted ml-1">/ {billing.agents_limit.toLocaleString()}</span>
                    </p>
                  </div>
                  <div className="w-10 h-10 rounded-xl bg-saibyl-violet/10 flex items-center justify-center">
                    <svg className="w-5 h-5 text-saibyl-violet" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M18 18.72a9.094 9.094 0 003.741-.479 3 3 0 00-4.682-2.72m.94 3.198l.001.031c0 .225-.012.447-.037.666A11.944 11.944 0 0112 21c-2.17 0-4.207-.576-5.963-1.584A6.062 6.062 0 016 18.719m12 0a5.971 5.971 0 00-.941-3.197m0 0A5.995 5.995 0 0012 12.75a5.995 5.995 0 00-5.058 2.772m0 0a3 3 0 00-4.681 2.72 8.986 8.986 0 003.74.477m.94-3.197a5.971 5.971 0 00-.94 3.197M15 6.75a3 3 0 11-6 0 3 3 0 016 0zm6 3a2.25 2.25 0 11-4.5 0 2.25 2.25 0 014.5 0zm-13.5 0a2.25 2.25 0 11-4.5 0 2.25 2.25 0 014.5 0z" />
                    </svg>
                  </div>
                </div>
                <div className="w-full h-1.5 bg-white/[0.05] rounded-full overflow-hidden">
                  <motion.div
                    initial={{ width: 0 }}
                    animate={{ width: `${Math.min(agentPct, 100)}%` }}
                    transition={{ duration: 0.8, ease: 'easeOut', delay: 0.35 }}
                    className="h-full rounded-full"
                    style={{ background: 'linear-gradient(90deg, #A78BFA, #5B5FEE)' }}
                  />
                </div>
                <p className="text-[11px] text-saibyl-muted mt-1.5">{agentPct}% used · {billing.plan} plan</p>
              </div>
            </motion.div>
          )}

          {/* Recent Simulations */}
          <motion.div
            initial={{ opacity: 0, y: 16 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.35, delay: 0.1 }}
            className="bg-saibyl-deep rounded-2xl border border-white/[0.05] overflow-hidden"
          >
            <div className="px-5 py-4 border-b border-white/[0.04] flex items-center justify-between">
              <h2 className="font-semibold text-saibyl-platinum text-sm">Recent Simulations</h2>
              <Link to="/app/simulations" className="text-[12px] text-saibyl-indigo hover:text-saibyl-cyan transition-colors">
                View all →
              </Link>
            </div>

            {sims.length === 0 ? (
              <div className="py-12 text-center">
                <p className="text-saibyl-muted text-sm mb-4">No simulations yet</p>
                <Link to="/app/simulations/new" className="text-sm text-saibyl-indigo hover:text-saibyl-cyan transition-colors">
                  Create your first →
                </Link>
              </div>
            ) : (
              <ul>
                {sims.map((sim, i) => (
                  <li
                    key={sim.id}
                    className={`flex items-center justify-between px-5 py-3.5 hover:bg-white/[0.02] transition-colors ${i < sims.length - 1 ? 'border-b border-white/[0.03]' : ''}`}
                  >
                    <Link to={`/app/simulations/${sim.id}`} className="font-medium text-saibyl-platinum hover:text-saibyl-indigo transition-colors text-sm">
                      {sim.name}
                    </Link>
                    <div className="flex items-center gap-4">
                      <span className="font-mono text-[11px] text-saibyl-muted">
                        {new Date(sim.created_at).toLocaleDateString()}
                      </span>
                      <StatusBadge status={sim.status} />
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </motion.div>
        </>
      )}
    </div>
  );
}
