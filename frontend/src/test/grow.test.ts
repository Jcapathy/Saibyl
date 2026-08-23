/**
 * The five promises the Grow surface makes, as assertions.
 *
 * Grow sells one thing: **rehearse the change before you make it, and be told
 * honestly when the room could not tell the difference.** Everything under it
 * already existed — the `growth` stage in the server's registry, the shared
 * room reading two things at once, the scoreboard that refuses to name a
 * winner. Grow is the door, and a door has exactly two ways to fail: it can
 * lead somewhere that no longer exists, or it can quietly improve the answer on
 * the way back.
 *
 * So the promises are:
 *
 *   1. It adds nothing  — no run is created here, no endpoint was added
 *   2. The handoff lands — the stage id and both parameters still exist
 *   3. The figures are read from where they are, not from where they look
 *   4. A winner the server declined to name is never invented
 *   5. Server copy is held to the same vocabulary as ours
 *
 * Promise 3 is here because the app gets it wrong today. `MessagesStagePage`
 * reads `response.data.scoreboard`, and the analysis endpoint answers
 * `{simulation_id, schema_version, artifact, generated_at}` — so that read is
 * `undefined` on every run that has ever finished, and the page has never once
 * shown a comparison. Nothing errors. That defect is what promise 3 is shaped
 * to make impossible here, and it is checked by *calling* the reader rather
 * than by reading its source, because the source looked fine at the other call
 * site too.
 */
import { readFileSync, readdirSync } from 'node:fs';
import { join } from 'node:path';

import { describe, expect, it } from 'vitest';

import { SRC, sourceFiles, type SourceFile } from './source';
import { routeNodes } from './routes';
import { SUPPORTED_SCHEMA_VERSION } from '../lib/analysis';
import type {
  AnalysisResponse,
  SimulationAnalysis,
  VariantScore,
  VariantScoreboard,
} from '../lib/analysis';
import {
  GROWTH_STAGE_ID,
  readRehearsal,
  rehearsalHref,
} from '../components/grow/grow';

const GROW_DIR = 'src/components/grow/';
const PAGE = 'src/pages/GrowPage.tsx';

/** Every file the Grow surface is made of. */
function growFiles(): SourceFile[] {
  return sourceFiles().filter(
    (f) => f.path.startsWith(GROW_DIR) || f.path === PAGE,
  );
}

/** The ones that render, as opposed to the ones that only compute. */
function growMarkup(): SourceFile[] {
  return growFiles().filter((f) => f.path.endsWith('.tsx'));
}

describe('0. The scan found the surface', () => {
  it('reads the page and its components', () => {
    // Every assertion below is a claim about a set of files. An empty set —
    // a renamed directory, a `.code` field that stopped being populated —
    // passes them all by finding nothing to check, which is the vacuous-test
    // failure this codebase has now shipped three times.
    const files = growFiles();
    expect(files.map((f) => f.path)).toContain(PAGE);
    expect(files.filter((f) => f.path.startsWith(GROW_DIR)).length).toBeGreaterThan(2);
  });
});

/* ================================================================== */
/*  1. It adds nothing                                                 */
/* ================================================================== */

