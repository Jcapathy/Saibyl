import { Info } from 'lucide-react';
import { CONFIDENCE_COPY, type QualityBlock } from '@/lib/analysis';

const ACCENT: Record<QualityBlock['confidence'], string> = {
  low: '#F59E0B',
  moderate: '#2563EB',
  high: '#22C55E',
};

/**
 * What this run's numbers are entitled to claim.
 *
 * Shown to the customer rather than kept internal. A 25-agent free run
 * genuinely has wide bands, and saying so plainly is both the honest read and
 * the most credible argument for buying more agents — far better than quietly
 * rendering the same confident-looking chart at every swarm size.
 */
export default function QualityNotice({ quality }: { quality: QualityBlock }) {
  const accent = ACCENT[quality.confidence];

  return (
    <div
      className="rounded-2xl border p-5 mb-6"
      style={{ borderColor: `${accent}33`, backgroundColor: `${accent}0D` }}
    >
      <div className="flex items-start gap-3">
        <Info className="w-4 h-4 mt-0.5 shrink-0" style={{ color: accent }} />
        <div className="min-w-0">
          <p className="text-[13px] font-semibold" style={{ color: accent }}>
            {quality.confidence === 'low'
              ? 'Low confidence'
              : quality.confidence === 'moderate'
                ? 'Moderate confidence'
                : 'High confidence'}
          </p>
          <p className="text-[12px] text-saibyl-silver mt-1 leading-relaxed">
            {CONFIDENCE_COPY[quality.confidence]}
          </p>

          <p className="text-[11px] text-saibyl-muted mt-2">
            {quality.events_measured.toLocaleString()} of{' '}
            {quality.events_total.toLocaleString()} events measured (
            {quality.coverage_pct.toFixed(1)}%) · {quality.agents_active} of{' '}
            {quality.agents_total} agents active · {quality.rounds} rounds
            {quality.measurement_model ? ` · scored by ${quality.measurement_model}` : ''}
          </p>

          {quality.caveats.length > 0 && (
            <ul className="mt-2 space-y-1">
              {quality.caveats.map((caveat) => (
                <li key={caveat} className="text-[11px] text-saibyl-muted leading-relaxed">
                  — {caveat}
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>
    </div>
  );
}
