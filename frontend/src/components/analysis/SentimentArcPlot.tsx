import { useId, useLayoutEffect, useRef, useState } from 'react';
import { formatSigned } from '@/lib/analysis';

/**
 * The drawing half of the sentiment arc. It knows geometry; it knows no copy.
 *
 * Every word a reader sees is composed by the parent and handed down on the
 * slot, so the plain-English register lives in one file and this one can be
 * reasoned about purely as marks on a scale.
 *
 * ## Why columns and whiskers rather than a coloured dash
 *
 * The version this replaces drew each round as a 20px dash floating at a height
 * on a −1..+1 scale, tinted green / slate / red by a three-bucket threshold. At
 * the values a real run produces — five rounds between −0.5 and +0.2 — those
 * dashes occupy 76px of a 216px box with ~100px of empty space between them, no
 * number anywhere on the figure, and a confidence band rendered as a 12×13px
 * rectangle at 22% opacity. The only thing that changed loudly between rounds
 * was the hue, and the hue was a bucket: −0.50 and −0.21 were the same red, so
 * colour did not even encode magnitude. That is the defect.
 *
 * The fix is the one `backend/app/services/export/vector_charts.py` already
 * shipped for print, ported to the browser:
 *
 * - **Length from a shared baseline.** A column grown from zero encodes the
 *   number as distance, which survives having every colour stripped out.
 * - **Sign carried by texture as well as by side.** Up is a solid fill, down is
 *   hollow and hatched. Two rounds of equal size and opposite sign are still
 *   two different objects in greyscale.
 * - **The interval drawn on the mark.** A capped whisker through the column
 *   end, to the same scale as the column, so a number nobody can stand behind
 *   looks like one.
 * - **The value printed on the figure.** Nothing about reading this chart is
 *   gated behind a hover.
 *
 * Colour is left in as a third, redundant channel. Nothing is encoded by it
 * alone, so removing it removes decoration and not information.
 *
 * ## Why the scale stays fixed at −1..+1
 *
 * Auto-scaling to the data makes a run that never left ±0.05 look as dramatic
 * as one that swung to −0.9, and this figure is read by someone deciding
 * whether a message landed. The legibility problem is solved by growing marks
 * from a baseline and printing the numbers, not by inflating the y-axis.
 */

/** A measured round: the average, its interval, and how many people it rests on. */
export interface ArcValue {
  mean: number;
  lower: number;
  upper: number;
  /** People who spoke that round. Never events. */
  n: number;
}

/** One position on the round axis. Absent rounds are slots with no value. */
export interface ArcSlot {
  round: number;
  /**
   * `null` when the round produced nothing measurable.
   *
   * The plot draws no mark at all for a null, and no mark for `n < 1` either.
   * There is deliberately no code path here that can put a point on the zero
   * line for a round that was never measured: the server's "nothing measured"
   * interval is literally `{mean: 0, lower: 0, upper: 0, n: 0}`, and drawing it
   * would state that the room felt neutral.
   */
  value: ArcValue | null;
  /** One short line under the round number. Composed by the parent. */
  caption: string | null;
  captionTone: 'muted' | 'alert';
  /** The whole round in a sentence, for the hover tooltip and screen readers. */
  description: string;
  /** Present only on rounds that have evidence to open. */
  onSelect?: () => void;
}

/* ── Scale ───────────────────────────────────────────────────────────── */

const PAD_L = 62;
const PAD_R = 14;
const PAD_T = 30;
const PLOT_H = 200;
const PLOT_TOP = PAD_T;
const PLOT_BOTTOM = PAD_T + PLOT_H;
const ZERO_Y = PAD_T + PLOT_H / 2;

const ROUND_LABEL_Y = PLOT_BOTTOM + 15;
const CAPTION_Y = PLOT_BOTTOM + 27;
const HEIGHT = CAPTION_Y + 6;

const AXIS_TICKS = [1, 0.5, 0, -0.5, -1] as const;

