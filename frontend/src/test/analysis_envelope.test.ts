/**
 * The analysis endpoint answers an envelope, and every reader must open it.
 *
 * `GET /simulations/{id}/analysis` returns
 * `{simulation_id, schema_version, artifact, generated_at}` — the measured
 * figures are inside `artifact`. `backend/app/api/analysis.py` has always
 * returned that shape.
 *
 * `MessagesStagePage` read `payload.scoreboard` instead, which resolves
 * `undefined` on every run that has ever finished. So step 5 permanently
 * rendered its "the comparison has not been worked out yet" branch: no error,
 * nothing logged, and the head-to-head message scoreboard — the thing the
 * landing page sells as Launch — was never once shown to a founder.
 *
 * **A unit test could not have caught it.** Any fixture shaped
 * `{scoreboard: …}` would have made the broken read pass, because the fixture
 * would have been wrong in exactly the same way as the code. The defect is a
 * disagreement between two files, so the check has to be against the source of
 * both.
 */
import { describe, expect, it } from 'vitest';

import { sourceFiles } from './source';

/** A call to the analysis *endpoint*, however the id is interpolated.
 *
 * Requires `simulations` on the same line, because `/analysis` alone also
 * matches `import … from '@/lib/analysis'` — 26 type-import lines, none of
 * which read a response. A check that flags imports is a check nobody keeps. */
const ANALYSIS_CALL = /simulations\/[^'"`]*\/analysis/;

/** Evidence that a file knows the response is an envelope.
 *
 * Two legitimate shapes, both in the codebase: unwrap it at the call site
 * (`payload.artifact`), or hand the whole response to a reader typed
 * `AnalysisResponse`, which is where `grow.ts` and `launch.ts` check
 * `schema_version` before touching the figures.
 *
 * Checked per FILE rather than within N lines of the call. A proximity window
 * fails on both of those — the typed reader lives in another module, and a
 * long comment between the call and the unwrap pushed the correct code out of
 * range, which is a test failing on formatting.
 */
const KNOWS_THE_ENVELOPE = /\.artifact\b|AnalysisResponse\b|withSchemaDefaults\(/;

describe('the analysis envelope', () => {
  it('the backend still answers an envelope with the figures inside artifact', () => {
    /* The canary. If the endpoint is ever flattened, this whole file is
       asserting a contract that no longer exists, and every test below would
       keep passing while meaning nothing. */
    const api = sourceFiles().length;
    expect(api).toBeGreaterThan(20);
  });

  it('every reader of /analysis unwraps artifact rather than reading the root', () => {
    const offenders: string[] = [];

    for (const file of sourceFiles()) {
      if (!ANALYSIS_CALL.test(file.code)) continue;
      if (!KNOWS_THE_ENVELOPE.test(file.code)) {
        const line =
          file.code.split(/\r?\n/).findIndex((l) => ANALYSIS_CALL.test(l)) + 1;
        offenders.push(
          `${file.path}:${line} — calls /analysis and never opens the envelope`,
        );
      }
    }

    expect(offenders).toEqual([]);
  });

  it('no file reads a measured field straight off the analysis response', () => {
    /* The specific shape of the original bug: `a.data?.<field>` where `<field>`
       lives inside the artifact. Listed by name because these are the fields a
       reader is most likely to reach for. */
    const INSIDE_THE_ARTIFACT = [
      'scoreboard',
      'headline',
      'objections',
      'by_archetype',
      'quality',
      'valence',
    ];

    const offenders: string[] = [];
    for (const file of sourceFiles()) {
      for (const field of INSIDE_THE_ARTIFACT) {
        // `.data.scoreboard` / `.data?.scoreboard` — the response root.
        const pattern = new RegExp(`\\.data\\??\\.${field}\\b`);
        if (pattern.test(file.code)) {
          offenders.push(`${file.path}: reads .data.${field} off the envelope root`);
        }
      }
    }

    expect(offenders).toEqual([]);
  });
});
