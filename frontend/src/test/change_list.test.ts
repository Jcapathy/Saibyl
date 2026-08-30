/**
 * The report opens with what to change, not with a score.
 *
 * The order was the other way round from the day the check shipped until
 * 2026-08-30, when the founder read the result and said the product had become
 * "a very mechanical scoring mechanism that ignores the original intent". The
 * intent is to make a page better; a mean across nine dimensions never asks
 * anyone to do anything. The score is still rendered, one block lower.
 *
 * These pin the ranking, because the ranking is the whole of the change: a
 * list in the wrong order is a backlog again.
 */
import { describe, expect, it } from 'vitest';

// Relative, not the `@/` alias: the build's project-references pass does not
// resolve the alias for files under src/test.
import { rankedChanges } from '../components/website/types';
import type { SiteDimension, SiteFindingSeverity } from '../components/website/types';

function finding(severity: SiteFindingSeverity, fix: string) {
  return { severity, region: 'page', quote: 'q', why: 'w', fix };
}

function dimension(key: string, ...findings: ReturnType<typeof finding>[]): SiteDimension {
  return { key, score: 50, findings, strengths: [] };
}

describe('the opening change list', () => {
  it('puts the worst thing first, whichever card it came from', () => {
    const changes = rankedChanges([
      dimension('copy', finding('minor', 'tighten the subhead')),
      dimension('found', finding('critical', 'let the crawlers read the page')),
      dimension('hierarchy', finding('major', 'say what this is above the fold')),
    ]);

    expect(changes.map((c) => c.finding.fix)).toEqual([
      'let the crawlers read the page',
      'say what this is above the fold',
      'tighten the subhead',
    ]);
  });

  it('keeps a dimension’s own ordering inside one severity', () => {
    // "Being found" orders its findings as an argument rather than a list:
    // crawler access first, because nothing else on that card is worth doing
    // until a machine is allowed to read the page at all. A stable sort is
    // what preserves that, and every engine this ships to has one.
    const changes = rankedChanges([
      dimension(
        'found',
        finding('critical', 'let the crawlers read the page'),
        finding('critical', 'serve the words before JavaScript runs'),
      ),
    ]);

    expect(changes.map((c) => c.finding.fix)).toEqual([
      'let the crawlers read the page',
      'serve the words before JavaScript runs',
    ]);
  });

  it('carries the founder-facing name of the card each change came from', () => {
    const changes = rankedChanges([dimension('found', finding('major', 'add structured data'))]);

    expect(changes[0].dimensionName).toBe('Being found');
    expect(changes[0].dimensionKey).toBe('found');
  });

  it('names the counted cards rather than showing a bare key', () => {
    // All three fell through to a capitalised key until 2026-08-30, so a
    // founder read "Measured" and "Standard" as headings.
    const changes = rankedChanges([
      dimension('measured', finding('minor', 'pick fewer radii')),
      dimension('standard', finding('minor', 'delete most of the eyebrows')),
    ]);

    expect(changes.map((c) => c.dimensionName)).toEqual(['Consistency', 'Craft']);
  });

  it('is empty when the page had nothing wrong with it', () => {
    expect(rankedChanges([dimension('copy')])).toEqual([]);
    expect(rankedChanges([])).toEqual([]);
  });

  it('gathers every finding, so nothing is only reachable by scrolling a card', () => {
    const changes = rankedChanges([
      dimension('copy', finding('minor', 'a'), finding('minor', 'b'), finding('major', 'c')),
      dimension('found', finding('critical', 'd'), finding('minor', 'e')),
    ]);

    expect(changes).toHaveLength(5);
    expect(changes[0].finding.fix).toBe('d');
  });
});