describe('1. A door, not a second way in', () => {
  it('nothing on this surface creates, changes or deletes anything', () => {
    /*
      The surface is read-only by construction, and that is a product decision
      rather than an accident of scope.

      A run staged at growth is priced and executed from one stored shape. The
      screen that creates runs already quotes it, already enforces the plan's
      ceilings, and already refuses a shape the engine will not run. A second
      creation path here would be a second opinion about what a run is, and the
      way that failure presents is a founder charged for arenas nobody ran —
      which has already happened once in this codebase.

      If a future change genuinely needs to write from this surface, this
      assertion is the conversation, not an obstacle to route around.
    */
    const offenders: string[] = [];
    for (const file of growFiles()) {
      for (const match of file.code.matchAll(/\bapi\.(post|put|patch|delete)\b/g)) {
        const line = file.code.slice(0, match.index).split('\n').length;
        offenders.push(`${file.path}:${line} — api.${match[1]}`);
      }
    }
    expect(offenders).toEqual([]);
  });

  it('the reads it does make are all endpoints that already existed', () => {
    const KNOWN = [
      '/products',
      '/simulations',
      '/simulations/founder-stages',
      '/analysis',
    ];
    const called = new Set<string>();
    for (const file of growFiles()) {
      for (const match of file.code.matchAll(
        /\bapi\s*\.\s*get(?:<[^>]*>)?\(\s*[`'"]([^`'"]+)[`'"]/g,
      )) {
        called.add(match[1]);
      }
    }
    expect(called.size).toBeGreaterThan(0);
    const unknown = [...called].filter(
      (path) => !KNOWN.some((known) => path.includes(known)),
    );
    expect(unknown).toEqual([]);
  });
});

/* ================================================================== */
/*  2. The handoff lands                                               */
/* ================================================================== */

const REGISTRY = join(
  SRC,
  '..',
  '..',
  'backend',
  'app',
  'services',
  'engine',
  'founder_stages.py',
);

function registrySource(): string {
  return readFileSync(REGISTRY, 'utf8');
}

/**
 * The `growth` entry, as a slice of the registry.
 *
 * Bounded by the next entry's key rather than by brace matching, because the
 * dict is written one `StageSpec(` per key in a fixed order and the following
 * key is the only unambiguous terminator that survives reformatting inside the
 * block. If the ordering ever changes, the canary below fails loudly rather
 * than silently scanning an empty slice.
 */
function growthBlock(): string {
  const source = registrySource();
  const start = source.indexOf(`"${GROWTH_STAGE_ID}": StageSpec(`);
  if (start === -1) return '';
  const end = source.indexOf('": StageSpec(', start + 20);
  return end === -1 ? source.slice(start) : source.slice(start, end);
}

/** Every double-quoted string inside one keyword argument of that entry. */
function registryField(name: string): string[] {
  const block = growthBlock();
  const scalar = block.match(new RegExp(`\\b${name}="([^"]*)"`));
  if (scalar) return [scalar[1]];

  const opener = `${name}=[`;
  const at = block.indexOf(opener);
  if (at === -1) return [];
  let depth = 1;
  let i = at + opener.length;
  for (; i < block.length && depth > 0; i += 1) {
    if (block[i] === '[') depth += 1;
    else if (block[i] === ']') depth -= 1;
  }
  // Python joins adjacent literals implicitly, so one sentence can arrive as
  // several matches. Scanned separately is the right granularity here anyway.
  return [...block.slice(at + opener.length, i - 1).matchAll(/"([^"]*)"/g)].map(
    (m) => m[1],
  );
}

describe('2. The handoff lands somewhere that exists', () => {
  it('the registry parsed', () => {
    const block = growthBlock();
    expect(block).not.toEqual('');
    expect(registryField('label')).toEqual(['Growth']);
  });

  it('the stage this surface asks for is still in the server registry', () => {
    /* The failure this prevents is silent and expensive. A stage renamed on the
       server does not 404 — `founder_stage` is nullable, so the run is created
       unstaged, the room is built with the default share instead of this
       moment's much higher one, the write-up is planned from no questions, and
       the founder is charged in full for an answer to a different question. */
    expect(registrySource()).toContain(`"${GROWTH_STAGE_ID}"`);
  });

  it('the screen it hands off to exists, and reads both parameters', () => {
    const href = rehearsalHref('a-product-id');
    const [path, query] = href.split('?');

    const patterns = routeNodes().map((n) => n.pattern);
    expect(patterns.length).toBeGreaterThan(15);
    expect(patterns).toContain(path);

    // Both parameters, read by name on the receiving side. A parameter nothing
    // reads is the "accepted but never used" class, and here its symptom is a
    // founder arriving at a blank wizard having been told they were part-way
    // through one.
    const wizard = sourceFiles().find(
      (f) => f.path === 'src/pages/NewSimulationPage.tsx',
    );
    expect(wizard).toBeDefined();
    for (const key of ['project', 'founder_stage']) {
      expect(query).toContain(`${key}=`);
      expect(wizard!.code).toContain(`searchParams.get('${key}')`);
    }
  });
});

/* ================================================================== */
/*  3 & 4. What the room decided                                       */
/* ================================================================== */

/** A scoreboard with two things on it, and whatever the server concluded. */
function scoreboard(winner: string | null, verdict: string): VariantScoreboard {
  return {
    objective: null,
    objective_intents: [],
    // Only the two fields this reader touches are real; the rest of a score row
    // is a page's problem, not this one's.
    variants: [
      { variant_key: 'a' },
      { variant_key: 'b' },
    ] as unknown as VariantScore[],
    winner_variant_key: winner,
    verdict,
    viral_score_threshold: 0,
    off_message_threshold: 0,
  };
}

function response(
  board: VariantScoreboard | null,
  schemaVersion = SUPPORTED_SCHEMA_VERSION,
): AnalysisResponse {
  return {
    simulation_id: 'sim-1',
    schema_version: schemaVersion,
    generated_at: '2026-08-23T00:00:00Z',
    artifact: { scoreboard: board } as unknown as SimulationAnalysis,
  };
}

describe('3. The figures are read from where they are', () => {
  it('reads the scoreboard out of the artifact', () => {
    const reading = readRehearsal(response(scoreboard('b', 'B did better.')));
    expect(reading).toEqual({ kind: 'ahead', sentence: 'B did better.' });
  });

  it('does not read one sitting at the root of the response', () => {
    /*
      This is the shape of the live defect, written down.

      `GET /simulations/{id}/analysis` answers an envelope. A reader that looks
      at `response.data.scoreboard` finds `undefined` forever, renders its
      "no comparison yet" branch on every finished run, and never errors — so
      nothing anywhere reports it. If someone ever "simplifies" the read in
      `grow.ts` to the root, this fails.
    */
    const misplaced = {
      simulation_id: 'sim-1',
      schema_version: SUPPORTED_SCHEMA_VERSION,
      generated_at: '2026-08-23T00:00:00Z',
      scoreboard: scoreboard('b', 'B did better.'),
      artifact: {},
    } as unknown as AnalysisResponse;

    expect(readRehearsal(misplaced).kind).toEqual('alone');
  });

  it('refuses figures written by a newer build rather than half-reading them', () => {
    // Not ceremony: what decides `winner_variant_key` changed between artifact
    // versions 3 and 4 — independent arenas, then the paired comparison over
    // the shared room — so the same field carries a different claim in an
    // artifact this build does not know. A winner is present here and must
    // still not be reported.
    const reading = readRehearsal(
      response(scoreboard('b', 'B did better.'), SUPPORTED_SCHEMA_VERSION + 1),
    );
    expect(reading.kind).toEqual('withheld');
  });

  it('an older artifact is still read — the schema is additive', () => {
    const reading = readRehearsal(
      response(scoreboard('b', 'B did better.'), SUPPORTED_SCHEMA_VERSION - 1),
    );
    expect(reading.kind).toEqual('ahead');
  });

  it('a run with nothing to compare against says so, rather than failing', () => {
    expect(readRehearsal(response(null)).kind).toEqual('alone');
    expect(readRehearsal(response(scoreboard(null, ''))).kind).not.toEqual('alone');
  });
});

describe('4. A winner the server declined to name is never invented', () => {
  it('an unnamed winner reads as too close, not as the top row', () => {
    const reading = readRehearsal(
      response(
        scoreboard(
          null,
          'No winner: the gap between the two is smaller than the bands around them.',
        ),
      ),
    );
    expect(reading.kind).toEqual('too-close');
    expect(reading.kind).not.toEqual('ahead');
  });

  it('says something even when the server sent an empty conclusion', () => {
    /* The A/A/A control case shipped `verdict=""` once, and the report printed
       "No winner." followed by nothing. A blank line under a refusal reads as a
       broken page, and a founder dismisses a broken page. */
    const reading = readRehearsal(response(scoreboard(null, '')));
    expect(reading.kind).toEqual('too-close');
    if (reading.kind === 'too-close') {
      expect(reading.sentence.trim().length).toBeGreaterThan(20);
    }
  });

  it('the surface renders the refusal as its own result', () => {
    // The reading is only half the promise: a page that computed `too-close`
    // and rendered nothing for it would pass every assertion above.
    const list = growFiles().find((f) => f.path.endsWith('RehearsalList.tsx'));
    expect(list).toBeDefined();
    expect(list!.code).toMatch(/'too-close'/);
    expect(list!.code).toContain('Too close to call.');
  });
});

/* ================================================================== */
/*  5. Server copy is held to the same vocabulary                      */
/* ================================================================== */

/**
 * The banned list, read out of `ia.test.ts` rather than copied.
 *
 * A second hand-written copy of this list is the "two sources of truth"
 * class, and its symptom is the most boring possible one: a word gets added
 * over there, and the check over here goes on passing.
 */
function jargon(): string[] {
  const source = readFileSync(join(SRC, 'test', 'ia.test.ts'), 'utf8');
  const at = source.indexOf('const JARGON = [');
  const end = source.indexOf('];', at);
  // Comments blanked first: the entries are annotated, and an apostrophe in a
  // sentence explaining an entry would otherwise be read as an entry.
  const body = source.slice(at, end).replace(/\/\/[^\n]*/g, '');
  return [...body.matchAll(/'([^']+)'/g)].map((m) => m[1]);
}

function jargonIn(text: string, words: string[]): string[] {
  return words.filter((word) =>
    new RegExp(`\\b${word.replace('/', '\\/')}s?\\b`, 'i').test(text),
  );
}

describe('5. Server copy is held to the same vocabulary as ours', () => {
  it('the banned list was read out of the acceptance suite', () => {
    const words = jargon();
    expect(words.length).toBeGreaterThan(8);
    expect(words).toContain('cohort');
  });

  it('every registry field this surface renders is in the founder’s words', () => {
    /*
      The vocabulary rule is enforced by a scan of *this repo's* source, so a
      banned word arriving from the server renders happily under a green suite.
      This surface renders three fields straight out of the stage registry, and
      they are checked here for the same reason the rest of the app's copy is
      checked: a founder does not care which side of the wire a word came from.
    */
    const words = jargon();
    const offenders: string[] = [];
    for (const field of ['question', 'expected_inputs', 'cannot_conclude']) {
      const values = registryField(field);
      expect(values.length, `${field} did not parse`).toBeGreaterThan(0);
      for (const value of values) {
        for (const word of jargonIn(value, words)) {
          offenders.push(`${field}: "${word}" in ${JSON.stringify(value)}`);
        }
      }
    }
    expect(offenders).toEqual([]);
  });

  it('report_questions stays unrendered, because it does not pass that bar', () => {
    /*
      A ratchet in the other direction, and the reason this file exists at all.

      `report_questions` is written for the report planner, not for a founder,
      and one of the growth entries carries a discipline word the house rules
      ban. It would be an obvious thing for a later session to render here —
      "the questions this answers" is a genuinely good section — so the
      omission is deliberate and pinned. Clean the registry copy first; then
      delete this test in the same change that renders the field.
    */
    expect(jargonIn(registryField('report_questions').join(' '), jargon())).not.toEqual([]);
    for (const file of growFiles()) {
      expect(file.code, `${file.path} renders report_questions`).not.toContain(
        'report_questions',
      );
    }
  });
});

/* ================================================================== */
/*  6. The house rules, on a surface the rail scan does not cover      */
/* ================================================================== */

describe('6. The house rules apply here too', () => {
  /* `railFiles()` covers `pages/product/`, `components/stages/` and a named
     handful. This surface is in neither, so rules 2 and 3 of the acceptance
     suite would pass over it entirely — which is the "a test scoped to the
     files that already pass it is a test of the scope" failure, one directory
     along. They are re-applied here rather than by widening `railFiles()`,
     because that file belongs to the rail. */

  it('no control on this surface is disabled', () => {
    const offenders: string[] = [];
    for (const file of growFiles()) {
      for (const match of file.code.matchAll(/\bdisabled\b/g)) {
        const line = file.code.slice(0, match.index).split('\n').length;
        offenders.push(`${file.path}:${line}`);
      }
    }
    expect(offenders).toEqual([]);
  });

  it('every empty state here offers a way forward', () => {
    const NEARBY = 12;
    const EMPTY_PHRASE = /(No .{0,40} yet|Nothing .{0,40} yet)/i;
    const WAY_FORWARD = /<(Link|Guarded|EmptyState|button)\b|\baction[=:]/;

    const offenders: string[] = [];
    for (const file of growFiles()) {
      const lines = file.code.split(/\r?\n/);
      lines.forEach((line, i) => {
        if (!EMPTY_PHRASE.test(line)) return;
        const near = lines.slice(Math.max(0, i - NEARBY), i + NEARBY).join(' ');
        if (!WAY_FORWARD.test(near)) offenders.push(`${file.path}:${i + 1}`);
      });
    }
    expect(offenders).toEqual([]);
  });

  it('the design system is composed, not re-typed', () => {
    /* The canvas's four rules are a washed ground, depth that means something,
       the dotted eyebrow and one serif phrase. Four hand-rolled copies of one
       system are four dialects of it, which is what a blind critic called this
       app before the restyle — so every rendering file here composes the shared
       primitives, and none of them spells a rule out itself. */
    const markup = growMarkup();
    expect(markup.length).toBeGreaterThan(2);

    const RE_TYPED = /radial-gradient\(|box-shadow\s*:|font-serif|sb-eyebrow/;
    for (const file of markup) {
      expect(file.code, `${file.path} does not compose the design system`).toMatch(
        /from\s+'@\/components\/design(?:\/[^']*)?'/,
      );
      expect(file.code, `${file.path} re-types a design rule`).not.toMatch(RE_TYPED);
    }

    // And no private stylesheet beside them, which is the other way a fourth
    // dialect arrives.
    const stray = readdirSync(join(SRC, 'components', 'grow')).filter((name) =>
      name.endsWith('.css'),
    );
    expect(stray).toEqual([]);
  });
});
