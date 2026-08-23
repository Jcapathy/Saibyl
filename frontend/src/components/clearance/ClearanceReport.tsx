import { ExternalLink } from 'lucide-react';

import { Card } from '@/components/design';
import { RiskChip } from './RiskChip';
import {
  FALLBACK_DISCLAIMER,
  NOT_LEGAL_ADVICE,
  TIER_SHORT,
  type ArtStatus,
  type ClearanceArtifact,
  type RiskTier,
  type TrademarkStatus,
} from './types';

/**
 * The clearance report, rendered from the artifact and nothing else.
 *
 * Non-negotiables carried over from the skill this tab productises:
 * NOT_SEARCHED never reads as clear; the pending-landscape blind-spot
 * sentence and the disclaimer render verbatim; the search record is on the
 * page so any run can be reproduced. Nothing here is invented to fill a
 * section — an empty array renders as the honest sentence about why empty
 * is not the same as cleared.
 */

/* ------------------------------------------------------------------ */
/*  Small shared pieces                                                */
/* ------------------------------------------------------------------ */

function Section({
  heading,
  sub,
  children,
}: {
  heading: string;
  sub?: string;
  children: React.ReactNode;
}) {
  return (
    <Card carries="meaning" as="section" className="p-6">
      <h2 className="text-[15px] font-medium text-saibyl-ink">{heading}</h2>
      {sub && (
        <p className="text-[12px] text-saibyl-muted mt-1 leading-relaxed">{sub}</p>
      )}
      <div className="mt-4">{children}</div>
    </Card>
  );
}

function Field({ name, value }: { name: string; value: React.ReactNode }) {
  return (
    <div className="flex gap-2 text-[12px]">
      <dt className="text-saibyl-muted shrink-0">{name}</dt>
      <dd className="text-saibyl-silver min-w-0">{value}</dd>
    </div>
  );
}

function formatDate(value: string | null | undefined): string {
  if (!value) return '—';
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return value;
  return parsed.toLocaleDateString(undefined, {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
  });
}

const ART_STATUS_WORDS: Record<ArtStatus, string> = {
  granted: 'Granted',
  pending: 'Pending',
  allowed: 'Allowed',
  abandoned: 'Abandoned',
  expired: 'Expired',
};

const SIMILARITY_WORDS: Record<string, string> = {
  identical: 'Identical',
  close: 'Close',
  'related-goods': 'Related goods',
};

const TRACK_WORDS: Record<string, string> = {
  trademark: 'trademarks',
  patents: 'prior art',
  pending_landscape: 'pending filings',
  examiner_behavior: 'examiner history',
};

/* ------------------------------------------------------------------ */
/*  Risk banner                                                        */
/* ------------------------------------------------------------------ */

const BANNER_STYLES: Record<RiskTier, string> = {
  GREEN: 'border-saibyl-positive/30 bg-saibyl-positive/[0.07]',
  YELLOW: 'border-saibyl-warning/30 bg-saibyl-warning/[0.07]',
  RED: 'border-saibyl-negative/30 bg-saibyl-negative/[0.07]',
};

const BANNER_READINGS: Record<RiskTier, string> = {
  GREEN:
    'Nothing we found blocks this. Read the closest matches below anyway — an empty search result is not the same as clearance.',
  YELLOW:
    'Some of what we found is close to yours. Read what the claims require below before you commit.',
  RED: 'At least one thing we found looks like a real conflict. Read it below, and talk to a patent attorney before building further.',
};

/* ------------------------------------------------------------------ */
/*  Trademark section                                                  */
/* ------------------------------------------------------------------ */

const TM_STATUS: Record<TrademarkStatus, { word: string; cls: string }> = {
  CLEAR_ON_SEARCH: {
    word: 'Nothing conflicting turned up',
    cls: 'border-saibyl-green/40 bg-saibyl-green/10 text-saibyl-positive',
  },
  CONFLICTS_FOUND: {
    word: 'Conflicts found',
    cls: 'border-saibyl-rose/40 bg-saibyl-rose/10 text-saibyl-negative',
  },
  NEEDS_REVIEW: {
    word: 'Needs a closer look',
    cls: 'border-[#f59e0b]/40 bg-[#f59e0b]/10 text-saibyl-warning',
  },
  NOT_SEARCHED: {
    word: 'Not searched',
    cls: 'border-saibyl-border-light bg-[#14294a]/[0.04] text-saibyl-silver',
  },
};

/* ------------------------------------------------------------------ */
/*  The report                                                         */
/* ------------------------------------------------------------------ */

