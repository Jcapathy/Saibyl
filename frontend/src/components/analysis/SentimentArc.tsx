import { useMemo, useState } from 'react';
import { formatSigned, type Flashpoint, type Interval, type TimelinePoint } from '@/lib/analysis';
import Panel, { NoData } from './Panel';
import SentimentArcPlot, { type ArcSlot } from './SentimentArcPlot';

/**
 * How the room felt, round by round, with the range around every figure.
 *
 * This file owns the words; `SentimentArcPlot` owns the marks. Three rules
 * decide everything here, and all three came out of the same defect:
 *
 * 1. **Magnitude is length, never hue.** The version this replaces drew each
 *    round as a 20px dash whose only loud property was a three-bucket colour,
 *    so −0.50 and −0.21 were the same red and a reader had no way to see the
 *    difference between them. The columns now grow from a zero line, so the
 *    figure survives having every colour stripped out of it.
 *
 * 2. **A figure is never shown without its range.** Drawn on the mark, to the
 *    same scale as the mark, not parked in a tooltip.
 *
 * 3. **Absent is absent.** A round nobody said anything measurable in keeps its
 *    slot on the axis and says "not measured" underneath. It is never closed up
 *    (which would turn four measured rounds into a five-round arc), never
 *    joined through by the trend line, and never drawn at zero — the server's
 *    "nothing measured" value is a literal zero, and plotting it would state
 *    that the room felt neutral.
 *
 * No word a reader sees here is a term of art. The measurement underneath is a
 * mean valence per round with a 95% interval; what this says is "how the room
 * felt" and "the range around it", because the person reading is deciding
 * whether their message landed, not reviewing a method.
 */

/** Two people is the smallest group that has a range at all. */
const RESOLVED_MIN_N = 2;

/**
 * Round slots the plot will lay out before it gives up and shows figures only.
 *
 * The axis is built from round *numbers* rather than list positions, so a round
 * the server dropped stays visible as a hole. A run whose numbers are far apart
 * would otherwise ask for hundreds of empty slots.
 */
const MAX_SLOTS = 60;

function rangeText(value: Interval): string {
  if (value.n < RESOLVED_MIN_N) return 'anywhere on the scale';
  return `${formatSigned(value.lower)} to ${formatSigned(value.upper)}`;
}

function peopleText(n: number): string {
  return n === 1 ? '1 person spoke' : `${n} people spoke`;
}

/** "Round 2", "Rounds 2 and 6", "Rounds 2, 6 and 9". */
function roundList(rounds: number[]): string {
  const names = rounds.map((round) => `${round}`);
  const noun = names.length === 1 ? 'Round' : 'Rounds';
  if (names.length === 1) return `${noun} ${names[0]}`;
  return `${noun} ${names.slice(0, -1).join(', ')} and ${names[names.length - 1]}`;
}

/**
 * One round, turned into marks-and-words for the plot.
 *
 * A round with no point, or a point resting on nobody, becomes `value: null`.
 * This is the only place that decision is made, so there is no second path
 * through which an unmeasured round could acquire a mark on the zero line.
 */
function buildSlot(
  round: number,
  point: TimelinePoint | undefined,
  flash: Flashpoint | undefined,
  onDrillDown?: (eventIds: string[], label: string) => void,
): ArcSlot {
  const evidence = flash?.trigger_event_ids ?? [];
  const onSelect =
    onDrillDown && evidence.length > 0
      ? () => onDrillDown(evidence, `Round ${round}: what was said`)
      : undefined;
  const openHint = onSelect ? ' Open what was said that round.' : '';

  if (!point || point.valence.n < 1) {
    return {
      round,
      value: null,
      caption: 'not measured',
      captionTone: 'muted',
      description:
        `Round ${round}: nobody said anything we could measure, so there is nothing to show.` +
        openHint,
      onSelect,
    };
  }

  const value = point.valence;
  const resolved = value.n >= RESOLVED_MIN_N;

  let caption: string | null = null;
  let captionTone: ArcSlot['captionTone'] = 'muted';
  if (!resolved) {
    caption = '1 person only';
  } else if (flash) {
    const arrow = flash.delta > 0 ? '↑' : '↓';
    caption = `${arrow} ${Math.abs(flash.delta).toFixed(2)}${flash.significant ? '' : ' ?'}`;
    captionTone = flash.significant ? 'alert' : 'muted';
  }

  const reading = resolved
    ? `Round ${round}: the room sat at ${formatSigned(value.mean)}, somewhere between ` +
      `${formatSigned(value.lower)} and ${formatSigned(value.upper)}. ${peopleText(value.n)}.`
    : `Round ${round}: only 1 person spoke, so ${formatSigned(value.mean)} is one voice rather ` +
      `than a reading of the room.`;

  const move = flash
    ? ` The mood ${flash.delta > 0 ? 'rose' : 'fell'} ${Math.abs(flash.delta).toFixed(2)} from ` +
      `the round before.${
        flash.significant
          ? ''
          : ' That is smaller than the range around the figures, so it may be nothing.'
      }`
    : '';

  return {
    round,
    value,
    caption,
    captionTone,
    description: `${reading}${move}${openHint}`,
    onSelect,
  };
}

