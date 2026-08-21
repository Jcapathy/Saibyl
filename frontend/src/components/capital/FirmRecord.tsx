import type { ReactNode } from 'react';
import { ExternalLink } from 'lucide-react';

import {
  checkRange,
  hostOf,
  FIRM_TYPE_LABEL,
  type FamilyOffice,
} from '@/lib/capital';
import {
  Chips,
  InboundRouteBlock,
  MonoLabel,
  PeopleBlock,
  Provenance,
} from './CapitalPrimitives';

/**
 * One firm in the bank, rendered whole.
 *
 * Every field the record holds appears here, including the ones a list vendor
 * would have quietly dropped: the firm that publishes no cheque range says so
 * rather than showing a plausible band, the firm that takes no inbound says so
 * rather than showing an empty route, and the date the claim was read sits
 * under all of it.
 *
 * `children` renders between the name and the published detail. That is where
 * a shortlist puts its verdict and its reasons, so the founder reads *why this
 * firm* before reading *what this firm says* — and so the record itself has
 * one rendering rather than two that can drift.
 */
export default function FirmRecord({
  firm,
  now,
  tone = 'plain',
  children,
}: {
  firm: FamilyOffice;
  now: Date;
  /** `refused` recesses the card. The label carries the meaning, not the hue. */
  tone?: 'plain' | 'refused';
  children?: ReactNode;
}) {
  const range = checkRange(firm);

  return (
    <article
      className={`rounded-2xl border border-saibyl-border p-5 space-y-4 ${
        tone === 'refused' ? 'bg-saibyl-elevated' : 'bg-white capital-card'
      }`}
    >
      <header>
        <div className="flex flex-wrap items-baseline gap-x-2.5 gap-y-1">
          <h3 className="text-[15px] font-semibold text-saibyl-ink">
            {firm.firm_name}
          </h3>
          <span className="rounded-full border border-saibyl-border bg-white px-2 py-0.5 font-mono text-[9.5px] uppercase tracking-[0.14em] text-saibyl-muted">
            {FIRM_TYPE_LABEL[firm.firm_type]}
          </span>
          {firm.domain && (
            <a
              href={`https://${firm.domain.replace(/^https?:\/\//, '')}`}
              target="_blank"
              rel="noreferrer noopener"
              className="inline-flex items-baseline gap-1 text-[12px] text-saibyl-blue hover:underline"
            >
              {hostOf(`https://${firm.domain.replace(/^https?:\/\//, '')}`)}
              <ExternalLink className="w-3 h-3 shrink-0 self-center" />
            </a>
          )}
        </div>
      </header>

      {children}

      <div>
        <MonoLabel>What they publish</MonoLabel>
        {firm.thesis.trim() ? (
          <p className="text-[12.5px] text-saibyl-ink italic border-l-2 border-saibyl-border-light pl-2.5 mt-1.5 leading-relaxed">
            &ldquo;{firm.thesis}&rdquo;
          </p>
        ) : (
          <p className="text-[12.5px] text-saibyl-muted mt-1.5 leading-relaxed">
            They publish nothing we could quote, so nothing is quoted. Their own
            page is linked below.
          </p>
        )}
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
        <Chips label="Sectors they state" items={firm.sectors} />
        <Chips label="Stages they state" items={firm.stages} />
        <Chips label="Where they invest" items={firm.geography} />
        <div>
          <MonoLabel>Cheque size</MonoLabel>
          <p className="text-[12.5px] text-saibyl-ink mt-1.5 font-mono tabular-nums">
            {range ?? (
              <span className="font-sans text-saibyl-muted">
                They publish no range, so we show none.
              </span>
            )}
          </p>
        </div>
      </div>

      <Chips label="What they have backed" items={firm.notable_investments} />

      <InboundRouteBlock path={firm.inbound_path} />

      <PeopleBlock people={firm.people} now={now} />

      <Provenance
        sourceUrl={firm.source_url}
        sourceTitle={firm.source_title}
        retrievedAt={firm.retrieved_at}
        verifiedAt={firm.verified_at}
        staleAfter={firm.stale_after}
        now={now}
      />
    </article>
  );
}
