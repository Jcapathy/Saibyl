import { useCallback, useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { ExternalLink, Loader2 } from 'lucide-react';

import api, { unwrapList } from '@/lib/api';
import { getErrorMessage } from '@/lib/errors';
import { present, sourceHost } from '@/lib/gtm';
import type { CandidateListItem } from '@/types';
import StageHeader from '@/components/stages/StageHeader';
import { EmptyState, Guarded, StageError } from '@/components/stages/StagePrimitives';
import { useProduct, useStage } from '@/components/stages/useProduct';

/**
 * Step 4 — who do I actually contact on Monday?
 *
 * The audience becomes search queries, and the search returns real companies
 * with the page that says so attached to each one. A candidate you cannot trace
 * back is a lead you cannot act on, so the source link is not decoration and is
 * never omitted.
 *
 * `match_score` is deliberately not rendered as a percentage. It is a rank
 * ordering against one buyer type, not a probability, and "73% match" would
 * invent precision the number does not carry — `lib/gtm.ts` exports no
 * percentage formatter for it on purpose.
 */
export default function BuyersStagePage() {
  const { product } = useProduct();
  const stage = useStage('buyers');

  const [candidates, setCandidates] = useState<CandidateListItem[]>([]);
  const [total, setTotal] = useState<number | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  const load = useCallback(() => {
    api
      .get('/gtm/candidates', { params: { project_id: product.id, limit: 25 } })
      .then((r) => {
        const page = unwrapList<CandidateListItem>(r.data);
        setCandidates(page.items);
        setTotal(page.total);
        setError('');
      })
      .catch((err) =>
        setError(getErrorMessage(err, 'We could not load the companies.')),
      )
      .finally(() => setLoading(false));
  }, [product.id]);

  useEffect(() => {
    load();
  }, [load]);

  /* Retrying is a click, so it says so. `load` itself never sets this: an
     effect that sets state synchronously on mount is a cascading render, and
     `loading` already starts true. */
  const retry = useCallback(() => {
    setLoading(true);
    load();
  }, [load]);

  const searchHref = `/app/prospects/discover?project_id=${product.id}`;

  return (
    <div className="space-y-6">
      <StageHeader stage={stage} />

      {error && <StageError message={error} retry={retry} />}

      {loading && candidates.length === 0 ? (
        <p className="flex items-center gap-2 text-[12.5px] text-saibyl-muted">
          <Loader2 className="w-3.5 h-3.5 animate-spin" />
          Loading…
        </p>
      ) : candidates.length === 0 ? (
        <EmptyState
          headline="No companies found yet"
          body="Saibyl turns your buyers into web searches and brings back real companies that look like them — each with the page that says so, so you can check it yourself before you contact anyone."
          action={{ label: 'Find companies', href: searchHref }}
        />
      ) : (
        <>
          <div className="flex flex-wrap items-center justify-between gap-3">
            <p className="text-[13px] text-saibyl-silver">
              {/* `total` is null when the server could not count. That is not
                  zero and must not render as a number. */}
              {total === null
                ? `${candidates.length} shown`
                : `${total} ${total === 1 ? 'company' : 'companies'} found`}
            </p>
            <Guarded label="Search again" to={searchHref} tone="quiet" />
          </div>

          <ul className="space-y-2">
            {candidates.map((row) => {
              const host = sourceHost(row.source_url);
              return (
                <li
                  key={row.id}
                  className="rounded-xl border border-white/[0.06] bg-white/[0.02] px-4 py-3.5"
                >
                  <div className="flex items-baseline justify-between gap-3">
                    <Link
                      to={`/app/prospects/${row.id}`}
                      className="text-[13.5px] text-saibyl-platinum hover:text-saibyl-gold transition-colors"
                    >
                      {row.company_name}
                    </Link>
                    {present(row.employee_count_range) && (
                      <span className="text-[11px] text-saibyl-muted shrink-0">
                        {row.employee_count_range}
                      </span>
                    )}
                  </div>
                  {present(row.one_liner) && (
                    <p className="text-[12px] text-saibyl-muted mt-1 leading-relaxed">
                      {row.one_liner}
                    </p>
                  )}
                  <div className="flex flex-wrap items-center gap-3 mt-2">
                    <span className="text-[11px] text-saibyl-muted">
                      Looks like: {row.archetype_label}
                    </span>
                    {host && (
                      <a
                        href={row.source_url}
                        target="_blank"
                        rel="noreferrer noopener"
                        className="inline-flex items-center gap-1 text-[11px] text-saibyl-gold hover:underline"
                      >
                        {host}
                        <ExternalLink className="w-3 h-3" />
                      </a>
                    )}
                  </div>
                </li>
              );
            })}
          </ul>

          <Link
            to={`/app/prospects?project_id=${product.id}`}
            className="inline-block text-[12.5px] text-saibyl-gold hover:underline"
          >
            See all of them, with the evidence for each
          </Link>
        </>
      )}
    </div>
  );
}
