/**
 * The design system's rules, as assertions against the canvas that set them.
 *
 * `design/canvas.json` is the spec, in the founder's own words, and
 * `design/Main.dc.html` is the drawing. Both are committed, so these tests read
 * them directly rather than restating their numbers — a test that hard-codes
 * `.45s` is a test that agrees with whoever typed it last, not with the design.
 *
 * Five things are checked, and each one is a thing a hurried afternoon breaks:
 *
 *   1. Motion collapses under `prefers-reduced-motion` — every animated class,
 *      derived from the stylesheet rather than listed by hand.
 *   2. The keyframes, durations and easings are the artboard's, unchanged.
 *   3. Shadow-vs-hairline is a required prop with an honest name, not a look a
 *      call site picks.
 *   4. The Playfair accent is one per heading, by type.
 *   5. Density did not move: no padding, and the app's existing label size.
 *
 * Static reads and pure functions, in the register of `ia.test.ts` and
 * `capital.test.ts`: no rendering, no screenshots, no opinion. The suite runs in
 * node with no DOM, which suits this — the claims here are about what the
 * system *is*, and every one of them is legible in the source.
 */
import { readFileSync } from 'node:fs';
import { join } from 'node:path';

import { describe, expect, it } from 'vitest';

import { SRC, sourceFiles } from './source';
import {
  cardSurface,
  dealDelayMs,
  DEAL_MAX_STEPS,
  DEAL_STEP_MS,
} from '../components/design/surfaces';

/* ------------------------------------------------------------------ */
/*  Reading the sources of truth                                       */
/* ------------------------------------------------------------------ */

/** The approved artboard. The app shell, with the motion it is supposed to have. */
const ARTBOARD = readFileSync(join(SRC, '..', '..', 'design', 'Main.dc.html'), 'utf8');

/**
 * All four artboards, concatenated.
 *
 * `canvas.json`'s annotation is a *change list* — "the four changes, applied
 * everywhere" — and reading it as the specification is what produced an app
 * the founder called sterile on 2026-08-23: four rules applied faithfully to
 * flat white cards. The artboards are the specification, and the vocabulary
 * they carry beyond those four rules is asserted against these bytes.
 */
const ARTBOARDS = ['Main', 'Report', 'Answers', 'Next']
  .map((n) => readFileSync(join(SRC, '..', '..', 'design', `${n}.dc.html`), 'utf8'))
  .join('\n');

/** The founder's brief and constraints, in their own words. */
const CANVAS = readFileSync(join(SRC, '..', '..', 'design', 'canvas.json'), 'utf8');

/** Global ground and keyframes. */
const INDEX_CSS = readFileSync(join(SRC, 'index.css'), 'utf8');

/** The design module's own sheet — depth, the eyebrow, motion, the collapse. */
const DESIGN_CSS = readFileSync(join(SRC, 'components/design/design.css'), 'utf8');

/** Where the system came from. */
const LANDING_CSS = readFileSync(join(SRC, 'pages/landing.css'), 'utf8');

const PRIMITIVES = 'src/components/design/DesignPrimitives.tsx';

/** A design-module source file, comments stripped, by repo-relative path. */
function designSource(path: string) {
  const file = sourceFiles().find((f) => f.path === path);
  expect(file, `${path} is missing`).toBeDefined();
  return file!;
}

/** Every `.ts`/`.tsx` file in the design module. */
function designFiles() {
  return sourceFiles().filter((f) => f.path.startsWith('src/components/design/'));
}

/* ------------------------------------------------------------------ */
/*  Small CSS readers                                                  */
/* ------------------------------------------------------------------ */

