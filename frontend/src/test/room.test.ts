/**
 * The room, and the three ways it is allowed to fail.
 *
 * `design/canvas.json`, annotation `the-room`, states the design rule in one
 * sentence: *"Same measured values underneath — nothing here is decoration
 * standing in for data."* A room drawn from a run's real numbers and a room
 * drawn from plausible ones look identical on screen, which is precisely why
 * this is a test and not a review note. The same defect class already cost this
 * codebase a report viewer that generated its sentiment timeline with
 * `Math.sin()` (`lib/analysis.ts`) and a website revision that invented three
 * certifications the founder does not hold
 * (`backend/app/services/website/claims.py`).
 *
 * Three things are pinned:
 *
 *   1. The motion collapses under `prefers-reduced-motion` — and is the
 *      landing page's motion in the first place, keyframe body for keyframe
 *      body, not a second vocabulary that happens to look similar.
 *   2. A measured value that is absent omits its element. Not a dash, not a
 *      zero, not a greyed row.
 *   3. **No digit reaches the screen that the props did not carry.** This is
 *      the one that catches a fabricated number, and it is checked by walking
 *      every readable string in the view rather than by naming the fields —
 *      a checker scoped to the fields that already pass it is a checker of the
 *      scope.
 *
 * Static, not rendered. `Room.tsx` holds no copy and no arithmetic: it renders
 * `buildRoomView`'s output and nothing else, so the view model *is* the
 * readable surface. Animation delays are the only numbers `Room.tsx` writes,
 * they are CSS timings rather than data, and rule 3 is deliberately about what
 * the founder reads.
 */
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { describe, expect, it } from 'vitest';

// Relative, not the `@/` alias: `tsconfig.test.json` declares no `paths`, so an
// aliased import here passes under vitest and fails under `tsc -b` — which is
// the gate this repo trusts. Same reason `revision_deltas.test.ts` does it.
import {
  MAX_ROWS,
  buildRoomView,
  readableStrings,
  type RoomProps,
} from '../components/room/model';
import type {
  ArchetypeSlice,
  Headline,
  ObjectionSummary,
  QualityBlock,
} from '../lib/analysis';

// `fileURLToPath`, not `URL.pathname` — the repo lives under "Saido Labs LLC"
// and `pathname` hands back `Saido%20Labs%20LLC`, which `readFileSync` cannot
// open. See the same note in `test/source.ts`.
const read = (relative: string): string =>
  readFileSync(fileURLToPath(new URL(relative, import.meta.url)), 'utf8');

const ROOM_CSS = read('../components/room/room.css');
const LANDING_CSS = read('../pages/landing.css');

/* ================================================================== */
/*  Fixtures                                                           */
/* ================================================================== */

const quality: QualityBlock = {
  events_total: 81,
  events_measured: 74,
  coverage_pct: 91.4,
  agents_total: 25,
  agents_active: 24,
  rounds: 3,
  measurement_model: 'sentiment-v2',
  mean_ci_width: 0.38,
  confidence: 'moderate',
  caveats: [],
};

const headline: Headline = {
  valence: { mean: 0.55, lower: 0.36, upper: 0.74, n: 24 },
  stance: { support_pct: 68, oppose_pct: 11, undecided_pct: 9, off_topic_pct: 12 },
  mean_intensity: 0.61,
  polarization_pct: 22,
  novel_claim_pct: 19,
  trajectory: 'flat',
  trajectory_delta: 0.04,
  top_objection_key: 'free_alternative',
};

function slice(archetype: string, agent_count: number): ArchetypeSlice {
  return {
    archetype,
    valence: { mean: 0.5, lower: 0.3, upper: 0.7, n: agent_count },
    stance: { support_pct: 60, oppose_pct: 20, undecided_pct: 15, off_topic_pct: 5 },
    mean_intensity: 0.6,
    event_count: 20,
    agent_count,
    top_objection_keys: [],
  };
}

function objection(
  key: string,
  label: string,
  agent_count: number,
  load_bearing_score: number,
): ObjectionSummary {
  return {
    key,
    label,
    summary: '',
    quotes: [],
    event_ids: [],
    agent_count,
    event_count: agent_count,
    first_round_seen: 1,
    originating_cohort: 'buyer',
    cohort_spread: {},
    propagation: [],
    mean_intensity: 0.6,
    load_bearing_score,
    originated_adversarial: false,
    adversarial_agent_count: 0,
    buyer_agent_count: agent_count,
  };
}

