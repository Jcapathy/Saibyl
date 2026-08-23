/*
  Imports here are relative rather than `@/`-aliased, and that is deliberate.

  `src/test/launch.test.ts` imports this module and calls `readDecision` with
  real payload shapes, which is a stronger check than reading the JSX and
  hoping. The test project (`tsconfig.test.json`) declares no `paths`, so an
  `@/lib/analysis` specifier inside a file the test pulls in transitively fails
  to resolve under `tsc -b` even though it resolves perfectly under
  `tsconfig.app.json`. `components/grow/grow.ts` and `components/website/types.ts`
  are the same arrangement for the same reason.

  **Do not "tidy" these to `@/`.** The type-check that breaks is the one nobody
  runs locally: `tsc --noEmit` on the app project is green either way, and only
  `npm run build` — which is what Render runs — surfaces it.
*/
import { isSupportedSchema, SUPPORTED_SCHEMA_VERSION } from '../../lib/analysis';
import type { AnalysisResponse } from '../../lib/analysis';
import type { Simulation } from '../../types';

/**
 * Launch, as logic: which runs put more than one wording in front of one room,
 * and what that room decided between them.
 *
 * Launch adds **no endpoint and no new kind of run**. Putting several wordings
 * head to head is something the engine has done since the third phase shipped:
 * one swarm, one order, one run per wording, and a scoreboard over the lot. What
 * did not exist was a door — the only way in was to know that a count buried in
 * the run wizard existed, which is why the founder asked where the marketing
 * section was. A capability nobody can find is a capability nobody bought.
 *
 * Two rules live here rather than at each call site, because both have already
 * cost something when they were re-decided by a screen:
 *
 * 1. **The figures are nested under `artifact`.** `GET /simulations/{id}/analysis`
 *    answers `{simulation_id, schema_version, artifact, generated_at}`. Reading
 *    `payload.scoreboard` yields `undefined` on every run that ever finishes —
 *    no error, no empty state, just a screen permanently claiming the comparison
 *    has not been worked out. That is live today in `MessagesStagePage.tsx`.
 * 2. **A winner the server declined to name is never invented.** When
 *    `winner_variant_key` is null the server has said the top two do not
 *    separate; ordering the rows and letting the reader assume the top one won
 *    is the same false precision one layer out, and this page is the one a
 *    founder reads immediately before spending a budget on the answer.
 *
 * `readDecision` is a near-twin of `readRehearsal` in `components/grow/grow.ts`,
 * deliberately not shared: the two carry different sentences for the same
 * measurement, and the honest shared home for the *reading* is `lib/analysis.ts`
 * — a file owned by neither surface. Worth folding together by whoever next owns
 * both.
 */

/* ------------------------------------------------------------------ */
/*  Which runs belong on this page                                     */
/* ------------------------------------------------------------------ */

/**
 * Whether this run put more than one wording in front of the room.
 *
 * `variants` is the count the run was priced and executed for, so it is the
 * only honest test: a run priced for one is a run that read one, whatever was
 * typed anywhere else.
 */
export function isHeadToHead(run: Simulation): boolean {
  return (run.variants ?? 1) > 1;
}

/**
 * The two states in which a run's wordings can still be written.
 *
 * Mirrors `_EDITABLE_STATUSES` in `backend/app/api/variants.py`. Offering any
 * other run here would be an invitation to a 409: the copy is frozen the moment
 * a run starts, because a comparison whose entries changed mid-flight is not a
 * comparison of anything.
 */
const OPEN_TO_WRITING = ['draft', 'ready'];

/** A run that has not gone yet, so more wordings can still be added to it. */
export function canStillTakeWordings(run: Simulation): boolean {
  return !isHeadToHead(run) && OPEN_TO_WRITING.includes(run.status);
}

/* ------------------------------------------------------------------ */
/*  Where the founder is sent                                          */
/* ------------------------------------------------------------------ */

/**
 * Where a new run is started for this product.
 *
 * **This page creates no runs of its own.** A second creation path is how two
 * screens end up disagreeing about what a run is, and the cost of that
 * disagreement is a founder billed for a shape the engine never executes — a
 * run priced for four wordings with copy for one was billed four times and ran
 * once, before `POST /simulations/{id}/start` learned to refuse it.
 */
export function newRunHref(productId: string): string {
  return `/app/simulations/new?project=${productId}`;
}

/** Where a run's wordings are written, which is the run's own page. */
export function writingHref(runId: string): string {
  return `/app/simulations/${runId}`;
}

/* ------------------------------------------------------------------ */
/*  What the room decided                                              */
/* ------------------------------------------------------------------ */

/**
 * The people who read both of the top two, and how many of them switched.
 *
 * Every wording is read by the same swarm, so the comparison is within-subject
 * and this is the honest sample size: somebody who answered identically to both
 * carries no information about which is better. On a control run with identical
 * copy in every slot, a fifth to a third of the room still flipped — so the
 * figure is worth showing rather than assuming.
 */
export interface SwitchedTheirAnswer {
  readBoth: number;
  switched: number;
}

/** The four things a finished head-to-head run can honestly say. */
export type Decision =
  | {
      kind: 'ahead';
      sentence: string;
      /** The winning wording's own name, where the scoreboard carries one. */
      winner: string | null;
      wordings: number;
      switched: SwitchedTheirAnswer | null;
    }
  | {
      kind: 'too-close';
      sentence: string;
      wordings: number;
      switched: SwitchedTheirAnswer | null;
    }
  /** Finished, but nothing has been worked out from it yet. */
  | { kind: 'unread' }
  /** Written by a newer build than this page knows how to read. */
  | { kind: 'withheld'; sentence: string };

/**
 * Read a finished run's decision out of the analysis response.
 *
 * The schema is checked before any figure is read, and that is not ceremony:
 * what decides the winner changed between artifact versions 3 and 4 — from
 * treating the wordings as independent samples to the paired comparison over
 * the shared room — so the same field carries a different claim in an older
 * artifact than this page believes. Refusing is the honest answer, and the run
 * itself is still one click away from every row.
 */
export function readDecision(payload: AnalysisResponse): Decision {
  if (!isSupportedSchema(payload.schema_version)) {
    return {
      kind: 'withheld',
      sentence:
        `These figures were written by a newer version of Saibyl (format ` +
        `${payload.schema_version}; this page reads up to ` +
        `${SUPPORTED_SCHEMA_VERSION}). We would rather show you nothing here ` +
        `than the half of it we recognise. Reload to pick up the current version.`,
    };
  }

  const board = payload.artifact?.scoreboard ?? null;
  if (!board || board.variants.length === 0) return { kind: 'unread' };

  const wordings = board.variants.length;
  const switched = board.paired
    ? {
        readBoth: board.paired.shared_agents,
        switched: board.paired.discordant_agents,
      }
    : null;

  if (board.winner_variant_key) {
    const won = board.variants.find((v) => v.variant_key === board.winner_variant_key);
    return {
      kind: 'ahead',
      sentence: board.verdict,
      winner: won?.label ?? null,
      wordings,
      switched,
    };
  }

  return {
    kind: 'too-close',
    sentence:
      board.verdict ||
      'The room could not tell them apart. Going with the top row would be going with noise.',
    wordings,
    switched,
  };
}

/**
 * How many finished runs get their decision fetched on load.
 *
 * Each one is its own request, and this list is a summary rather than the
 * reading surface — the side-by-side is one click from every row. Four covers
 * what a founder sees without scrolling; the rest say plainly that the decision
 * is on the run's own page rather than pretending there is none.
 */
export const MAX_DECISIONS_READ = 4;