export default function SentimentArc({
  timeline,
  flashpoints = [],
  onDrillDown,
}: {
  timeline: TimelinePoint[];
  flashpoints?: Flashpoint[];
  onDrillDown?: (eventIds: string[], label: string) => void;
}) {
  const [showTable, setShowTable] = useState(false);

  const { slots, spanned } = useMemo(() => {
    if (timeline.length === 0) return { slots: [] as ArcSlot[], spanned: true };

    const byRound = new Map(timeline.map((p) => [p.round_number, p]));
    const flashByRound = new Map(flashpoints.map((f) => [f.round_number, f]));
    // Flashpoint rounds join the span too, so a move the server found never
    // lands outside the axis it is meant to be read on.
    const numbers = [...byRound.keys(), ...flashByRound.keys()];
    const first = Math.min(...numbers);
    const last = Math.max(...numbers);
    const span = last - first + 1;
    const complete = span <= MAX_SLOTS;

    const roundNumbers = complete
      ? Array.from({ length: span }, (_, index) => first + index)
      : timeline.map((p) => p.round_number);

    return {
      slots: roundNumbers.map((round) =>
        buildSlot(round, byRound.get(round), flashByRound.get(round), onDrillDown),
      ),
      spanned: complete,
    };
  }, [timeline, flashpoints, onDrillDown]);

  // An empty timeline and a timeline of rounds that all measured nobody are the
  // same thing to a reader. Both say so in words: the alternative is an axis
  // with a grid and no marks on it, which looks broken rather than empty.
  if (timeline.length === 0 || slots.every((slot) => slot.value === null)) {
    return (
      <Panel title="How the room felt, round by round">
        <NoData>
          No round produced anything we could measure, so there is nothing to show here. That
          happens when people reacted instead of posting, or when everything said was off the
          subject.
        </NoData>
      </Panel>
    );
  }

  // Named, not counted. The captions under the axis are dropped when a slot is
  // too narrow to hold one, so these sentences are what guarantees a reader on
  // a narrow panel still learns which rounds are missing.
  const missingRounds = slots.filter((slot) => slot.value === null).map((slot) => slot.round);
  const thinRounds = slots
    .filter((slot) => slot.value !== null && slot.value.n < RESOLVED_MIN_N)
    .map((slot) => slot.round);
  const hasUnclearMove = flashpoints.some((flash) => !flash.significant);
  // Gaps are only meaningful once the axis is a continuous run of rounds.
  const tableOpen = showTable || !spanned;

  return (
    <Panel
      title="How the room felt, round by round"
      note={
        <>
          Each bar is the average of everyone who spoke that round, on a scale where +1 is loved
          it and −1 is hated it. The line through the end of the bar is the range the real figure
          is 95% likely to sit in. It is worked out across people, not posts — someone posting ten
          times is one opinion, not ten.
        </>
      }
      action={
        spanned && (
          <button
            type="button"
            onClick={() => setShowTable((open) => !open)}
            className="text-[11px] text-saibyl-blue hover:underline whitespace-nowrap"
            aria-expanded={showTable}
          >
            {showTable ? 'Hide the numbers' : 'Show the numbers'}
          </button>
        )
      }
    >
      {spanned ? (
        <SentimentArcPlot slots={slots} />
      ) : (
        <p className="text-[12px] text-saibyl-muted leading-relaxed">
          This run covers too many rounds to chart legibly, so the figures are listed below
          instead.
        </p>
      )}

      {spanned && (
        <>
          <div className="mt-4 flex flex-wrap items-center gap-x-5 gap-y-2 text-[10px] text-saibyl-muted">
            <span className="flex items-center gap-1.5">
              <svg width="14" height="12" aria-hidden="true">
                <rect
                  x="1"
                  y="1"
                  width="12"
                  height="10"
                  fill="#2fbf8a"
                  fillOpacity="0.5"
                  stroke="#2fbf8a"
                />
              </svg>
              above the line — they warmed to it
            </span>
            <span className="flex items-center gap-1.5">
              <svg width="14" height="12" aria-hidden="true">
                <defs>
                  <pattern
                    id="arc-legend-hatch"
                    width="4"
                    height="4"
                    patternUnits="userSpaceOnUse"
                    patternTransform="rotate(45)"
                  >
                    <line x1="0" y1="0" x2="0" y2="4" stroke="#ff6e79" strokeWidth="1.2" />
                  </pattern>
                </defs>
                <rect x="1" y="1" width="12" height="10" fill="#ffffff" stroke="#ff6e79" />
                <rect x="1" y="1" width="12" height="10" fill="url(#arc-legend-hatch)" />
              </svg>
              below the line — they cooled on it
            </span>
            <span className="flex items-center gap-1.5">
              <svg width="14" height="12" aria-hidden="true">
                <line x1="7" y1="1" x2="7" y2="11" stroke="#14294a" strokeWidth="1.5" />
                <line x1="2" y1="1" x2="12" y2="1" stroke="#14294a" strokeWidth="1.5" />
                <line x1="2" y1="11" x2="12" y2="11" stroke="#14294a" strokeWidth="1.5" />
              </svg>
              the range around the figure
            </span>
          </div>

          <ul className="mt-2 space-y-1 text-[10px] text-saibyl-muted leading-relaxed">
            <li>
              The scale is always −1 to +1, so a small move looks small. That is deliberate — a
              run that never left ±0.05 should not look like one that swung to −0.9.
            </li>
            {missingRounds.length > 0 && (
              <li>
                {roundList(missingRounds)} {missingRounds.length === 1 ? 'is' : 'are'} not
                measured. Nobody said anything we could read, so nothing is drawn there and the
                line stops rather than guessing across the gap.
              </li>
            )}
            {thinRounds.length > 0 && (
              <li>
                {roundList(thinRounds)} {thinRounds.length === 1 ? 'rests' : 'rest'} on one
                person, so {thinRounds.length === 1 ? 'it gets' : 'they get'} a dotted line down
                the whole scale instead of a bar. One person tells you nothing about where the
                room sat.
              </li>
            )}
            {hasUnclearMove && (
              <li>
                A move marked “?” is smaller than the range around the figures either side of it,
                so we cannot tell it apart from noise.
              </li>
            )}
          </ul>
        </>
      )}

      {tableOpen && (
        <div className="mt-5 overflow-x-auto">
          <table className="w-full text-[11px] tabular-nums">
            <caption className="sr-only">
              How the room felt in each round, with the range around each figure
            </caption>
            <thead>
              <tr className="text-left text-saibyl-muted border-b border-saibyl-border">
                <th scope="col" className="py-1.5 pr-4 font-medium">
                  Round
                </th>
                <th scope="col" className="py-1.5 pr-4 font-medium">
                  How the room felt
                </th>
                <th scope="col" className="py-1.5 pr-4 font-medium">
                  The range around it
                </th>
                <th scope="col" className="py-1.5 font-medium">
                  Who that rests on
                </th>
              </tr>
            </thead>
            <tbody>
              {slots.map((slot) => (
                <tr key={slot.round} className="border-b border-saibyl-border/50">
                  <th scope="row" className="py-1.5 pr-4 font-normal text-saibyl-silver">
                    R{slot.round}
                  </th>
                  {slot.value ? (
                    <>
                      <td className="py-1.5 pr-4 text-saibyl-ink">
                        {formatSigned(slot.value.mean)}
                      </td>
                      <td className="py-1.5 pr-4 text-saibyl-silver">{rangeText(slot.value)}</td>
                      <td className="py-1.5 text-saibyl-muted">{peopleText(slot.value.n)}</td>
                    </>
                  ) : (
                    /* Three empty cells would read as three zeroes. One cell,
                       saying what happened, cannot be misread as a figure. */
                    <td colSpan={3} className="py-1.5 text-saibyl-muted">
                      Nobody said anything we could measure.
                    </td>
                  )}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </Panel>
  );
}