/** Blank out `/* … *\/` comments so a rule about CSS never fires on prose. */
function stripCssComments(css: string): string {
  return css.replace(/\/\*[\s\S]*?\*\//g, ' ');
}

/** Whitespace-insensitive form, so reformatting a rule is not a failure. */
function normalise(value: string): string {
  return value
    .replace(/\s+/g, ' ')
    .replace(/\s*([{}:;,])\s*/g, '$1')
    .trim();
}

interface Rule {
  selector: string;
  body: string;
}

/** The flat rules in a stylesheet fragment. Not a parser; these sheets are flat. */
function rules(css: string): Rule[] {
  return [...stripCssComments(css).matchAll(/([^{}]+)\{([^{}]*)\}/g)].map((m) => ({
    selector: m[1].trim(),
    body: m[2].trim(),
  }));
}

/** The class names named by a selector — `.sb-lift:hover` → `.sb-lift`. */
function classesIn(selector: string): string[] {
  return [...selector.matchAll(/\.[\w-]+/g)].map((m) => m[0]);
}

/** Every `animation: …` value in a sheet, normalised. `animation-delay` is not one. */
function animationValues(css: string): string[] {
  return [...stripCssComments(css).matchAll(/\banimation:\s*([^;}]+)/g)].map((m) =>
    normalise(m[1]),
  );
}

/** The body of `@keyframes <name>`, normalised. */
function keyframes(css: string, name: string): string | null {
  const source = stripCssComments(css);
  const start = source.indexOf(`@keyframes ${name}`);
  if (start === -1) return null;
  let depth = 0;
  for (let i = source.indexOf('{', start); i < source.length; i++) {
    if (source[i] === '{') depth++;
    else if (source[i] === '}') {
      depth--;
      if (depth === 0) return normalise(source.slice(start, i + 1));
    }
  }
  return null;
}

/** The `radial-gradient(…)` layers in a CSS value, paren-balanced and normalised. */
function radialWashes(value: string): string[] {
  const flat = value.replace(/\s+/g, ' ');
  const out: string[] = [];
  let from = 0;
  for (;;) {
    const start = flat.indexOf('radial-gradient(', from);
    if (start === -1) return out;
    let depth = 0;
    let end = flat.indexOf('(', start);
    for (; end < flat.length; end++) {
      if (flat[end] === '(') depth++;
      else if (flat[end] === ')' && --depth === 0) {
        end++;
        break;
      }
    }
    out.push(normalise(flat.slice(start, end)));
    from = end;
  }
}

/** A declaration's value from the first rule with this exact selector. */
function declaration(css: string, selector: string, property: string): string {
  const rule = rules(css).find((r) => r.selector === selector);
  expect(rule, `no rule for \`${selector}\``).toBeDefined();
  const match = rule!.body.match(new RegExp(`\\b${property}:\\s*([^;]+)`));
  expect(match, `\`${selector}\` declares no \`${property}\``).toBeTruthy();
  return match![1];
}

/* ================================================================== */
/*  0. The canvas still says what these tests think it says            */
/* ================================================================== */

/*
  A guard against the quiet failure mode of every test that reads a spec: the
  spec changes, the reader keeps passing, and the assertions below are now
  enforcing a rule nobody holds. If one of these four sentences leaves the
  canvas, this file needs re-reading before it needs fixing.
*/
describe('0. The rules being enforced are the ones on the canvas', () => {
  it('the four changes and the density constraint are still the brief', () => {
    expect(CANVAS).toContain('Radial washes on the ground');
    expect(CANVAS).toContain(
      'Soft blue shadows on cards that carry meaning — hairlines stay on dense lists',
    );
    expect(CANVAS).toContain('The dotted eyebrow on every mono label');
    expect(CANVAS).toContain('One Playfair italic phrase per major heading');
    expect(CANVAS).toContain('Density is deliberately unchanged');
    expect(CANVAS).toContain('collapses its animation under prefers-reduced-motion');
  });
});

/* ================================================================== */
/*  1. The reduced-motion collapse                                     */
/* ================================================================== */

