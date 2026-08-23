/*
  Imports here are relative rather than `@/`-aliased, and that is deliberate.

  `src/test/grow.test.ts` imports this module and calls `readRehearsal` with
  real payload shapes, which is a stronger check than reading the JSX and
  hoping. The test project (`tsconfig.test.json`) declares no `paths`, so an
  `@/lib/analysis` specifier inside a file the test pulls in transitively fails
  to resolve under `tsc -b` even though it resolves perfectly under
  `tsconfig.app.json`. `components/website/types.ts` is the same arrangement for
  the same reason.

  **Do not "tidy" these to `@/`.** The type-check that breaks is the one nobody
  runs locally: `tsc --noEmit` on the app project is green either way, and only
  `npm run build` — which is what Render runs — surfaces it.
*/
import { isSupportedSchema, SUPPORTED_SCHEMA_VERSION } from '../../lib/analysis';
import type { AnalysisResponse } from '../../lib/analysis';
import type { Simulation } from '../../types';

/**
 * Grow, as logic: which runs rehearsed a change, and what the room decided.
 *
 * Grow adds **no endpoint**. A change is rehearsed by a run staged at `growth`
 * — an entry that has been in `backend/app/services/engine/founder_stages.py`
 * since the Founder lens shipped — carrying two or more things for one shared
 * room to read. What this module holds is the small amount of reading that
 * would otherwise be re-derived on every screen that shows a result, plus the
 * one refusal that must survive every future edit.
 */

/* ------------------------------------------------------------------ */
/*  The handoff                                                        */
/* ------------------------------------------------------------------ */

/**
 * The stage id in the server's registry.
 *
 * Never rendered — it travels in a URL, and the receiving screen matches it
 * against the list it fetches from `GET /api/simulations/founder-stages`.
 * `grow.test.ts` asserts this value still exists in the backend registry,
 * because a stage renamed on the server would leave this handoff landing
 * silently on an unstaged run: one that completes, costs money, and answers a
 * different question with no error anywhere.
 */
export const GROWTH_STAGE_ID = 'growth';

/**
 * Where "rehearse this change" goes.
 *
 * One spelling, called from every card. The receiving screen already reads both
 * parameters — the rail inside a product hands it the same pair — so this adds
 * a way in rather than a second implementation of run creation.
 *
 * **This surface creates no runs of its own.** A second creation path is how
 * two screens end up disagreeing about what a run is, and the cost of that
 * disagreement is a founder charged for a shape the engine never executes.
 */
export function rehearsalHref(productId: string): string {
  return `/app/simulations/new?project=${productId}&founder_stage=${GROWTH_STAGE_ID}`;
}

/* ------------------------------------------------------------------ */
/*  A run that rehearsed a change                                      */
/* ------------------------------------------------------------------ */

/**
 * A run row, plus the one column `src/types` does not declare.
 *
 * `founder_stage` is written by `POST /api/simulations` and returned by
 * `GET /api/simulations` (`select("*")`), but the shared `Simulation` interface
 * predates it and this module does not own that file. Narrowed here rather than
 * reached for with a cast, so the optionality stays visible at every read:
 * every run created before the Founder lens shipped carries null.
 */
export interface GrowthRun extends Simulation {
  founder_stage?: string | null;
}

/** The runs that rehearsed a change, in the order the list endpoint returned them. */
export function growthRuns(runs: GrowthRun[]): GrowthRun[] {
  return runs.filter((run) => run.founder_stage === GROWTH_STAGE_ID);
}

/**
 * Whether a run put more than one thing in front of the room.
 *
 * `variants` is the count the run was priced and executed for. One means the
 * change was graded on its own, which is a legitimate rehearsal and not a
 * failed comparison — it just cannot say "better than what you have now".
 */
export function comparedMoreThanOne(run: GrowthRun): boolean {
  return (run.variants ?? 1) > 1;
}

/* ------------------------------------------------------------------ */
/*  What the room decided                                              */
/* ------------------------------------------------------------------ */

/**
 * The four things a finished rehearsal can honestly say.
 *
 * `too-close` is a result, not a missing one. It is the single most important
 * state on this surface: a founder about to raise a price wants to be told that
 * the room could not tell the difference, and an ordering drawn from bands that
 * overlap would launder sampling noise into a decision about revenue.
 */
export type RehearsalReading =
  | { kind: 'ahead'; sentence: string }
  | { kind: 'too-close'; sentence: string }
  | { kind: 'alone' }
  | { kind: 'withheld'; sentence: string };

/**
 * Read a finished run's decision out of the analysis response.
 *
 * Three things this does that are easy to get wrong, and one of them is
 * currently wrong elsewhere in the app:
 *
 * 1. **The artifact is nested.** `GET /api/simulations/{id}/analysis` answers
 *    `{simulation_id, schema_version, artifact, generated_at}`, so the figures
 *    live at `payload.artifact`. Reading `payload.scoreboard` yields
 *    `undefined` on every run that ever finishes — no error, no empty state,
 *    just a screen permanently saying the comparison has not been worked out.
 *    `MessagesStagePage.tsx` does exactly that today (see the report handed
 *    over with this work); the report viewer and the print view both read
 *    `payload.artifact` and are correct.
 *
 * 2. **The schema is checked before the figures are read.** Not ceremony here:
 *    what decides `winner_variant_key` changed between artifact versions 3 and
 *    4 — from treating the arenas as independent samples to the paired
 *    comparison over the shared room — so the same field carries a different
 *    claim in an older artifact than this build believes. Refusing is the
 *    honest answer, and the run is still one click away.
 *
 * 3. **A winner the server declined to name is never invented.** When
 *    `winner_variant_key` is null the server has said the top two do not
 *    separate, and `verdict` says so in words including what it would take to
 *    settle it. Ordering the rows and letting the reader assume the top one won
 *    is the same defect one layer out.
 */
export function readRehearsal(payload: AnalysisResponse): RehearsalReading {
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
  if (!board || board.variants.length === 0) return { kind: 'alone' };

  if (board.winner_variant_key) {
    return { kind: 'ahead', sentence: board.verdict };
  }

  return {
    kind: 'too-close',
    sentence:
      board.verdict ||
      'The room could not tell them apart. Going with the top row would be going with noise.',
  };
}

/**
 * How many finished rehearsals get their decision fetched on load.
 *
 * Each one is its own request, and the list is a summary rather than the
 * reading surface — the run's own report is one click from every row. Four
 * covers what a founder can see without scrolling; the rest say plainly that
 * the decision is on the run's page rather than pretending there is none.
 */
export const MAX_DECISIONS_FETCHED = 4;
