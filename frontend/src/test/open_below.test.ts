/**
 * The row that is already open links to the report, and the link has a target.
 *
 * This cell has now been misread twice by the same founder.
 *
 * It first rendered **nothing** when the open check was this row, because the
 * report sits a screen below. He had just paid for a check, saw every other
 * row carrying a link and his carrying none, and concluded his had failed.
 * That was fixed with the words "Open below ↓".
 *
 * On 2026-08-31 he ran a check on one site, found its row wearing grey text,
 * clicked the nearest blue thing — which belonged to a different row — and got
 * a different site's report. Grey passive text in a column of blue links does
 * not read as "you are already there". It reads as the absence of a control,
 * and the eye goes to the nearest real one.
 *
 * So the contract is: the open row carries a real `<a href>`, and it points at
 * an id that actually exists on the report. Those two halves live about 350
 * lines apart in one file, which is exactly the distance at which a rename
 * silently breaks a link — so they are pinned together here.
 *
 * Read as source text rather than rendered: `npm run build` runs `tsc -b`, and
 * a test importing a `.tsx` fails that pass with "--jsx is not set" while
 * vitest goes green.
 */
import { readFileSync } from 'node:fs';
import { join } from 'node:path';

import { describe, expect, it } from 'vitest';

import { SRC } from './source';

const PAGE = readFileSync(
  join(SRC, 'pages/product/AudienceStagePage.tsx'),
  'utf8',
);

describe('the open check links to its own report', () => {
  it('declares one id for the report anchor', () => {
    expect(PAGE).toMatch(/const SITE_REPORT_ID = '([a-z-]+)'/);
  });

  it('gives the report element that id', () => {
    expect(PAGE).toContain('id={SITE_REPORT_ID}');
  });

  it('points the open row at it with a real anchor, not a label', () => {
    // The `<a href>` and the target must both be present. An onClick handler
    // would work with a mouse and fail from the keyboard.
    expect(PAGE).toContain('href={`#${SITE_REPORT_ID}`}');
    expect(PAGE).not.toMatch(
      /<span className="text-saibyl-muted">Open below/,
      // The grey-label version. If it comes back, so does the confusion.
    );
  });

  it('keeps the report heading clear of the top edge when jumped to', () => {
    // The summary line names the address, and that line is how a founder
    // confirms *which* check they are reading. Flush against the viewport top
    // it is the first thing cropped.
    expect(PAGE).toMatch(/id=\{SITE_REPORT_ID\}[^>]*scroll-mt/);
  });

  it('still offers a real control on every other finished row', () => {
    // The fix must not take the working affordance away from the rows that
    // are not open.
    expect(PAGE).toContain('See what we found');
    expect(PAGE).toContain('openCheck(row.id)');
  });
});
