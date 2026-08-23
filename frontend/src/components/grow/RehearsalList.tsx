import { useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';

import api from '@/lib/api';
import { isFinished } from '@/lib/status';
import type { AnalysisResponse } from '@/lib/analysis';
import { Card, Deal, Eyebrow } from '@/components/design';
import { EmptyState } from '@/components/stages/StagePrimitives';
import StatusBadge from '@/components/StatusBadge';

import {
  MAX_DECISIONS_FETCHED,
  comparedMoreThanOne,
  readRehearsal,
  rehearsalHref,
  type GrowthRun,
  type RehearsalReading,
} from './grow';

/**
 * Changes this product has already put in front of a room, and what came back.
 *
 * The whole value of the list is the middle line of each row, and the state
 * that line most often has to carry is **"too close to call"**. A founder about
 * to raise a price wants to be told when the room could not tell the
 * difference; handing them an ordering drawn from bands that overlap would
 * launder sampling noise into a decision about revenue. So the refusal is
 * rendered as a result in its own right, in the same weight as a win, rather
 * than as an absence the eye slides past.
 *
 * Rows are the dense kind — hairline, no shadow — because a list where every
 * row has depth is a list where nothing does. The one thing that carries the
 * shadow on this screen is the panel the screen is about.
 */

/** A row's decision, or the honest reason there isn't one on this screen. */
type Decisions = Record<string, RehearsalReading>;

function whenWords(run: GrowthRun): string {
  const stamp = run.completed_at ?? run.created_at;
  return new Date(stamp).toLocaleDateString(undefined, {
    day: 'numeric',
    month: 'short',
    year: 'numeric',
  });
}

/**
 * The decision line, in the four shapes a finished run can honestly take.
 *
 * Colour carries the reading before the words do: green for a result that
 * separates, amber for one that does not. Amber and not grey — "too close" is
 * something to act on, not a gap in the data.
 */
function Decision({ reading }: { reading: RehearsalReading }) {
  if (reading.kind === 'ahead') {
    return (
      <>
        <p className="text-[12.5px] text-saibyl-positive mt-2">
          One of them came out ahead.
        </p>
        <p className="text-[12px] text-saibyl-muted mt-1 leading-relaxed">
          {reading.sentence}
        </p>
      </>
    );
  }

  if (reading.kind === 'too-close') {
    return (
      <>
        <p className="text-[12.5px] text-saibyl-warning mt-2">Too close to call.</p>
        <p className="text-[12px] text-saibyl-muted mt-1 leading-relaxed">
          {reading.sentence}
        </p>
      </>
    );
  }

  if (reading.kind === 'withheld') {
    return (
      <p className="text-[12px] text-saibyl-muted mt-2 leading-relaxed">
        {reading.sentence}
      </p>
    );
  }

  return (
    <p className="text-[12px] text-saibyl-muted mt-2 leading-relaxed">
      One thing went in front of the room, so there is nothing here it was
      weighed against. Everything they said about it is on its page.
    </p>
  );
}

export default function RehearsalList({
  productId,
  runs,
  settled,
}: {
  productId: string;
  runs: GrowthRun[];
  /**
   * Whether `runs` is an answer about this product yet.
   *
   * An empty list means two opposite things — "you have rehearsed nothing" and
   * "we have not been told yet" — and only one of them should put a founder in
   * front of a first-run empty state. Somebody with six rehearsals switching
   * products should not read "no changes rehearsed yet" on the way.
   */
  settled: boolean;
}) {
  const [decisions, setDecisions] = useState<Decisions>({});

  /* Which rows get their decision fetched, as a stable string so the effect
     below does not re-run on every render of a freshly-built array. */
  const wanted = useMemo(
    () =>
      runs
        .filter((run) => isFinished(run.status))
        .slice(0, MAX_DECISIONS_FETCHED)
        .map((run) => run.id)
        .join(','),
    [runs],
  );

  /* Every setter fires from a promise callback rather than from the effect
     body: a synchronous `setState` here is a cascading render, and the initial
     empty map already covers the first paint.

     A failure is deliberately silent per row. A run that has not been analysed
     yet answers 404 and one whose analysis died answers 409 — neither is an
     error on *this* screen, and the row already says where to read the run.
     Turning a normal 404 into a red banner over the whole list is how a page
     starts crying wolf. */
  useEffect(() => {
    const ids = wanted ? wanted.split(',') : [];
    // Returning early rather than clearing: a synchronous `setState` in an
    // effect body is the cascading render this codebase has been bitten by, and
    // there is nothing to clear — a decision is only ever looked up by the id
    // of a row being rendered, so an entry for a run that has left the list is
    // unreachable rather than stale.
    if (ids.length === 0) return;

    let cancelled = false;
    Promise.all(
      ids.map((id) =>
        api
          .get<AnalysisResponse>(`/simulations/${id}/analysis`)
          .then((res) => [id, readRehearsal(res.data)] as const)
          .catch(() => null),
      ),
    ).then((pairs) => {
      if (cancelled) return;
      const next: Decisions = {};
      for (const pair of pairs) {
        if (pair) next[pair[0]] = pair[1];
      }
      setDecisions(next);
    });

    return () => {
      cancelled = true;
    };
  }, [wanted]);

  if (runs.length === 0 && !settled) {
    return (
      <section className="space-y-4">
        <Eyebrow>What you have rehearsed</Eyebrow>
        <p className="text-[12.5px] text-saibyl-muted" aria-live="polite">
          Loading&hellip;
        </p>
      </section>
    );
  }

  if (runs.length === 0) {
    return (
      <section className="space-y-4">
        <Eyebrow>What you have rehearsed</Eyebrow>
        <EmptyState
          headline="No changes rehearsed yet"
          body="Once a change has been in front of a room, it lands here with what the room decided — including when it decided nothing, which is the answer worth having before you move a price."
          action={{
            label: 'Rehearse your first change',
            href: rehearsalHref(productId),
          }}
        />
      </section>
    );
  }

  return (
    <section className="space-y-4">
      <div>
        <Eyebrow>What you have rehearsed</Eyebrow>
        <p className="text-[12.5px] text-saibyl-muted mt-2 leading-relaxed max-w-2xl">
          Newest first. The decision is shown for the most recent few &mdash;
          for the rest it is on the run&rsquo;s own page, one click away.
        </p>
      </div>

      <div className="space-y-2">
        {runs.map((run, index) => {
          const done = isFinished(run.status);
          const reading = decisions[run.id];
          return (
            <Deal key={run.id} index={index}>
              <Card carries="density" className="p-4">
                <div className="flex flex-wrap items-center justify-between gap-x-3 gap-y-1.5">
                  <span className="text-[14px] font-medium text-saibyl-ink">
                    {run.name}
                  </span>
                  <StatusBadge status={run.status} />
                </div>

                <p className="font-mono text-[10.5px] tabular-nums text-saibyl-muted mt-1">
                  {whenWords(run)}
                  {comparedMoreThanOne(run)
                    ? ` · ${run.variants} things, one room`
                    : ' · one thing, one room'}
                </p>

                {!done ? (
                  <p className="text-[12px] text-saibyl-muted mt-2 leading-relaxed">
                    This one has not finished. Open it and you can watch the
                    room work through it.
                  </p>
                ) : reading ? (
                  <Decision reading={reading} />
                ) : (
                  <p className="text-[12px] text-saibyl-muted mt-2 leading-relaxed">
                    What the room decided is on this run&rsquo;s own page.
                  </p>
                )}

                <div className="flex flex-wrap items-center gap-4 mt-3">
                  <Link
                    to={
                      done
                        ? `/app/simulations/${run.id}/report`
                        : `/app/simulations/${run.id}`
                    }
                    className="text-[12.5px] text-saibyl-blue hover:underline"
                  >
                    {done ? 'Read what they said' : 'Open it'}
                  </Link>
                  {done && comparedMoreThanOne(run) && (
                    <Link
                      to={`/app/simulations/${run.id}/compare`}
                      className="text-[12.5px] text-saibyl-muted hover:text-saibyl-blue hover:underline"
                    >
                      See them side by side
                    </Link>
                  )}
                </div>
              </Card>
            </Deal>
          );
        })}
      </div>

      <Link
        to={rehearsalHref(productId)}
        className="inline-flex text-[12.5px] text-saibyl-blue hover:underline"
      >
        Rehearse another change
      </Link>
    </section>
  );
}
