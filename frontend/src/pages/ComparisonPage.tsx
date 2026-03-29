import { useEffect, useState } from 'react';
import { useParams } from 'react-router-dom';
import api from '@/lib/api';

interface VariantSummary {
  variant: string;
  total_events: number;
  avg_sentiment: number;
  engagement_rate: number;
  viral_posts: number;
  top_platform: string;
}

interface MetricRow {
  metric: string;
  variant_a: string | number;
  variant_b: string | number;
  winner: 'A' | 'B' | 'tie';
}

interface ComparisonData {
  simulation_id: string;
  simulation_name: string;
  variant_a: VariantSummary;
  variant_b: VariantSummary;
  metrics: MetricRow[];
  overall_winner: 'A' | 'B' | 'tie';
  winner_explanation: string;
}

export default function ComparisonPage() {
  const { id } = useParams<{ id: string }>();
  const [data, setData] = useState<ComparisonData | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const fetchComparison = async () => {
      try {
        const [simRes, reportRes] = await Promise.all([
          api.get(`/simulations/${id}`),
          api.get(`/reports/by-simulation/${id}`),
        ]);
        const sim = simRes.data;
        const report = reportRes.data;

        // Build comparison data from simulation and report
        const comparison: ComparisonData = {
          simulation_id: sim.id,
          simulation_name: sim.name,
          variant_a: report.variant_a || { variant: 'A', total_events: 0, avg_sentiment: 0, engagement_rate: 0, viral_posts: 0, top_platform: 'N/A' },
          variant_b: report.variant_b || { variant: 'B', total_events: 0, avg_sentiment: 0, engagement_rate: 0, viral_posts: 0, top_platform: 'N/A' },
          metrics: report.metrics || [],
          overall_winner: report.overall_winner || 'tie',
          winner_explanation: report.winner_explanation || '',
        };
        setData(comparison);
      } catch {
        // handle error
      } finally {
        setLoading(false);
      }
    };
    fetchComparison();
  }, [id]);

  if (loading) return <div className="p-8 text-center text-saibyl-muted">Loading comparison...</div>;
  if (!data) return <div className="p-8 text-center text-red-500">Comparison data not available.</div>;

  const winnerLabel = data.overall_winner === 'tie' ? 'Tie' : `Variant ${data.overall_winner} wins`;
  const winnerBg = data.overall_winner === 'A' ? 'bg-blue-900/30 border-blue-500' : data.overall_winner === 'B' ? 'bg-green-900/30 border-green-500' : 'bg-saibyl-surface border-saibyl-border';

  return (
    <div className="p-6 max-w-5xl mx-auto bg-saibyl-void">
      <h1 className="text-2xl font-bold text-saibyl-platinum mb-2">A/B Comparison</h1>
      <p className="text-saibyl-muted mb-6">{data.simulation_name}</p>

      {/* Winner callout */}
      <div className={`rounded-2xl border-2 p-4 mb-8 ${winnerBg}`}>
        <div className="text-lg font-bold text-saibyl-platinum">{winnerLabel}</div>
        <p className="text-sm text-saibyl-muted mt-1">{data.winner_explanation}</p>
      </div>

      {/* Two-column variant summaries */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6 mb-8">
        {[data.variant_a, data.variant_b].map((v, i) => (
          <div key={i} className="bg-saibyl-deep rounded-2xl p-6 border border-saibyl-border">
            <h2 className="text-lg font-semibold text-saibyl-platinum mb-4">
              Variant {i === 0 ? 'A' : 'B'}
            </h2>
            <dl className="space-y-2 text-sm">
              <div className="flex justify-between">
                <dt className="text-saibyl-muted">Total Events</dt>
                <dd className="font-medium text-saibyl-platinum">{v.total_events}</dd>
              </div>
              <div className="flex justify-between">
                <dt className="text-saibyl-muted">Avg Sentiment</dt>
                <dd className="font-medium text-saibyl-platinum">{v.avg_sentiment.toFixed(3)}</dd>
              </div>
              <div className="flex justify-between">
                <dt className="text-saibyl-muted">Engagement Rate</dt>
                <dd className="font-medium text-saibyl-platinum">{(v.engagement_rate * 100).toFixed(1)}%</dd>
              </div>
              <div className="flex justify-between">
                <dt className="text-saibyl-muted">Viral Posts</dt>
                <dd className="font-medium text-saibyl-platinum">{v.viral_posts}</dd>
              </div>
              <div className="flex justify-between">
                <dt className="text-saibyl-muted">Top Platform</dt>
                <dd className="font-medium text-saibyl-platinum">{v.top_platform}</dd>
              </div>
            </dl>
          </div>
        ))}
      </div>

      {/* Metrics comparison table */}
      <div className="bg-saibyl-deep rounded-2xl overflow-hidden border border-saibyl-border">
        <table className="w-full text-sm">
          <thead className="bg-saibyl-surface">
            <tr>
              <th className="text-left px-4 py-3 font-medium text-saibyl-platinum">Metric</th>
              <th className="text-center px-4 py-3 font-medium text-saibyl-platinum">Variant A</th>
              <th className="text-center px-4 py-3 font-medium text-saibyl-platinum">Variant B</th>
              <th className="text-center px-4 py-3 font-medium text-saibyl-platinum">Winner</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-saibyl-border">
            {data.metrics.map((row, i) => (
              <tr key={i} className="hover:bg-saibyl-elevated">
                <td className="px-4 py-3 font-medium text-saibyl-platinum">{row.metric}</td>
                <td className={`px-4 py-3 text-center ${row.winner === 'A' ? 'text-saibyl-indigo font-bold' : 'text-saibyl-platinum'}`}>
                  {row.variant_a}
                </td>
                <td className={`px-4 py-3 text-center ${row.winner === 'B' ? 'text-saibyl-indigo font-bold' : 'text-saibyl-platinum'}`}>
                  {row.variant_b}
                </td>
                <td className="px-4 py-3 text-center">
                  <span className={`text-xs px-2 py-1 rounded-full ${
                    row.winner === 'A' ? 'bg-blue-100 text-blue-700' :
                    row.winner === 'B' ? 'bg-green-100 text-green-700' :
                    'bg-saibyl-surface text-saibyl-muted'
                  }`}>
                    {row.winner === 'tie' ? 'Tie' : row.winner}
                  </span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