/** An interval is only an interval once two people have spoken. */
const RESOLVED_MIN_N = 2;

/**
 * A printed figure is always five characters — "+0.12", "-0.47" — which is
 * about 32px at 11px type. Below a slot that wide plus air, the labels would
 * touch, so they are dropped and the table carries the numbers.
 */
const VALUE_LABEL_W = 32;
const LABEL_MIN_BAND = VALUE_LABEL_W + 5;
/** Below this a label cannot be set beside a column either, so it goes to the table. */
const SIDE_LABEL_MIN_BAND = 90;

/* ── Ink ─────────────────────────────────────────────────────────────── */
/* Literals rather than Tailwind classes: these are SVG paint attributes, and
   the point of the exercise is that a reader can check them against a
   greyscale conversion without chasing a class name. */

const INK = '#E8ECF2'; // saibyl-platinum — whiskers and printed values
const INK_SOFT = '#8B97A8'; // saibyl-silver — axis numbers, the trend line
const INK_MUTED = '#5A6578'; // saibyl-muted — captions
const GRID = '#1E293B'; // saibyl-border
const ZERO_RULE = '#2A3A55'; // saibyl-border-light
const SURFACE = '#111827'; // saibyl-surface — the halo colour and the hollow fill
const UP = '#22C55E'; // saibyl-positive
const DOWN = '#EF4444'; // saibyl-negative

/**
 * The rendered width of the container, in real pixels.
 *
 * The chart is drawn 1:1 at that width rather than scaled from a fixed
 * viewBox, so 11px type is 11px on every panel width instead of shrinking to
 * five on a narrow one.
 *
 * The first measurement is taken synchronously rather than waiting on the
 * observer. Chrome delivers `ResizeObserver` notifications in a bounded loop
 * and defers the overflow to a later frame; with several charts mounting at
 * once the later ones were still at width 0 when the page settled, so their
 * panels rendered a title, a note and an empty box. A chart that quietly
 * disappears is worse than one that is hard to read. The observer stays, for
 * everything after mount — panel resizes, sidebar toggles, window drags.
 */
function useMeasuredWidth() {
  const ref = useRef<HTMLDivElement>(null);
  const [width, setWidth] = useState(0);

  useLayoutEffect(() => {
    const node = ref.current;
    if (!node) return;
    setWidth(node.getBoundingClientRect().width);
    const observer = new ResizeObserver((entries) => {
      const next = entries[0]?.contentRect.width ?? 0;
      if (next > 0) setWidth(next);
    });
    observer.observe(node);
    return () => observer.disconnect();
  }, []);

  return [ref, width] as const;
}

function yOf(value: number): number {
  const clamped = Math.max(-1, Math.min(1, value));
  return PAD_T + ((1 - clamped) / 2) * PLOT_H;
}

