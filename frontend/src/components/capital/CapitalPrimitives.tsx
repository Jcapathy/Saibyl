import type { ReactNode } from 'react';
import { ExternalLink, Info } from 'lucide-react';

import {
  ageInWords,
  formatDay,
  freshnessNote,
  hostOf,
  inboundRoute,
  DIMENSION_LABEL,
  type FirmPerson,
  type InboundPath,
  type MatchReason,
  type StaleRecord,
} from '@/lib/capital';

import './capital.css';

/**
 * The pieces every capital surface is built from.
 *
 * They live together because between them they keep three rules that a screen
 * assembled by hand would eventually break:
 *
 *   1. A firm always shows where it came from and when it was read.
 *   2. A firm that publishes no inbound route is shown as having refused
 *      inbound, never as a lead with a missing field.
 *   3. Nothing here offers to make contact. There is no `mailto:`, no send,
 *      no copy-the-address button — Saibyl holds no personal contact detail
 *      and does not approach anyone on a founder's behalf.
 */

/* ------------------------------------------------------------------ */
/*  Labels                                                             */
/* ------------------------------------------------------------------ */

/** A mono label wearing its dot, per the design guide. Every one of them. */
export function MonoLabel({
  children,
  className = '',
}: {
  children: ReactNode;
  className?: string;
}) {
  return (
    <p
      className={`capital-eyebrow font-mono text-[10px] uppercase tracking-[0.16em] text-saibyl-muted ${className}`}
    >
      {children}
    </p>
  );
}

