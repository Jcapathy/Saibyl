import { Loader2 } from 'lucide-react';

import { cn } from '@/lib/utils';
import { Card, Deal, Eyebrow, Rise, dealDelayMs } from '@/components/design';
import { StageError } from '@/components/stages/StagePrimitives';
import SiteCheckForm from '@/components/website/SiteCheckForm';
import SiteCritique from '@/components/website/SiteCritique';
import SiteRevisionPanel from '@/components/website/SiteRevisionPanel';
import { SiteStatusChip } from '@/components/website/chips';
import { CHECK_PROGRESS, isCheckUnderway } from '@/components/website/types';

import type { SiteChecks } from './checks';

/**
 * The page a stranger reads, and the rewrite that has to beat it.
 *
 * "Test the fix on the same room, and watch the delta" is one movement, not
 * three features, so it is one panel: paste the address, see what six readers
 * took away, rewrite it, and let the same six score both. Splitting the check
 * from its revision is how the revision stopped being found.
 *
 * ── The arrangement is the artboard's, not an invention ─────────────────────
 *
 * `design/Main.dc.html` puts the thing a screen is *about* in one soft-shadowed
 * glass card — a heading, a sentence, and the controls that start the work —
 * and everything that card *produced* below it, on the washed ground. That is
 * exactly the shape here: the stage card is the address and the checks you have
 * run; the findings and the rewrite are the output stack beneath it.
 *
 * The row for the check you are looking at wears the artboard's active step:
 * blue hairline, blue tint, no lift. A card that is already open should not
 * offer to rise.
 *
 * Two things are deliberately *not* re-typed here. The critique and the
 * revision panel are the components the audience step renders, with the same
 * props — a second implementation of a check would drift from the first inside
 * a month. And nothing in this file sets a type size the app did not already
 * use, because the canvas is explicit that density does not change: the card
 * heading is 15px because every other card heading in the app is 15px, not
 * because a shared primitive re-decided it.
 */

/** The findings arrive after the card that produced them. The artboard's beat. */
const AFTER_THE_CARD_MS = dealDelayMs(2);

export default function SiteCheckPanel({
  productId,
  checks,
}: {
  productId: string;
  checks: SiteChecks;
}) {
  const { rows, active, underway, opening, error, reload, open, started } = checks;

  /* A check the worker has finished with, either way. A check still being read
     has nothing to show below the card, and rendering the stack for it would
     put an empty block where the findings are about to land. */
  const settled =
    active !== null && (active.status === 'complete' || active.status === 'failed')
      ? active
      : null;

  /* The way forward from a check that died: the address box is already on
     screen above, so the honest fix is to put the founder's cursor in it
     rather than open a second copy of the same form somewhere else. */
  const focusAddress = () => {
    const field = document.getElementById('site-check-url');
    if (field instanceof HTMLInputElement) field.focus();
  };

  return (
    <div className="space-y-6">
      <Rise delayMs={dealDelayMs(1)}>
        <Card carries="stage" className="p-5 sm:p-6 space-y-4">
          <div>
            {/* Live only while a page is genuinely being read. The pulse is a
                state, and it stops meaning anything on a static surface. */}
            <Eyebrow live={underway}>On the page</Eyebrow>
            <h2 className="text-[15px] font-semibold text-saibyl-ink mt-1">
              What your page says before you do
            </h2>
            <p className="text-[12.5px] text-saibyl-muted mt-1.5 leading-relaxed max-w-2xl">
              Six reviewers read your page the way a stranger would &mdash; the
              reading order, the trust signals, the route to action, the words,
              the phone experience, the look &mdash; and tell you what they take
              away. Then we rewrite it and let the same six score the difference.
            </p>
          </div>

          <SiteCheckForm productId={productId} onStarted={started} />

          {error && <StageError message={error} retry={reload} />}

          {rows.length > 0 && (
            <div className="space-y-2">
              <p className="text-[12.5px] text-saibyl-silver">
                Pages you have checked
              </p>

              <ul className="space-y-1.5">
                {rows.map((row, index) => {
                  /* While a check is underway the list row lags the polled
                     copy, so the polled copy wins for its own row. */
                  const live = active?.id === row.id ? active : null;
                  const status = live?.status ?? row.status;
                  const score = live?.critique?.overall_score ?? row.overall_score;
                  const isOpen = active?.id === row.id;

                  return (
                    <Deal as="li" key={row.id} index={index}>
                      <Card
                        carries="density"
                        lift={!isOpen}
                        className={cn(
                          'rounded-xl overflow-hidden transition-colors',
                          isOpen
                            ? 'border-saibyl-border-active bg-saibyl-blue/[0.07]'
                            : 'hover:border-saibyl-blue/40',
                        )}
                      >
                        <button
                          type="button"
                          onClick={() => open(row.id)}
                          className="w-full flex flex-wrap items-center justify-between gap-2 px-4 py-3 text-left"
                        >
                          <span className="text-[13px] text-saibyl-ink truncate">
                            {row.url}
                          </span>
                          <span className="flex items-center gap-2 shrink-0">
                            {typeof score === 'number' && (
                              <span className="font-mono text-[12px] tabular-nums text-saibyl-muted">
                                {Math.round(score)}/100
                              </span>
                            )}
                            <SiteStatusChip status={status} />
                          </span>
                        </button>
                      </Card>
                    </Deal>
                  );
                })}
              </ul>

              {active !== null && isCheckUnderway(active.status) && (
                <p
                  className="flex items-center gap-2 text-[12px] text-saibyl-muted"
                  aria-live="polite"
                >
                  <Loader2 className="w-3.5 h-3.5 animate-spin shrink-0" />
                  {CHECK_PROGRESS[active.status]}
                </p>
              )}

              {opening && (
                <p className="text-[12px] text-saibyl-muted" aria-live="polite">
                  Opening&hellip;
                </p>
              )}
            </div>
          )}
        </Card>
      </Rise>

      {/* ── What the check produced ──
          Keyed on the check, so opening a different one replays the arrival and
          hands the revision panel a fresh state rather than an inherited draft.
          `SiteCritique` renders the failure case itself, in the words the
          worker returned, so there is one place a dead check is explained. */}
      {settled && (
        <Rise key={settled.id} delayMs={AFTER_THE_CARD_MS} className="space-y-6">
          <SiteCritique check={settled} onRetry={focusAddress} />
          {settled.status === 'complete' && (
            <SiteRevisionPanel snapshotId={settled.id} productId={productId} />
          )}
        </Rise>
      )}
    </div>
  );
}
