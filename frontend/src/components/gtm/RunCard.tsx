import { formatDistanceToNow } from 'date-fns';
import { AlertTriangle, Ban, Check, Info, Loader2 } from 'lucide-react';
import {
  ANGLE_COPY,
  TONE_COLOR,
  describeRun,
  derivedFromLabel,
  formatCredits,
  runOutcome,
} from '@/lib/gtm';
import type { RunTone } from '@/lib/gtm';
import type { DiscoveryQuery, DiscoveryRun } from '@/types';

/**
 * One discovery search, shown as what happened rather than as a status value.
 *
 * The distinction this component exists to protect: **a failed run is not an
 * empty run.** `failed` means the search provider was unreachable and nothing
 * was looked up. A `completed` run with zero candidates means every search ran
 * and the market came back empty — a real finding, and one a founder may act on.
 * Rendering both as a grey "0 results" would tell somebody their market is dead
 * when the truth was a vendor outage. `describeRun` draws the line; this only
 * paints it.
 *
 * It also shows the run's **age**, always. Discovery runs inline in the request
 * that started it and there is no worker to reap a run whose process died, so a
 * row can sit at `running` forever by design. Age is what turns that from a
 * spinner nobody can interpret into a legible fact, and past twice the server's
 * own deadline the card says so outright.
 */

// `style` is passed at the call site to tint the icon by tone, so the declared
// prop type has to admit it. Typed as the icon components' real shape rather
// than the two props we happen to use — narrowing here is what made `tsc -b`
// reject a call that `tsc --noEmit` let through.
const TONE_ICON: Record<
  RunTone,
  React.ComponentType<React.SVGProps<SVGSVGElement>>
> = {
  positive: Check,
  negative: Ban,
  warning: AlertTriangle,
  neutral: Info,
  active: Loader2,
};

/** The compiled searches, in the founder's words and the provider's. */
export function QueryList({ queries }: { queries: DiscoveryQuery[] }) {
  if (queries.length === 0) return null;

  const byAngle = new Map<string, DiscoveryQuery[]>();
  for (const query of queries) {
    const bucket = byAngle.get(query.angle);
    if (bucket) bucket.push(query);
    else byAngle.set(query.angle, [query]);
  }

  return (
    <div className="space-y-4">
      {[...byAngle.entries()].map(([angle, group]) => {
        const copy = ANGLE_COPY[angle as DiscoveryQuery['angle']];
        return (
          <div key={angle}>
            <p className="text-[12px] font-medium text-saibyl-ink">
              {copy?.label ?? angle.replace(/_/g, ' ')}
            </p>
            {copy && (
              <p className="text-[11px] text-saibyl-muted mt-0.5 leading-relaxed">{copy.hint}</p>
            )}
            <ul className="mt-2 space-y-1.5">
              {group.map((query, i) => (
                <li
                  key={`${query.archetype_id}-${query.angle}-${i}`}
                  className="rounded-lg border border-saibyl-border bg-white px-3 py-2"
                >
                  <p className="font-mono text-[12px] text-saibyl-ink break-words">
                    {query.query}
                  </p>
                  <p className="text-[10px] text-saibyl-muted mt-1">
                    Looking for {query.archetype_label || 'your buyers'}
                    {query.derived_from.length > 0 && (
                      <>
                        , from {query.derived_from.map(derivedFromLabel).join(', ')}
                      </>
                    )}
                  </p>
                </li>
              ))}
            </ul>
          </div>
        );
      })}
    </div>
  );
}

export function RunCard({
  run,
  /** Rendered under the counters — usually a link into the candidates found. */
  action,
}: {
  run: DiscoveryRun;
  action?: React.ReactNode;
}) {
  const shown = describeRun(run);
  const outcome = runOutcome(run);
  const color = TONE_COLOR[shown.tone];
  const Icon = TONE_ICON[shown.tone];
  const started = new Date(run.created_at);
  const validDate = Number.isFinite(started.getTime());

  return (
    <div
      className="rounded-2xl border bg-white p-5"
      style={{ borderColor: `${color}33` }}
    >
      <div className="flex items-start justify-between gap-4">
        <div className="flex items-start gap-2.5 min-w-0">
          <Icon
            className={`w-4 h-4 shrink-0 mt-0.5 ${
              outcome.kind === 'running' && !outcome.stalled ? 'animate-spin' : ''
            }`}
            style={{ color }}
          />
          <div className="min-w-0">
            <p className="text-[14px] font-medium" style={{ color }}>
              {shown.headline}
            </p>
            <p className="text-[12px] text-saibyl-silver mt-1 leading-relaxed max-w-2xl">
              {shown.detail}
            </p>
          </div>
        </div>

        {/* Age, on every run and not only the stuck ones. A reader cannot tell
            a run that is 20 seconds old from one that is three days old
            otherwise, and that is the whole difference between "wait" and
            "this is never coming back". */}
        {validDate && (
          <p
            className="text-[11px] font-mono text-saibyl-muted whitespace-nowrap shrink-0"
            title={started.toLocaleString()}
          >
            {formatDistanceToNow(started, { addSuffix: true })}
          </p>
        )}
      </div>

      {/* The provider's own words on a failure. Shown verbatim rather than
          summarised — it is the only thing that says which vendor broke. */}
      {run.error && (
        <p className="mt-3 rounded-lg bg-[#14294a]/[0.04] px-3 py-2 font-mono text-[11px] text-saibyl-silver break-words">
          {run.error}
        </p>
      )}

      {run.purged_at && (
        <p className="mt-3 text-[11px] text-saibyl-warning leading-relaxed">
          The companies from this search were deleted when you cleared your saved
          companies. This record is kept because it holds what the search cost, which is
          not information about anybody.
        </p>
      )}

      <dl className="mt-4 flex flex-wrap gap-x-6 gap-y-2">
        <Counter label="Companies" value={run.candidates_found} />
        <Counter label="Searches run" value={`${run.queries_completed} of ${run.query_count}`} />
        {run.queries_failed > 0 && <Counter label="Searches that errored" value={run.queries_failed} />}
        {run.contacts_enabled && <Counter label="People" value={run.contacts_found} />}
        <Counter label="Credits" value={formatCredits(run.credits_charged)} />
      </dl>

      {action && <div className="mt-4">{action}</div>}
    </div>
  );
}

function Counter({ label, value }: { label: string; value: string | number }) {
  return (
    <div>
      <dt className="text-[10px] uppercase tracking-widest text-saibyl-muted">{label}</dt>
      <dd className="font-mono text-[13px] text-saibyl-ink mt-0.5">{value}</dd>
    </div>
  );
}
