import { sentimentBarColor } from '@/lib/constants';
import {
  formatSigned,
  type Flashpoint,
  type TimelinePoint,
} from '@/lib/analysis';
import Panel, { NoData } from './Panel';

/**
 * The sentiment arc, plotted with its confidence bands.
 *
 * The band is the point of the chart. V1 drew a smooth curve generated with
 * `Math.sin()` from a single scraped scalar; a reader had no way to see that a
 * 25-agent run cannot resolve a 0.1 move. Here the interval is drawn to scale,
 * so a wide band is visible as a wide band.
 *
 * Rounds where nothing measurable was said are absent rather than interpolated
 * — a flat segment would read as "sentiment held steady", which is a different
 * claim from "nobody spoke".
 */
export default function SentimentArc({
  timeline,
  flashpoints = [],
  onDrillDown,
}: {
  timeline: TimelinePoint[];
  flashpoints?: Flashpoint[];
  onDrillDown?: (eventIds: string[], label: string) => void;
}) {
  if (timeline.length === 0) {
    return (
      <Panel title="Sentiment arc">
        <NoData>
          No round produced a measurable opinion, so there is no arc to plot.
          This happens when agents reacted rather than posted, or when every
          event was off-topic.
        </NoData>
      </Panel>
    );
  }

  const flashByRound = new Map(flashpoints.map((f) => [f.round_number, f]));

  // Fixed -1..1 scale rather than auto-scaling to the data. Auto-scaling makes
  // a run that never left ±0.05 look as dramatic as one that swung to -0.9.
  const toY = (value: number) => ((1 - value) / 2) * 100;

  return (
    <Panel
      title="Sentiment arc"
      note={
        <>
          Mean valence per round with its 95% confidence interval. The interval
          is computed across agents, not events — one agent posting ten times is
          one opinion, not ten.
        </>
      }
    >
      <div className="relative h-56 flex items-stretch gap-1 pt-2">
        {/* Zero line — the reference the eye needs to read sign at a glance. */}
        <div
          className="absolute left-0 right-0 border-t border-dashed border-saibyl-border pointer-events-none"
          style={{ top: '50%' }}
        />

        {timeline.map((point) => {
          const { valence } = point;
          const flash = flashByRound.get(point.round_number);
          const top = toY(valence.upper);
          const bottom = toY(valence.lower);
          const color = sentimentBarColor(valence.mean);
          const unresolvable = valence.n < 2;

          return (
            <button
              key={point.round_number}
              type="button"
              onClick={
                flash && onDrillDown
                  ? () =>
                      onDrillDown(
                        flash.trigger_event_ids,
                        `Round ${point.round_number} shift`,
                      )
                  : undefined
              }
              className={`relative flex-1 group ${
                flash && onDrillDown ? 'cursor-pointer' : 'cursor-default'
              }`}
              title={
                `Round ${point.round_number}: ${formatSigned(valence.mean)} ` +
                (unresolvable
                  ? '(1 agent — not resolvable)'
                  : `(95% CI ${formatSigned(valence.lower)} to ${formatSigned(valence.upper)}, ${valence.n} agents)`)
              }
            >
              {/* Confidence band drawn to scale. */}
              <div
                className="absolute left-1/2 -translate-x-1/2 w-3 rounded-sm"
                style={{
                  top: `${top}%`,
                  height: `${Math.max(bottom - top, 1)}%`,
                  backgroundColor: color,
                  opacity: 0.22,
                }}
              />
              {/* The mean. */}
              <div
                className="absolute left-1/2 -translate-x-1/2 w-5 h-[3px] rounded-full"
                style={{ top: `${toY(valence.mean)}%`, backgroundColor: color }}
              />
              {flash && (
                <span
                  className={`absolute left-1/2 -translate-x-1/2 -top-1 text-[9px] font-bold px-1 rounded whitespace-nowrap ${
                    flash.significant
                      ? 'text-saibyl-negative bg-saibyl-negative/15'
                      : 'text-saibyl-muted bg-white/[0.04]'
                  }`}
                >
                  {flash.delta > 0 ? '↑' : '↓'} {Math.abs(flash.delta).toFixed(2)}
                  {flash.significant ? '' : '?'}
                </span>
              )}
              <span className="absolute -bottom-5 left-0 right-0 text-[10px] text-saibyl-muted text-center">
                R{point.round_number}
              </span>
            </button>
          );
        })}
      </div>

      <div className="mt-8 flex flex-wrap items-center gap-x-5 gap-y-1 text-[10px] text-saibyl-muted">
        <span>
          <span className="inline-block w-3 h-[3px] align-middle bg-saibyl-silver rounded-full mr-1" />
          mean
        </span>
        <span>
          <span className="inline-block w-3 h-3 align-middle bg-saibyl-silver/25 rounded-sm mr-1" />
          95% interval
        </span>
        <span>↓0.00? — moved, but inside the bands</span>
        <span>Scale is fixed at −1 to +1.</span>
      </div>
    </Panel>
  );
}