/*
  "Every artboard collapses its animation under prefers-reduced-motion, exactly
  as the landing page does." — the canvas.

  The list of animated classes is derived from the stylesheet, not typed out
  here. That is the whole value of the test: a primitive added next year with a
  new animation fails this immediately, where a hand-written list would have
  gone on passing while the new thing moved for everybody.
*/
describe('1. Motion collapses under prefers-reduced-motion', () => {
  const marker = '@media (prefers-reduced-motion: reduce)';
  const split = DESIGN_CSS.indexOf(marker);

  it('the design sheet has a reduced-motion block at all', () => {
    expect(split, 'design.css declares no prefers-reduced-motion block').toBeGreaterThan(
      -1,
    );
  });

  it('every class the sheet animates is named in that block', () => {
    const base = DESIGN_CSS.slice(0, split);
    const collapse = DESIGN_CSS.slice(split);

    const animated = new Set<string>();
    for (const rule of rules(base)) {
      if (!/\b(animation|transition):/.test(rule.body)) continue;
      for (const cls of classesIn(rule.selector)) animated.add(cls);
    }

    // Non-vacuous: if the sheet stops animating anything, this test has stopped
    // meaning anything, and that should be loud rather than green.
    expect([...animated].sort()).toEqual([
      '.sb-deal',
      '.sb-eyebrow-live',
      '.sb-lift',
      // The scroll reveal. It transitions rather than animating, and it is the
      // one that matters most here: a reveal that does not collapse leaves a
      // reduced-motion reader looking at `opacity: 0` for content that will
      // never arrive, because the travel it was waiting for was removed.
      '.sb-reveal',
      '.sb-rise',
    ]);

    const collapsed = new Set(
      rules(collapse).flatMap((rule) => classesIn(rule.selector)),
    );
    const uncollapsed = [...animated].filter((cls) => !collapsed.has(cls)).sort();
    expect(uncollapsed, 'animated but never collapsed').toEqual([]);
  });

  it('the block actually stops motion rather than merely mentioning it', () => {
    const collapse = DESIGN_CSS.slice(split);
    expect(collapse).toMatch(/animation:\s*none/);
    expect(collapse).toMatch(/transition:\s*none/);
    // The deal and the rise both start at opacity 0. Turning the animation off
    // without restoring the resting state is how a reduced-motion reader gets
    // an invisible page instead of a still one.
    expect(collapse).toMatch(/opacity:\s*1/);
    expect(collapse).toMatch(/transform:\s*none/);
  });

  it('the landing page still does the same thing, which is why the app does', () => {
    expect(LANDING_CSS).toContain('@media (prefers-reduced-motion: reduce)');
  });
});

/* ================================================================== */
/*  2. The motion is the artboard's, to the millisecond                */
/* ================================================================== */

describe('2. Keyframes and durations match the artboard', () => {
  const NAMES = ['sb-deal', 'sb-rise', 'sb-pulse-dot'];

  it.each(NAMES)('@keyframes %s is the artboard\'s, unchanged', (name) => {
    const drawn = keyframes(ARTBOARD, name);
    expect(drawn, `the artboard no longer defines @keyframes ${name}`).toBeTruthy();
    expect(keyframes(INDEX_CSS, name)).toBe(drawn);
  });

  it('every animation the artboard runs is run with the same duration and easing', () => {
    const drawn = animationValues(ARTBOARD).filter((value) =>
      NAMES.some((name) => value.startsWith(name)),
    );
    // The rail deals its five steps, then the open stage arrives, and the live
    // dot blinks: three, and the artboard should not have quietly lost one.
    expect(drawn.sort()).toEqual([
      'sb-deal .45s cubic-bezier(.22,.61,.36,1) both',
      'sb-pulse-dot 2.6s ease-in-out infinite',
      'sb-rise .5s cubic-bezier(.22,.61,.36,1) both',
    ]);

    const shipped = animationValues(DESIGN_CSS);
    for (const value of drawn) expect(shipped).toContain(value);
  });

  it('the hover lift is the artboard\'s hairline rise', () => {
    expect(normalise(declaration(DESIGN_CSS, '.sb-lift', 'transition'))).toBe(
      normalise(declaration(ARTBOARD, '.sb-step', 'transition')),
    );
    expect(normalise(declaration(DESIGN_CSS, '.sb-lift:hover', 'transform'))).toBe(
      normalise(declaration(ARTBOARD, '.sb-step:hover', 'transform')),
    );
  });

  it('the deal staggers at the artboard\'s 70ms, and caps so a long list has no tail', () => {
    expect(DEAL_STEP_MS).toBe(70);
    expect(dealDelayMs(0)).toBe(0);
    expect(dealDelayMs(4)).toBe(280);
    // The artboard's open stage arrives at .42s — one step past a rail of five.
    expect(dealDelayMs(6)).toBe(420);
    expect(ARTBOARD).toContain('.42s');

    // A sixty-row list dealt at 70ms apart is a four-second wait for the tail.
    expect(dealDelayMs(60)).toBe(DEAL_MAX_STEPS * DEAL_STEP_MS);
    expect(dealDelayMs(-3)).toBe(0);
    expect(dealDelayMs(Number.NaN)).toBe(0);
  });
});

