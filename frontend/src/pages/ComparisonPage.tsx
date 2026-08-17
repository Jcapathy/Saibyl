import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import api, { unwrapList } from '@/lib/api';
import { getErrorMessage } from '@/lib/errors';
import { isFinished } from '@/lib/status';
import type { Simulation } from '@/types';

/** `POST /comparison` — a per-run rollup, not a `simulations` row. */
interface SimSummary {
  simulation_id: string;
  name: string;
  persona_packs: string[];
  platforms: string[];
  agent_count: number;
  max_rounds: number;
  total_events: number;
  // Null when the run has no measured sentiment. It used to be computed from
  // the dead `metadata.sentiment` key and defaulted to 0.0, so two unmeasured
  // runs compared as identically neutral — a fabricated agreement.
  avg_sentiment: number | null;
  sentiment_agents?: number | null;
  top_platform: string;
  event_breakdown: Record<string, number>;
  platform_breakdown: Record<string, number>;
}

export default function ComparisonPage() {
  const [simulations, setSimulations] = useState<Simulation[]>([]);
  const [selected, setSelected] = useState<string[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [result, setResult] = useState<{ simulations: SimSummary[]; analysis: string } | null>(null);

  useEffect(() => {
    api.get('/simulations', { params: { limit: 50 } }).then((r) => {
      // `isFinished` rather than a hand-written list. The database holds both
      // `complete` and `completed`, and a list built from one spelling silently
      // hides half the runs a founder is trying to compare.
      const finished = unwrapList<Simulation>(r.data).items.filter((s: Simulation) =>
        isFinished(s.status),
      );
      setSimulations(finished);
    }).catch((err) => {
      setError(getErrorMessage(err, 'We could not load your runs.'));
    });
  }, []);

  const toggleSim = (id: string) => {
    setSelected((prev) =>
      prev.includes(id) ? prev.filter((x) => x !== id) : prev.length < 5 ? [...prev, id] : prev
    );
  };

  const runComparison = async () => {
    if (selected.length < 2) return;
    setLoading(true);
    setError('');
    try {
      const { data } = await api.post('/compare', { simulation_ids: selected });
      setResult(data);
    } catch (err) {
      // Previously swallowed, which left the button flipping back to its idle
      // label having said nothing about why no table appeared.
      setError(getErrorMessage(err, 'We could not compare those runs.'));
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="p-8 max-w-5xl mx-auto">
      <h1 className="text-h1 text-saibyl-white mb-2">Put your runs side by side</h1>
      <p className="text-small mb-6">
        Pick two to five finished runs and we&rsquo;ll show you what changed between
        them — how people took it, how much they had to say, and where.
      </p>

      {!result ? (
        <>
          <div className="glass rounded-2xl p-6 mb-6">
            <h2 className="text-[11px] font-mono text-saibyl-muted uppercase tracking-widest mb-4">Pick the runs</h2>
            {simulations.length === 0 ? (
              <div>
                <p className="text-saibyl-muted text-[13px] mb-3">
                  You have no finished runs yet, so there is nothing to compare.
                </p>
                <Link
                  to="/app/simulations/new"
                  className="text-[13px] text-saibyl-gold hover:underline"
                >
                  Start a run →
                </Link>
              </div>
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
                          ? 'border-saibyl-gold/50 bg-saibyl-blue/[0.06]'
                          : 'border-saibyl-border bg-white hover:border-saibyl-border-light'
                      }`}
                    >
                      <div className="flex items-center justify-between">
                        <div>
                          <span className="text-[14px] font-medium text-saibyl-platinum">{sim.name}</span>
                          <span className="text-[11px] text-saibyl-muted ml-3">{sim.agent_count ?? '—'} people</span>
                          <span className="text-[11px] text-saibyl-muted ml-2">{new Date(sim.created_at).toLocaleDateString()}</span>
                        </div>
                        {isSelected && (
                          <div className="w-5 h-5 rounded-full bg-saibyl-gold flex items-center justify-center">
                            <svg className="w-3 h-3 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={3} d="M5 13l4 4L19 7" /></svg>
                          </div>
                        )}
                      </div>
                    </button>
                  );
                })}
              </div>
            )}
            <div className="flex items-center justify-between mt-4 gap-4">
              <p className="text-[12px] text-saibyl-muted">
                {selected.length === 0
                  ? 'Pick at least two.'
                  : selected.length === 1
                    ? 'Pick one more — you need at least two to compare.'
                    : `${selected.length} picked. You can compare up to five at once.`}
              </p>
              <button
                onClick={runComparison}
                disabled={loading || selected.length < 2}
                className="px-6 py-2.5 rounded-xl bg-saibyl-gold text-saibyl-void text-[13px] font-semibold hover:bg-saibyl-gold-hover disabled:opacity-50 transition-all shrink-0"
              >
                {loading ? 'Comparing…' : 'Compare them'}
              </button>
            </div>

            {error && (
              <p className="mt-3 text-[12px] text-saibyl-negative leading-relaxed">{error}</p>
            )}
          </div>
        </>
      ) : (
        <>
          {/* Results */}
          <div className="glass rounded-2xl p-6 mb-6">
            <h2 className="text-[11px] font-mono text-saibyl-muted uppercase tracking-widest mb-4">Side by side</h2>
            <div className="overflow-x-auto">
              <table className="w-full text-[13px]">
                <thead>
                  <tr className="border-b border-saibyl-border">
                    <th className="text-left py-3 pr-4 text-saibyl-muted font-medium">&nbsp;</th>
                    {result.simulations.map((s) => (
                      <th key={s.simulation_id} className="text-center py-3 px-3 text-saibyl-platinum font-medium">{s.name}</th>
                    ))}
                  </tr>
                </thead>
                <tbody className="divide-y divide-saibyl-border">
                  <tr>
                    <td className="py-3 pr-4 text-saibyl-muted">Posts and replies</td>
                    {result.simulations.map((s) => (
                      <td key={s.simulation_id} className="text-center py-3 px-3 text-saibyl-platinum font-mono tabular-nums">{s.total_events}</td>
                    ))}
                  </tr>
                  <tr>
                    <td className="py-3 pr-4 text-saibyl-muted">
                      How they felt
                      <span className="block text-[11px] text-saibyl-muted/70">
                        +1 loved it, &minus;1 hated it
                      </span>
                    </td>
                    {result.simulations.map((s) => (
                      <td key={s.simulation_id} className={`text-center py-3 px-3 font-mono tabular-nums ${s.avg_sentiment === null ? 'text-saibyl-muted' : s.avg_sentiment > 0.2 ? 'text-saibyl-positive' : s.avg_sentiment < -0.2 ? 'text-saibyl-negative' : 'text-saibyl-muted'}`}>
                        {s.avg_sentiment === null ? <span title="Nothing in this run could be measured, so it cannot be compared on this row.">not measured</span> : s.avg_sentiment.toFixed(3)}
                      </td>
                    ))}
                  </tr>
                  <tr>
                    <td className="py-3 pr-4 text-saibyl-muted">People in the room</td>
                    {result.simulations.map((s) => (
                      <td key={s.simulation_id} className="text-center py-3 px-3 text-saibyl-platinum font-mono tabular-nums">{s.agent_count}</td>
                    ))}
                  </tr>
                  <tr>
                    <td className="py-3 pr-4 text-saibyl-muted">Busiest platform</td>
                    {result.simulations.map((s) => (
                      <td key={s.simulation_id} className="text-center py-3 px-3 text-saibyl-blue">{s.top_platform}</td>
                    ))}
                  </tr>
                  <tr>
                    <td className="py-3 pr-4 text-saibyl-muted">Groups of buyers</td>
                    {result.simulations.map((s) => (
                      <td key={s.simulation_id} className="text-center py-3 px-3 text-saibyl-muted text-[11px]">{s.persona_packs.join(', ') || 'Worked out fresh'}</td>
                    ))}
                  </tr>
                </tbody>
              </table>
            </div>
          </div>

          {/* Analysis */}
          <div className="glass rounded-2xl p-6 mb-6">
            <h2 className="text-[11px] font-mono text-saibyl-muted uppercase tracking-widest mb-4">What changed between them</h2>
            <p className="text-[13px] text-saibyl-platinum/80 leading-relaxed whitespace-pre-wrap">{result.analysis}</p>
          </div>

          <button
            onClick={() => { setResult(null); setError(''); }}
            className="text-[12px] text-saibyl-gold hover:underline"
          >
            ← Compare a different set
          </button>
        </>
      )}
    </div>
  );
}
