import { PLATFORM_NAMES, platformColor, sentimentBarColor } from '@/lib/constants';
import {
  differsSignificantly,
  formatSigned,
  type ArchetypeSlice,
  type CohortSlice,
  type PlatformSlice,
} from '@/lib/analysis';
import Panel, { NoData } from './Panel';
import { groupLabel } from '@/lib/groups';

type Slice = PlatformSlice | ArchetypeSlice | CohortSlice;

function labelOf(slice: Slice): string {
  if ('platform' in slice) return PLATFORM_NAMES[slice.platform] ?? slice.platform;
  if ('cohort' in slice) return groupLabel(slice.cohort);
  return slice.archetype;
}

function colorOf(slice: Slice): string {
  if ('platform' in slice) return platformColor(slice.platform);
  return sentimentBarColor(slice.valence.mean);
}

/**
 * How each group felt, with the range around every figure drawn to scale.
 *
 * Groups arrive from the server worst-first, and the ranking is only asserted
 * where the ranges actually separate. A "worst platform" callout over two
 * overlapping ranges is the same false precision as a generated number,
 * arrived at more expensively.
 */
export default function GroupBreakdown({
  title,
  slices,
  objectionLabels,
  onDrillDown,
}: {
  title: string;
  slices: Slice[];
  objectionLabels?: Record<string, string>;
  onDrillDown?: (keys: string[], label: string) => void;
}) {
  if (slices.length === 0) {
    return (
      <Panel title={title}>
        <NoData>
          Nobody in this run said anything we could measure, so there is nothing to
          break down.
        </NoData>
      </Panel>
    );
  }

  const worst = slices[0];
  const best = slices[slices.length - 1];
  const resolved =
    slices.length > 1 && differsSignificantly(worst.valence, best.valence);

  // -1..1 mapped onto 0..100% of the track width.
  const toPct = (value: number) => ((value + 1) / 2) * 100;

  return (
    <Panel
      title={title}
      note={
        slices.length > 1
          ? resolved
            ? `${labelOf(worst)} took this worse than ${labelOf(best)}, and the gap is wide enough to be real — the ranges around the two figures do not overlap.`
            : 'The ranges around every group overlap, so this run cannot tell them apart.'
          : undefined
      }
    >
      <div className="space-y-4">
        {slices.map((slice) => {
          const { valence } = slice;
          const label = labelOf(slice);
          const objections = slice.top_objection_keys ?? [];
          return (
            <div key={label}>
              <div className="flex justify-between items-baseline text-[13px] mb-1.5 gap-3">
                <span className="text-saibyl-platinum font-medium leading-tight line-clamp-2">{label}</span>
                <span className="text-saibyl-silver text-[11px] whitespace-nowrap">
                  {valence.n < 2 ? (
                    <span className="text-saibyl-muted">
                      {valence.n === 1 ? 'one person only' : 'nobody spoke'} — too few to
                      read anything into
                    </span>
                  ) : (
                    <>
                      {formatSigned(valence.mean)}{' '}
                      <span className="text-saibyl-muted">
                        (somewhere between {formatSigned(valence.lower)} and{' '}
                        {formatSigned(valence.upper)}, across {valence.n} people)
                      </span>
                    </>
                  )}
                </span>
              </div>

              <div className="relative h-2.5 bg-[#14294a]/[0.06] rounded-full">
                {/* Midpoint marker: without it a bar length is unreadable on a
                    scale that runs from -1 to +1. */}
                <div className="absolute left-1/2 top-0 bottom-0 w-px bg-saibyl-border" />
                <div
                  className="absolute top-0 bottom-0 rounded-full"
                  style={{
                    left: `${toPct(valence.lower)}%`,
                    width: `${Math.max(toPct(valence.upper) - toPct(valence.lower), 1)}%`,
                    backgroundColor: colorOf(slice),
                    opacity: 0.3,
                  }}
                />
                <div
                  className="absolute top-[-2px] bottom-[-2px] w-[3px] rounded-full"
                  style={{
                    left: `${toPct(valence.mean)}%`,
                    backgroundColor: colorOf(slice),
                  }}
                />
              </div>

              <div className="flex flex-wrap items-center gap-x-3 gap-y-1 mt-1.5 text-[10px] text-saibyl-muted">
                <span>
                  {slice.stance.oppose_pct.toFixed(0)}% against ·{' '}
                  {slice.stance.support_pct.toFixed(0)}% for
                </span>
                <span>{slice.event_count} posts and replies</span>
                {/* A group that was given places in the room and barely spoke is
                    a finding, not a rounding error — but only if the places
                    given are the denominator. Platform and buyer-type splits
                    carry no allocation, so this appears on the buyers-versus-
                    sceptics split alone. */}
                {'agents_total' in slice && slice.agents_total > slice.agent_count && (
                  <span>
                    {slice.agent_count} of {slice.agents_total} said anything
                  </span>
                )}
                {objections.map((key) => (
                  <button
                    key={key}
                    type="button"
                    onClick={onDrillDown ? () => onDrillDown([key], label) : undefined}
                    className="px-1.5 py-0.5 rounded bg-saibyl-gold/10 text-saibyl-gold hover:bg-saibyl-gold/20 transition-colors"
                  >
                    {objectionLabels?.[key] ?? key}
                  </button>
                ))}
              </div>
            </div>
          );
        })}
      </div>
    </Panel>
  );
}
