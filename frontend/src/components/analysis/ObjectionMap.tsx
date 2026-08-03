import { useState } from 'react';
import { ChevronDown, ChevronRight, Quote } from 'lucide-react';
import { PLATFORM_NAMES } from '@/lib/constants';
import type { ObjectionSummary } from '@/lib/analysis';
import Panel, { NoData } from './Panel';

/**
 * Canonical objections, ranked by load-bearing weight.
 *
 * Not by frequency. Reach x intensity x cohort spread is what separates the
 * objection that loses the deal from the one that is merely most quotable —
 * an objection voiced once by every cohort, firmly, outranks one repeated ten
 * times inside a single archetype.
 *
 * Every row expands to the verbatim agent quotes behind it. That is the
 * difference between a finding and an assertion.
 */
export default function ObjectionMap({
  objections,
  onDrillDown,
}: {
  objections: ObjectionSummary[];
  onDrillDown?: (eventIds: string[], label: string) => void;
}) {
  const [expanded, setExpanded] = useState<string | null>(
    objections.length > 0 ? objections[0].key : null,
  );

  if (objections.length === 0) {
    return (
      <Panel title="Objection map">
        <NoData>
          No agent raised an objection to the subject in this run. That is a
          finding, not a gap — but check the stance split before reading it as
          approval: a swarm that was mostly off-topic never engaged.
        </NoData>
      </Panel>
    );
  }

  const maxScore = Math.max(...objections.map((o) => o.load_bearing_score), 1);

  return (
    <Panel
      title="Objection map"
      note={
        <>
          Ranked by load-bearing weight — how far it reached, how firmly it was
          held, and how many cohorts it crossed. Not by how often it was
          repeated.
        </>
      }
    >
      <div className="divide-y divide-saibyl-border">
        {objections.map((objection) => {
          const open = expanded === objection.key;
          const cohorts = Object.entries(objection.cohort_spread).sort(
            (a, b) => b[1] - a[1],
          );

          return (
            <div key={objection.key} className="py-3 first:pt-0 last:pb-0">
              <button
                type="button"
                onClick={() => setExpanded(open ? null : objection.key)}
                className="w-full text-left group"
              >
                <div className="flex items-start gap-2">
                  {open ? (
                    <ChevronDown className="w-4 h-4 text-saibyl-muted mt-0.5 shrink-0" />
                  ) : (
                    <ChevronRight className="w-4 h-4 text-saibyl-muted mt-0.5 shrink-0" />
                  )}
                  <div className="flex-1 min-w-0">
                    <div className="flex items-baseline justify-between gap-3">
                      <span className="text-[14px] font-semibold text-saibyl-platinum group-hover:text-white transition-colors">
                        {objection.label}
                      </span>
                      <span className="text-[11px] font-mono text-saibyl-gold whitespace-nowrap">
                        {objection.load_bearing_score.toFixed(1)}
                      </span>
                    </div>
                    <div className="h-1.5 bg-saibyl-void rounded-full mt-1.5 overflow-hidden">
                      <div
                        className="h-full bg-saibyl-gold rounded-full"
                        style={{
                          width: `${(objection.load_bearing_score / maxScore) * 100}%`,
                        }}
                      />
                    </div>
                    <p className="text-[11px] text-saibyl-muted mt-1.5">
                      {objection.agent_count} agents · first seen round{' '}
                      {objection.first_round_seen ?? '—'}
                      {objection.originating_cohort
                        ? ` · started with ${objection.originating_cohort}`
                        : ''}
                      {cohorts.length > 1
                        ? ` · reached ${cohorts.length} cohorts`
                        : ' · confined to one cohort'}
                    </p>
                  </div>
                </div>
              </button>

              {open && (
                <div className="mt-3 ml-6 space-y-3">
                  {objection.summary && (
                    <p className="text-[12px] text-saibyl-silver leading-relaxed">
                      {objection.summary}
                    </p>
                  )}

                  {cohorts.length > 0 && (
                    <div>
                      <p className="text-[10px] uppercase tracking-wider text-saibyl-muted mb-1.5">
                        Share of each cohort holding it
                      </p>
                      <div className="space-y-1">
                        {cohorts.map(([cohort, share]) => (
                          <div key={cohort} className="flex items-center gap-2">
                            <span className="text-[11px] text-saibyl-silver w-40 truncate">
                              {cohort}
                            </span>
                            <div className="flex-1 h-1.5 bg-saibyl-void rounded-full overflow-hidden">
                              <div
                                className="h-full bg-saibyl-insight-violet rounded-full"
                                style={{ width: `${Math.min(share * 100, 100)}%` }}
                              />
                            </div>
                            <span className="text-[10px] text-saibyl-muted w-10 text-right">
                              {(share * 100).toFixed(0)}%
                            </span>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}

                  {objection.quotes.length > 0 && (
                    <div className="space-y-2">
                      {objection.quotes.map((quote) => (
                        <blockquote
                          key={quote.event_id}
                          className="border-l-2 border-saibyl-gold/40 pl-3 py-0.5"
                        >
                          <p className="text-[12px] text-saibyl-silver italic leading-relaxed">
                            <Quote className="w-3 h-3 inline -mt-1 mr-1 text-saibyl-muted" />
                            {quote.text}
                          </p>
                          <p className="text-[10px] text-saibyl-muted mt-1">
                            @{quote.agent_username}
                            {quote.archetype ? ` · ${quote.archetype}` : ''}
                            {quote.platform
                              ? ` · ${PLATFORM_NAMES[quote.platform] ?? quote.platform}`
                              : ''}
                            {quote.round_number != null ? ` · round ${quote.round_number}` : ''}
                          </p>
                        </blockquote>
                      ))}
                    </div>
                  )}

                  {onDrillDown && (
                    <button
                      type="button"
                      onClick={() =>
                        onDrillDown(objection.event_ids, objection.label)
                      }
                      className="text-[11px] text-saibyl-signal-blue hover:underline"
                    >
                      Show all {objection.event_count} events →
                    </button>
                  )}
                </div>
              )}
            </div>
          );
        })}
      </div>
    </Panel>
  );
}
