/**
 * Every word and every digit the room puts on screen, decided here.
 *
 * `Room.tsx` renders this object and holds no copy of its own. That split is
 * the point rather than a tidiness preference: it makes "nothing here is
 * decoration standing in for data" (`design/canvas.json`, annotation
 * `the-room`) a property a test can check, because the whole readable surface
 * of the component is one plain value with no DOM around it.
 *
 * The rule this file exists to enforce, in the words of `lib/analysis.ts`:
 * nothing computes a metric. It reads what the server measured and formats it.
 * **A value that was not measured is not drawn** — no dash, no zero, no
 * plausible-looking placeholder. `backend/app/services/website/claims.py`
 * documents what that failure costs when it is allowed to happen once.
 *
 * Imported relatively rather than through `@/`: `src/test` is checked by
 * `tsconfig.test.json`, which declares no `paths`, so an aliased import in a
 * module the tests reach fails `tsc -b` while vitest stays green. Same reason
 * `src/test/revision_deltas.test.ts` reaches for a relative path.
 */
import {
  formatSigned,
  type ArchetypeSlice,
  type Headline,
  type ObjectionSummary,
  type QualityBlock,
  type Trajectory,
} from '../../lib/analysis';

/* ── Props ─────────────────────────────────────────────────────────── */

export interface RoomProps {
  /**
   * What sat in the middle of the room — the run's own name
   * (`Simulation.name`). An empty string renders no name rather than a
   * placeholder one.
   */
  pitchName: string;
  /**
   * The kinds of buyer the run measured — `SimulationAnalysis.by_archetype`.
   * Empty on a run that measured no group breakdown, which draws no chips.
   */
  groups?: ArchetypeSlice[];
  /**
   * What they pushed back on — `SimulationAnalysis.objections`. Empty means
   * nobody objected, which draws no console: a room with an empty objection
   * list is a finding, and an empty-looking panel says it better than three
   * grey rows.
   */
  objections?: ObjectionSummary[];
  /**
   * The measured headline — `SimulationAnalysis.headline`. Null or absent
   * until the analysis artifact exists, and then no numbers land.
   */
  headline?: Headline | null;
  /**
   * What the measurement rests on — `SimulationAnalysis.quality`. Supplies
   * every count in the eyebrow, the pitch tile and the note under the room.
   */
  quality?: QualityBlock | null;
  /** Passed through to the root element. */
  className?: string;
}

/* ── The view ──────────────────────────────────────────────────────── */

export interface RoomChip {
  key: string;
  /** The group's name, exactly as the run measured it. */
  label: string;
  /** A monogram of `label` — a rendering of the name, not a stand-in for one. */
  initials: string;
  /** How many people it holds. Null when the slice carried no count. */
  meta: string | null;
  fg: string;
  bg: string;
}

export interface RoomObjectionRow {
  key: string;
  label: string;
  /** How many people raised it. Null when the summary carried no count. */
  meta: string | null;
  color: string;
}

export interface RoomConsole {
  title: string;
  /** "17 found" — a count of what was passed in, never of what is shown. */
  found: string;
  rows: RoomObjectionRow[];
}

export interface RoomStat {
  key: string;
  label: string;
  value: string;
  /** What the value rests on. Null when nothing measured supports a sentence. */
  note: string | null;
  dot: string;
}

export interface RoomView {
  /** "The room", plus whichever counts the run actually carried. */
  eyebrow: string;
  pitchLabel: string;
  /** Null when no name was passed. */
  pitchName: string | null;
  /** Null when nothing measured supports a line under the name. */
  pitchMeta: string | null;
  chips: RoomChip[];
  console: RoomConsole | null;
  /** What the room rests on, in the register `QualityNotice` already uses. */
  note: string | null;
  stats: RoomStat[];
  /**
   * True when there is nothing real to draw. The component renders nothing at
   * all in that case — an empty stage with two rings turning is the decoration
   * this design is not allowed to be.
   */
  isEmpty: boolean;
}

