import type { CSSProperties } from 'react';

import { StageError } from '@/components/stages/StagePrimitives';
import {
  formatDay,
  hasFilters,
  EMPTY_FILTERS,
  FIRM_TYPE_CHOICES,
  STAGE_CHOICES,
  type BankFilters,
  type BankPage,
} from '@/lib/capital';
import FirmRecord from './FirmRecord';
import { CalmNotice, MonoLabel, Withheld } from './CapitalPrimitives';

/**
 * The bank itself — every record we would stand behind today.
 *
 * Browsable rather than hidden behind the paid match, because the thing a
 * founder is being asked to trust is the evidence, and evidence you cannot
 * look at is a claim. The match is what costs credits; reading what it will
 * match against costs nothing.
 *
 * Three counts are shown that a commercial investor list would not print:
 * what is current, what is **withheld** because it passed the date we will
 * stand behind it, and what is **unreadable** because a stored row no longer
 * satisfies the rules the record is held to. Every one of those is a fact
 * about the bank's honesty, and hiding any of them would make the visible list
 * look like the whole market.
 */

const MAX_STAGGER = 8;

const controlBase =
  'w-full rounded-xl bg-white border border-saibyl-border-light px-3 py-2 text-[13px] text-saibyl-ink placeholder:text-saibyl-muted/70 focus:outline-none focus:border-saibyl-blue focus:ring-2 focus:ring-saibyl-blue/20';

export default function BankPanel({
  bank,
  filters,
  onFilters,
  loading,
  error,
  onRetry,
  now,
}: {
  bank: BankPage | null;
  filters: BankFilters;
  onFilters: (next: BankFilters) => void;
  loading: boolean;
  error: string;
  onRetry: () => void;
  now: Date;
}) {
  const filtered = hasFilters(filters);

  return (
    <section className="space-y-4">
      <div>
        <MonoLabel>What the match reads</MonoLabel>
        <h2 className="text-[15px] font-semibold text-saibyl-ink mt-1.5">
          Every firm we would stand behind today
        </h2>
        <p className="text-[12.5px] text-saibyl-muted mt-1.5 leading-relaxed max-w-2xl">
          Curated, not crawled. Each record is read from the firm&rsquo;s own
          published pages and carries the date it was read, because fifty firms
          you can check beat five thousand you cannot.
        </p>
      </div>

      {/* ── Filters ── */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
        <div>
          <label
            htmlFor="bank-sector"
            className="block text-[11.5px] text-saibyl-silver mb-1"
          >
            Sector
          </label>
          <input
            id="bank-sector"
            value={filters.sector}
            onChange={(e) => onFilters({ ...filters, sector: e.target.value })}
            placeholder="Any"
            className={controlBase}
          />
        </div>
        <div>
          <label
            htmlFor="bank-stage"
            className="block text-[11.5px] text-saibyl-silver mb-1"
          >
            Stage
          </label>
          <select
            id="bank-stage"
            value={filters.stage}
            onChange={(e) => onFilters({ ...filters, stage: e.target.value })}
            className={controlBase}
            style={{ colorScheme: 'light' }}
          >
            <option value="">Any</option>
            {STAGE_CHOICES.map((choice) => (
              <option key={choice} value={choice}>
                {choice}
              </option>
            ))}
          </select>
        </div>
        <div>
          <label
            htmlFor="bank-type"
            className="block text-[11.5px] text-saibyl-silver mb-1"
          >
            Kind of firm
          </label>
          <select
            id="bank-type"
            value={filters.firm_type}
            onChange={(e) => onFilters({ ...filters, firm_type: e.target.value })}
            className={controlBase}
            style={{ colorScheme: 'light' }}
          >
            <option value="">Any</option>
            {FIRM_TYPE_CHOICES.map((choice) => (
              <option key={choice.value} value={choice.value}>
                {choice.label}
              </option>
            ))}
          </select>
        </div>
      </div>

      {/* The one thing about this filter that could mislead, said next to it.
          A firm hidden here is not a firm that refused you — the paid match
          never hides one, it reports it as a refusal quoting its own words. */}
      {filters.stage !== '' && (
        <p className="text-[11.5px] text-saibyl-muted leading-relaxed">
          Filtering by stage hides firms that publish other stages. A matched
          shortlist never hides them &mdash; it reports them as refusals,
          quoting the range they publish.
        </p>
      )}

      {error && <StageError message={error} retry={onRetry} />}

      {loading && !bank && (
        <p className="text-[12.5px] text-saibyl-muted" aria-live="polite">
          Reading the bank&hellip;
        </p>
      )}

      {bank && (
        <>
          <p
            className="font-mono text-[11px] tabular-nums text-saibyl-muted"
            aria-live="polite"
          >
            {bank.firms.length.toLocaleString()} current &middot;{' '}
            {bank.withheld_stale.length.toLocaleString()} withheld &middot;{' '}
            {bank.unreadable.toLocaleString()} flagged &middot; as of{' '}
            {formatDay(bank.as_of)}
            {/* A filter change re-reads the bank. Saying so beats a list that
                silently sits there for a moment looking like the answer. */}
            {loading && <> &middot; reading&hellip;</>}
          </p>

          {bank.unreadable > 0 && (
            <CalmNotice
              headline={`${bank.unreadable} record(s) we hold cannot be shown`}
            >
              <p>
                They no longer satisfy the rules a record here is held to, so
                they are counted and flagged for review rather than served. A
                count you can see beats a row quietly missing.
              </p>
            </CalmNotice>
          )}

          {bank.firms.length === 0 ? (
            filtered ? (
              <CalmNotice headline="Nothing current matches those filters">
                <p>
                  The bank holds {bank.withheld_stale.length} record(s) past
                  their verification date, which are never matched or shown as
                  current.
                </p>
                <p>
                  <button
                    type="button"
                    onClick={() => onFilters(EMPTY_FILTERS)}
                    className="text-saibyl-blue hover:underline font-medium"
                  >
                    Clear the filters
                  </button>{' '}
                  to see everything we hold.
                </p>
              </CalmNotice>
            ) : (
              <CalmNotice headline="The bank has nothing current in it yet">
                <p>
                  Curation is an editorial act with our name on the
                  recommendation, so a record only enters when a firm has
                  published something we can quote and link. Until one has,
                  there is nothing here and we would rather say so than pad it.
                </p>
                <p>
                  Nothing is charged for a match against an empty bank &mdash;
                  the build refuses before it takes any credits.
                </p>
              </CalmNotice>
            )
          ) : (
            <div className="space-y-3">
              {bank.firms.map((firm, index) => (
                <div
                  key={`${firm.firm_name}-${firm.source_url}`}
                  className="capital-arrive"
                  style={{ '--i': Math.min(index, MAX_STAGGER) } as CSSProperties}
                >
                  <FirmRecord firm={firm} now={now} />
                </div>
              ))}
            </div>
          )}

          {bank.withheld_stale.length > 0 && (
            <Withheld records={bank.withheld_stale} now={now} />
          )}
        </>
      )}
    </section>
  );
}
