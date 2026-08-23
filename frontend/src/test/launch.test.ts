/**
 * The promises the Launch surface makes, as assertions.
 *
 * Launch sells one thing, and the landing page says it in a sentence: *"Up to
 * eight versions of the message, head to head, in front of the same room — the
 * winner earns your budget."* Everything under that already existed — the
 * shared swarm, one run per wording, the scoreboard, the messaging document,
 * the outreach. Launch is the door. A door has two ways to fail: it can lead
 * somewhere that no longer exists, or it can quietly improve the answer on the
 * way back.
 *
 * **Promise 1 is here because the app has never once shown this feature.**
 * `MessagesStagePage.tsx` reads `response.data.scoreboard`, and the analysis
 * endpoint answers an envelope — `{simulation_id, schema_version, artifact,
 * generated_at}` — so that read is `undefined` on every run that has ever
 * finished. Stage 5 has rendered its "the comparison has not been worked out
 * yet" branch for every founder, every time, with nothing logged and a green
 * suite throughout. The defect survived because it is invisible from every
 * angle except the one that calls the reader with a payload shaped like the
 * real one.
 *
 * So promise 1 is checked by *calling* the reader, with a fixture in the
 * envelope shape — and, in the same breath, by proving that a scoreboard
 * sitting at the root of the response is **not** read. A test that mocked
 * `{scoreboard: …}` at the root would have stayed green through the entire
 * defect, which is exactly how it survived.
 */
import { readFileSync, readdirSync } from 'node:fs';
import { join } from 'node:path';

import { describe, expect, it } from 'vitest';

import { SRC, sourceFiles, toPattern, type SourceFile } from './source';
import { routeNodes } from './routes';
import { SUPPORTED_SCHEMA_VERSION } from '../lib/analysis';
import type {
  AnalysisResponse,
  PairedComparison,
  SimulationAnalysis,
  VariantScore,
  VariantScoreboard,
} from '../lib/analysis';
import type { Simulation } from '../types';
import {
  canStillTakeWordings,
  isHeadToHead,
  newRunHref,
  readDecision,
  writingHref,
} from '../components/launch/launch';

const LAUNCH_DIR = 'src/components/launch/';
const PAGE = 'src/pages/LaunchPage.tsx';

/** Every file the Launch surface is made of. */
function launchFiles(): SourceFile[] {
  return sourceFiles().filter(
    (f) => f.path.startsWith(LAUNCH_DIR) || f.path === PAGE,
  );
}

/** The ones that render, as opposed to the ones that only compute. */
function launchMarkup(): SourceFile[] {
  return launchFiles().filter((f) => f.path.endsWith('.tsx'));
}

function pageSource(): SourceFile {
  const page = launchFiles().find((f) => f.path === PAGE);
  if (!page) throw new Error(`${PAGE} is missing`);
  return page;
}

describe('0. The scan found the surface', () => {
  it('reads the page and its components', () => {
    // Every assertion below is a claim about a set of files. An empty set — a
    // renamed directory, a `.code` field that stopped being populated — passes
    // them all by finding nothing to check, which is the vacuous-test failure
    // this codebase has now shipped three times.
    const files = launchFiles();
    expect(files.map((f) => f.path)).toContain(PAGE);
    expect(files.filter((f) => f.path.startsWith(LAUNCH_DIR)).length).toBeGreaterThan(1);
  });
});

/* ================================================================== */
/*  Fixtures, in the shape the server actually answers                 */
/* ================================================================== */

/** A scoreboard over two wordings, and whatever the server concluded. */
function scoreboard(
  winner: string | null,
  verdict: string,
  paired: PairedComparison | null = null,
): VariantScoreboard {
  return {
    objective: null,
    objective_intents: [],
    // Only the fields this reader touches are real; the rest of a score row is
    // a rendering page's problem, not this module's.
    variants: [
      { variant_key: 'a', label: 'The time one' },
      { variant_key: 'b', label: 'The money one' },
    ] as unknown as VariantScore[],
    winner_variant_key: winner,
    verdict,
    paired,
    viral_score_threshold: 0,
    off_message_threshold: 0,
  };
}

/**
 * The envelope, exactly as `GET /simulations/{id}/analysis` answers it.
 *
 * Written out in full rather than as a partial, because the whole point of this
 * file is that the *shape* is the thing under test. A fixture that flattened
 * the envelope for convenience would be a fixture agreeing with the bug.
 */
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