/* ── Palettes ──────────────────────────────────────────────────────── */

/* Colour here encodes position in an ordering, never a magnitude. The
   avatar pairs and the row hues are the landing page's own (`landing.css`
   `.buyer-a`…`.buyer-d`, `--rose` / `--violet` / `--cyan`). */
const CHIP_COLOURS: readonly { fg: string; bg: string }[] = [
  { fg: '#456ce0', bg: '#e8efff' },
  { fg: '#5d4ac4', bg: '#eeeaff' },
  { fg: '#d94f5d', bg: '#ffe9ec' },
  { fg: '#167f93', bg: '#dff9fa' },
  { fg: '#1e5ad9', bg: '#e4edff' },
  { fg: '#0e7d55', bg: '#e2f7ee' },
];

const ROW_COLOURS: readonly string[] = ['#ff6e79', '#8b73ee', '#35c7d5'];

/** Six anchors on the stage; `room.css` positions `.sbroom-slot-{n}`. */
export const MAX_CHIPS = CHIP_COLOURS.length;

/** The console holds three rows before it starts covering the pitch. */
export const MAX_ROWS = ROW_COLOURS.length;

/**
 * Which way sentiment went, in the room's register rather than the method's.
 *
 * `TRAJECTORY_COPY` in `lib/analysis.ts` says the same thing in measurement
 * language ("Sentiment did not move beyond its confidence bands"). That file is
 * shared with the report and is not this one's to rewrite — `QualityNotice`
 * makes the same call about `CONFIDENCE_COPY` for the same reason.
 */
const MOVEMENT: Record<Trajectory, string> = {
  improving: 'Moved up, past the bands it started in',
  declining: 'Moved down, past the bands it started in',
  flat: 'Never left its confidence bands',
};

/* ── Guards ────────────────────────────────────────────────────────── */

/**
 * Whether a number is actually there.
 *
 * The interfaces in `lib/analysis.ts` promise `number`, but an artifact is JSON
 * off the wire and an older one predates fields a newer client knows about —
 * `withSchemaDefaults` fills absent *collections* for exactly that reason and
 * deliberately never fills a value. This is the value-level half of the same
 * rule: the type says a number is there, and this asks.
 */
function measured(value: number | null | undefined): value is number {
  return typeof value === 'number' && Number.isFinite(value);
}

function text(value: string | null | undefined): value is string {
  return typeof value === 'string' && value.trim().length > 0;
}

const count = (value: number): string => value.toLocaleString('en-US');
const pct = (value: number): string => value.toFixed(0);
const people = (value: number): string =>
  `${count(value)} ${value === 1 ? 'person' : 'people'}`;

/**
 * A monogram for a group's name.
 *
 * Derived from the label and from nothing else, so it carries no claim the
 * label does not already make.
 */
export function initialsOf(label: string): string {
  const words = label.trim().split(/\s+/).filter(Boolean);
  if (words.length === 0) return '';
  if (words.length === 1) return words[0].slice(0, 2).toUpperCase();
  return (words[0][0] + words[words.length - 1][0]).toUpperCase();
}

/* ── The build ─────────────────────────────────────────────────────── */

/**
 * The room, assembled from what the run measured and from nothing else.
 *
 * Read it in the order the annotation gives: the room assembles (eyebrow,
 * pitch, chips), then argues (the console), then reports (the stats). Each
 * stage drops out cleanly when its input is missing.
 */
