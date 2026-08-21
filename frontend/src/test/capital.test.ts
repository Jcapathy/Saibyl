/**
 * The four promises the capital surface makes, as assertions.
 *
 * This module recommends firms and evidences the recommendation. It does not
 * hold anyone's contact details and it does not approach anyone. That is a
 * legal position rather than a preference — `services/gtm/privacy.py` opens by
 * saying the contact gate "is not a feature flag, it is the boundary between
 * two legal positions" — and a boundary that lives only in a reviewer's memory
 * is a boundary that moves the first busy afternoon.
 *
 * So each promise is checked mechanically, the same way `ia.test.ts` checks the
 * rail: read the source, assert the shape. No rendering and no opinion.
 */
import { readFileSync } from 'node:fs';
import { join } from 'node:path';

import { describe, expect, it } from 'vitest';

import { SRC, sourceFiles } from './source';

const CAPITAL = 'src/components/capital/';
const PAGE = 'src/pages/CapitalPage.tsx';

function capitalFiles() {
  return sourceFiles().filter(
    (f) => f.path.startsWith(CAPITAL) || f.path === PAGE,
  );
}

function byPath(path: string) {
  const file = sourceFiles().find((f) => f.path === path);
  expect(file, `${path} is missing`).toBeDefined();
  return file!;
}

/** The stylesheet, read directly: `sourceFiles` walks `.ts`/`.tsx` only. */
function capitalCss(): string {
  return readFileSync(join(SRC, 'components/capital/capital.css'), 'utf8');
}

