import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import api from '@/lib/api';

interface Simulation {
  id: string;
  name: string;
  status: string;
  created_at: string;
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

export default function SimulationsPage() {
  const [sims, setSims] = useState<Simulation[]>([]);
  const [loading, setLoading] = useState(true);
  const [page, setPage] = useState(1);
  const [totalPages, setTotalPages] = useState(1);
  const perPage = 20;

  useEffect(() => {
    setLoading(true);
    api
      .get('/simulations', { params: { page, limit: perPage } })
      .then((res) => {
        setSims(res.data.items || res.data);
        setTotalPages(res.data.total_pages || Math.ceil((res.data.total || 0) / perPage) || 1);
      })
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [page]);

  return (
    <div className="p-6 max-w-5xl mx-auto bg-saibyl-void">
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-2xl font-bold text-saibyl-platinum">Simulations</h1>
        <Link
          to="/app/simulations/new"
          className="bg-saibyl-indigo text-white px-4 py-2 rounded-lg hover:bg-[#4B4FDE] transition"
        >
          + New Simulation
        </Link>
      </div>

      {loading ? (
        <p className="text-saibyl-muted">Loading simulations...</p>
      ) : sims.length === 0 ? (
        <p className="text-saibyl-muted">No simulations found.</p>
      ) : (
        <>
          <div className="bg-saibyl-deep rounded-2xl overflow-hidden border border-saibyl-border">
            <table className="w-full text-sm">
              <thead className="bg-saibyl-surface">
                <tr>
                  <th className="text-left px-4 py-3 font-medium text-saibyl-platinum">Name</th>
                  <th className="text-left px-4 py-3 font-medium text-saibyl-platinum">Status</th>
                  <th className="text-left px-4 py-3 font-medium text-saibyl-platinum">Created</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-saibyl-border">
                {sims.map((sim) => (
                  <tr key={sim.id} className="hover:bg-saibyl-elevated">
                    <td className="px-4 py-3">
                      <Link to={`/app/simulations/${sim.id}`} className="text-saibyl-indigo hover:underline font-medium">
                        {sim.name}
                      </Link>
                    </td>
                    <td className="px-4 py-3">
                      <span className={`text-xs px-2 py-1 rounded-full ${statusColor[sim.status] || 'bg-saibyl-deep'}`}>
                        {sim.status}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-saibyl-muted">
                      {new Date(sim.created_at).toLocaleDateString()}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {/* Pagination */}
          <div className="flex items-center justify-center gap-4 mt-6">
            <button
              disabled={page <= 1}
              onClick={() => setPage((p) => p - 1)}
              className="px-3 py-1 border border-saibyl-border rounded-lg disabled:opacity-40 hover:bg-saibyl-elevated text-saibyl-platinum"
            >
              Previous
            </button>
            <span className="text-sm text-saibyl-muted">
              Page {page} of {totalPages}
            </span>
            <button
              disabled={page >= totalPages}
              onClick={() => setPage((p) => p + 1)}
              className="px-3 py-1 border border-saibyl-border rounded-lg disabled:opacity-40 hover:bg-saibyl-elevated text-saibyl-platinum"
            >
              Next
            </button>
          </div>
        </>
      )}
    </div>
  );
}
