/**
 * The six acceptance tests for the staged rail.
 *
 * They exist because the person who built the rail is the worst available judge
 * of whether it reads well — every label looks obvious to whoever wrote it. So
 * most of the judgement is turned into assertions here, and the residue is
 * judged by a reader who has not seen the design.
 *
 * Each one is mechanical. No screenshots, no rendering, no opinion.
 *
 *   1. Jargon        — no discipline vocabulary in anything that renders
 *   2. No dead ends  — every empty state offers a way forward
 *   3. No grey button — no disabled control without an explanation beside it
 *   4. Inheritance   — every stage declares what it got, or what is missing
 *   5. Reachability  — every built route is ≤ 3 clicks from /app
 *   6. One design    — every page composes the shared design primitives
 *
 * Where a rule is not yet true of the whole app, the exceptions are **listed by
 * name with a reason** and the count is asserted. That is a ratchet: the debt
 * cannot grow, and it is visible rather than hidden behind a convenient glob.
 * A test scoped to only the files that pass it is a test of the scope.
 */
import { readFileSync } from 'node:fs';
import { join } from 'node:path';

import { describe, expect, it } from 'vitest';

import { railFiles, renderedStrings, sourceFiles, SRC } from './source';
import { clickDepths, componentSources, routeNodes } from './routes';

/* ================================================================== */
/*  1. Jargon                                                          */
/* ================================================================== */

/**
 * Words a founder should never have to learn to use this product.
 *
 * `simulation` is here as a noun the reader must understand. It survives in the
 * legacy surfaces listed below and in URLs, which nobody reads as prose.
 */
const JARGON = [
  'ICP',
  'variant',
  'A/B',
  'adversarial',
  'cohort',
  'arena',
  'lens',
  'archetype',
  'canonical',
  'valence',
  'simulation',
  // The word the design replaced. A founder has a *product*; a consultant has
  // projects, and the noun decides who the page thinks it is talking to. It was
  // missing from this list entirely, so an acceptance reader found it rendering
  // on step 1 — inside the very file named as the register to match.
  'project',
];

/**
 * Legacy surfaces that still carry the vocabulary, with why each is still here.
 *
 * These are the pages the rail does not lead to. They remain reachable on
 * purpose — see `AppLayout.tsx` — and rewriting all of their copy is a separate
 * piece of work from building the rail. Listing them by name is the point: the
 * debt is countable, and the assertion below fails if it grows.
 */
const JARGON_DEBT: Record<string, string> = {};

function jargonHits(files: ReturnType<typeof sourceFiles>) {
  const hits: { path: string; word: string; text: string }[] = [];
  for (const file of files) {
    for (const text of renderedStrings(file)) {
      for (const word of JARGON) {
        // `s?` because the plural is the form that actually ships. `\bsimulation\b`
        // does not match "Simulations", so the sidebar's usage-bar label survived
        // a green run of this test and was found by screenshotting the page.
        const pattern = new RegExp(`\\b${word.replace('/', '\\/')}s?\\b`, 'i');
        if (pattern.test(text)) hits.push({ path: file.path, word, text });
      }
    }
  }
  return hits;
}

describe('1. Jargon', () => {
  it('the staged rail uses no word a founder has to learn', () => {
    const hits = jargonHits(railFiles());
    expect(
      hits.map((h) => `${h.path}: "${h.word}" in ${JSON.stringify(h.text)}`),
    ).toEqual([]);
  });

  it('no surface outside the listed legacy debt carries jargon', () => {
    const debt = new Set(Object.keys(JARGON_DEBT));
    const hits = jargonHits(sourceFiles().filter((f) => !debt.has(f.path)));
    expect(
      hits.map((h) => `${h.path}: "${h.word}" in ${JSON.stringify(h.text)}`),
    ).toEqual([]);
  });

  it('the legacy debt list names only files that still exist', () => {
    const present = new Set(sourceFiles().map((f) => f.path));
    const stale = Object.keys(JARGON_DEBT).filter((p) => !present.has(p));
    expect(stale).toEqual([]);
  });
});

/* ================================================================== */
/*  2. No dead ends                                                    */
/* ================================================================== */