/** A finished run with every measured value the room can draw. */
function fullRun(): RoomProps {
  return {
    pitchName: 'Tallyhook',
    quality,
    headline,
    groups: [slice('Finance lead', 8), slice('Agency owner', 7), slice('Solo founder', 6)],
    objections: [
      objection('free_tool', 'A free tool already does this', 6, 8.2),
      objection('no_need', 'Doubts anyone needs this kind of thing', 6, 7.1),
      objection('happy_now', 'Gets a lot out of what they already use', 4, 5.5),
      objection('price', 'Too expensive for what it is', 2, 1.9),
    ],
  };
}

/* ================================================================== */
/*  1. The motion is the landing page's, and it collapses              */
/* ================================================================== */

/** One `@keyframes` body, whitespace-collapsed. Throws rather than returning ''. */
function keyframeBody(css: string, name: string): string {
  const opener = new RegExp(`@keyframes\\s+${name}\\s*\\{`);
  const line = css.split(/\r?\n/).find((l) => opener.test(l));
  // A missing keyframe must fail loudly. Returning '' would make the parity
  // assertions below pass by comparing nothing to nothing.
  if (!line) throw new Error(`@keyframes ${name} is missing`);
  return line
    .slice(line.indexOf('{') + 1, line.lastIndexOf('}'))
    .replace(/\s+/g, ' ')
    .trim();
}

describe('1. The room moves the way the landing page moves', () => {
  it('collapses every animation and transition under prefers-reduced-motion', () => {
    const start = ROOM_CSS.indexOf('@media (prefers-reduced-motion: reduce)');
    expect(start, 'room.css declares no reduced-motion block').toBeGreaterThan(-1);
    const block = ROOM_CSS.slice(start);

    // The same three declarations landing.css uses, and the same reach: the
    // root, every descendant, and both generated-content pseudo-elements. A
    // block that names only `.sbroom *` leaves the orbits turning, because the
    // rings are children and the stage's own arrival is not.
    expect(block).toMatch(/animation-duration:\s*\.01ms\s*!important/);
    expect(block).toMatch(/animation-iteration-count:\s*1\s*!important/);
    expect(block).toMatch(/transition-duration:\s*\.01ms\s*!important/);
    for (const selector of ['.sbroom,', '.sbroom *,', '.sbroom *::before,', '.sbroom *::after']) {
      expect(block, `reduced-motion block does not cover ${selector}`).toContain(selector);
    }
  });

  it('collapses only its own subtree', () => {
    /*
      Every selector in this sheet is scoped under `.sbroom`.

      The reduced-motion rule is the dangerous one: written as `*, *::before,
      *::after` — which is how landing.css's own block reads before you notice
      the `.v3land` prefix — importing this file would kill motion across the
      whole app from whichever route happened to load it first.
    */
    const withoutComments = ROOM_CSS.replace(/\/\*[\s\S]*?\*\//g, ' ');
    const withoutKeyframes = withoutComments.replace(/@keyframes[^\n]*\n/g, '\n');

    const stray: string[] = [];
    for (const match of withoutKeyframes.matchAll(/([^{}]+)\{/g)) {
      const head = match[1].trim();
      if (!head || head.startsWith('@')) continue;
      for (const selector of head.split(',')) {
        const trimmed = selector.trim();
        if (trimmed && !trimmed.startsWith('.sbroom')) stray.push(trimmed);
      }
    }
    expect(stray).toEqual([]);
  });

  it('reuses the landing page keyframes rather than re-deriving them', () => {
    // Body for body, not merely "also has an orbit". These two files are the
    // sort of pair that drifts silently, and a room that moves differently
    // reads as a different product.
    for (const [here, there] of [
      ['sbroom-slowspin', 'v3land-slowspin'],
      ['sbroom-slowspin-reverse', 'v3land-slowspin-reverse'],
      ['sbroom-chip-float', 'v3land-buyer-float'],
      ['sbroom-blink', 'v3land-blink'],
    ] as const) {
      expect(keyframeBody(ROOM_CSS, here), `${here} drifted from ${there}`).toBe(
        keyframeBody(LANDING_CSS, there),
      );
    }

    /* `core-float` is the one deliberate difference: the room centres its pitch
       on both axes (`translate(-50%,-50%)`) where the landing page pins it to a
       top offset (`translateX(-50%)`). The rotation and the lift — the part
       anybody perceives — are identical, and this asserts that. */
    const core = keyframeBody(ROOM_CSS, 'sbroom-core-float');
    expect(core).toContain('rotate(-9deg)');
    expect(core).toContain('rotate(-5deg) translateY(-10px)');
    expect(keyframeBody(LANDING_CSS, 'v3land-core-float')).toContain('rotate(-5deg) translateY(-10px)');
  });

  it('runs them at the durations the design guide fixes', () => {
    // 20s and 25s counter-rotating, 6s float, 5s drift, 1.7s blink —
    // docs/DESIGN_GUIDE.md §Motion, and landing.css is the authority.
    for (const [what, here, there] of [
      [
        'the inner orbit',
        /\.sbroom-orbit-one\b[^}]*animation:\s*sbroom-slowspin\s+20s\s+linear\s+infinite/,
        /\.orbit\.one\b[^}]*animation:\s*v3land-slowspin\s+20s\s+linear\s+infinite/,
      ],
      [
        'the outer orbit',
        /\.sbroom-orbit-two\b[^}]*animation:\s*sbroom-slowspin-reverse\s+25s\s+linear\s+infinite/,
        /\.orbit\.two\b[^}]*animation:\s*v3land-slowspin-reverse\s+25s\s+linear\s+infinite/,
      ],
      [
        'the floating pitch',
        /\.sbroom-core\b[^}]*animation:\s*sbroom-core-float\s+6s\s+ease-in-out\s+infinite/,
        /\.core-card\b[^}]*animation:\s*v3land-core-float\s+6s\s+ease-in-out\s+infinite/,
      ],
      [
        'the drifting buyers',
        /\.sbroom-chip\b[^}]*animation:\s*sbroom-chip-float\s+5s\s+ease-in-out\s+infinite/,
        /\.buyer\b[^}]*animation:\s*v3land-buyer-float\s+5s\s+ease-in-out\s+infinite/,
      ],
      [
        'the live dot',
        /\.sbroom-live i\b[^}]*animation:\s*sbroom-blink\s+1\.7s\s+infinite/,
        /\.console-live i\b[^}]*animation:\s*v3land-blink\s+1\.7s\s+infinite/,
      ],
    ] as const) {
      expect(ROOM_CSS, `${what} is not on the landing page's timing`).toMatch(here);
      expect(LANDING_CSS, `landing.css moved ${what}; the room did not follow`).toMatch(there);
    }
  });
});

