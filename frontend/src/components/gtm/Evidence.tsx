import { ExternalLink, Quote } from 'lucide-react';
import { EVIDENCE_FIELD_COPY, present, presentList, sourceHost } from '@/lib/gtm';
import type { EvidenceItem } from '@/types';

/**
 * The parts of a candidate that make it checkable.
 *
 * These components exist so that two rules cannot be broken by accident at a
 * call site.
 *
 * **Absence renders as nothing.** `Fact` and `FactList` return `null` for a
 * field no source evidenced. There is no dash, no "Unknown", no "—" that a
 * reader could mistake for a measurement. A candidate whose headcount was never
 * stated simply has no headcount line, and the founder learns the true thing:
 * we did not find out. Every one of these fields is nullable in migration 027
 * *on purpose*, with a comment saying so.
 *
 * **A claim without its source is not shown.** `EvidenceList` renders the quote
 * and the link together, never one without the other, and never behind a
 * disclosure triangle. Being able to click through to the page a claim came
 * from is the product; a candidate whose evidence a founder cannot see is a lead
 * they cannot act on.
 */

/** A single evidenced field. Renders nothing when nothing evidenced it. */
export function Fact({ label, value }: { label: string; value: string | null | undefined }) {
  const shown = present(value);
  if (!shown) return null;
  return (
    <div>
      <dt className="text-[10px] uppercase tracking-widest text-[#5A6578]">{label}</dt>
      <dd className="text-[13px] text-[#E8ECF2] mt-0.5">{shown}</dd>
    </div>
  );
}

/** A list-valued evidenced field. Renders nothing when the list is empty. */
export function FactList({ label, values }: { label: string; values: string[] | null | undefined }) {
  const shown = presentList(values);
  if (!shown) return null;
  return (
    <div>
      <dt className="text-[10px] uppercase tracking-widest text-[#5A6578]">{label}</dt>
      <dd className="flex flex-wrap gap-1.5 mt-1">
        {shown.map((value) => (
          <span
            key={value}
            className="rounded-md bg-white/[0.05] px-2 py-0.5 text-[11px] text-[#8B97A8]"
          >
            {value}
          </span>
        ))}
      </dd>
    </div>
  );
}

/** An outbound link to the page a claim came from. */
export function SourceLink({
  url,
  label,
  className = '',
}: {
  url: string;
  /** Falls back to the host, then to the raw URL. Never to "source". */
  label?: string | null;
  className?: string;
}) {
  const text = present(label) ?? sourceHost(url) ?? url;
  return (
    <a
      href={url}
      target="_blank"
      rel="noopener noreferrer"
      title={url}
      className={`inline-flex items-baseline gap-1 text-[#2563EB] hover:text-[#8B5CF6] hover:underline break-all transition-colors ${className}`}
    >
      {text}
      <ExternalLink className="w-3 h-3 shrink-0 self-center" />
    </a>
  );
}

/**
 * Every quote behind a candidate, each with the page it came from.
 *
 * Grouped by field so a founder reading "50-200 employees" can find the sentence
 * that said so. An empty `evidence` array renders its own explanation rather
 * than nothing at all: on a detail view, "there are no quotes" is itself the
 * most important thing on the screen, because it means every field on the record
 * except the name and the source is blank.
 */
export function EvidenceList({ evidence }: { evidence: EvidenceItem[] }) {
  if (evidence.length === 0) {
    return (
      <p className="text-[12px] text-[#8B97A8] leading-relaxed">
        No quotes were saved for this company. The page below was returned by the search
        and named them, but nothing on it stated anything we could check &mdash; which is
        why the details above are mostly blank. Open the page yourself before acting on
        this one.
      </p>
    );
  }

  return (
    <ul className="space-y-3">
      {evidence.map((item, i) => (
        <li
          key={`${item.field}-${item.source_url}-${i}`}
          className="rounded-xl border border-[#1E293B] bg-white/[0.02] p-3.5"
        >
          <p className="text-[10px] uppercase tracking-widest text-[#5A6578] mb-1.5">
            {EVIDENCE_FIELD_COPY[item.field] ?? item.field.replace(/_/g, ' ')}
          </p>
          <blockquote className="flex gap-2">
            <Quote className="w-3.5 h-3.5 text-[#5A6578] shrink-0 mt-0.5" />
            <p className="text-[13px] text-[#E8ECF2] leading-relaxed italic">{item.quote}</p>
          </blockquote>
          <p className="text-[11px] mt-2 pl-[22px]">
            <SourceLink url={item.source_url} />
          </p>
        </li>
      ))}
    </ul>
  );
}