describe('1. No contact affordance', () => {
  it('nothing on the capital surface composes a message to anyone', () => {
    /*
      A `mailto:` is the shape a "helpful" contact button takes, and the reason
      there must not be one here is not that this module lacks the data — it is
      that approaching on a founder's behalf makes deliverability, consent and
      reputation ours. The record stores a firm's own published route precisely
      so the founder walks it themselves.

      Saibyl's own address on the landing page, the privacy page and settings is
      a different thing entirely and is not in scope: that is us, reachable.
    */
    const offenders = capitalFiles()
      .filter((f) => /mailto:/i.test(f.code))
      .map((f) => f.path);
    expect(offenders).toEqual([]);
  });

  it('no link anywhere is built out of a stored address', () => {
    // The app-wide half of the same rule. A literal `mailto:info@saidolabs.com`
    // is our own front door; a `mailto:` assembled from a value is a contact
    // affordance over somebody else's data, wherever it is written.
    const offenders = sourceFiles()
      .filter((f) => /mailto:[^"'`]*\$\{/.test(f.code))
      .map((f) => f.path);
    expect(offenders).toEqual([]);
  });

  it('a stored firm address is written out, never wired up', () => {
    // The one field in this whole package that may hold an address is
    // `inbound_path.value` on a `firm_address` record, and the schema only
    // admits it when the local part is a published role word. It renders as
    // text; an `href` built from it would be the affordance this module
    // refuses.
    const primitives = byPath(`${CAPITAL}CapitalPrimitives.tsx`);
    expect(primitives.code).toMatch(/route\.isUrl \?/);
  });
});

describe('2. Every firm is traceable', () => {
  it('the record renderer always renders its source', () => {
    // `Provenance` is unconditional in `FirmRecord`, and it is the only place
    // a firm's `source_url` reaches a screen. A recommendation a founder
    // cannot trace back to a published page is one they cannot check — which
    // is why the schema refuses to hold a record without one, and why the
    // renderer must not be able to drop it.
    const record = byPath(`${CAPITAL}FirmRecord.tsx`);
    expect(record.code).toMatch(/<Provenance\b/);
    expect(record.code).toMatch(/sourceUrl=\{firm\.source_url\}/);

    const primitives = byPath(`${CAPITAL}CapitalPrimitives.tsx`);
    const provenance = primitives.code.slice(
      primitives.code.indexOf('export function Provenance('),
    );
    expect(provenance).toMatch(/href=\{sourceUrl\}/);
  });

  it('the age of a claim is rendered beside it', () => {
    // Hiding the date is how a list launders decay into confidence. Every
    // record carries `retrieved_at` and every surface prints it.
    const primitives = byPath(`${CAPITAL}CapitalPrimitives.tsx`);
    expect(primitives.code).toMatch(/ageInWords\(retrievedAt, now\)/);
  });
});

describe('3. A refusal is a position, not a gap', () => {
  it('both refusing inbound kinds return no route at all', () => {
    /*
      `warm_intro_only` and `no_inbound` are the firm's published position.
      The schema refuses to store a route beside either, because a route shown
      next to "they take no inbound" is a route somebody uses anyway. If this
      reader ever handed back a value for one of them, the UI would render a
      lead with a missing field instead of a firm that said no.
    */
    const lib = byPath('src/lib/capital.ts');
    for (const kind of ['warm_intro_only', 'no_inbound']) {
      const start = lib.code.indexOf(`case '${kind}':`);
      expect(start, `${kind} is not handled`).toBeGreaterThan(-1);
      const branch = lib.code.slice(start, start + 320);
      expect(branch, `${kind} must be a refusal`).toMatch(/refused: true/);
      expect(branch, `${kind} must carry no route`).toMatch(/value: null/);
    }
  });

  it('the shortlist renders refusals, withheld records and the denominator', () => {
    // The three things a padded list would have dropped. Each is read from the
    // stored artifact and rendered; dropping any one turns a short, honest
    // answer into a list that reads as the whole market.
    const panel = byPath(`${CAPITAL}ShortlistPanel.tsx`);
    expect(panel.code).toMatch(/shortlist\.refusals\.map\(/);
    expect(panel.code).toMatch(/<Withheld\b/);
    expect(panel.code).toMatch(/firms_considered/);
  });

  it('an empty bank is a calm state, not an error', () => {
    // 409 is the bank having nothing current to match against, and 422 is a
    // description we will not store. Both are the product working correctly
    // and saying no, so neither may render in the failure colour.
    const panel = byPath(`${CAPITAL}ShortlistPanel.tsx`);
    expect(panel.code).toMatch(/status === 409/);
    expect(panel.code).toMatch(/status === 422/);
    expect(panel.code).toMatch(/<CalmNotice\b/);
  });
});

describe('4. It looks like Saibyl, and it stops when asked', () => {
  it('every animated class in this module is reset under reduced motion', () => {
    // The landing page collapses under `prefers-reduced-motion`, so everything
    // does — it is not optional (docs/DESIGN_GUIDE.md). A stylesheet that
    // animates without a matching reset is how one surface keeps moving for a
    // reader who asked the whole system to stop.
    const css = capitalCss();
    const marker = '@media (prefers-reduced-motion: reduce)';
    expect(css).toContain(marker);

    const reduced = css.slice(css.indexOf(marker));
    for (const animated of ['capital-arrive', 'capital-lift']) {
      expect(reduced, `${animated} keeps moving`).toContain(animated);
    }
    expect(reduced).toMatch(/animation: none/);
  });

  it('the module carries the design system rather than a dialect of it', () => {
    // The four things that make a surface feel like Saibyl: a washed ground,
    // soft blue shadows on the cards that carry meaning, a dot on every mono
    // label, and exactly one serif italic phrase in the biggest heading.
    const css = capitalCss();
    expect(css).toContain('radial-gradient');
    expect(css).toContain('#35c7d5');
    expect(css).toMatch(/box-shadow: 0 22px 60px rgba\(52, 96, 164, \.12\)/);

    const page = byPath(PAGE);
    expect(page.code).toContain('capital-ground');
    const serif = [...page.code.matchAll(/font-serif italic/g)];
    expect(serif.length, 'one serif italic phrase — not zero, not four').toBe(1);

    // And every mono label here wears its dot, because they all go through the
    // one component that draws it.
    const bare = capitalFiles().filter(
      (f) =>
        f.path !== `${CAPITAL}CapitalPrimitives.tsx` &&
        /font-mono text-\[10px\] uppercase/.test(f.code),
    );
    expect(bare.map((f) => f.path)).toEqual([]);
  });
});
