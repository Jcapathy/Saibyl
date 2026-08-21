/**
 * The before/after table of a page revision — the proof-of-improvement the
 * whole revision loop exists to produce.
 *
 * It rendered as nothing, always. `revision_tasks.py` writes
 * `{overall, dimensions: {…}}`; this reader iterated top-level keys, found
 * `overall` and `dimensions`, coerced the nested object with `Number({...})`
 * to NaN, and returned an empty list. Both sides were green: the writer had
 * already been fixed once for this exact asymmetry and the reader was missed.
 *
 * These tests pin both shapes, because rows written before that fix carry the
 * flat one and a founder's past revision should not lose its table to a
 * cleanup.
 */
import { describe, expect, it } from 'vitest';

// Relative, not the `@/` alias: the build's project-references pass does not
// resolve the alias for files under src/test, and `npm run build` is the gate
// this repo trusts — vitest passing is not the same check.
import { overallScore, scoreDeltas } from '../components/website/types';

describe('per-dimension before/after', () => {
  it('reads the nested shape the worker actually writes', () => {
    const before = { overall: 57, dimensions: { credibility: 42, clarity: 60 } };
    const after = { overall: 64, dimensions: { credibility: 58, clarity: 66 } };

    const rows = scoreDeltas(before as never, after as never);

    expect(rows.map((r) => r.key).sort()).toEqual(['clarity', 'credibility']);
    expect(rows.find((r) => r.key === 'credibility')).toEqual({
      key: 'credibility',
      before: 42,
      after: 58,
    });
    expect(overallScore(after as never)).toBe(64);
  });

  it('still reads the flat shape older rows carry', () => {
    const rows = scoreDeltas(
      { overall: 57, credibility: 42 } as never,
      { overall: 64, credibility: 58 } as never,
    );

    expect(rows).toEqual([{ key: 'credibility', before: 42, after: 58 }]);
  });

  it('never renders the literal key "dimensions" as a row', () => {
    const rows = scoreDeltas(
      null,
      { overall: 64, dimensions: { credibility: 58 } } as never,
    );

    expect(rows.map((r) => r.key)).not.toContain('dimensions');
  });
});