export default function ClearanceReport({ artifact }: { artifact: ClearanceArtifact }) {
  const tm = artifact.trademark;
  const tmStatus = TM_STATUS[tm.status] ?? TM_STATUS.NEEDS_REVIEW;
  const pat = artifact.patents;
  const pend = artifact.pending_landscape;
  const tracks = artifact.tracks_run
    .map((t) => TRACK_WORDS[t] ?? t)
    .join(' · ');

  return (
    <div className="space-y-5">
      {/* ── Overall risk ── */}
      <div className={`rounded-2xl border p-6 ${BANNER_STYLES[pat.overall_risk]}`}>
        <div className="flex flex-wrap items-center gap-3">
          <RiskChip risk={pat.overall_risk} />
          <p className="text-[15px] font-medium text-saibyl-ink min-w-0">
            {artifact.item}
          </p>
        </div>
        <p className="text-[13px] text-saibyl-ink mt-2.5 leading-relaxed">
          {BANNER_READINGS[pat.overall_risk]}
        </p>
        <p className="text-[11.5px] text-saibyl-muted mt-2">{NOT_LEGAL_ADVICE}</p>
        <p className="text-[11px] text-saibyl-muted/70 mt-2.5 font-mono">
          {TIER_SHORT[artifact.tier]} · searched {formatDate(artifact.search_date)}
          {tracks ? ` · ${tracks}` : ''}
          {pat.records_screened > 0
            ? ` · ${pat.records_screened.toLocaleString()} records screened`
            : ''}
        </p>
        {artifact.assumptions.length > 0 && (
          <div className="mt-3 pt-3 border-t border-saibyl-border">
            <p className="text-[11px] text-saibyl-muted">What we assumed:</p>
            <ul className="mt-1 space-y-0.5">
              {artifact.assumptions.map((a) => (
                <li key={a} className="text-[11.5px] text-saibyl-silver leading-relaxed">
                  {a}
                </li>
              ))}
            </ul>
          </div>
        )}
      </div>

      {/* ── The name ── */}
      <Section heading="The name" sub="What the US trademark register says.">
        <div className="flex flex-wrap items-center gap-2">
          <span
            className={`inline-flex items-center px-2.5 py-1 rounded-full border text-[11px] font-medium ${tmStatus.cls}`}
          >
            {tmStatus.word}
          </span>
          {tm.marks_checked.length > 0 && (
            <span className="text-[12px] text-saibyl-muted">
              Checked: {tm.marks_checked.join(', ')}
            </span>
          )}
        </div>

        {tm.status === 'NOT_SEARCHED' && (
          <p className="text-[12.5px] text-saibyl-muted mt-3 leading-relaxed">
            The trademark register was not searched on this run, so nothing here
            says the name is clear.{' '}
            {tm.official_search_link ? (
              <a
                href={tm.official_search_link}
                target="_blank"
                rel="noreferrer"
                className="inline-flex items-center gap-1 text-saibyl-blue hover:underline"
              >
                Run the official USPTO search yourself
                <ExternalLink className="w-3 h-3" />
              </a>
            ) : (
              <span>
                You can run the official USPTO search yourself at
                tmsearch.uspto.gov.
              </span>
            )}
          </p>
        )}

        {tm.status !== 'NOT_SEARCHED' && tm.conflicts.length === 0 && (
          <p className="text-[12.5px] text-saibyl-muted mt-3 leading-relaxed">
            No conflicting mark came back from this search. That covers federal
            registrations only — state and unregistered uses are outside what we
            can see.
          </p>
        )}

        {tm.conflicts.length > 0 && (
          <ul className="mt-4 space-y-2.5">
            {tm.conflicts.map((c) => (
              <li
                key={`${c.mark}-${c.serial_or_reg}`}
                className="rounded-xl border border-saibyl-border bg-white p-4"
              >
                <div className="flex flex-wrap items-center gap-2">
                  <span className="text-[13.5px] font-medium text-saibyl-ink">
                    {c.mark}
                  </span>
                  <span
                    className={`text-[10.5px] font-mono uppercase tracking-widest ${
                      c.live ? 'text-saibyl-negative' : 'text-saibyl-muted'
                    }`}
                  >
                    {c.live ? 'Live' : 'Dead'}
                  </span>
                  <span className="text-[11px] text-saibyl-muted">
                    {SIMILARITY_WORDS[c.similarity] ?? c.similarity}
                  </span>
                </div>
                <dl className="mt-2 space-y-1">
                  <Field name="Owner" value={c.owner} />
                  <Field name="Serial / reg" value={c.serial_or_reg} />
                  {c.classes.length > 0 && (
                    <Field name="Classes" value={c.classes.join(', ')} />
                  )}
                  {c.goods_services && (
                    <Field name="Goods & services" value={c.goods_services} />
                  )}
                </dl>
              </li>
            ))}
          </ul>
        )}
      </Section>

      {/* ── Closest art ── */}
      <Section
        heading="The closest patents and filings"
        sub="What already exists, what its claims require, and how yours differs."
      >
        {pat.closest_art.length === 0 ? (
          <p className="text-[12.5px] text-saibyl-muted leading-relaxed">
            This search surfaced no close match. Empty is not the same as
            cleared — the search record and its limits are further down this
            report.
          </p>
        ) : (
          <ul className="space-y-3">
            {pat.closest_art.map((art) => (
              <li
                key={art.number}
                className="rounded-xl border border-saibyl-border bg-white p-4"
              >
                <div className="flex flex-wrap items-center gap-2">
                  <span className="font-mono text-[12px] text-saibyl-blue">
                    {art.number}
                  </span>
                  <RiskChip risk={art.risk} />
                  <span className="text-[11px] text-saibyl-muted">
                    {ART_STATUS_WORDS[art.status] ?? art.status}
                  </span>
                </div>
                <p className="text-[13.5px] text-saibyl-ink mt-1.5 leading-snug">
                  {art.title}
                </p>
                <dl className="mt-2 space-y-1">
                  <Field name="Owner" value={art.assignee || '—'} />
                  <Field name="Filed" value={formatDate(art.filed)} />
                  <Field name="Priority" value={formatDate(art.priority)} />
                </dl>
                <div className="mt-3 pt-3 border-t border-saibyl-border space-y-2">
                  <div>
                    <p className="text-[11px] font-medium text-saibyl-silver uppercase tracking-wider">
                      What the claims require
                    </p>
                    <p className="text-[12.5px] text-saibyl-muted mt-0.5 leading-relaxed">
                      {art.claim_requirements}
                    </p>
                  </div>
                  <div>
                    <p className="text-[11px] font-medium text-saibyl-silver uppercase tracking-wider">
                      How yours differs
                    </p>
                    <p className="text-[12.5px] text-saibyl-muted mt-0.5 leading-relaxed">
                      {art.differences}
                    </p>
                  </div>
                </div>
              </li>
            ))}
          </ul>
        )}
      </Section>

      {/* ── Pending landscape ── */}
      <Section
        heading="Still pending"
        sub="Applications in the pipeline that could become claims later."
      >
        {pend.notable_pending.length === 0 &&
          pend.provisional_priorities_revealed.length === 0 && (
            <p className="text-[12.5px] text-saibyl-muted leading-relaxed">
              No published pending application stood out on this search.
            </p>
          )}

        {pend.notable_pending.length > 0 && (
          <ul className="space-y-2">
            {pend.notable_pending.map((p) => (
              <li
                key={p.app}
                className="rounded-xl border border-saibyl-border bg-white px-4 py-3"
              >
                <div className="flex flex-wrap items-center gap-2">
                  <span className="font-mono text-[12px] text-saibyl-blue">{p.app}</span>
                  {p.status && (
                    <span className="text-[11px] text-saibyl-muted">{p.status}</span>
                  )}
                </div>
                <p className="text-[13px] text-saibyl-ink mt-1 leading-snug">
                  {p.title}
                </p>
                {p.assignee && (
                  <p className="text-[11.5px] text-saibyl-muted mt-0.5">{p.assignee}</p>
                )}
              </li>
            ))}
          </ul>
        )}

        {pend.provisional_priorities_revealed.length > 0 && (
          <div className="mt-4">
            <p className="text-[11px] font-medium text-saibyl-silver uppercase tracking-wider">
              Provisional filings revealed through later applications
            </p>
            <ul className="mt-1.5 space-y-1">
              {pend.provisional_priorities_revealed.map((p) => (
                <li key={p.provisional} className="text-[12.5px] text-saibyl-muted">
                  <span className="font-mono text-[12px] text-saibyl-silver">
                    {p.provisional}
                  </span>{' '}
                  — via {p.via}
                </li>
              ))}
            </ul>
          </div>
        )}

        {/* The honesty clause, verbatim from the artifact. Recent filings are
            invisible to everyone — pretending otherwise is how a clear report
            becomes a lawsuit. */}
        {pend.blind_spot_note && (
          <div className="mt-4 rounded-xl border border-saibyl-warning/30 bg-saibyl-warning/[0.07] p-4">
            <p className="text-[12px] font-medium text-saibyl-warning">
              What nobody can see yet
            </p>
            <p className="text-[12.5px] text-saibyl-muted mt-1 leading-relaxed">
              {pend.blind_spot_note}
            </p>
          </div>
        )}
      </Section>

      {/* ── Open vs crowded ── */}
      {(pat.whitespace_signals.length > 0 || pat.crowded_areas.length > 0) && (
        <Section
          heading="Where it looks open, and where it is crowded"
          sub="Read the open ground with the search limits in mind — zero hits can also mean the words were wrong."
        >
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            {pat.whitespace_signals.length > 0 && (
              <div className="rounded-xl border border-saibyl-positive/25 bg-saibyl-positive/[0.05] p-4">
                <p className="text-[12px] font-medium text-saibyl-positive">
                  Came back empty
                </p>
                <ul className="mt-2 space-y-1.5">
                  {pat.whitespace_signals.map((s) => (
                    <li
                      key={s}
                      className="text-[12.5px] text-saibyl-muted leading-relaxed"
                    >
                      {s}
                    </li>
                  ))}
                </ul>
              </div>
            )}
            {pat.crowded_areas.length > 0 && (
              <div className="rounded-xl border border-saibyl-negative/25 bg-saibyl-negative/[0.05] p-4">
                <p className="text-[12px] font-medium text-saibyl-negative">
                  Dense with live filings
                </p>
                <ul className="mt-2 space-y-1.5">
                  {pat.crowded_areas.map((s) => (
                    <li
                      key={s}
                      className="text-[12.5px] text-saibyl-muted leading-relaxed"
                    >
                      {s}
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        </Section>
      )}

      {/* ── Watch list ── */}
      {artifact.watch_list.length > 0 && (
        <Section
          heading="Worth watching"
          sub="Applications and owners whose next move could change this picture."
        >
          <ul className="space-y-2">
            {artifact.watch_list.map((w) => (
              <li
                key={w.target}
                className="rounded-xl border border-saibyl-border bg-white px-4 py-3"
              >
                <p className="text-[13px] text-saibyl-ink">{w.target}</p>
                <p className="text-[12px] text-saibyl-muted mt-0.5 leading-relaxed">
                  {w.reason}
                </p>
              </li>
            ))}
          </ul>
        </Section>
      )}

      {/* ── The search record ── */}
      <Section
        heading="The search record"
        sub="Every query this run made, with hit counts — so the search can be repeated and checked."
      >
        <details className="group">
          <summary className="cursor-pointer text-[12.5px] text-saibyl-blue hover:underline select-none">
            Show all {artifact.queries_run.length} queries
          </summary>
          <div className="mt-3 overflow-x-auto">
            <table className="w-full text-left text-[12px]">
              <thead>
                <tr className="border-b border-saibyl-border-light text-saibyl-muted">
                  <th className="py-1.5 pr-4 font-medium">Track</th>
                  <th className="py-1.5 pr-4 font-medium">Query</th>
                  <th className="py-1.5 font-medium text-right">Hits</th>
                </tr>
              </thead>
              <tbody>
                {artifact.queries_run.map((q, i) => (
                  <tr
                    key={`${q.track}-${q.query}-${i}`}
                    className="border-b border-saibyl-border"
                  >
                    <td className="py-1.5 pr-4 text-saibyl-muted whitespace-nowrap">
                      {TRACK_WORDS[q.track] ?? q.track}
                    </td>
                    <td className="py-1.5 pr-4 text-saibyl-silver font-mono text-[11.5px]">
                      {q.query}
                    </td>
                    <td className="py-1.5 text-right text-saibyl-ink font-mono tabular-nums">
                      {q.hits.toLocaleString()}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </details>
      </Section>

      {/* ── Limits ── */}
      <Section heading="What this search could not see">
        {artifact.limitations.length > 0 ? (
          <ul className="space-y-1.5 list-disc pl-4">
            {artifact.limitations.map((l) => (
              <li key={l} className="text-[12.5px] text-saibyl-muted leading-relaxed">
                {l}
              </li>
            ))}
          </ul>
        ) : (
          <p className="text-[12.5px] text-saibyl-muted leading-relaxed">
            This run recorded no specific limits, but the usual ones still
            apply: titles and summaries rather than full text, US federal
            records only, and nothing filed recently enough to be unpublished.
          </p>
        )}
      </Section>

      {/* ── The disclaimer — on every report, never omitted ── */}
      <div className="rounded-xl border border-saibyl-border bg-white p-4">
        <p className="text-[11.5px] text-saibyl-muted leading-relaxed">
          {artifact.disclaimer || FALLBACK_DISCLAIMER}
        </p>
      </div>
    </div>
  );
}
