/**
 * What "finished" is spelled as in the database.
 *
 * **It is `complete`, not `completed`.** The ingestion pipeline writes
 * `"complete"` and the simulation runner writes `"complete"`; on 2026-08-05
 * production held 27 documents and 52 simulations spelled that way, and every
 * row spelled `completed` had been seeded by hand for testing.
 *
 * The staged rail first shipped comparing against `"completed"` and was wrong
 * on every real row — a founder who had uploaded and processed a deck was told
 * "Nothing to read yet", and a product with a finished run was told nothing had
 * run. **It passed its own tests and its own screenshots**, because the seed
 * data was written from the same wrong assumption as the code. Found by
 * uploading a real file to production and reading what came back.
 *
 * One module rather than a comparison at each call site: a status string
 * compared in eight places is eight chances to get it wrong, and this is the
 * "two sources of truth for one value" class the codebase keeps producing.
 * Both spellings are accepted because the database genuinely contains both.
 */

const READ = new Set(['complete', 'completed']);
const IN_FLIGHT = new Set(['pending', 'processing']);
const RUN_DONE = new Set(['complete', 'completed']);
const RUN_IN_FLIGHT = new Set(['pending', 'running', 'ready']);

/** A document whose text reached the product. */
export function isRead(status: string | null | undefined): boolean {
  return READ.has(status ?? '');
}

/** A document still being read. */
export function isBeingRead(status: string | null | undefined): boolean {
  return IN_FLIGHT.has(status ?? '');
}

/** A run that produced a result. */
export function isFinished(status: string | null | undefined): boolean {
  return RUN_DONE.has(status ?? '');
}

/** A run that has not finished and has not failed. */
export function isUnderway(status: string | null | undefined): boolean {
  return RUN_IN_FLIGHT.has(status ?? '');
}

/**
 * What a document's state is called on screen.
 *
 * Falls through to the raw value rather than to a blank, because an unknown
 * status is something to notice — a blank reads as "nothing to say about this
 * file", which is a different claim.
 */
export function documentStateWord(status: string | null | undefined): string {
  if (isRead(status)) return 'Read';
  if (status === 'processing') return 'Being read';
  if (status === 'pending') return 'Queued';
  if (status === 'failed') return 'Could not be read';
  return status ?? 'Unknown';
}
