import { useEffect, useState } from 'react';
import api from '@/lib/api';

interface SimSummary {
  simulation_id: string;
  name: string;
  persona_packs: string[];
  platforms: string[];
  agent_count: number;
  max_rounds: number;
  total_events: number;
  avg_sentiment: number;
  top_platform: string;
  event_breakdown: Record<string, number>;
  platform_breakdown: Record<string, number>;
}

interface SimOption {
  id: string;
  name: string;
  status: string;
  created_at: string;
  agent_count: number;
}

export default function ComparisonPage() {
  const [simulations, setSimulations] = useState<SimOption[]>([]);
  const [selected, setSelected] = useState<string[]>([]);
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<{ simulations: SimSummary[]; analysis: string } | null>(null);

  useEffect(() => {
    api.get('/simulations', { params: { limit: 50 } }).then((r) => {
      const completed = (Array.isArray(r.data) ? r.data : []).filter(
        (s: SimOption) => ['complete', 'completed'].includes(s.status)
      );
      setSimulations(completed);
    }).catch(() => {});
  }, []);

  const toggleSim = (id: string) => {
    setSelected((prev) =>
      prev.includes(id) ? prev.filter((x) => x !== id) : prev.length < 5 ? [...prev, id] : prev
    );
  };

  const runComparison = async () => {
    if (selected.length < 2) return;
    setLoading(true);
    try {
      const { data } = await api.post('/compare', { simulation_ids: selected });
      setResult(data);
    } catch { /* ignore */ } finally {
      setLoading(false);
    }
  };

  return (
    <div className="p-8 max-w-5xl mx-auto">
      <h1 className="text-h1 text-saibyl-white mb-2">Multi-Simulation Comparison</h1>
      <p className="text-small mb-6">Select 2-5 completed simulations to compare outcomes, sentiment, and engagement across different configurations.</p>

      {!result ? (
        <>
          <div className="glass rounded-2xl p-6 mb-6">
            <h2 className="text-[11px] font-mono text-saibyl-muted uppercase tracking-widest mb-4">Select Simulations</h2>
            {simulations.length === 0 ? (
              <p className="text-saibyl-muted text-[13px]">No completed simulations found.</p>
            ) : (
              <div className="space-y-2">
                {simulations.map((sim) => {
                  const isSelected = selected.includes(sim.id);
                  return (
                    <button
                      key={sim.id}
                      onClick={() => toggleSim(sim.id)}
                      className={`w-full text-left p-3 rounded-xl border transition-all ${
                        isSelected
                          ? 'border-saibyl-indigo/50 bg-saibyl-indigo/10'
                          : 'border-white/[0.06] bg-white/[0.02] hover:border-white/[0.12]'
                      }`}
                    >
                      <div className="flex items-center justify-between">
                        <div>
                          <span className="text-[14px] font-medium text-saibyl-platinum">{sim.name}</span>
                          <span className="text-[11px] text-saibyl-muted ml-3">{sim.agent_count} agents</span>
                          <span className="text-[11px] text-saibyl-muted ml-2">{new Date(sim.created_at).toLocaleDateString()}</span>
                        </div>
                        {isSelected && (
                          <div className="w-5 h-5 rounded-full bg-saibyl-indigo flex items-center justify-center">
                            <svg className="w-3 h-3 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={3} d="M5 13l4 4L19 7" /></svg>
                          </div>
                        )}
                      </div>
                    </button>
                  );
                })}
              </div>
            )}
            <div className="flex items-center justify-between mt-4">
              <p className="text-[12px] text-saibyl-muted">{selected.length} selected (min 2, max 5)</p>
              <button
                onClick={runComparison}
                disabled={loading || selected.length < 2}
                className="px-6 py-2.5 rounded-xl bg-saibyl-indigo text-white text-[13px] font-medium hover:bg-[#4B4FDE] disabled:opacity-50 transition-all"
              >
                {loading ? 'Comparing...' : 'Compare Simulations'}
              </button>
            </div>
          </div>
        </>
      ) : (
        <>
          {/* Results */}
          <div className="glass rounded-2xl p-6 mb-6">
            <h2 className="text-[11px] font-mono text-saibyl-muted uppercase tracking-widest mb-4">Comparison Results</h2>
            <div className="overflow-x-auto">
              <table className="w-full text-[13px]">
                <thead>
                  <tr className="border-b border-white/[0.06]">
                    <th className="text-left py-3 pr-4 text-saibyl-muted font-medium">Metric</th>
                    {result.simulations.map((s) => (
                      <th key={s.simulation_id} className="text-center py-3 px-3 text-saibyl-platinum font-medium">{s.name}</th>
                    ))}
                  </tr>
                </thead>
                <tbody className="divide-y divide-white/[0.04]">
                  <tr>
                    <td className="py-3 pr-4 text-saibyl-muted">Total Events</td>
                    {result.simulations.map((s) => (
                      <td key={s.simulation_id} className="text-center py-3 px-3 text-saibyl-platinum font-mono">{s.total_events}</td>
                    ))}
                  </tr>
                  <tr>
                    <td className="py-3 pr-4 text-saibyl-muted">Avg Sentiment</td>
                    {result.simulations.map((s) => (
                      <td key={s.simulation_id} className={`text-center py-3 px-3 font-mono ${s.avg_sentiment > 0.2 ? 'text-saibyl-positive' : s.avg_sentiment < -0.2 ? 'text-saibyl-negative' : 'text-saibyl-muted'}`}>
                        {s.avg_sentiment.toFixed(3)}
                      </td>
                    ))}
                  </tr>
                  <tr>
                    <td className="py-3 pr-4 text-saibyl-muted">Agents</td>
                    {result.simulations.map((s) => (
                      <td key={s.simulation_id} className="text-center py-3 px-3 text-saibyl-platinum font-mono">{s.agent_count}</td>
                    ))}
                  </tr>
                  <tr>
                    <td className="py-3 pr-4 text-saibyl-muted">Top Platform</td>
                    {result.simulations.map((s) => (
                      <td key={s.simulation_id} className="text-center py-3 px-3 text-saibyl-cyan">{s.top_platform}</td>
                    ))}
                  </tr>
                  <tr>
                    <td className="py-3 pr-4 text-saibyl-muted">Persona Packs</td>
                    {result.simulations.map((s) => (
                      <td key={s.simulation_id} className="text-center py-3 px-3 text-saibyl-muted text-[11px]">{s.persona_packs.join(', ') || 'N/A'}</td>
                    ))}
                  </tr>
                </tbody>
              </table>
            </div>
          </div>

          {/* Analysis */}
          <div className="glass rounded-2xl p-6 mb-6">
            <h2 className="text-[11px] font-mono text-saibyl-muted uppercase tracking-widest mb-4">Analysis</h2>
            <p className="text-[13px] text-saibyl-platinum/80 leading-relaxed whitespace-pre-wrap">{result.analysis}</p>
          </div>

          <button onClick={() => setResult(null)} className="text-[12px] text-saibyl-indigo hover:underline">
            ← New comparison
          </button>
        </>
      )}
    </div>
  );
}