export default function SentimentArcPlot({ slots }: { slots: ArcSlot[] }) {
  const [ref, width] = useMeasuredWidth();
  // React's generated ids carry guillemets, which have no business inside a
  // `url(#…)` reference. Stripped rather than trusted.
  const hatchId = `arc-hatch-${useId().replace(/[^a-zA-Z0-9]/g, '')}`;

  const plotW = Math.max(1, width - PAD_L - PAD_R);
  const band = plotW / Math.max(1, slots.length);
  const colW = Math.min(24, Math.max(6, band * 0.42));
  const capW = colW / 2 + 4; // Caps overhang the column, or they vanish into it.
  const xOf = (index: number) => PAD_L + (index + 0.5) * band;

  // A round number is printed on every slot while "R20" fits, then every kth.
  // Thinned by how much room a label actually has rather than by how many
  // rounds there are: 20 rounds across a wide panel have room for all 20.
  const labelEvery = Math.max(1, Math.ceil(26 / band));
  const showValues = band >= LABEL_MIN_BAND;

  return (
    <div ref={ref} style={{ minHeight: HEIGHT }}>
      {width > 0 && (
        <svg
          width={width}
          height={HEIGHT}
          viewBox={`0 0 ${width} ${HEIGHT}`}
          role="group"
          aria-label="How the room felt in each round, with the range around each figure"
        >
          <defs>
            {/* Browsers implement `<pattern>` consistently, so the hatching that
                vector_charts.py has to draw as explicit line geometry for print
                renderers can be a pattern here. */}
            <pattern
              id={hatchId}
              width="7"
              height="7"
              patternUnits="userSpaceOnUse"
              patternTransform="rotate(45)"
            >
              <line x1="0" y1="0" x2="0" y2="7" stroke={DOWN} strokeWidth="1.2" opacity="0.8" />
            </pattern>
          </defs>

          {/* Grid. Solid hairlines — a dashed grid reads as a threshold. */}
          {AXIS_TICKS.map((tick) => {
            const y = yOf(tick);
            const isZero = tick === 0;
            return (
              <g key={tick}>
                <line
                  x1={PAD_L}
                  y1={y}
                  x2={PAD_L + plotW}
                  y2={y}
                  stroke={isZero ? ZERO_RULE : GRID}
                  strokeWidth="1"
                />
                <text x={PAD_L - 8} y={y + 3.5} textAnchor="end" fontSize="10" fill={INK_SOFT}>
                  {isZero ? '0' : formatSigned(tick, 1)}
                </text>
              </g>
            );
          })}

          {/* What the two ends of the scale mean, in words, so the reader never
              has to be told separately what "+1" is. */}
          <text x={PAD_L - 8} y={yOf(1) + 15} textAnchor="end" fontSize="9" fill={INK_MUTED}>
            loved it
          </text>
          <text x={PAD_L - 8} y={yOf(-1) - 8} textAnchor="end" fontSize="9" fill={INK_MUTED}>
            hated it
          </text>

          {/* Columns, grown from the zero line. This is the encoding that
              survives greyscale: the reader is comparing lengths. */}
          {slots.map((slot, index) => {
            const value = slot.value;
            if (!value || value.n < 1) return null;
            if (value.n < RESOLVED_MIN_N) return null; // drawn below, differently

            const cx = xOf(index);
            const yMean = yOf(value.mean);
            const positive = value.mean >= 0;
            const top = positive ? yMean : ZERO_Y;
            const height = Math.max(1.5, Math.abs(yMean - ZERO_Y));

            return (
              <rect
                key={slot.round}
                x={cx - colW / 2}
                y={top}
                width={colW}
                height={height}
                rx="1"
                fill={positive ? UP : SURFACE}
                fillOpacity={positive ? 0.5 : 1}
                stroke={positive ? UP : DOWN}
                strokeWidth="1"
              />
            );
          })}

          {/* Hatching on the hollow (downward) columns, as a second layer so the
              solid surface fill underneath keeps the gridlines from showing
              through and reading as texture of their own. */}
          {slots.map((slot, index) => {
            const value = slot.value;
            if (!value || value.n < RESOLVED_MIN_N || value.mean >= 0) return null;
            const cx = xOf(index);
            const height = Math.max(1.5, yOf(value.mean) - ZERO_Y);
            return (
              <rect
                key={slot.round}
                x={cx - colW / 2}
                y={ZERO_Y}
                width={colW}
                height={height}
                rx="1"
                fill={`url(#${hatchId})`}
              />
            );
          })}

          {/* The round-over-round move, made literal. Broken wherever the next
              round was not measured or rests on one person — a line drawn
              across either of those would be an interpolation presented as a
              trend, which is the move this whole layer exists to stop. */}
          {slots.slice(0, -1).map((slot, index) => {
            const next = slots[index + 1];
            const a = slot.value;
            const b = next.value;
            if (!a || !b || a.n < RESOLVED_MIN_N || b.n < RESOLVED_MIN_N) return null;
            const x1 = xOf(index);
            const x2 = xOf(index + 1);
            const y1 = yOf(a.mean);
            const y2 = yOf(b.mean);
            return (
              <g key={`link-${slot.round}`}>
                <line x1={x1} y1={y1} x2={x2} y2={y2} stroke={SURFACE} strokeWidth="4" />
                <line
                  x1={x1}
                  y1={y1}
                  x2={x2}
                  y2={y2}
                  stroke={INK_SOFT}
                  strokeWidth="1.75"
                  strokeLinecap="round"
                  opacity="0.85"
                />
              </g>
            );
          })}

          {/* The interval, drawn to the same scale as the column. Laid over a
              surface-coloured halo so it stays readable where it crosses a
              filled column. */}
          {slots.map((slot, index) => {
            const value = slot.value;
            if (!value || value.n < RESOLVED_MIN_N) return null;
            const cx = xOf(index);
            const yUpper = yOf(value.upper);
            const yLower = yOf(value.lower);
            return (
              <g key={slot.round}>
                <line x1={cx} y1={yUpper} x2={cx} y2={yLower} stroke={SURFACE} strokeWidth="4.5" />
                <line x1={cx} y1={yUpper} x2={cx} y2={yLower} stroke={INK} strokeWidth="1.5" />
                <line
                  x1={cx - capW}
                  y1={yUpper}
                  x2={cx + capW}
                  y2={yUpper}
                  stroke={INK}
                  strokeWidth="1.5"
                />
                <line
                  x1={cx - capW}
                  y1={yLower}
                  x2={cx + capW}
                  y2={yLower}
                  stroke={INK}
                  strokeWidth="1.5"
                />
              </g>
            );
          })}

          {/* A round only one person spoke in. The server hands back an interval
              spanning the entire scale for these, which is the truth: there is
              no column to draw because there is no level anyone can stand
              behind. Drawn as a dotted full-height rule with an open marker at
              the figure, so it is visibly a different kind of object from a
              measured column rather than a short one. */}
          {slots.map((slot, index) => {
            const value = slot.value;
            if (!value || value.n < 1 || value.n >= RESOLVED_MIN_N) return null;
            const cx = xOf(index);
            return (
              <g key={slot.round}>
                <line
                  x1={cx}
                  y1={PLOT_TOP}
                  x2={cx}
                  y2={PLOT_BOTTOM}
                  stroke={INK_MUTED}
                  strokeWidth="1.5"
                  strokeDasharray="2 4"
                />
                <circle
                  cx={cx}
                  cy={yOf(value.mean)}
                  r="4.5"
                  fill={SURFACE}
                  stroke={INK_SOFT}
                  strokeWidth="1.75"
                />
              </g>
            );
          })}

          {/* Printed values. Set outside the end of the column; moved beside it
              where the column runs to the edge of the scale and there is no room
              outside; dropped entirely when the slots are too narrow for either.
              A dropped label is never a clipped one — the figure is still on the
              hover, the screen-reader label and the table underneath. */}
          {showValues &&
            slots.map((slot, index) => {
              const value = slot.value;
              if (!value || value.n < 1) return null;

              const cx = xOf(index);
              const yMean = yOf(value.mean);
              const resolved = value.n >= RESOLVED_MIN_N;
              const positive = value.mean >= 0;

              let x = cx;
              let y = resolved
                ? positive
                  ? yOf(value.upper) - 7
                  : yOf(value.lower) + 13
                : yMean - 10;
              let anchor: 'middle' | 'start' = 'middle';

              if (y < PLOT_TOP + 8 || y > PLOT_BOTTOM + 4) {
                if (band < SIDE_LABEL_MIN_BAND) return null;
                // Clear of the cap, not just the column — the caps overhang.
                x = cx + capW + 5;
                y = yMean + 3.5;
                anchor = 'start';
              }

              return (
                <text
                  key={slot.round}
                  x={x}
                  y={y}
                  textAnchor={anchor}
                  fontSize="11"
                  fontWeight="600"
                  fill={resolved ? INK : INK_MUTED}
                  // A halo in the surface colour, painted under the glyphs, so
                  // a figure stays readable where it lands on the trend line or
                  // the dotted rule of a one-person round.
                  stroke={SURFACE}
                  strokeWidth="3.5"
                  strokeLinejoin="round"
                  paintOrder="stroke"
                >
                  {formatSigned(value.mean)}
                </text>
              );
            })}

          {/* Baseline. */}
          <line
            x1={PAD_L}
            y1={PLOT_BOTTOM}
            x2={PAD_L + plotW}
            y2={PLOT_BOTTOM}
            stroke={GRID}
            strokeWidth="1"
          />

          {/* Round labels and captions. An unmeasured round keeps its slot and
              its number and says so underneath, rather than being closed up —
              closing the gap would turn four measured rounds out of five into a
              five-round arc. */}
          {slots.map((slot, index) => {
            const cx = xOf(index);
            // An unmeasured round always keeps its number, even when the rest
            // are thinned. It is the one slot whose label the reader needs, and
            // thinning by index parity was silently hiding half of them.
            const show = slot.value === null || index % labelEvery === 0;
            if (!show) return null;
            return (
              <g key={slot.round}>
                <text
                  x={cx}
                  y={ROUND_LABEL_Y}
                  textAnchor="middle"
                  fontSize="10"
                  fill={slot.value ? INK_SOFT : INK_MUTED}
                >
                  R{slot.round}
                </text>
                {/* A caption is drawn only when it actually fits its slot;
                    the alternative is two captions colliding into an unreadable
                    smear. Nothing is lost when one is dropped — the panel's
                    footnotes name every unmeasured and one-person round in
                    words, so a narrow panel still says which rounds those are. */}
                {slot.caption && slot.caption.length * 4.8 + 6 <= band && (
                  <text
                    x={cx}
                    y={CAPTION_Y}
                    textAnchor="middle"
                    fontSize="9"
                    fill={slot.captionTone === 'alert' ? INK : INK_MUTED}
                    fontWeight={slot.captionTone === 'alert' ? 600 : 400}
                  >
                    {slot.caption}
                  </text>
                )}
              </g>
            );
          })}

          {/* Hit targets last, so they sit above every mark. Each slot is one
              target the full width of its band and the full height of the plot,
              rather than the 24px column — a column at +0.05 is 5px tall. */}
          {slots.map((slot, index) => {
            const interactive = Boolean(slot.onSelect);
            const cx = xOf(index);
            return (
              <g
                key={slot.round}
                role={interactive ? 'button' : 'img'}
                aria-label={slot.description}
                tabIndex={interactive ? 0 : undefined}
                onClick={slot.onSelect}
                onKeyDown={
                  interactive
                    ? (event) => {
                        if (event.key === 'Enter' || event.key === ' ') {
                          event.preventDefault();
                          slot.onSelect?.();
                        }
                      }
                    : undefined
                }
                // The highlight is on the child rect rather than the group, so
                // hovering anywhere in the slot lights the whole slot and not
                // just the marks the pointer happens to be over.
                //
                // The browser's own focus ring is deliberately left in place.
                // Suppressing it in favour of the fill below would stake a
                // keyboard user's only indicator on `:focus-visible` matching
                // an SVG `<g>`, and the ring lands on the slot-sized hit rect,
                // which is the right shape for it anyway.
                className={`focus-visible:[&>rect]:fill-[rgba(255,255,255,0.07)] ${
                  interactive
                    ? 'cursor-pointer hover:[&>rect]:fill-[rgba(255,255,255,0.05)]'
                    : ''
                }`}
              >
                <title>{slot.description}</title>
                <rect
                  x={cx - band / 2}
                  y={PLOT_TOP}
                  width={band}
                  height={PLOT_H + 30}
                  fill="transparent"
                />
              </g>
            );
          })}
        </svg>
      )}
    </div>
  );
}
