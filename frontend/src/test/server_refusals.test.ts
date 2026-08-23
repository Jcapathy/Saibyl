/**
 * A sentence the server wrote must reach the founder who caused it.
 *
 * Two refusals were being thrown away on this side of the wire, and both are
 * the same shape as the blocker that stopped the last release: a guard added to
 * one side of a two-call contract.
 *
 *  - `run_prepare_agents` refuses to rebuild a room whose people have already
 *    posted, with a sentence written to be read. `handleRunNow` polled until
 *    `status === 'failed'` and then rendered a hard-coded guess — "Check that
 *    you picked at least one group of buyers" — which for that case is advice
 *    about the one thing a retry cannot fix. The founder clicked again and paid
 *    for another swarm.
 *
 *  - `DELETE /simulations/{id}` now answers 409 when the run is the "before"
 *    for a re-simulation, because deleting it cascades away a before/after the
 *    founder paid for. `handleDelete` used `Promise.all` with no catch, so the
 *    rejection was unhandled: nothing was deleted, nothing was said, and the
 *    button looked broken.
 *
 * Static scans rather than renders, following `ia.test.ts`: the claim is about
 * what the shipped source does with a failure, and comments are stripped so a
 * rule never matches the paragraph explaining the rule.
 */
import { describe, expect, it } from 'vitest';

import { sourceFiles } from './source';

function fileNamed(path: string) {
  const found = sourceFiles().find((f) => f.path === path);
  if (!found) throw new Error(`${path} is gone — update this test`);
  return found;
}

describe('a failed preparation shows the row’s own sentence', () => {
  const page = fileNamed('src/pages/SimulationDetailPage.tsx');

  it('prefers error_message over the hard-coded guess', () => {
    const block = page.code.slice(
      page.code.indexOf("status === 'failed'"),
      page.code.indexOf("status === 'failed'") + 600,
    );

    expect(block).toContain('error_message');
    // The guess survives only as the fallback for a row carrying nothing.
    const guessAt = block.indexOf('We could not build the room');
    const readAt = block.indexOf('error_message');
    expect(readAt).toBeGreaterThan(-1);
    expect(guessAt).toBeGreaterThan(readAt);
  });
});

describe('a refused delete is read rather than dropped', () => {
  const page = fileNamed('src/pages/SimulationsPage.tsx');

  it('does not fire deletes through an uncaught Promise.all', () => {
    const handler = page.code.slice(
      page.code.indexOf('async function handleDelete'),
      page.code.indexOf('async function handleDelete') + 1200,
    );

    expect(handler).not.toContain('Promise.all(');
    expect(handler).toContain('Promise.allSettled(');
  });

  it('puts the server’s own words on screen', () => {
    const handler = page.code.slice(
      page.code.indexOf('async function handleDelete'),
      page.code.indexOf('async function handleDelete') + 1200,
    );

    expect(handler).toContain('getErrorMessage(');
    expect(handler).toContain('setDeleteError(');
    // And the state it sets is actually rendered somewhere on the page.
    expect(page.code).toMatch(/\{deleteError\s*&&/);
  });
});
