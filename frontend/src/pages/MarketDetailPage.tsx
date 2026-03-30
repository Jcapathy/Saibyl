import { useEffect, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import api from '@/lib/api';
import StatusBadge from '@/components/StatusBadge';

interface Prediction {
  id: string;
  predicted_outcome: string;
  predicted_probability: number;
  recommended_position: string;
  edge_vs_market: number;
  reasoning_summary: string;
  market_price_at_prediction: number;
  created_at: string;
}

interface Market {
  id: string;
  platform: string;
  title: string;
  description: string;
  resolution_rules: string;
  status: string;
  outcomes: { label: string; current_probability: number }[];
  volume_usd: number;
  open_interest_usd: number;
  closes_at: string;
  external_url: string;
  predictions: Prediction[];
}

export default function MarketDetailPage() {
  const { id } = useParams<{ id: string }>();
  const [market, setMarket] = useState<Market | null>(null);
  const [loading, setLoading] = useState(true);
  const [predicting, setPredicting] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState('');

  const load = () => {
    api.get(`/markets/${id}`).then((r) => { setMarket(r.data); setLoading(false); }).catch(() => setLoading(false));
  };

  useEffect(() => { load(); }, [id]);

  const runPrediction = async () => {
    setPredicting(true);
    setError('');
    const existingCount = market?.predictions?.length || 0;
    try {
      await api.post(`/markets/${id}/predict`);
      // Poll for new prediction to appear
      const poll = setInterval(() => {
        api.get(`/markets/${id}`).then((r) => {
          setMarket(r.data);
          const newCount = r.data.predictions?.length || 0;
          if (newCount > existingCount) {
            clearInterval(poll);
            setPredicting(false);
          }
        }).catch(() => {});
      }, 10000);
      // Stop polling after 10 minutes — prediction includes sim + report
      setTimeout(() => {
        clearInterval(poll);
        if (predicting) {
          setError('Prediction is taking longer than expected. Check back shortly.');
          setPredicting(false);
        }
      }, 600000);
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Prediction failed to start');
      setPredicting(false);
    }
  };

  const refresh = async () => {
    setRefreshing(true);
    setError('');
    try {
      await api.post(`/markets/${id}/refresh`);
      load();
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Refresh failed');
    }
    setRefreshing(false);
  };

  if (loading) return <div className="p-8 text-saibyl-muted">Loading...</div>;
  if (!market) return <div className="p-8 text-saibyl-muted">Market not found</div>;

  const yesOutcome = market.outcomes?.find((o) => o.label?.toLowerCase() === 'yes');
  const yesProb = yesOutcome ? Math.round(yesOutcome.current_probability * 100) : null;

  return (
    <div className="p-8 bg-saibyl-void min-h-full">
      <div className="max-w-4xl mx-auto">
        {/* Breadcrumb */}
        <div className="flex items-center gap-2 text-sm text-saibyl-muted mb-6">
          <Link to="/app/markets" className="hover:text-saibyl-platinum transition-colors">Markets</Link>
          <span>/</span>
          <span className="text-saibyl-platinum truncate max-w-xs">{market.title}</span>
        </div>

        {error && (
          <div className="mb-4 px-4 py-3 rounded-xl bg-saibyl-negative/10 border border-saibyl-negative/20 text-saibyl-negative text-sm">
            {error}
            <button onClick={() => setError('')} className="ml-3 underline">dismiss</button>
          </div>
        )}

        {/* Header card */}
        <div className="glass rounded-2xl p-8 mb-6">
          <div className="flex items-start justify-between gap-6">
            <div className="flex-1">
              <div className="flex items-center gap-2 mb-3">
                <span className="font-mono text-[10px] tracking-[0.15em] uppercase text-saibyl-cyan">{market.platform}</span>
                <StatusBadge status={market.status} />
              </div>
              <h1 className="text-[22px] font-display font-bold text-saibyl-white leading-tight mb-3">{market.title}</h1>
              {market.description && (
                <p className="text-[14px] text-saibyl-muted leading-relaxed mb-4">{market.description}</p>
              )}
              <div className="flex flex-wrap items-center gap-4 text-[13px] text-saibyl-muted">
                <span>Vol: <span className="text-saibyl-platinum font-medium">${(market.volume_usd || 0).toLocaleString()}</span></span>
                {market.open_interest_usd > 0 && (
                  <span>OI: <span className="text-saibyl-platinum">${market.open_interest_usd.toLocaleString()}</span></span>
                )}
                {market.closes_at && (
                  <span>Closes: <span className="text-saibyl-platinum">{new Date(market.closes_at).toLocaleDateString()}</span></span>
                )}
                <a href={market.external_url} target="_blank" rel="noopener noreferrer" className="text-saibyl-indigo hover:text-saibyl-cyan transition-colors">
                  View on {market.platform} →
                </a>
              </div>
            </div>

            {/* Probability gauge */}
            {yesProb !== null && (
              <div className="text-center shrink-0">
                <div className="relative w-28 h-28">
                  <svg className="w-28 h-28 -rotate-90" viewBox="0 0 100 100">
                    <circle cx="50" cy="50" r="42" fill="none" stroke="rgba(255,255,255,0.06)" strokeWidth="8" />
                    <circle
                      cx="50" cy="50" r="42" fill="none"
                      stroke="url(#gauge-grad)" strokeWidth="8" strokeLinecap="round"
                      strokeDasharray={`${yesProb * 2.64} ${264 - yesProb * 2.64}`}
                    />
                    <defs>
                      <linearGradient id="gauge-grad" x1="0%" y1="0%" x2="100%" y2="0%">
                        <stop offset="0%" stopColor="#5B5FEE" />
                        <stop offset="100%" stopColor="#00D4FF" />
                      </linearGradient>
                    </defs>
                  </svg>
                  <div className="absolute inset-0 flex flex-col items-center justify-center">
                    <span className="text-2xl font-display font-bold text-white">{yesProb}%</span>
                    <span className="text-[10px] text-saibyl-muted uppercase">YES</span>
                  </div>
                </div>
              </div>
            )}
          </div>

          {/* Outcome bars */}
          {market.outcomes && market.outcomes.length > 0 && (
            <div className="mt-6 space-y-2">
              {market.outcomes.map((o) => (
                <div key={o.label} className="flex items-center gap-3">
                  <span className="text-[13px] text-saibyl-muted w-12">{o.label}</span>
                  <div className="flex-1 h-2 bg-saibyl-elevated rounded-full overflow-hidden">
                    <div
                      className="h-full rounded-full bg-gradient-to-r from-saibyl-indigo to-saibyl-cyan"
                      style={{ width: `${Math.round(o.current_probability * 100)}%` }}
                    />
                  </div>
                  <span className="text-[13px] font-mono text-saibyl-platinum w-12 text-right">
                    {Math.round(o.current_probability * 100)}%
                  </span>
                </div>
              ))}
            </div>
          )}

          {/* Actions */}
          <div className="flex gap-3 mt-6">
            <button
              onClick={runPrediction}
              disabled={predicting}
              className="relative flex-1 py-3 rounded-xl text-white font-medium text-[14px] transition-all hover:scale-[1.01] disabled:opacity-40 overflow-hidden"
            >
              <div className="absolute inset-0 bg-gradient-to-r from-[#5B5FEE] to-[#00D4FF]" />
              <span className="relative">{predicting ? 'Running prediction...' : 'Run Saibyl Prediction'}</span>
            </button>
            <button
              onClick={refresh}
              disabled={refreshing}
              className="glass glass-hover px-5 py-3 rounded-xl text-saibyl-platinum text-[14px] font-medium transition-all disabled:opacity-40"
            >
              {refreshing ? '↻' : '↻ Refresh prices'}
            </button>
          </div>
        </div>

        {/* Market Context */}
        {(market as any).market_context && (
          <div className="glass rounded-2xl p-6 mb-6">
            <h3 className="font-mono text-[11px] tracking-[0.18em] uppercase text-saibyl-muted mb-3">Market Context</h3>
            <p className="text-[14px] text-saibyl-platinum leading-relaxed">{(market as any).market_context}</p>
          </div>
        )}

        {/* Resolution rules */}
        {market.resolution_rules && (
          <div className="glass rounded-2xl p-6 mb-6">
            <h3 className="font-mono text-[11px] tracking-[0.18em] uppercase text-saibyl-muted mb-3">Resolution Rules</h3>
            <p className="text-[14px] text-saibyl-platinum leading-relaxed">{market.resolution_rules}</p>
          </div>
        )}

        {/* Prediction History */}
        <div className="mb-6">
          <h2 className="text-h2 text-saibyl-white mb-4">Prediction History</h2>
          {(!market.predictions || market.predictions.length === 0) ? (
            <div className="glass rounded-2xl p-12 text-center">
              <p className="text-saibyl-muted text-sm">No predictions yet. Click "Run Saibyl Prediction" to generate one.</p>
            </div>
          ) : (
            <div className="space-y-3">
              {market.predictions.map((pred) => {
                const edge = pred.edge_vs_market;
                const edgeColor = Math.abs(edge) < 0.03 ? 'text-saibyl-muted' : edge > 0 ? 'text-saibyl-positive' : 'text-saibyl-negative';
                const isPass = pred.recommended_position === 'PASS';
                const posColor = isPass ? 'bg-saibyl-elevated text-saibyl-muted' : 'bg-saibyl-indigo/15 text-saibyl-indigo';

                return (
                  <div key={pred.id} className="glass rounded-xl p-6">
                    <div className="flex items-start justify-between gap-4">
                      <div className="flex-1">
                        <div className="flex items-center gap-3 mb-2">
                          <span className={`px-2.5 py-1 rounded-md font-mono text-[11px] font-medium ${posColor}`}>
                            {pred.recommended_position}
                          </span>
                          <span className="text-[12px] text-saibyl-muted">
                            {new Date(pred.created_at).toLocaleString()}
                          </span>
                        </div>
                        <p className="text-[14px] text-saibyl-platinum leading-relaxed">{pred.reasoning_summary}</p>
                      </div>
                      <div className="text-right shrink-0 space-y-1">
                        <div className="text-xl font-display font-bold text-gradient">
                          {Math.round(pred.predicted_probability * 100)}%
                        </div>
                        <div className="text-[11px] text-saibyl-muted">Saibyl estimate</div>
                        <div className={`text-[13px] font-mono font-medium ${edgeColor}`}>
                          {edge > 0 ? '+' : ''}{(edge * 100).toFixed(1)}pp edge
                        </div>
                        <div className="text-[11px] text-saibyl-muted">
                          Mkt was {Math.round(pred.market_price_at_prediction * 100)}%
                        </div>
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
