import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import api from '@/lib/api';
import StatusBadge from '@/components/StatusBadge';

interface Simulation {
  id: string;
  name: string;
  status: string;
  created_at: string;
  project_name?: string;
}

export default function SimulationsPage() {
  const [sims, setSims] = useState<Simulation[]>([]);
  const [loading, setLoading] = useState(true);
  const [page, setPage] = useState(1);
  const [totalPages, setTotalPages] = useState(1);
  const perPage = 20;

  useEffect(() => {
    setLoading(true);
    api
      .get('/simulations', { params: { offset: (page - 1) * perPage, limit: perPage } })
      .then((res) => {
        setSims(res.data.items || res.data);
        setTotalPages(res.data.total_pages || Math.ceil((res.data.total || 0) / perPage) || 1);
      })
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [page]);

  return (
    <div className="p-6 max-w-5xl mx-auto">
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-2xl font-bold text-saibyl-platinum">Simulations</h1>
        <Link
          to="/app/simulations/new"
          className="inline-flex items-center gap-2 bg-saibyl-indigo text-white px-4 py-2 rounded-xl text-sm font-medium hover:bg-[#4B4FDE] hover:shadow-[0_0_20px_rgba(91,95,238,0.3)] transition-all"
        >
          <span className="text-base leading-none">+</span> New Simulation
        </Link>
      </div>

      {loading ? (
        <div className="space-y-2">
          {[...Array(5)].map((_, i) => (
            <div key={i} className="h-12 rounded-xl bg-saibyl-deep animate-pulse" />
          ))}
        </div>
      ) : sims.length === 0 ? (
        <div className="flex flex-col items-center justify-center py-20 text-center">
          <div className="w-14 h-14 rounded-2xl bg-saibyl-indigo/10 flex items-center justify-center mb-4">
            <svg className="w-7 h-7 text-saibyl-indigo" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M9.75 3.104v5.714a2.25 2.25 0 01-.659 1.591L5 14.5M9.75 3.104c-.251.023-.501.05-.75.082m.75-.082a24.301 24.301 0 014.5 0m0 0v5.714c0 .597.237 1.17.659 1.591L19.8 15.3M14.25 3.104c.251.023.501.05.75.082M19.8 15.3l-1.57.393A9.065 9.065 0 0112 15a9.065 9.065 0 00-6.23-.693L5 14.5m14.8.8l1.402 1.402c1.232 1.232.65 3.318-1.067 3.611A48.309 48.309 0 0112 21c-2.773 0-5.491-.235-8.135-.687-1.718-.293-2.3-2.379-1.067-3.61L5 14.5" />
            </svg>
          </div>
          <p className="text-saibyl-platinum font-medium mb-1">No simulations yet</p>
          <p className="text-saibyl-muted text-sm mb-6">Create your first simulation to get started</p>
          <Link to="/app/simulations/new" className="bg-saibyl-indigo text-white px-5 py-2.5 rounded-xl text-sm font-medium hover:bg-[#4B4FDE] transition">
            Create Simulation
          </Link>
        </div>
      ) : (
        <>
          <div className="rounded-2xl overflow-hidden border border-white/[0.05] bg-saibyl-deep">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-white/[0.04]">
                  <th className="text-left px-5 py-3.5 font-medium text-saibyl-muted text-[11px] tracking-widest uppercase">Name</th>
                  <th className="text-left px-5 py-3.5 font-medium text-saibyl-muted text-[11px] tracking-widest uppercase">Status</th>
                  <th className="text-left px-5 py-3.5 font-medium text-saibyl-muted text-[11px] tracking-widest uppercase">Created</th>
                </tr>
              </thead>
              <tbody>
                {sims.map((sim, i) => (
                  <tr
                    key={sim.id}
                    className={`border-b border-white/[0.03] hover:bg-white/[0.02] transition-colors ${i === sims.length - 1 ? 'border-b-0' : ''}`}
                  >
                    <td className="px-5 py-3.5">
                      <Link
                        to={`/app/simulations/${sim.id}`}
                        className="font-medium text-saibyl-platinum hover:text-saibyl-indigo transition-colors"
                      >
                        {sim.name}
                      </Link>
                      {sim.project_name && (
                        <p className="text-[11px] text-saibyl-muted mt-0.5">{sim.project_name}</p>
                      )}
                    </td>
                    <td className="px-5 py-3.5">
                      <StatusBadge status={sim.status} />
                    </td>
                    <td className="px-5 py-3.5 text-saibyl-muted font-mono text-[12px]">
                      {new Date(sim.created_at).toLocaleDateString()}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <div className="flex items-center justify-center gap-4 mt-6">
            <button
              disabled={page <= 1}
              onClick={() => setPage((p) => p - 1)}
              className="px-4 py-1.5 rounded-xl border border-white/[0.06] disabled:opacity-30 hover:bg-saibyl-elevated text-saibyl-platinum text-sm transition-colors"
            >
              Previous
            </button>
            <span className="text-sm text-saibyl-muted font-mono">{page} / {totalPages}</span>
            <button
              disabled={page >= totalPages}
              onClick={() => setPage((p) => p + 1)}
              className="px-4 py-1.5 rounded-xl border border-white/[0.06] disabled:opacity-30 hover:bg-saibyl-elevated text-saibyl-platinum text-sm transition-colors"
            >
              Next
            </button>
          </div>
        </>
      )}
    </div>
  );
}
