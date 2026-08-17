import { Info } from 'lucide-react';
import { CONFIDENCE_COPY, type QualityBlock } from '@/lib/analysis';

const ACCENT: Record<QualityBlock['confidence'], string> = {
  low: '#f59e0b',
  moderate: '#286cf0',
  high: '#2fbf8a',
};

/* The darker text-safe variant of each accent — the bright fill hues above do
   not hold 4.5:1 on the light ground, so headings never use them directly. */
const ACCENT_TEXT: Record<QualityBlock['confidence'], string> = {
  low: '#b45309',
  moderate: '#1e5ad9',
  high: '#0e7d55',
};

/**
 * What this run's numbers are entitled to claim.
 *
 * Shown to the customer rather than kept internal. A 25-person free run
 * genuinely has wide ranges, and saying so plainly is both the honest read and
 * the most credible argument for putting more people in the room — far better
 * than quietly rendering the same confident-looking chart at every size.
 *
 * The sentence under the heading comes from `CONFIDENCE_COPY` in `lib/analysis`
 * and is still written in method language. That file is not this one's to
 * change; the heading and the counts below are.
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
          <p
            className="text-[13px] font-semibold"
            style={{ color: ACCENT_TEXT[quality.confidence] }}
          >
            {quality.confidence === 'low'
              ? 'Treat this as a rough read'
              : quality.confidence === 'moderate'
                ? 'Solid on the big differences, not the small ones'
                : 'Solid enough to act on'}
          </p>
          <p className="text-[12px] text-saibyl-silver mt-1 leading-relaxed">
            {CONFIDENCE_COPY[quality.confidence]}
          </p>

          <p className="text-[11px] text-saibyl-muted mt-2">
            We could read {quality.events_measured.toLocaleString()} of the{' '}
            {quality.events_total.toLocaleString()} posts and replies (
            {quality.coverage_pct.toFixed(1)}%) · {quality.agents_active} of{' '}
            {quality.agents_total} people said something · {quality.rounds} rounds
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