describe('2. No dead ends', () => {
  it('every empty state on the rail renders a way forward', () => {
    /*
      Proximity, not presence.

      The first version asked whether a link existed *anywhere in the file*,
      and every rail page already contains one — so it could not fail. An
      acceptance reader proved it by pasting a literal dead end into a stage
      page and watching the suite stay green.

      A way forward now has to sit within 12 lines of the phrase that says
      there is nothing here, which is roughly "in the same block on the same
      screen". `EmptyState` remains the structural guarantee — it requires an
      `action` and the type refuses a screen without one — and this is the
      check that the guarantee is the one actually being used.
    */
    const NEARBY = 12;
    /* The phrase has to *finish* on "yet".
     *
     * An empty state is a claim that a surface has nothing on it, and it stops
     * there: "No versions tested yet", "Nothing to report yet." Reassurance
     * inside a form hint reads the same for four words and then keeps going —
     * `NewProductPage` says "And nothing written yet **is fine** — the next step
     * takes a deck or a landing page", which the old pattern flagged as a dead
     * end on a screen whose whole point is the two buttons under it.
     *
     * Requiring a sentence boundary is what separates the two, and it is a
     * tighter rule rather than a looser one: widening the proximity window
     * instead would have let a real dead end pass anywhere in twice the file.
     */
    const EMPTY_PHRASE = /(No |Nothing ).{0,40} yet(?=[.!?"'`<}]|\s*$)/i;
    /* `Action` joined the list on 2026-08-23 with the design primitive of that
       name. It is polymorphic — `<Action as={Link} to=…>` — so the raw `<Link`
       it used to render no longer appears in the source, and without this the
       rule would fire on a page that had just been given a *better* way
       forward than it had before. It counts for the same reason `Guarded`
       does: it is a control, and a control is a way out. */
    const WAY_FORWARD = /<(Link|Guarded|EmptyState|Action|button)\b|\baction[=:]/;

    const offenders: string[] = [];
    for (const file of railFiles()) {
      const lines = file.code.split(/\r?\n/);
      lines.forEach((line, i) => {
        if (!EMPTY_PHRASE.test(line)) return;
        const near = lines
          .slice(Math.max(0, i - NEARBY), i + NEARBY)
          .join(' ');
        if (!WAY_FORWARD.test(near)) offenders.push(`${file.path}:${i + 1}`);
      });
    }
    expect(offenders).toEqual([]);
  });

  it('EmptyState cannot be constructed without an action', () => {
    const primitives = sourceFiles().find(
      (f) => f.path === 'src/components/stages/StagePrimitives.tsx',
    );
    expect(primitives).toBeDefined();
    // `action` is required — not `action?`. If this ever gains a `?`, a screen
    // with no way forward becomes constructible and the type stops guarding.
    //
    // Scoped to EmptyState's own prop block. `Guarded`'s `blockedBy` carries an
    // optional `action?` for the case where the reason is the whole answer, and
    // matching on the bare word across the file would conflate the two.
    const emptyStateProps = primitives!.code
      .slice(primitives!.code.indexOf('export function EmptyState('))
      .slice(0, 400);
    expect(emptyStateProps).toMatch(/action:\s*StageAction;/);
    expect(emptyStateProps).not.toMatch(/action\?:\s*StageAction/);
  });
});

/* ================================================================== */
/*  3. Never a grey button                                             */
/* ================================================================== */

describe('3. Never a grey button', () => {
  it('no control on the rail is disabled', () => {
    // The binding rule: a stage either runs and states what the answer will be
    // missing, or it is blocked with the button that unblocks it. There is no
    // third rendering, so there is no `disabled` on the rail at all.
    const offenders: string[] = [];
    for (const file of railFiles()) {
      for (const match of file.code.matchAll(/\bdisabled\b/g)) {
        const line = file.code.slice(0, match.index).split('\n').length;
        offenders.push(`${file.path}:${line}`);
      }
    }
    expect(offenders).toEqual([]);
  });

  it('nowhere in the app is a control greyed by a precondition', () => {
    /* **The rail was never where this rule was being broken.**
     *
     * The check above scans `railFiles()` and has always passed. On 2026-08-23
     * a sweep found three live grey buttons outside that set — in
     * `founder/`, `marketing/` — each greyed by a precondition with no
     * explanation beside it:
     *
     *   disabled={!projectId || synthesizing}
     *   disabled={saving || filled === 1}
     *   disabled={selected.length === 0 || launching}
     *
     * The rule the founder wrote has no "on the rail" in it. A control either
     * runs and states what its answer will be missing, or it is blocked with
     * the reason and the button that unblocks it.
     *
     * **`disabled={busy}` is not that, and stays allowed.** It does not
     * withhold an action on a condition the founder could fix — the click
     * already landed and the answer is on its way, so re-firing it would
     * double-charge. `StagePrimitives`' own `Guarded` draws exactly this line:
     * "`busy` is separate and does not disable anything conceptually — it says
     * the click already landed."
     */
    /* Matched on the TAIL of the identifier, not the whole of it, because a
       busy flag is routinely scoped by what it is busy with —
       `variantResetting`, `interviewLoading`. Anchoring to the whole name
       flagged both of those as preconditions, which would have pushed somebody
       to "fix" a correct double-submit guard. */
    const BUSY =
      /(saving|loading|busy|submitting|launching|drafting|running|synthesizing|regenerating|resetting|uploading|deleting|purging|exporting|generating|fetching|refreshing|working|pending|inflight)$/i;

    const offenders: string[] = [];
    for (const file of sourceFiles()) {
      // `disabled={…}` only — `disabled:opacity-40` inside a className is a
      // Tailwind style for the state, not a decision to enter it.
      for (const match of file.code.matchAll(/\bdisabled=\{([^}]*)\}/g)) {
        const expr = match[1].trim();
        // Every operand of the guard must be a busy flag. One precondition in
        // the expression is enough to make the button grey for a reason the
        // founder can act on, which is the case this rule exists for.
        const operands = expr.split(/\|\||&&/).map((s) => s.trim().replace(/^!/, ''));
        if (operands.every((o) => BUSY.test(o))) continue;
        const line = file.code.slice(0, match.index).split('\n').length;
        offenders.push(`${file.path}:${line} — disabled={${expr}}`);
      }
    }
    expect(offenders).toEqual([]);
  });

  it('Guarded offers no way to spell a silent disable', () => {
    const primitives = sourceFiles().find(
      (f) => f.path === 'src/components/stages/StagePrimitives.tsx',
    );
    expect(primitives).toBeDefined();
    // No `disabled` prop exists. `blockedBy` takes the reason and the way out,
    // so the explanation cannot be forgotten — it is the only spelling.
    expect(primitives!.code).not.toMatch(/disabled\??:\s*boolean/);
    expect(primitives!.code).toMatch(/blockedBy\?:/);
    expect(primitives!.code).toMatch(/reason:\s*string/);
  });
});

/* ================================================================== */
/*  4. Inheritance is declared                                         */
/* ================================================================== */

describe('4. Inheritance is declared', () => {
  const STAGE_PAGES = [
    'src/pages/product/AudienceStagePage.tsx',
    'src/pages/product/ReactionsStagePage.tsx',
    'src/pages/product/AnswersStagePage.tsx',
    'src/pages/product/BuyersStagePage.tsx',
    'src/pages/product/MessagesStagePage.tsx',
  ];

  it('all five stage pages exist', () => {
    const present = new Set(sourceFiles().map((f) => f.path));
    expect(STAGE_PAGES.filter((p) => !present.has(p))).toEqual([]);
  });

  it('every stage page renders StageHeader', () => {
    const byPath = new Map(sourceFiles().map((f) => [f.path, f]));
    const missing = STAGE_PAGES.filter(
      (p) => !/<StageHeader\b/.test(byPath.get(p)?.code ?? ''),
    );
    expect(missing).toEqual([]);
  });

  it('StageHeader always renders inherited state or a missing-input notice', () => {
    const header = sourceFiles().find(
      (f) => f.path === 'src/components/stages/StageHeader.tsx',
    );
    expect(header).toBeDefined();
    expect(header!.code).toMatch(/<Inherited\b/);
    expect(header!.code).toMatch(/<Missing\b/);
    // And says so explicitly in the one case neither can cover, rather than
    // rendering an empty header that reads as "nothing to tell you".
    expect(header!.code).toMatch(
      /inherited\.length === 0 && stage\.missing\.length === 0/,
    );
  });

  it('all three declaration kinds are marked in the DOM so this is checkable', () => {
    const primitives = sourceFiles().find(
      (f) => f.path === 'src/components/stages/StagePrimitives.tsx',
    );
    expect(primitives!.code).toMatch(/data-stage-declares="inherited"/);
    expect(primitives!.code).toMatch(/data-stage-declares="missing"/);
    // `stale` is the third: the stage inherited the input, and the answer
    // already on the page was produced without it. Marked because it is the
    // one a founder is most likely to mistake for one of the other two.
    expect(primitives!.code).toMatch(/data-stage-declares="stale"/);
  });

  it('a stale result is not spelled as a missing input', () => {
    // They carry the same three fields and make opposite statements. If `Stale`
    // ever renders through `Missing`, a finished wrong answer starts reading as
    // a caution about a future run — which is the confusion it exists to end.
    const primitives = sourceFiles().find(
      (f) => f.path === 'src/components/stages/StagePrimitives.tsx',
    );
    expect(primitives!.code).toMatch(/export function Stale\(/);

    const header = sourceFiles().find(
      (f) => f.path === 'src/components/stages/StageHeader.tsx',
    );
    expect(header!.code).toContain('<Stale result=');
  });
});

/* ================================================================== */
/*  5. Reachability                                                    */
/* ================================================================== */

/**
 * Routes that are deliberately not reachable by clicking.
 *
 * Both are arrived at from somewhere other than a link: `/app/simulations/:p/run`
 * is where the configurator sends you after starting a run, and the print view
 * is opened by the browser's own print flow. Listed rather than excluded by a
 * pattern, so adding a third requires saying why.
 */
const NOT_CLICKABLE: Record<string, string> = {
  '/app/simulations/:p/run': 'entered by the configurator after a run starts',
  '/app/simulations/:p/report/print': 'opened by the print flow, not by a link',
  // Retired paths kept alive for bookmarks and shared links. Each renders an
  // `<Absorbed>` redirect to the stage that took it over, so nothing links to
  // them on purpose — being unlinked is the point, not an oversight. That they
  // still lead somewhere sensible is asserted below, by their own test.
  '/app/ip-check': 'absorbed by Validate; kept as a redirect for old links',
  '/app/website': 'absorbed by Position; kept as a redirect for old links',
  '/app/sales': 'absorbed by Launch; kept as a redirect for old links',
  '/app/marketing': 'absorbed by Launch; kept as a redirect for old links',
};

/**
 * Routes deliberately pushed out of the primary navigation.
 *
 * Companies. GTM discovery ranks candidates against a buyer archetype rather
 * than against any intent to buy, and on a live security run it returned the
 * competitors building the same product — companies that would never be
 * customers. The founder's call was to drop it from the product; the module,
 * its routes and its backend stay, so the call is reversible.
 *
 * Exempt from the depth budget and **not** from reachability. Demoted is not
 * deleted: if the last link into Companies disappears the test above still
 * fails, because a route nothing can reach is a different mistake from a route
 * somebody chose to bury.
 */
const DEMOTED: Record<string, string> = {
  '/app/prospects/settings': 'Companies, demoted 2026-08-23; reachable from the list',
};

describe('5. Reachability', () => {
  it('the route graph parsed', () => {
    const nodes = routeNodes();
    // A parser that silently returns nothing would make every assertion below
    // pass vacuously. This is the canary.
    expect(nodes.length).toBeGreaterThan(15);
    expect(nodes.map((n) => n.pattern)).toContain('/app/products/:p/audience');
  });

  it('every built feature is reachable in three clicks or fewer', () => {
    const depths = clickDepths();
    const unreachable: string[] = [];
    const tooDeep: string[] = [];

    for (const node of routeNodes()) {
      if (!node.pattern.startsWith('/app')) continue;
      if (node.pattern in NOT_CLICKABLE) continue;
      const depth = depths.get(node.pattern);
      if (depth === undefined) unreachable.push(node.pattern);
      // A demoted route is still checked for reachability — losing the last
      // link into Companies must still fail — but not for depth.
      else if (depth > 3 && !(node.pattern in DEMOTED)) {
        tooDeep.push(`${node.pattern} (${depth})`);
      }
    }

    // This is the test that would have caught the original defect: Audiences,
    // Companies and the whole scoreboard shipped with no route to them.
    expect({
      unreachable: [...new Set(unreachable)].sort(),
      tooDeep: [...new Set(tooDeep)].sort(),
    }).toEqual({ unreachable: [], tooDeep: [] });
  });

  it('every stage the landing page sells is one click from anywhere', () => {
    /* Reachable is not the same as findable, and the difference cost us the
       flagship.

       The website check and the three sales artifacts were reachable — three
       clicks, inside a product's rail — so the test above passed while a
       founder on `/app/home` had no way to know they existed. The only route
       in was a nav item called "Everything you uploaded". Two rounds of
       adversarial review missed it too, because every check called the API
       directly and none asked what a person can click.

       The names a founder goes looking for are now the five the landing page
       taught him on the way in. Those are the primary nav, so those are what
       must be one click; the modules live inside their stage. */
    const depths = clickDepths();
    const buried: string[] = [];
    for (const [path, what] of [
      ['/app/validate', 'Validate — is anyone going to want this'],
      ['/app/position', 'Position — say it so the room hears it'],
      ['/app/launch', 'Launch — the words that go out'],
      ['/app/grow', 'Grow — what to build, and for whom, next'],
      ['/app/capital', 'Raise — the family-office shortlist'],
      ['/app/dashboard', 'the reports export surface'],
    ] as const) {
      const depth = depths.get(path);
      if (depth === undefined || depth > 1) {
        buried.push(`${path} — ${what} — ${depth ?? 'unreachable'} clicks`);
      }
    }
    expect(buried).toEqual([]);
  });

  it('every retired path still lands on the stage that absorbed it', () => {
    /* Four modules lost their own noun when the nav became the journey, and
       their pages were deleted rather than left as a second implementation of
       a screen. The paths stay: a bookmark, a shared link or muscle memory
       would otherwise fall through the catch-all onto the marketing site,
       which reads as "your account is gone".

       Checked against `App.tsx` rather than through `clickDepths`, because
       being unlinked is the point — a redirect nothing points at is exactly
       what these are, and a reachability walk cannot tell that apart from a
       route somebody forgot to wire. */
    const app = sourceFiles().find((f) => f.path === 'src/App.tsx');
    expect(app, 'App.tsx not found by the source scan').toBeDefined();

    const broken: string[] = [];
    for (const [retired, stage] of [
      ['ip-check', '/app/validate'],
      ['website', '/app/position'],
      ['sales', '/app/launch'],
      ['marketing', '/app/launch'],
    ] as const) {
      const declared = new RegExp(
        `path="${retired}"[^\\n]*<Absorbed by="${stage}"`,
      );
      if (!declared.test(app!.code)) broken.push(`${retired} -> ${stage}`);
    }
    expect(broken).toEqual([]);
  });

  it('nothing links to a path that only redirects', () => {
    /* A link that bounces is a link that rots quietly: it keeps working, so
       nobody notices it names a surface that no longer exists, and the next
       person to read it learns the wrong map of the app. Four of these were
       live when the stages landed — `WhatNext` still sent people to the
       clearance page, and three surfaces still sent them to Message tests. */
    const RETIRED = ['/app/ip-check', '/app/website', '/app/sales', '/app/marketing'];
    const offenders: string[] = [];
    for (const file of sourceFiles()) {
      if (file.path === 'src/App.tsx') continue;
      for (const path of RETIRED) {
        // A route target, not prose: quoted, and followed by `"`, `?` or a
        // template hole rather than by more path.
        if (new RegExp(`['"\`]${path}(\\?|['"\`]|\\$\\{)`).test(file.code)) {
          offenders.push(`${file.path} -> ${path}`);
        }
      }
    }
    expect(offenders).toEqual([]);
  });

  it('the five steps are each one click from a product', () => {
    const depths = clickDepths();
    for (const segment of [
      'audience',
      'reactions',
      'answers',
      'buyers',
      'messages',
    ]) {
      const depth = depths.get(`/app/products/:p/${segment}`);
      expect(depth, `${segment} is unreachable`).toBeDefined();
      expect(depth!, `${segment} is ${depth} clicks away`).toBeLessThanOrEqual(3);
    }
  });

  it('there is no Crisis route, nav item or label anywhere', () => {
    // Deferred by explicit decision. Not as a nav item, not greyed out, not
    // "coming soon" — a stage that leads nowhere is worse than one that is not
    // there yet.
    const offenders: string[] = [];
    for (const file of sourceFiles()) {
      for (const text of renderedStrings(file)) {
        if (/\bcrisis\b/i.test(text)) offenders.push(`${file.path}: ${text}`);
      }
      if (/['"`]\/app\/crisis/.test(file.code)) offenders.push(`${file.path}: route`);
    }
    expect(offenders).toEqual([]);
  });
});

/* ================================================================== */
/*  6. One design, composed rather than re-typed                       */
/* ================================================================== */

/**
 * The founder approved a design canvas on 2026-08-20 — `design/`, four
 * artboards and `design/canvas.json`, whose annotations state the rules
 * verbatim. Three days later a session built two brand-new app pages without
 * ever opening that folder, because nothing in the repo pointed at it, and the
 * founder found the drift himself on his first read-through of the site.
 *
 * The pointers now exist (`CLAUDE.md`, `design/README.md`, `docs/HANDOFF.md`
 * §2) but prose is the weakest possible guarantee: a cold session reads a
 * compaction summary, not the file, and the summary is where "read `design/`
 * first" quietly stops existing. So the rule is also a test.
 *
 * A page that renders its own top-level heading is a page a founder looks at
 * whole. Every one of them must compose `src/components/design/` rather than
 * re-typing a washed ground, a dotted eyebrow, a soft-shadow card or a
 * serif-italic phrase inline — because four hand-rolled copies of one system
 * are four dialects of it, which is exactly what a blind critic called the app
 * before the restyle.
 */
const DESIGN_PRIMITIVES =
  /from\s+['"](?:@\/|(?:\.\.?\/)+)components\/design(?:\/[^'"]*)?['"]/;

/**
 * A page-level heading — either spelled out, or composed.
 *
 * `<PageHeader>` had to join this on 2026-08-23, and the reason is a hole this
 * check had from the day it was written: the primitive **renders the `<h1>`
 * itself**, so the moment a page was converted it stopped matching `<h1`,
 * dropped out of the scan entirely, and left through the same door as a page
 * with no heading at all. The sweep would have "passed" by making its own
 * subject invisible — and the canary counting the scanned pages would have gone
 * down, not up, as the work succeeded.
 *
 * **`<Hero>` had to join it the same day, for the identical reason, and it was
 * missed at first.** `GuidePage` was converted to a longform hero and quietly
 * left the scan — the fix above was applied to one primitive and not to the
 * concept, so the next primitive that rendered an `<h1>` reopened the hole. A
 * reviewing agent caught it. If a third heading primitive is ever added, it
 * belongs here in the same commit.
 */
const TOP_LEVEL_HEADING = /<h1[\s/>]|<PageHeader[\s/>]|<Hero[\s/>]/;

/**
 * Pages that carry the system directly instead of through the primitives.
 *
 * These three style from `pages/landing.css` — the approved stylesheet the
 * whole system was designed in, and still the source of truth for its values.
 * They are not debt and they are not exempt by convenience: the assertion
 * below checks that each one really does import that stylesheet, so the
 * exemption cannot be claimed by a page that has not earned it.
 *
 * The five stage pages need no entry here. They render no `<h1>` of their own —
 * their heading comes from `StageHeader`, one component, already on the system.
 */
const SYSTEM_ORIGIN: Record<string, string> = {
  'src/pages/LandingPage.tsx': 'the public page the system was designed on',
  'src/pages/PrivacyPage.tsx': 'landing tokens, scoped under .v3land',
  'src/pages/TermsPage.tsx': 'landing tokens, scoped under .v3land',
};

/**
 * Pages the sweep has not reached yet.
 *
 * **This list may only ever shrink.** It is asserted to match the tree
 * *exactly*, in both directions, which is the whole point:
 *
 *   - Adding a page that renders a heading without composing the primitives
 *     fails, so the debt cannot grow while nobody is looking.
 *   - Converting a page and leaving its name here **also** fails, so the list
 *     cannot rot into a stale glob that quietly exempts live code. Converting
 *     a page means deleting its line, in the same change.
 *
 * Never add an entry to make a red suite green. An entry here is a promise
 * that somebody will come back, and the number of promises is the debt.
 */
const AWAITING_THE_SWEEP: string[] = [
  // Empty, as of 2026-08-23. Every page behind the login composes
  // `components/design/`.
  //
  // **Keep it empty.** The list was twenty-six entries when it was written and
  // it only ever shrank, which was the design: adding a page that renders a
  // heading without the primitives fails, and converting a page while leaving
  // its name here also fails. An entry is a promise somebody will come back,
  // and there are none outstanding. Putting one back is a deliberate act with
  // a name attached, not a way to make a red suite green.
];

function headingPages() {
  return sourceFiles().filter(
    (f) => f.path.startsWith('src/pages/') && TOP_LEVEL_HEADING.test(f.code),
  );
}

describe('6. One design, composed rather than re-typed', () => {
  it('the page scan found the pages', () => {
    // Every assertion below is a claim about a set. If the set is empty — a
    // renamed directory, a `.code` field that stopped being populated — they
    // all pass by finding nothing to check, which is the vacuous-test failure
    // this codebase has now shipped three times.
    const pages = headingPages();
    expect(pages.length).toBeGreaterThan(20);
    expect(pages.map((f) => f.path)).toContain('src/pages/DashboardPage.tsx');
  });

  it('the pages exempted as the system origin really do style from landing.css', () => {
    const byPath = new Map(sourceFiles().map((f) => [f.path, f]));
    const unearned = Object.keys(SYSTEM_ORIGIN).filter(
      (p) => !/import\s+['"]\.\/landing\.css['"]/.test(byPath.get(p)?.code ?? ''),
    );
    expect(unearned).toEqual([]);
  });

  it('the pages awaiting the sweep are exactly the ones named', () => {
    /*
      True today and a ratchet tomorrow.

      Today most pages predate `src/components/design/`, so this list is long
      and the test passes honestly rather than by being scoped to the files
      that already comply — a test scoped to what passes is a test of the
      scope, which is the mistake this file's header opens with.

      Tomorrow it is the thing that stops the next session from repeating the
      one that made it necessary: a new page that renders a heading and skips
      the primitives turns up on the left of this diff, by name, before it is
      ever deployed.
    */
    const origin = new Set(Object.keys(SYSTEM_ORIGIN));
    const unconverted = headingPages()
      .filter((f) => !origin.has(f.path))
      .filter((f) => !DESIGN_PRIMITIVES.test(f.code))
      .map((f) => f.path)
      .sort();

    expect(unconverted).toEqual([...AWAITING_THE_SWEEP].sort());
  });
});

/* ================================================================== */
/*  7. The theme flipped, and the names did not                        */
/* ================================================================== */

/**
 * No rendered class may name a colour from the dark theme.
 *
 * **This is the rule that explains why the app looked sterile for three days
 * while every check was green.** Saibyl was dark once. When it flipped to the
 * light editorial system, `tailwind.config.js` kept the old names alive and
 * remapped their values:
 *
 *     void: '#f8fbff'      // was the dark page background → now paper
 *     white: '#14294a'     // was white text → now ink
 *     platinum: '#14294a'  // was primary text → now ink
 *     gold: '#286cf0'      // was the gold accent → now the blue accent
 *
 * That was the right call for the flip — nothing broke, and every page kept
 * rendering. It was also how the problem hid: a page written for the dark theme
 * and never once looked at since kept resolving to sensible light values, so it
 * read as *ink on paper* while never having been **designed** as ink on paper.
 * There were 246 of these across 25 files on 2026-08-23, and `bg-saibyl-void`
 * on a page root actively painted a flat panel over the radial wash `<body>`
 * carries — canvas rule 1, switched off, on the first screen every founder
 * sees.
 *
 * The aliases stay in the token file: deleting them would turn every one this
 * check missed into a class that resolves to nothing, which fails invisibly.
 * The usage is what is banned, and it is banned here rather than by convention,
 * because convention is what failed.
 */
const DARK_THEME_ALIASES = ['void', 'white', 'platinum', 'gold'] as const;

/**
 * Comments stripped, conservatively.
 *
 * Block comments go entirely; a line comment only counts when `//` opens the
 * line, so a `https://` inside a string can never swallow the code after it.
 * Erring toward keeping code means this check can produce a false positive a
 * human resolves — never a false negative that hides one.
 */
function withoutComments(code: string): string {
  return code
    .replace(/\/\*[\s\S]*?\*\//g, '')
    .split(/\r?\n/)
    .filter((line) => !/^\s*(\/\/|\*)/.test(line))
    .join('\n');
}

describe('7. No rendered class names a colour from the dark theme', () => {
  it('the aliases still exist in the token file, so this bans usage and not the names', () => {
    /* The canary. If somebody deletes the aliases instead of the usages, every
       class this check missed starts resolving to nothing — a colour that
       silently does not apply — and the assertion below would pass while the
       app got worse. */
    const tokens = readFileSync(join(SRC, '..', 'tailwind.config.js'), 'utf8');
    for (const alias of DARK_THEME_ALIASES) {
      expect(tokens, `the '${alias}' alias was deleted rather than swept`).toMatch(
        new RegExp(`\\b${alias}:\\s*'#`),
      );
    }
    // And the pair that had no light-theme counterpart until the sweep needed
    // one: `gold-hover` existed, `blue-hover` did not, so renaming the first to
    // the second would have dropped the hover state on every button that had it.
    expect(tokens).toMatch(/'blue-hover':\s*'#/);
  });

  it('no source file uses one', () => {
    const offenders: string[] = [];
    for (const file of sourceFiles()) {
      const code = withoutComments(file.code);
      code.split(/\r?\n/).forEach((line, i) => {
        for (const alias of DARK_THEME_ALIASES) {
          // `saibyl-gold` but not `saibyl-gold-hover`, which is its own token
          // and is checked by the same rule under its own name.
          if (new RegExp(`saibyl-${alias}\\b(?!-)`).test(line)) {
            offenders.push(`${file.path}:${i + 1} — saibyl-${alias}`);
          }
        }
      });
    }
    expect(offenders).toEqual([]);
  });
});

/* ================================================================== */
/*  8. Every page in the nav opens like the landing page               */
/* ================================================================== */

/**
 * Founder's decision, 2026-08-23, after reading the swept app beside the public
 * site: **"treat each clickable page like a landing page that has the same feel
 * as the primary landing page. Hero section, large type font, then scroll for
 * information."** His word for what was there instead was "sterile", twice.
 *
 * `How this works` was built as the example and approved, and the shape then
 * went to every page in the navigation. This is the ratchet that keeps it
 * there — and, more usefully, what makes the *next* page somebody adds to the
 * nav inherit it. The failure it catches is not a page being restyled back; it
 * is a page added in six weeks that quietly is not this.
 *
 * Derived from `AppLayout`'s own nav arrays rather than a list typed here, so
 * adding a nav entry adds the obligation automatically. A hand-written list is
 * a list somebody forgets to extend, which is how `AWAITING_THE_SWEEP` came to
 * exist in the first place.
 */
function navPaths(): string[] {
  const layout = sourceFiles().find(
    (f) => f.path === 'src/components/AppLayout.tsx',
  );
  expect(layout, 'AppLayout not found by the source scan').toBeDefined();
  return [...layout!.code.matchAll(/path:\s*'(\/app\/[^']*)'/g)].map((m) => m[1]);
}

describe('8. Every page in the nav opens like the landing page', () => {
  it('the nav was actually read', () => {
    // The canary. A regex that stops matching turns every assertion below into
    // a loop over nothing — the vacuous pass this suite has shipped before.
    const paths = navPaths();
    expect(paths.length).toBeGreaterThan(8);
    expect(paths).toContain('/app/validate');
    expect(paths).toContain('/app/settings');
  });

  it('each one composes Longform and opens with a Hero', () => {
    const byPattern = new Map(routeNodes().map((n) => [n.pattern, n]));
    const sources = componentSources();

    const missing: string[] = [];
    for (const path of navPaths()) {
      const node = byPattern.get(path);
      if (!node) {
        missing.push(`${path} — no route`);
        continue;
      }
      const file = sources.get(node.component);
      if (!file) {
        missing.push(`${path} — no source for <${node.component}>`);
        continue;
      }
      if (!/<Longform[\s/>]/.test(file.code)) missing.push(`${file.path} — no <Longform>`);
      if (!/<Hero[\s/>]/.test(file.code)) missing.push(`${file.path} — no <Hero>`);
    }
    expect(missing).toEqual([]);
  });

  it('no hero is wrapped in a Reveal', () => {
    /* A page whose first screen fades in looks broken for 700ms, and the reader
       who notices is the one on a slow connection who was already unsure. The
       hero is above the fold by definition: there is no scroll event to wait
       for, so waiting is the only thing the wrapper would do. */
    const offenders: string[] = [];
    for (const file of sourceFiles()) {
      if (!/<Hero[\s/>]/.test(file.code)) continue;
      if (/<Reveal\b[^>]*>\s*(?:\{\/\*[\s\S]*?\*\/\}\s*)?<Hero\b/.test(file.code)) {
        offenders.push(file.path);
      }
    }
    expect(offenders).toEqual([]);
  });

  it('a longform page still declares its ground', () => {
    // `Longform` sets the measure and nothing else. Without `Ground` the page
    // is the flat `#f8fbff` the canvas's first rule exists to end — and on a
    // page that now opens with 88px of type, a flat ground is very visible.
    const offenders: string[] = [];
    for (const file of sourceFiles()) {
      if (!/<Longform[\s/>]/.test(file.code)) continue;
      if (!/<Ground[\s/>]/.test(file.code)) offenders.push(file.path);
    }
    expect(offenders).toEqual([]);
  });
});