/* ================================================================== */
/*  3. Depth means meaning, and the call site has to say which         */
/* ================================================================== */

/*
  "Soft blue shadows on cards that carry meaning — hairlines stay on dense
  lists." The rule is about content, so the prop is about content. A prop called
  `variant` or `elevation` would hand the call site a look to choose, and a call
  site choosing a look is exactly how "a shadow means something" stops being
  true by the fourth page.
*/
describe('3. The shadow/hairline distinction is a required, honest prop', () => {
  it('the three kinds are distinct surfaces, and only two of them have depth', () => {
    const stage = cardSurface('stage');
    const meaning = cardSurface('meaning');
    const density = cardSurface('density');

    expect(stage).toContain('sb-stage');
    expect(meaning).toContain('sb-meaning');

    // The hairline row carries neither depth class. This is the assertion the
    // whole prop exists for.
    expect(density).not.toContain('sb-stage');
    expect(density).not.toContain('sb-meaning');
    expect(density).toContain('border');

    expect(new Set([stage, meaning, density]).size).toBe(3);
  });

  it('the depth classes are real shadows, and there is no third one hiding', () => {
    for (const selector of ['.sb-stage', '.sb-meaning']) {
      const shadow = declaration(DESIGN_CSS, selector, 'box-shadow');
      expect(shadow, `${selector} has no offset or blur`).toMatch(/\d+px/);
      expect(shadow, `${selector} is not a soft blue shadow`).toMatch(/rgba\(/);
    }
    // A `.sb-density` shadow would be the rule quietly reversed.
    expect(stripCssComments(DESIGN_CSS)).not.toMatch(/\.sb-density/);
  });

  it('`carries` is required — no default, so no card can be given depth by accident', () => {
    const { code } = designSource(PRIMITIVES);
    expect(code).toMatch(/carries:\s*CardCarries;/);
    expect(code, '`carries` was made optional').not.toMatch(/carries\?\s*:/);
    expect(code, '`carries` was given a default').not.toMatch(/carries\s*=/);
  });

  it('no primitive hard-codes a shadow, so depth only ever comes from `carries`', () => {
    for (const file of designFiles()) {
      expect(file.code, `${file.path} spells its own shadow`).not.toMatch(
        /\bshadow-(?!none)/,
      );
      expect(file.code, `${file.path} spells its own shadow`).not.toMatch(/box-shadow/);
    }
  });
});

/* ================================================================== */
/*  4. One Playfair italic phrase per major heading                    */
/* ================================================================== */

describe('4. The Playfair accent is one per heading', () => {
  it('`phrase` is a single optional string — not a node, not a list', () => {
    const { code } = designSource(PRIMITIVES);
    expect(code).toMatch(/phrase\?:\s*string;/);
    expect(code, '`phrase` was widened to a node').not.toMatch(/phrase\?:\s*ReactNode/);
    expect(code, '`phrase` was widened to a list').not.toMatch(/phrase\?:\s*string\[\]/);
  });

  it('the header renders it exactly once', () => {
    const { code } = designSource(PRIMITIVES);
    expect([...code.matchAll(/\{phrase\}/g)]).toHaveLength(1);
  });

  it('the accent is spent in two places, and both of them are headings', () => {
    /* This asserted that `design.css` named Playfair nowhere at all, which was
       true while the only accent was `PageHeader`'s phrase, set with the
       `font-serif` utility. The longform hero and chapter headings need it in
       the stylesheet — they size and letter-space it to match the landing page,
       and a Tailwind class cannot carry `letter-spacing: -.07em` at
       `clamp(3rem, 5.9vw, 5.5rem)` without becoming an arbitrary-value soup.

       So the rule is unchanged in substance — the serif is a heading accent and
       nothing else — and now says so by enumerating where it lives. */
    // The components: still exactly one file, still exactly one `font-serif`.
    // (`designFiles()` reads TS and TSX; the sheet is checked below.)
    const serif = designFiles().filter((f) => /font-serif|Playfair/.test(f.code));
    expect(serif.map((f) => f.path)).toEqual([PRIMITIVES]);
    expect([...serif[0].code.matchAll(/font-serif/g)]).toHaveLength(1);

    // In the sheet, only the two heading accents may name it.
    const wearing = rules(DESIGN_CSS)
      .filter((r) => /Playfair/.test(r.body))
      .map((r) => r.selector)
      .sort();
    expect(wearing).toEqual(['.sb-chapter-title em', '.sb-hero h1 .sb-serif']);
  });

  it('it is italic and violet, as the landing page and the artboard both have it', () => {
    const { code } = designSource(PRIMITIVES);
    expect(code).toMatch(/font-serif[^'"`]*italic/);
    expect(code).toMatch(/text-saibyl-violet/);
    // Both sources agree on the treatment; neither is being re-invented here.
    expect(LANDING_CSS).toMatch(/em\s*\{[^}]*Playfair[^}]*\}/);
    expect(ARTBOARD).toContain('Playfair Display');
  });
});

/* ================================================================== */
/*  5. The ground, and the density that did not move                   */
/* ================================================================== */

describe('5. The washed ground is the landing page\'s own', () => {
  it('`.sb-ground` is the two washes from `.v3land`, value for value', () => {
    const landing = radialWashes(declaration(LANDING_CSS, '.v3land', 'background'));
    expect(landing, 'landing.css no longer washes its ground').toHaveLength(2);
    expect(radialWashes(declaration(INDEX_CSS, '.sb-ground', 'background'))).toEqual(
      landing,
    );
  });

  it('<body> carries the same wash, so the app is not flat by default', () => {
    const body = rules(INDEX_CSS).find((r) => r.selector === 'body');
    expect(body, 'index.css no longer styles <body>').toBeDefined();
    const washes = radialWashes(body!.body);
    expect(washes).toEqual(
      radialWashes(declaration(LANDING_CSS, '.v3land', 'background')),
    );
    // And still on paper, which is what the canvas says the app is today.
    expect(body!.body).toContain('#f8fbff');
  });

  it('the artboard washes the same ground, so all three agree', () => {
    expect(radialWashes(ARTBOARD)).toContain(
      radialWashes(declaration(LANDING_CSS, '.v3land', 'background'))[0],
    );
  });
});

describe('6. Density is deliberately unchanged', () => {
  it('no primitive that wraps content sets padding — only the two that are shapes', () => {
    /* The line, and it is a distinction rather than a loophole:

       A **container** — `Card`, `Ground`, `PageHeader` — wraps content whose
       density it cannot know, so its spacing belongs to the caller who does.
       A shared card that re-pads every call site is the fastest way to break
       the canvas's density rule everywhere at once.

       A **shape** — `Action`, `Notice` — is drawn at a fixed size on the
       artboard (the action at 9px/15px, radius 12, weight 800). A shape whose
       every call site retypes its own padding has no definition, and the third
       call site will get it wrong.

       So padding is allowed only on a line that is building one of the two
       shapes, and `sb-action` / `sb-note-` are how such a line is recognised.
       Anything else re-padding a container fails here. */
    const PADDING = /(?:^|[\s'"`])(p[xytblrse]?-[\w[\].%/-]+)/g;
    /** The only two exports allowed to pad, by name. Adding a third is a
        decision somebody has to make here, in the open, rather than by
        writing `px-4` into a component and finding the suite still green. */
    const SHAPES = new Set(['Action', 'Notice']);

    for (const file of designFiles()) {
      /* Split on the export boundary so the check is per COMPONENT rather than
         per line: the artboard's padding and the class that identifies the
         shape do not have to land on the same line of JSX, and a line-based
         check would quietly pass whichever of the two the author wrapped. */
      const blocks = file.code.split(/(?=^export function )/m);
      const offenders = blocks.flatMap((block) => {
        const name = /^export function (\w+)/.exec(block)?.[1] ?? '(module scope)';
        if (SHAPES.has(name)) return [];
        return [...block.matchAll(PADDING)].map((m) => `${name}: ${m[1]}`);
      });
      expect(offenders, `${file.path} re-pads its call sites`).toEqual([]);
    }
    /* The sheet may pad the page frame, and nothing else.
       It named no `padding` at all until the longform hero and chapters
       arrived: those two carry the landing page's own section rhythm, which is
       the whole of what the founder asked for. Enumerated rather than banned,
       so padding a card from the stylesheet — the back door around the rule
       above — is still a failure. */
    const padded = rules(DESIGN_CSS)
      .filter((r) => /\bpadding(-top)?:/.test(r.body))
      .map((r) => r.selector)
      .sort();
    expect(padded, 'design.css pads something that is not the page frame').toEqual(
      // `.sb-hero` and `.sb-chapter` appear twice each: once at full size and
      // once in the ≤660px step-down.
      ['.sb-chapter', '.sb-chapter', '.sb-hero', '.sb-hero'],
    );
  });

  it('the gradient vocabulary is the artboards\', value for value', () => {
    /* Until 2026-08-23 this folder emitted no gradient at all, and every page
       built on it came out as flat white cards on a washed ground — which is
       what the founder was looking at when he called the app sterile. These
       are read off `design/*.dc.html`; a value invented here would be a second
       brand inside a month. */
    const css = stripCssComments(DESIGN_CSS);
    const artboards = ARTBOARDS.replace(/\s+/g, ' ');

    for (const gradient of [
      // The thing to press, and the glow of the same blue underneath it.
      'linear-gradient(135deg, #286cf0, #5268e9)',
      // A panel with a ground of its own, rather than white on the wash.
      'linear-gradient(180deg, #edf5ff 0%, #f8fbff 87%)',
    ]) {
      expect(css, `design.css lost ${gradient}`).toContain(gradient);
      expect(
        artboards,
        `${gradient} is not on any artboard — it was invented here`,
      ).toContain(gradient);
    }

    // And the glow, which is what separates an action from a coloured box.
    expect(css).toContain('0 8px 18px rgba(40, 108, 240, .22)');
  });

  it('every raised surface has the inset highlight the artboards give it', () => {
    // An outer shadow with no lit top edge is a rectangle with a shadow under
    // it. All four artboards carry `inset 0 1px rgba(255,255,255,.35..42)` on
    // anything raised; the app had none until the same date.
    for (const selector of ['.sb-stage', '.sb-meaning', '.sb-action']) {
      expect(
        declaration(DESIGN_CSS, selector, 'box-shadow'),
        `${selector} has no lit edge`,
      ).toMatch(/inset 0 1px rgba\(255, 255, 255, \.\d+\)/);
    }
  });

  it('the eyebrow adds a dot to the app\'s existing label, not a bigger label', () => {
    const { code } = designSource(PRIMITIVES);
    // The size the app's mono labels are already set at. Rule 3 was "add the
    // dot", and a primitive that also grew the label would be answering a
    // question nobody asked.
    expect(code).toMatch(/text-\[10px\]/);
    expect(code).toMatch(/tracking-\[0\.16em\]/);
    // 7px dot, 5px ring — the landing page's eyebrow, exactly.
    const dot = rules(DESIGN_CSS).find((r) => r.selector === '.sb-eyebrow::before');
    expect(dot, 'the eyebrow lost its dot').toBeDefined();
    expect(normalise(dot!.body)).toContain('width:7px');
    expect(normalise(dot!.body)).toContain(
      normalise(declaration(LANDING_CSS, '.v3land .eyebrow::before', 'box-shadow')),
    );
  });

  it('the page header is the one named exception, and it is a front door', () => {
    /* **The canvas's density constraint is unchanged, and still quoted below.**
       What changed, on 2026-08-23, is where it is understood to apply.

       The founder read the five live stage pages and could not comfortably
       read the accent phrase on his own monitor — 15px serif italic, sitting
       *above* a 13px paragraph, on a page whose entire job is to explain a
       stage to somebody who has just arrived on it. His instruction: expand
       the block with explanatory copy and put the tagline under it, larger.

       So the rule holds where it was written to hold — rows, cards, lists,
       every dense surface in the app — and does not govern the block that
       carries the page's `<h1>`. The canvas itself names the accent phrase as
       the place warmth is allowed to come from; this is that place. */
    const { code } = designSource(PRIMITIVES);

    // The lead, and the phrase under it at its largest.
    expect(code, 'the header lead went back to 13px').toMatch(/sm:text-\[15px\]/);
    expect(code, 'the accent phrase stopped being an accent').toMatch(
      /lg:text-\[26px\]/,
    );
    // Both scale down. The complaint named mobile first, and a single fixed
    // 26px line is the same defect facing the other way.
    expect(code).toMatch(/text-\[20px\]\s+sm:text-\[23px\]/);
    expect(code).toMatch(/text-\[14px\]\s+sm:text-\[15px\]/);

    // The explanation reads before the phrase it earns. Asserted on order,
    // because "put the tagline underneath" was the instruction and a later
    // refactor swapping them back would look like a formatting change.
    expect(
      code.indexOf('{children}'),
      'the phrase moved back above the explanation',
    ).toBeLessThan(code.indexOf('{phrase}'));

    // And the constraint that did not move: nothing in the system sizes type
    // for a dense surface. `Card` and `cardSurface` set no font size at all,
    // so no row, list or record grew because a header did.
    for (const file of designFiles().filter((f) => f.path !== PRIMITIVES)) {
      expect(
        [...file.code.matchAll(/text-\[\d+(?:\.\d+)?px\]/g)].map((m) => m[0]),
        `${file.path} sizes type outside the page header`,
      ).toEqual([]);
    }
    /* `design.css` may size type, but **only for the page frame**.
       It could name no `font-size` at all until the longform hero and chapters
       arrived, and the substance of the rule has not moved: the constraint was
       always about rows, cards and lists, and nothing that sizes a dense
       surface has appeared. Enumerated by selector rather than banned outright,
       so adding a `font-size` to a card is still a failure. */
    const sized = rules(DESIGN_CSS)
      .filter((r) => /\bfont-size:/.test(r.body))
      .map((r) => r.selector)
      .sort();
    expect(sized, 'design.css sizes type outside the page frame').toEqual(
      [
        '.sb-chapter-copy',
        '.sb-chapter-title',
        '.sb-hero h1',
        '.sb-hero-text',
        // The mobile step-down for the same two headings.
        '.sb-hero h1',
        '.sb-chapter-title',
      ].sort(),
    );
    expect(CANVAS).toContain('same 13px body');
  });
});

/* ================================================================== */
/*  7. The longform page is the landing page's own                     */
/* ================================================================== */

/**
 * Founder's decision, 2026-08-23: **every page behind the login is a landing
 * page.** Hero, large type, then scroll, with content arriving as the reader
 * reaches it. His words for what was there instead were "very sterile,
 * mechanical, and looks AI-generated".
 *
 * The danger in granting that is the one this whole suite exists for: a second
 * set of hero numbers, drifting from the public site, and within a month the
 * app is a *different* marketing page rather than the same one. So `design.css`
 * carries copies of `landing.css`'s values, and this section asserts value for
 * value that they are copies.
 *
 * Each row is (app selector, app property, landing selector, landing property).
 */
const LONGFORM_MIRRORS: [string, string, string, string][] = [
  ['.sb-longform', 'width', '.v3land .container', 'width'],
  ['.sb-hero', 'padding', '.v3land .hero', 'padding'],
  ['.sb-hero h1', 'font-size', '.v3land .hero h1', 'font-size'],
  ['.sb-hero h1', 'line-height', '.v3land .hero h1', 'line-height'],
  ['.sb-hero h1', 'letter-spacing', '.v3land .hero h1', 'letter-spacing'],
  ['.sb-hero-text', 'font-size', '.v3land .hero-text', 'font-size'],
  ['.sb-hero-text', 'line-height', '.v3land .hero-text', 'line-height'],
  ['.sb-chapter-title', 'font-size', '.v3land .section-title', 'font-size'],
  ['.sb-chapter-title', 'line-height', '.v3land .section-title', 'line-height'],
  ['.sb-chapter-title', 'letter-spacing', '.v3land .section-title', 'letter-spacing'],
  ['.sb-chapter-copy', 'font-size', '.v3land .section-copy', 'font-size'],
  ['.sb-reveal', 'transition', '.v3land .reveal', 'transition'],
  ['.sb-reveal', 'transform', '.v3land .reveal', 'transform'],
];

describe("7. The longform page carries the landing page's numbers", () => {
  it("every hero and chapter value is the landing page's, not a new one", () => {
    for (const [appSel, appProp, landSel, landProp] of LONGFORM_MIRRORS) {
      expect(
        normalise(declaration(DESIGN_CSS, appSel, appProp)),
        `${appSel} { ${appProp} } drifted from ${landSel}`,
      ).toBe(normalise(declaration(LANDING_CSS, landSel, landProp)));
    }
  });

  it('the Playfair accent in a hero and a chapter is the landing violet', () => {
    for (const selector of ['.sb-hero h1 .sb-serif', '.sb-chapter-title em']) {
      expect(normalise(declaration(DESIGN_CSS, selector, 'color'))).toBe('#8b73ee');
      expect(declaration(DESIGN_CSS, selector, 'font-family')).toContain('Playfair Display');
    }
    // …and the landing token behind it holds the same hex. Read rather than
    // assumed: `--violet` carrying another value is how two brands start.
    expect(LANDING_CSS).toMatch(/--violet:\s*#8b73ee/);
  });

  it('a reveal that never fires shows its content rather than hiding it', () => {
    /* The failure worth testing, and it has happened once: a scroll-reveal page
       photographed as blank in a full-page capture and was reported as a broken
       deploy (`docs/CRITICS_LOG.md`, 2026-08-16).

       Two independent guarantees, because either alone leaves a hole — the CSS,
       for a reader who asked for no motion, and the hook's 2.5s post-load
       fallback, for an environment that never delivers the callbacks at all. */
    const sheet = stripCssComments(DESIGN_CSS);
    const reduced = sheet.slice(sheet.indexOf('prefers-reduced-motion'));
    expect(reduced, 'the reveal keeps opacity:0 under reduced motion').toContain('.sb-reveal');

    const hook = readFileSync(join(SRC, 'components/design/useReveal.ts'), 'utf8');
    expect(hook, 'the reduced-motion branch is gone').toContain(
      "matchMedia('(prefers-reduced-motion: reduce)')",
    );
    expect(hook, 'the blank-capture fallback is gone').toMatch(/setTimeout\(revealAll, 2500\)/);
    expect(hook, 'revealed elements are no longer unobserved').toContain('unobserve');
  });

  it('there is one reveal implementation, and the landing page uses it too', () => {
    // If `LandingPage` grows its own observer again, the public site and the
    // app drift apart in exactly the way that produced this work.
    const landing = readFileSync(join(SRC, 'pages/LandingPage.tsx'), 'utf8');
    expect(landing).toContain('useReveal(rootRef');
    expect(landing, 'LandingPage built a second observer').not.toContain(
      'new IntersectionObserver',
    );
  });
});