/** A published list — sectors, stages, places — in the firm's own words. */
export function Chips({ label, items }: { label: string; items: string[] }) {
  if (items.length === 0) return null;
  return (
    <div>
      <MonoLabel>{label}</MonoLabel>
      <div className="flex flex-wrap gap-1.5 mt-1.5">
        {items.map((item) => (
          <span
            key={item}
            className="rounded-full border border-saibyl-border bg-white px-2.5 py-0.5 text-[11.5px] text-saibyl-silver"
          >
            {item}
          </span>
        ))}
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  Where a claim came from, and how old it is                         */
/* ------------------------------------------------------------------ */

/**
 * The page this record was read from, and the dates that bound it.
 *
 * Not optional decoration on any surface here. A firm a founder cannot trace
 * back to a published page is a recommendation they cannot check, and a claim
 * with no date on it is how an investor list launders decay into confidence.
 */
export function Provenance({
  sourceUrl,
  sourceTitle,
  retrievedAt,
  verifiedAt,
  staleAfter,
  now,
}: {
  sourceUrl: string;
  sourceTitle?: string;
  retrievedAt: string;
  verifiedAt?: string | null;
  staleAfter?: string | null;
  now: Date;
}) {
  const freshness = staleAfter ? freshnessNote(staleAfter, now) : null;
  return (
    <div className="border-t border-saibyl-border pt-3">
      <MonoLabel>Where this came from</MonoLabel>
      <a
        href={sourceUrl}
        target="_blank"
        rel="noreferrer noopener"
        className="inline-flex items-baseline gap-1.5 mt-1.5 text-[12.5px] text-saibyl-blue hover:underline break-all"
      >
        {sourceTitle?.trim() ? sourceTitle : hostOf(sourceUrl)}
        <ExternalLink className="w-3 h-3 shrink-0 self-center" />
      </a>
      <p className="font-mono text-[11px] tabular-nums text-saibyl-muted mt-1.5 leading-relaxed">
        {ageInWords(retrievedAt, now)} &middot; {formatDay(retrievedAt)}
        {' · '}
        {verifiedAt
          ? `re-checked ${formatDay(verifiedAt)}`
          : 'not re-checked since'}
        {freshness && (
          <>
            {' · '}
            <span className={freshness.closing ? 'text-saibyl-warning' : undefined}>
              {freshness.text}
            </span>
          </>
        )}
      </p>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  The firm's own published route                                     */
/* ------------------------------------------------------------------ */

/**
 * How the firm itself says to approach it — including when it says not to.
 *
 * Family offices are private by design and many take no inbound at all. Where
 * that is the firm's published position, that is what this renders: a stated
 * refusal with the page it was stated on, and no route, because a route shown
 * beside "they take no inbound" is a route somebody uses anyway.
 */
export function InboundRouteBlock({ path }: { path: InboundPath }) {
  const route = inboundRoute(path);

  if (route.refused) {
    return (
      <div className="rounded-xl border border-[#8b73ee]/35 bg-[#8b73ee]/[0.08] p-3.5">
        <p className="flex items-start gap-2 text-[12.5px] font-medium text-[#6a4fe0]">
          <Info className="w-4 h-4 shrink-0 mt-px" />
          {route.headline}
        </p>
        <p className="text-[12px] text-saibyl-muted mt-1.5 leading-relaxed">
          There is no route to give you. That is the position they publish, not
          a gap in this record.
        </p>
        <a
          href={route.source_url}
          target="_blank"
          rel="noreferrer noopener"
          className="inline-flex items-center gap-1 mt-2 text-[11.5px] text-saibyl-blue hover:underline"
        >
          Where they say so
          <ExternalLink className="w-3 h-3" />
        </a>
      </div>
    );
  }

  return (
    <div className="rounded-xl border border-saibyl-border bg-white p-3.5">
      <MonoLabel>How they say to approach them</MonoLabel>
      <p className="text-[12.5px] text-saibyl-ink mt-1.5">{route.headline}</p>
      {route.value &&
        (route.isUrl ? (
          <a
            href={route.value}
            target="_blank"
            rel="noreferrer noopener"
            className="inline-flex items-baseline gap-1.5 mt-1.5 text-[12.5px] text-saibyl-blue hover:underline break-all"
          >
            {hostOf(route.value)}
            <ExternalLink className="w-3 h-3 shrink-0 self-center" />
          </a>
        ) : (
          /* Written out, never wired up. This is the firm's own published
             address for strangers, so it belongs on the record — and an app
             that opened a composer over it would be making the approach on
             the founder's behalf, which is the one thing this module does
             not do. */
          <p className="font-mono text-[12px] text-saibyl-ink mt-1.5 break-all select-all">
            {route.value}
          </p>
        ))}
      <a
        href={route.source_url}
        target="_blank"
        rel="noreferrer noopener"
        className="inline-flex items-center gap-1 mt-2 text-[11.5px] text-saibyl-muted hover:text-saibyl-blue hover:underline"
      >
        Where they published it
        <ExternalLink className="w-3 h-3" />
      </a>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  Named people — the permitted set, and nothing else                 */
/* ------------------------------------------------------------------ */

/**
 * Who is named on the firm's own pages, and nothing beyond that.
 *
 * Name, role, employer and a public professional page — the six fields the
 * privacy gate permits, minus the two that are provenance. No address, no
 * number, and no way to ask this app for one, because it does not have one.
 */
export function PeopleBlock({ people, now }: { people: FirmPerson[]; now: Date }) {
  if (people.length === 0) return null;
  return (
    <div>
      <MonoLabel>Who they name publicly</MonoLabel>
      <ul className="mt-2 space-y-2">
        {people.map((person) => (
          <li
            key={`${person.full_name}-${person.source_url}`}
            className="text-[12.5px] leading-relaxed"
          >
            <span className="text-saibyl-ink font-medium">{person.full_name}</span>
            {person.role_title && (
              <span className="text-saibyl-silver">, {person.role_title}</span>
            )}
            {person.employer && (
              <span className="text-saibyl-silver"> at {person.employer}</span>
            )}
            <span className="block font-mono text-[10.5px] tabular-nums text-saibyl-muted mt-0.5">
              {person.public_profile_url && (
                <>
                  <a
                    href={person.public_profile_url}
                    target="_blank"
                    rel="noreferrer noopener"
                    className="text-saibyl-blue hover:underline"
                  >
                    their published page
                  </a>
                  {' · '}
                </>
              )}
              {ageInWords(person.retrieved_at, now)}
              {' · '}
              <a
                href={person.source_url}
                target="_blank"
                rel="noreferrer noopener"
                className="hover:text-saibyl-blue hover:underline"
              >
                {hostOf(person.source_url)}
              </a>
            </span>
          </li>
        ))}
      </ul>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  A reason, in both sides' words                                     */
/* ------------------------------------------------------------------ */

/**
 * Why this firm — quoting the firm and quoting the founder, both verbatim.
 *
 * A reason carrying only the firm's language is a claim about the founder;
 * carrying only the founder's is a claim about the firm. Carrying both is a
 * comparison that can be checked in ten seconds against two pages, which is
 * what makes this list worth more than one somebody bought.
 */
export function ReasonBlock({
  reason,
  bridge = false,
}: {
  reason: MatchReason;
  bridge?: boolean;
}) {
  return (
    <div
      /* The bridge is emphasis, so it is violet. Blue in this system marks an
         action and nothing else, and a highlighted panel that cannot be
         clicked is exactly how that stops being true. */
      className={`rounded-xl border p-3.5 ${
        bridge
          ? 'border-[#8b73ee]/35 bg-[#8b73ee]/[0.07]'
          : 'border-saibyl-border bg-saibyl-elevated'
      }`}
    >
      <MonoLabel>{DIMENSION_LABEL[reason.dimension]}</MonoLabel>
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 mt-2">
        <div>
          <p className="font-mono text-[9.5px] uppercase tracking-[0.14em] text-saibyl-muted">
            Their words
          </p>
          <p className="text-[12.5px] text-saibyl-ink italic border-l-2 border-saibyl-border-light pl-2.5 mt-1 leading-relaxed">
            &ldquo;{reason.firm_quote}&rdquo;
          </p>
        </div>
        <div>
          <p className="font-mono text-[9.5px] uppercase tracking-[0.14em] text-saibyl-muted">
            Yours
          </p>
          <p className="text-[12.5px] text-saibyl-silver italic border-l-2 border-saibyl-border-light pl-2.5 mt-1 leading-relaxed">
            &ldquo;{reason.founder_quote}&rdquo;
          </p>
        </div>
      </div>
      {reason.explanation && (
        <p className="text-[11.5px] text-saibyl-muted mt-2 leading-relaxed">
          {reason.explanation}
        </p>
      )}
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  What we hold and will not assert                                   */
/* ------------------------------------------------------------------ */

/**
 * Records past the date we will stand behind them, named rather than dropped.
 *
 * This is the difference between this bank and every commercial investor list,
 * which is partly wrong the day it ships and says nothing about it. Withheld is
 * honest; stale is a wrong pitch sent to a real firm with our name on the
 * recommendation. A founder told which firms went dark can go and check them
 * in an afternoon.
 */
export function Withheld({ records, now }: { records: StaleRecord[]; now: Date }) {
  return (
    <div className="rounded-2xl border border-saibyl-border bg-saibyl-elevated p-5">
      <MonoLabel>Held back, and named</MonoLabel>
      <p className="text-[12.5px] text-saibyl-muted mt-1.5 leading-relaxed max-w-2xl">
        We hold {records.length} {records.length === 1 ? 'record' : 'records'}{' '}
        that passed the date we will stand behind. They are named here rather
        than quietly dropped, so you can check them yourself &mdash; a shorter
        list with no explanation teaches you nothing.
      </p>
      <ul className="mt-3 space-y-2">
        {records.map((record) => (
          <li
            key={`${record.firm_name}-${record.stale_after}`}
            className="flex flex-wrap items-baseline gap-x-2.5 gap-y-0.5 border-b border-saibyl-border last:border-0 pb-2 last:pb-0"
          >
            <span className="text-[12.5px] text-saibyl-ink">{record.firm_name}</span>
            <span className="font-mono text-[10.5px] tabular-nums text-saibyl-muted">
              {ageInWords(record.retrieved_at, now)} &middot; lapsed{' '}
              {formatDay(record.stale_after)}
            </span>
            <span className="text-[11.5px] text-saibyl-muted">{record.reason}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  A state that is not a failure                                      */
/* ------------------------------------------------------------------ */

/**
 * Something the product will not do, said calmly.
 *
 * An empty bank, a record past its date, a description we will not store —
 * none of these are errors and none of them should be red. Red is for
 * something that went wrong; this is the product working correctly and saying
 * so.
 */
export function CalmNotice({
  headline,
  children,
}: {
  headline: string;
  children?: ReactNode;
}) {
  return (
    <div className="rounded-xl border border-[#8b73ee]/30 bg-[#8b73ee]/[0.07] p-4">
      <p className="flex items-start gap-2 text-[13px] font-medium text-[#6a4fe0]">
        <Info className="w-4 h-4 shrink-0 mt-px" />
        {headline}
      </p>
      {children && (
        <div className="text-[12.5px] text-saibyl-muted mt-1.5 leading-relaxed space-y-1.5">
          {children}
        </div>
      )}
    </div>
  );
}