/* ================================================================== */
/*  1. The figures are read from where they are                        */
/* ================================================================== */

describe('1. The scoreboard is read out of the envelope', () => {
  it('reads it from `artifact`, which is where the server puts it', () => {
    const decision = readDecision(
      response(scoreboard('b', 'The money one came out ahead.')),
    );
    expect(decision.kind).toEqual('ahead');
    if (decision.kind === 'ahead') {
      expect(decision.sentence).toEqual('The money one came out ahead.');
      // The winning wording's own name, resolved from the key. A founder
      // reading "b came out ahead" learns nothing they can act on.
      expect(decision.winner).toEqual('The money one');
      expect(decision.wordings).toEqual(2);
    }
  });

  it('does not read one sitting at the root of the response', () => {
    /*
      This is the shape of the live defect, written down.

      A reader that looks at `response.data.scoreboard` finds `undefined`
      forever, renders its "no comparison yet" branch on every finished run and
      never errors — so nothing anywhere reports it. That is what stage 5 has
      been doing since it shipped. If someone ever "simplifies" the read in
      `launch.ts` to the root, this fails.
    */
    const misplaced = {
      simulation_id: 'sim-1',
      schema_version: SUPPORTED_SCHEMA_VERSION,
      generated_at: '2026-08-23T00:00:00Z',
      scoreboard: scoreboard('b', 'The money one came out ahead.'),
      artifact: {},
    } as unknown as AnalysisResponse;

    expect(readDecision(misplaced).kind).toEqual('unread');
  });

  it('refuses figures written by a newer build rather than half-reading them', () => {
    // Not ceremony: what decides the winner changed between artifact versions 3
    // and 4 — from independent wordings to the paired comparison over the
    // shared room — so the same field carries a different claim in an artifact
    // this build has never seen. A winner is present here and must still not be
    // reported.
    const decision = readDecision(
      response(scoreboard('b', 'The money one won.'), SUPPORTED_SCHEMA_VERSION + 1),
    );
    expect(decision.kind).toEqual('withheld');
  });

  it('an older artifact is still read — the schema is additive', () => {
    const decision = readDecision(
      response(scoreboard('b', 'The money one won.'), SUPPORTED_SCHEMA_VERSION - 1),
    );
    expect(decision.kind).toEqual('ahead');
  });

  it('a run with nothing on its scoreboard says so rather than failing', () => {
    expect(readDecision(response(null)).kind).toEqual('unread');
  });

  it('carries the paired figures the backend computes and nothing has rendered', () => {
    /* `discordant_agents` is the honest sample size behind every verdict: an
       agent who answered identically to both wordings carries no information
       about which is better. It has been computed since schema 4 and displayed
       nowhere, which is the "computed but never rendered" class this repo logs
       as a defect. */
    const paired: PairedComparison = {
      top_variant_key: 'b',
      against_variant_key: 'a',
      shared_agents: 60,
      discordant_agents: 17,
      mean_difference: 0.08,
      lower: 0.01,
      upper: 0.15,
      separates: true,
    };
    const decision = readDecision(
      response(scoreboard('b', 'The money one came out ahead.', paired)),
    );
    expect(decision.kind).toEqual('ahead');
    if (decision.kind === 'ahead') {
      expect(decision.switched).toEqual({ readBoth: 60, switched: 17 });
    }
  });

  it('a run predating the paired comparison reports no figure rather than zero', () => {
    // Null is not zero. "Nobody changed their mind" and "we did not measure who
    // changed their mind" are opposite claims, and the second one is the truth
    // about a v3 artifact.
    const decision = readDecision(response(scoreboard('b', 'Ahead.')));
    expect(decision.kind).toEqual('ahead');
    if (decision.kind === 'ahead') expect(decision.switched).toBeNull();
  });
});

/* ================================================================== */
/*  2. A winner the server declined to name is never invented          */
/* ================================================================== */