/* ================================================================== */
/*  2. A missing measured value omits its element                      */
/* ================================================================== */

describe('2. What was not measured is not drawn', () => {
  it('drops every count from the eyebrow, the pitch tile and the note when there is no quality block', () => {
    const props = fullRun();
    const view = buildRoomView({ ...props, quality: null });

    // Not "The room · 0 people · 0 rounds", and not an em dash standing where
    // a count would go. The label is true on its own; the counts are absent.
    expect(view.eyebrow).toBe('The room');
    expect(view.pitchMeta).toBeNull();
    expect(view.note ?? '').not.toContain('posts and replies');
    expect(view.note ?? '').not.toContain('said something');

    // With nothing else to say either, the note goes entirely. (The full run
    // keeps one clause even without a quality block — four objections came in
    // and three fit, which is a fact about the props, not about the run's
    // measurement coverage.)
    const quiet = buildRoomView({ ...props, quality: null, objections: [] });
    expect(quiet.note).toBeNull();
  });

  it('omits the sentiment card when nobody said anything measurable', () => {
    const view = buildRoomView({
      ...fullRun(),
      headline: { ...headline, valence: { mean: 0, lower: 0, upper: 0, n: 0 } },
    });

    // `n: 0` means nobody's opinion was measured. A `0.00` here reads as a
    // neutral room, which is a different and untrue claim.
    expect(view.stats.map((s) => s.key)).not.toContain('felt');
    // And the three the run *did* measure still land.
    expect(view.stats.map((s) => s.key)).toEqual(['moved', 'sides', 'ground']);
  });

  it('keeps how split the room was, not only which way it leaned', () => {
    /* `polarization_pct` is measured, and it is the only figure that tells a
       mildly-unconvinced room apart from one split down the middle — two runs
       report the same "% against" either way. `HeadlineStats` showed it and
       this component replaced that one, so its absence would be a measured
       number going missing in a restyle rather than a design choice. */
    const sides = buildRoomView(fullRun()).stats.find((s) => s.key === 'sides');
    expect(sides?.note).toContain('22%');

    /* And it is omitted, not zeroed, when the run did not measure it. The type
       says `number`; the API has shipped nulls into non-nullable analysis
       fields before, which is why `measured()` exists at all — so the guard is
       tested against the shape that actually arrives, cast the same way the
       chip tests in this file do. */
    const without = buildRoomView({
      ...fullRun(),
      headline: { ...headline, polarization_pct: null },
    } as unknown as Parameters<typeof buildRoomView>[0]);
    const bare = without.stats.find((s) => s.key === 'sides');
    expect(bare?.note).not.toContain('opposite side');
    // The half that *was* measured still lands.
    expect(bare?.note).toContain('68% for');
  });

  it('omits a chip’s headcount rather than showing a zero for it', () => {
    const partial = slice('Finance lead', 0) as unknown as Record<string, unknown>;
    // The wire shape an older artifact carries: the field is simply not there.
    delete partial.agent_count;

    const view = buildRoomView({
      ...fullRun(),
      groups: [partial as unknown as ArchetypeSlice],
    });

    expect(view.chips).toHaveLength(1);
    expect(view.chips[0].label).toBe('Finance lead');
    expect(view.chips[0].meta).toBeNull();
  });

  it('omits an objection’s headcount rather than showing a zero for it', () => {
    const partial = objection('free_tool', 'A free tool already does this', 0, 8.2) as unknown as Record<
      string,
      unknown
    >;
    delete partial.agent_count;

    const view = buildRoomView({
      ...fullRun(),
      objections: [partial as unknown as ObjectionSummary],
    });

    expect(view.console?.rows).toHaveLength(1);
    expect(view.console?.rows[0].label).toBe('A free tool already does this');
    expect(view.console?.rows[0].meta).toBeNull();
  });

  it('draws no console when nobody pushed back, and no stats before the numbers exist', () => {
    const view = buildRoomView({ ...fullRun(), objections: [], headline: null });
    expect(view.console).toBeNull();
    expect(view.stats).toEqual([]);
    // The room itself still stands: the pitch and the people in it are real.
    expect(view.isEmpty).toBe(false);
    expect(view.chips.length).toBeGreaterThan(0);
  });

  it('renders nothing at all when there is nothing measured to render', () => {
    // Room.tsx returns null on this. An empty stage with two rings turning is
    // exactly the decoration this design is not allowed to be.
    expect(buildRoomView({ pitchName: '' }).isEmpty).toBe(true);
    expect(buildRoomView({ pitchName: '   ', groups: [], objections: [] }).isEmpty).toBe(true);
  });

  it('counts what it was handed, not what it had room to show', () => {
    const props = fullRun();
    const view = buildRoomView(props);

    // Four objections came in; the console holds three. The header still says
    // four, because a header that counted only the visible rows would shrink
    // the finding to fit the panel.
    expect(view.console?.rows).toHaveLength(MAX_ROWS);
    expect(view.console?.found).toBe('4 found');
    expect(view.note).toContain('worst 3 of 4 shown, worst first');
    // Worst first, by load-bearing score — not by how often it came up.
    expect(view.console?.rows.map((r) => r.key)).toEqual(['free_tool', 'no_need', 'happy_now']);
  });
});

