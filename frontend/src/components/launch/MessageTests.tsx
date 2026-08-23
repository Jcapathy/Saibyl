import { useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';

import api from '@/lib/api';
import type { AnalysisResponse } from '@/lib/analysis';
import { isFinished } from '@/lib/status';
import type { Simulation } from '@/types';
import { Card, Deal, Eyebrow } from '@/components/design';
import { EmptyState } from '@/components/stages/StagePrimitives';
import StatusBadge from '@/components/StatusBadge';

import {
  MAX_DECISIONS_READ,
  canStillTakeWordings,
  isHeadToHead,
  newRunHref,
  readDecision,
  writingHref,
  type Decision,
} from './launch';

/**
 * Several ways of saying the same thing, read by one room, and what it decided.
 *
 * This is the panel the Launch page is about, so it is the one card on the
 * screen carrying stage depth. Everything inside it is a dense row on a
 * hairline: a list where every row has a shadow is a list where nothing does.
 *
 * **The state this surface exists to render well is "too close to call."** A
 * founder reads this immediately before deciding where a launch budget goes,
 * and an ordering drawn from bands that overlap would launder sampling noise
 * into that decision. So the refusal gets the same tinted block, at the same
 * size, in the same place as a win — amber rather than grey, because it is a
 * finding to act on and not a hole in the data. Greyed, it reads as a loss.
 *
 * The words are chosen for a reader who has never sat through a marketing
 * course and will not read documentation — the register of
 * `components/founder/AudienceReview.tsx`. Nobody should have to learn a
 * discipline's vocabulary to operate their own product.
 */

/** A row's decision, keyed by run. Absent means "not fetched", never "none". */
type Decisions = Record<string, Decision>;

function whenWords(run: Simulation): string {
  const when = new Date(run.completed_at ?? run.created_at);
  // An "Invalid Date" beside a run name is worse than no date at all.
  return Number.isNaN(when.getTime())
    ? ''
    : when.toLocaleDateString(undefined, {
        day: 'numeric',
        month: 'short',
        year: 'numeric',
      });
}

/**
 * How many of the room changed their mind between the leading two.
 *
 * A field the backend computes and no screen has ever rendered. It is the
 * honest denominator under every verdict above it: somebody who answered the
 * same way to both wordings carries no information about which is better, so a
 * founder who cannot see this number cannot tell a decisive result from a thin
 * one that happened to land on a winner.
 */
function Switched({ readBoth, switched }: { readBoth: number; switched: number }) {
  if (readBoth <= 0) return null;
  return (
    <p className="text-[11.5px] text-saibyl-muted mt-2 leading-relaxed">
      <span className="font-mono tabular-nums">{switched}</span> of the{' '}
      <span className="font-mono tabular-nums">{readBoth}</span> people who read
      both of the leading two answered differently between them. Those are the
      only people this rests on &mdash; everyone who did not budge tells you
      nothing either way.
    </p>
  );
}

/**
 * What the room decided, in the four shapes a finished run can honestly take.
 *
 * A win and a refusal are the same block in two colours, on purpose. The first
 * draft of this had the win in green type and the refusal as a quieter line,
 * and that is the arrangement that teaches a reader to skim past exactly the
 * sentence they most need.
 */
function Verdict({ decision }: { decision: Decision }) {
  if (decision.kind === 'ahead') {
    return (
      <div className="rounded-xl border border-saibyl-green/30 bg-saibyl-green/[0.08] p-3.5 mt-2.5">
        <p className="text-[13px] font-medium text-saibyl-positive">
          {decision.winner
            ? `One came out ahead: ${decision.winner}`
            : 'One of them came out ahead.'}
        </p>
        <p className="text-[12px] text-saibyl-muted mt-1.5 leading-relaxed">
          {decision.sentence}
        </p>
        {decision.switched && (
          <Switched
            readBoth={decision.switched.readBoth}
            switched={decision.switched.switched}
          />
        )}
      </div>
    );
  }

  if (decision.kind === 'too-close') {
    return (
      <div className="rounded-xl border border-[#f59e0b]/30 bg-[#f59e0b]/[0.08] p-3.5 mt-2.5">
        <p className="text-[13px] font-medium text-saibyl-warning">
          Too close to call.
        </p>
        <p className="text-[12px] text-saibyl-muted mt-1.5 leading-relaxed">
          {decision.sentence}
        </p>
        {decision.switched && (
          <Switched
            readBoth={decision.switched.readBoth}
            switched={decision.switched.switched}
          />
        )}
      </div>
    );
  }

  if (decision.kind === 'withheld') {
    return (
      <p className="text-[12px] text-saibyl-muted mt-2 leading-relaxed">
        {decision.sentence}
      </p>
    );
  }

  return (
    <p className="text-[12px] text-saibyl-muted mt-2 leading-relaxed">
      This one finished and the side-by-side has not been worked out yet. Open
      it and everything the room said is there.
    </p>
  );
}

export default function MessageTests({
  productId,
  runs,
}: {
  productId: string;
  runs: Simulation[];
}) {
  const tests = useMemo(() => runs.filter(isHeadToHead), [runs]);
  const waiting = useMemo(() => runs.filter(canStillTakeWordings), [runs]);

  const [decisions, setDecisions] = useState<Decisions>({});

  /* Which rows get their decision fetched, as a stable string so the effect
     below does not re-run on every render of a freshly-built array. */
  const wanted = useMemo(
    () =>
      tests
        .filter((run) => isFinished(run.status))
        .slice(0, MAX_DECISIONS_READ)
        .map((run) => run.id)
        .join(','),
    [tests],
  );

  /* Every setter fires from a promise callback rather than from the effect
     body: a synchronous `setState` here is the cascading render this codebase
     has been bitten by, and the initial empty map already covers first paint.

     A failure is deliberately silent per row. A run nobody has worked out yet
     answers 404 and one whose analysis died answers 409 — neither is an error
     on *this* screen, and the row already says where to read the run. Turning
     an ordinary 404 into a banner over the whole list is how a page starts
     crying wolf. */
  useEffect(() => {
    const ids = wanted ? wanted.split(',') : [];
    if (ids.length === 0) return;

    let cancelled = false;
    void Promise.all(
      ids.map((id) =>
        api
          .get<AnalysisResponse>(`/simulations/${id}/analysis`)
          .then((res) => [id, readDecision(res.data)] as const)
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

  return (
    <Card carries="stage" className="p-6 space-y-5">
      <div>
        <Eyebrow>Head to head</Eyebrow>
        <h2 className="text-[19px] font-semibold text-saibyl-ink mt-1.5 tracking-[-0.02em]">
          Which way of saying it wins
        </h2>
        <p className="text-[12.5px] text-saibyl-muted mt-2 leading-relaxed max-w-2xl">
          Write up to eight ways of saying the same thing. One room of buyers
          reads every one of them, in the same order, so whatever changes
          between them is down to the words and not to who happened to be
          listening. You get a side by side of how each one landed, and how many
          people changed their mind between the leading two.
        </p>
        <p className="text-[12.5px] text-saibyl-muted mt-2 leading-relaxed max-w-2xl">
          When the room cannot tell two of them apart, you are told so in those
          words. Ranking things that did not separate is a budget spent on a
          coin toss.
        </p>
      </div>

      {tests.length === 0 ? (
        <EmptyState
          headline="No wordings have gone head to head yet"
          body="Write two or more ways of saying the same thing on a run's own page before it starts, and one room reads all of them. Each extra one is a full run, so the price is shown before anything goes."
          action={{ label: 'Start a run', href: newRunHref(productId) }}
        />
      ) : (
        <div className="space-y-2">
          {tests.map((run, index) => {
            const done = isFinished(run.status);
            const decision = decisions[run.id];
            const meta = [
              `${run.variants} ways of saying it, one room`,
              whenWords(run),
            ]
              .filter(Boolean)
              .join(' · ');

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
                    {meta}
                  </p>

                  {!done ? (
                    <p className="text-[12px] text-saibyl-muted mt-2 leading-relaxed">
                      This one has not finished. Open it and you can watch the
                      room work through each wording.
                    </p>
                  ) : decision ? (
                    <Verdict decision={decision} />
                  ) : (
                    <p className="text-[12px] text-saibyl-muted mt-2 leading-relaxed">
                      What the room decided is on this run&rsquo;s own page.
                    </p>
                  )}

                  <div className="flex flex-wrap items-center gap-4 mt-3">
                    <Link
                      to={
                        done
                          ? `/app/simulations/${run.id}/compare`
                          : writingHref(run.id)
                      }
                      className="text-[12.5px] text-saibyl-blue hover:underline"
                    >
                      {done ? 'See how each one landed' : 'Open it'}
                    </Link>
                    {done && (
                      <Link
                        to={`/app/simulations/${run.id}/report`}
                        className="text-[12.5px] text-saibyl-muted hover:text-saibyl-blue hover:underline"
                      >
                        Read what they said
                      </Link>
                    )}
                  </div>
                </Card>
              </Deal>
            );
          })}
        </div>
      )}

      {/* ── Where the next set gets written ──────────────────────────────
          Deliberately a route out rather than a form. How many wordings a run
          carries is set from the copy actually written, on the run's own page,
          by `PUT /api/variants/{id}`. Offering a number here would be a second
          way to configure one object, and the two would eventually disagree
          about what was bought — a run priced for four and executed as one has
          already happened in this codebase. */}
      <div className="border-t border-saibyl-border pt-5 space-y-3">
        <Eyebrow>Write the next set</Eyebrow>
        <p className="text-[12.5px] text-saibyl-muted leading-relaxed max-w-2xl">
          The wordings are written on a run&rsquo;s own page, and only before it
          starts &mdash; the whole point of the comparison is that the runs
          differed in the words and nothing else, so they are fixed once one has
          gone. Every wording you add is a full run of its own, so the price
          rises with each and you see the exact figure before anything starts.
        </p>

        {waiting.length === 0 ? (
          <Link
            to={newRunHref(productId)}
            className="inline-flex text-[12.5px] text-saibyl-blue hover:underline"
          >
            Start a run and write them
          </Link>
        ) : (
          <>
            <ul className="space-y-2">
              {waiting.map((run) => (
                <li key={run.id}>
                  <Card
                    carries="density"
                    className="flex flex-wrap items-center justify-between gap-x-4 gap-y-1.5 px-4 py-3"
                  >
                    <span className="min-w-0">
                      <span className="block truncate text-[13.5px] text-saibyl-ink">
                        {run.name}
                      </span>
                      <span className="block text-[11.5px] text-saibyl-muted">
                        Not started &mdash; the words can still change
                      </span>
                    </span>
                    <Link
                      to={writingHref(run.id)}
                      className="shrink-0 text-[12.5px] text-saibyl-blue hover:underline"
                    >
                      Write the wordings
                    </Link>
                  </Card>
                </li>
              ))}
            </ul>
            <Link
              to={newRunHref(productId)}
              className="inline-flex text-[12.5px] text-saibyl-muted hover:text-saibyl-blue hover:underline"
            >
              Or start a new run
            </Link>
          </>
        )}
      </div>
    </Card>
  );
}