describe('2. The refusal is a result, not an absence', () => {
  it('an unnamed winner reads as too close, never as the top row', () => {
    const decision = readDecision(
      response(
        scoreboard(
          null,
          'No winner: the gap between the leading two is smaller than the bands around them.',
        ),
      ),
    );
    expect(decision.kind).toEqual('too-close');
  });

  it('says something even when the server sent an empty conclusion', () => {
    /* The control case — identical copy in every slot — shipped `verdict=""`
       once, and the report printed "No winner." followed by nothing. A blank
       line under a refusal reads as a broken page, and a founder dismisses a
       broken page. */
    const decision = readDecision(response(scoreboard(null, '')));
    expect(decision.kind).toEqual('too-close');
    if (decision.kind === 'too-close') {
      expect(decision.sentence.trim().length).toBeGreaterThan(20);
    }
  });

  it('the surface renders the refusal in the same weight as a win', () => {
    /*
      The reading is only half the promise: a page that computed `too-close` and
      rendered it as a quiet grey line would pass every assertion above, and a
      founder would read it as a loss rather than as "do not spend on this yet".

      So both branches are asserted to exist, and to be built from the same
      block — the tinted panel, not a bare sentence.
    */
    const panel = launchFiles().find((f) => f.path.endsWith('MessageTests.tsx'));
    expect(panel).toBeDefined();
    expect(panel!.code).toMatch(/'too-close'/);
    expect(panel!.code).toContain('Too close to call.');

    const blocks = [...panel!.code.matchAll(/rounded-xl border border-[^"]*p-3\.5/g)];
    expect(
      blocks.length,
      'a win and a refusal must be the same block in two colours',
    ).toBeGreaterThanOrEqual(2);
  });
});

/* ================================================================== */
/*  3. Which runs belong on this page                                  */
/* ================================================================== */

const VARIANTS_API = join(SRC, '..', '..', 'backend', 'app', 'api', 'variants.py');

function run(fields: Partial<Simulation>): Simulation {
  return { id: 'r', name: 'A run', status: 'draft', variants: 1, ...fields } as Simulation;
}

describe('3. A run is a head-to-head when it was priced for one', () => {
  it('the count it was executed for is what decides it', () => {
    expect(isHeadToHead(run({ variants: 4 }))).toBe(true);
    expect(isHeadToHead(run({ variants: 1 }))).toBe(false);
    // Rows written before the column existed carry null, and a null is one.
    expect(isHeadToHead(run({ variants: null as unknown as number }))).toBe(false);
  });

  it('only runs the server would still accept wordings for are offered', () => {
    /*
      Two sources of truth for one value is the class this codebase produces
      most often, so the second one is read rather than remembered. Offering a
      started run here would be an invitation to a 409 — the copy is frozen the
      moment a run goes, because a comparison whose entries changed mid-flight
      is not a comparison of anything.
    */
    const source = readFileSync(VARIANTS_API, 'utf8');
    const declared = source.match(/_EDITABLE_STATUSES\s*=\s*\{([^}]*)\}/);
    expect(declared, 'the backend no longer declares _EDITABLE_STATUSES').not.toBeNull();

    const statuses = [...declared![1].matchAll(/"([^"]+)"/g)].map((m) => m[1]);
    expect(statuses.length).toBeGreaterThan(0);

    for (const status of statuses) {
      expect(canStillTakeWordings(run({ status })), `${status} should be offered`).toBe(true);
    }
    for (const status of ['running', 'complete', 'failed', 'analyzing']) {
      expect(canStillTakeWordings(run({ status })), `${status} must not be offered`).toBe(false);
    }
    // And a run that already carries several wordings is not offered as one
    // waiting for them, however editable its status is.
    expect(canStillTakeWordings(run({ status: statuses[0], variants: 3 }))).toBe(false);
  });
});

/* ================================================================== */
/*  4. The handoffs land somewhere that exists                         */
/* ================================================================== */

describe('4. Every way out of this page goes somewhere real', () => {
  it('the screens it hands off to are routes in the app', () => {
    const patterns = routeNodes().map((n) => n.pattern);
    expect(patterns.length).toBeGreaterThan(15);

    expect(patterns).toContain(newRunHref('a-product').split('?')[0]);
    expect(patterns).toContain(
      toPattern(writingHref('596ab7f7-4c79-4db7-9282-8edfb658794a')),
    );
  });

  it('the parameter it hands over is read by name on the other side', () => {
    // A parameter nothing reads is the "accepted but never used" class, and
    // here its symptom is a founder arriving at a blank wizard having been told
    // they were part-way through one.
    const [, query] = newRunHref('a-product').split('?');
    expect(query).toContain('project=');

    const wizard = sourceFiles().find(
      (f) => f.path === 'src/pages/NewSimulationPage.tsx',
    );
    expect(wizard).toBeDefined();
    expect(wizard!.code).toContain("searchParams.get('project')");
  });
});

/* ================================================================== */
/*  5. The page adds nothing, and picks nothing for itself             */
/* ================================================================== */

describe('5. A door, not a second way in', () => {
  it('nothing on this surface creates, changes or deletes anything', () => {
    /* The screen that creates runs already quotes the price, enforces the
       plan's ceilings and refuses a shape the engine will not run. A second
       creation path here would be a second opinion about what a run is, and the
       way that failure presents is a founder charged for work nobody ran —
       which has already happened once in this codebase. */
    const offenders: string[] = [];
    for (const file of launchFiles()) {
      for (const match of file.code.matchAll(/\bapi\.(post|put|patch|delete)\b/g)) {
        const line = file.code.slice(0, match.index).split('\n').length;
        offenders.push(`${file.path}:${line} — api.${match[1]}`);
      }
    }
    expect(offenders).toEqual([]);
  });

  it('the reads it makes are all endpoints that already existed', () => {
    const KNOWN = ['/products', '/simulations', '/analysis'];
    const called = new Set<string>();
    for (const file of launchFiles()) {
      for (const match of file.code.matchAll(
        /\bapi\s*\.\s*get(?:<[^>]*>)?\(\s*[`'"]([^`'"]+)[`'"]/g,
      )) {
        called.add(match[1]);
      }
    }
    expect(called.size).toBeGreaterThan(0);
    expect([...called].filter((p) => !KNOWN.some((k) => p.includes(k)))).toEqual([]);
  });

  it('the run behind the two written artifacts is the one the server named', () => {
    /*
      `GET /simulations` orders on `created_at`; the rail sorts on `completed_at
      or created_at`. A run that started earlier and finished later is the
      latest to one of them and not the other — so a page choosing "the latest"
      for itself will eventually show a founder a different answer from the one
      the rail says they have.

      The objections both artifacts are built from are produced at step 2, so
      the run is that step's own `produced_by` and this page never picks one.
    */
    const page = pageSource();
    expect(page.code).toMatch(/findStage\(\s*selected\s*,\s*'reactions'\s*\)/);
    expect(page.code).toContain('produced_by');
    expect(
      page.code,
      'the page is choosing a run by date instead of taking the server’s',
    ).not.toMatch(/\.sort\(|completed_at/);
  });

  it('both re-homed artifacts are actually on the page', () => {
    // The whole reason this page exists is that these two were behind a nav
    // item nobody understood. Losing one in the move would be the same defect
    // wearing a new label.
    const page = pageSource();
    expect(page.code).toContain('<MessagingDocPanel');
    expect(page.code).toContain('<OutboundPanel');
    expect(page.code).toContain('<MessageTests');
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
    for (const file of launchFiles()) {
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
    for (const file of launchFiles()) {
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
    const markup = launchMarkup();
    expect(markup.length).toBeGreaterThan(1);

    const RE_TYPED = /radial-gradient\(|box-shadow\s*:|font-serif|sb-eyebrow/;
    for (const file of markup) {
      expect(file.code, `${file.path} does not compose the design system`).toMatch(
        /from\s+'@\/components\/design(?:\/[^']*)?'/,
      );
      expect(file.code, `${file.path} re-types a design rule`).not.toMatch(RE_TYPED);
    }

    // And no private stylesheet beside them, which is the other way a fourth
    // dialect arrives.
    const stray = readdirSync(join(SRC, 'components', 'launch')).filter((name) =>
      name.endsWith('.css'),
    );
    expect(stray).toEqual([]);
  });

  it('the page says what stage of a company it is for', () => {
    /*
      The nav label this replaced was "What to say", which the founder called
      unintuitive — and he was right: it names a sentence, not a moment in a
      company's life. The page's own words have to carry it, because a nav label
      is one word and this page is a stage.
    */
    const page = pageSource();
    expect(page.code).toContain('eyebrow="Go to market"');
    expect(page.code).toContain('title="Launch"');
    expect(page.code).toMatch(/take it to market/i);
  });
});