/* ================================================================== */
/*  3. No number the props did not carry                               */
/* ================================================================== */

const NUMERIC = /\d+(?:[.,]\d+)*/g;

/** Every numeric token a founder can read in this view, commas stripped. */
function numbersOnScreen(props: RoomProps): string[] {
  return readableStrings(buildRoomView(props)).flatMap((line) =>
    [...line.matchAll(NUMERIC)].map((match) => match[0].replace(/,/g, '')),
  );
}

describe('3. Nothing here is decoration standing in for data', () => {
  it('puts no digit on screen that did not come from the props', () => {
    const props = fullRun();
    const carried = JSON.stringify(props);

    /* A count of the items the caller passed in *is* carried by the props —
       `objections.length` is not a number this component invented, it is the
       length of the array it was handed. Everything else must appear verbatim
       in the serialised props. */
    const lengths = new Set([
      String(props.objections?.length ?? 0),
      String(props.groups?.length ?? 0),
      String(Math.min(props.objections?.length ?? 0, MAX_ROWS)),
    ]);

    const invented = numbersOnScreen(props).filter(
      (token) => !carried.includes(token) && !lengths.has(token),
    );
    expect(invented).toEqual([]);
  });

  it('reads no number at all from a run that measured none', () => {
    /*
      The load-bearing case, and the one a rendered mock cannot fake its way
      through. Handed nothing but a name, the room must be silent — no `0`, no
      `—`, no `+0.00`, no "0 of 0 replies". Every digit that appeared here would
      be a digit with no measurement behind it.
    */
    expect(numbersOnScreen({ pitchName: 'Tallyhook' })).toEqual([]);
  });

  it('is checking something — the same walk finds the real numbers', () => {
    // The canary for the two assertions above. A `readableStrings` that walked
    // nothing would make both of them pass by finding nothing to object to.
    const found = numbersOnScreen(fullRun());
    expect(found.length).toBeGreaterThan(10);
    expect(found).toContain('0.55');
    expect(found).toContain('74');
    expect(found).toContain('91.4');
  });
});