export function buildRoomView(props: RoomProps): RoomView {
  const quality = props.quality ?? null;
  const headline = props.headline ?? null;
  const objections = props.objections ?? [];
  const groups = props.groups ?? [];

  /* — The room assembles — */

  const eyebrowParts: string[] = ['The room'];
  if (quality && measured(quality.agents_total)) {
    eyebrowParts.push(people(quality.agents_total));
  }
  if (quality && measured(quality.rounds)) {
    eyebrowParts.push(`${count(quality.rounds)} rounds`);
  }

  const metaParts: string[] = [];
  if (quality && measured(quality.rounds)) {
    metaParts.push(`${count(quality.rounds)} rounds`);
  }
  if (quality && measured(quality.events_measured)) {
    metaParts.push(`${count(quality.events_measured)} replies`);
  }

  const chips: RoomChip[] = groups
    .filter((slice) => text(slice.archetype))
    /* Biggest groups first, so the six anchors hold the six that most of the
       room belongs to rather than the six the server happened to list first. */
    .slice()
    .sort(
      (a, b) =>
        (measured(b.agent_count) ? b.agent_count : 0) -
        (measured(a.agent_count) ? a.agent_count : 0),
    )
    .slice(0, MAX_CHIPS)
    .map((slice, index) => ({
      key: slice.archetype,
      label: slice.archetype,
      initials: initialsOf(slice.archetype),
      // Not `0 people` and not a dash. A slice that carried no count says
      // nothing about its size, so the chip says nothing about its size.
      meta:
        measured(slice.agent_count) && slice.agent_count > 0
          ? people(slice.agent_count)
          : null,
      fg: CHIP_COLOURS[index].fg,
      bg: CHIP_COLOURS[index].bg,
    }));

  /* — The room argues — */

  const ranked = objections
    .filter((objection) => text(objection.label))
    .slice()
    /* Worst first, by the same load-bearing score `ObjectionMap` ranks on —
       how far it spread × how strongly it was meant × how many kinds of buyer
       raised it. Not most frequent first. */
    .sort(
      (a, b) =>
        (measured(b.load_bearing_score) ? b.load_bearing_score : 0) -
        (measured(a.load_bearing_score) ? a.load_bearing_score : 0),
    );

  const rows: RoomObjectionRow[] = ranked.slice(0, MAX_ROWS).map((objection, index) => ({
    key: objection.key,
    label: objection.label,
    meta:
      measured(objection.agent_count) && objection.agent_count > 0
        ? people(objection.agent_count)
        : null,
    color: ROW_COLOURS[index],
  }));

  const console_: RoomConsole | null =
    rows.length > 0
      ? {
          title: 'What they pushed back on',
          // The count is of everything passed in, not of the three drawn. A
          // header that counted only the visible rows would quietly shrink the
          // finding to fit the panel.
          found: `${count(ranked.length)} found`,
          rows,
        }
      : null;

  /* — What the room rests on — */

  const noteParts: string[] = [];
  if (quality && measured(quality.events_measured) && measured(quality.events_total)) {
    const coverage = measured(quality.coverage_pct)
      ? ` (${quality.coverage_pct.toFixed(1)}%)`
      : '';
    noteParts.push(
      `We could read ${count(quality.events_measured)} of the ${count(
        quality.events_total,
      )} posts and replies${coverage}`,
    );
  }
  if (quality && measured(quality.agents_active) && measured(quality.agents_total)) {
    noteParts.push(
      `${count(quality.agents_active)} of ${count(quality.agents_total)} people said something`,
    );
  }
  if (ranked.length > rows.length) {
    noteParts.push(`worst ${count(rows.length)} of ${count(ranked.length)} shown, worst first`);
  }

  /* — The room reports — */

  const stats: RoomStat[] = [];
  if (headline) {
    const valence = headline.valence;
    if (valence && measured(valence.n) && valence.n > 0 && measured(valence.mean)) {
      stats.push({
        key: 'felt',
        label: 'How the room felt',
        value: formatSigned(valence.mean),
        note:
          valence.n === 1
            ? 'One person, so this is one voice rather than a read of the room.'
            : measured(valence.lower) && measured(valence.upper)
              ? `Between ${formatSigned(valence.lower)} and ${formatSigned(
                  valence.upper,
                )}, across ${people(valence.n)}.`
              : `Across ${people(valence.n)}.`,
        dot: '#2fbf8a',
      });
    }

    const trajectory = headline.trajectory;
    if (trajectory && trajectory in MOVEMENT) {
      const over =
        quality && measured(quality.rounds) ? `, over ${count(quality.rounds)} rounds` : '';
      stats.push({
        key: 'moved',
        label: 'Which way it moved',
        value:
          trajectory === 'flat'
            ? 'Held steady'
            : measured(headline.trajectory_delta)
              ? formatSigned(headline.trajectory_delta)
              : // The direction is measured even when the size of the move is
                // not. Say the half that is real.
                trajectory === 'improving'
                ? 'Moved up'
                : 'Moved down',
        note: `${MOVEMENT[trajectory]}${over}.`,
        dot: '#286cf0',
      });
    }

    const stance = headline.stance;
    if (stance && measured(stance.oppose_pct)) {
      const sides: string[] = [];
      if (measured(stance.support_pct)) sides.push(`${pct(stance.support_pct)}% for`);
      if (measured(stance.undecided_pct)) sides.push(`${pct(stance.undecided_pct)}% undecided`);
      /* How split the room was, as distinct from which way it leaned. Two runs
         can report the same "% against" with one room mildly unconvinced and
         the other split down the middle, and only this number tells them
         apart. Carried over from `HeadlineStats`, which this replaces — a
         measured figure must not go missing in a restyle. */
      const split = measured(headline.polarization_pct)
        ? ` ${pct(headline.polarization_pct)}% of what was said sat on the` +
          " opposite side from the room's average."
        : '';
      stats.push({
        key: 'sides',
        label: 'For and against',
        value: `${pct(stance.oppose_pct)}% against`,
        note: sides.length > 0 ? `${sides.join(', ')}.${split}` : split.trim() || null,
        dot: '#8b73ee',
      });
    }

    if (measured(headline.novel_claim_pct)) {
      stats.push({
        key: 'ground',
        label: 'New ground',
        value: `${pct(headline.novel_claim_pct)}%`,
        note: 'The rest is people repeating each other.',
        dot: '#35c7d5',
      });
    }
  }

  const pitchName = text(props.pitchName) ? props.pitchName.trim() : null;
  const note = noteParts.length > 0 ? `${noteParts.join(' · ')}.` : null;
  const pitchMeta = metaParts.length > 0 ? metaParts.join(' · ') : null;

  return {
    eyebrow: eyebrowParts.join(' · '),
    pitchLabel: 'Your pitch',
    pitchName,
    pitchMeta,
    chips,
    console: console_,
    note,
    stats,
    isEmpty:
      pitchName === null &&
      pitchMeta === null &&
      note === null &&
      chips.length === 0 &&
      console_ === null &&
      stats.length === 0,
  };
}

/**
 * Every string this view puts in front of a founder.
 *
 * Exported for the test that asserts no digit reaches the screen without a
 * prop behind it. Keeping the list here rather than in the test means a field
 * added to `RoomView` is a field this walks — a checker that lives beside the
 * thing it checks does not go stale the way a copied one does.
 */
export function readableStrings(view: RoomView): string[] {
  const out: string[] = [view.eyebrow, view.pitchLabel];
  if (view.pitchName) out.push(view.pitchName);
  if (view.pitchMeta) out.push(view.pitchMeta);
  if (view.note) out.push(view.note);
  for (const chip of view.chips) {
    out.push(chip.label, chip.initials);
    if (chip.meta) out.push(chip.meta);
  }
  if (view.console) {
    out.push(view.console.title, view.console.found);
    for (const row of view.console.rows) {
      out.push(row.label);
      if (row.meta) out.push(row.meta);
    }
  }
  for (const stat of view.stats) {
    out.push(stat.label, stat.value);
    if (stat.note) out.push(stat.note);
  }
  return out;
}
