import { useCallback, useEffect, useState } from 'react';

import api, { unwrapList } from '@/lib/api';
import { getErrorMessage } from '@/lib/errors';
import { EmptyState, StageError } from '@/components/stages/StagePrimitives';
import { type ProductState } from '@/lib/stages';
import SiteCheckForm from '@/components/website/SiteCheckForm';
import SiteCritique from '@/components/website/SiteCritique';
import SiteRevisionPanel from '@/components/website/SiteRevisionPanel';
import { SiteStatusChip } from '@/components/website/chips';
import { type SiteCheck, type SiteCheckListItem } from '@/components/website/types';

/**
 * The Website Gauntlet, reachable in one click.
 *
 * The check and the revision are also step one of a product's rail, and that
 * is where they were *only* reachable: a founder landing on `/app/home` saw
 * Home, Your reports, IP check, Who would fund this and Settings, and no path
 * to the flagship module at all. It was three clicks deep behind a nav item
 * called "Everything you uploaded".
 *
 * Global for the same reason `CapitalPage` and `IpCheckPage` are: "what does a
 * stranger take away from my page" is asked at any point, including before
 * there is a run to hang it on. The product picker is what ties one check to
 * one product, because the snapshot is stored against it.
 *
 * This renders the same components the stage page does, with the same props —
 * there is no second implementation of a check here to drift from the first.
 */
export default function WebsitePage() {
  const [products, setProducts] = useState<ProductState[]>([]);
  const [productsLoading, setProductsLoading] = useState(true);
  const [productsError, setProductsError] = useState('');
  const [selectedId, setSelectedId] = useState('');

  const [checks, setChecks] = useState<SiteCheckListItem[]>([]);
  const [checksError, setChecksError] = useState('');
  const [activeCheck, setActiveCheck] = useState<SiteCheck | null>(null);
  const [openingId, setOpeningId] = useState('');

  const loadProducts = useCallback(() => {
    api
      .get('/products')
      .then((r) => {
        const items = unwrapList<ProductState>(r.data).items;
        setProducts(items);
        setProductsError('');
        setSelectedId((current) =>
          current && items.some((p) => p.id === current)
            ? current
            : (items[0]?.id ?? ''),
        );
      })
      .catch((err) =>
        setProductsError(getErrorMessage(err, 'We could not load your products.')),
      )
      .finally(() => setProductsLoading(false));
  }, []);

  useEffect(() => {
    loadProducts();
  }, [loadProducts]);

  /* Every write in here happens in a promise callback, never synchronously.
     A synchronous `setChecks([])` on the no-product path is a setState in an
     effect body, which is both a lint error and a real double render. The
     no-product case cannot reach this anyway: the picker only exists once
     products have loaded. */
  const loadChecks = useCallback(() => {
    if (!selectedId) return;
    api
      .get('/website/check', { params: { project_id: selectedId } })
      .then((r) => {
        setChecks(unwrapList<SiteCheckListItem>(r.data).items);
        setChecksError('');
      })
      .catch((err) =>
        setChecksError(getErrorMessage(err, 'We could not load your checks.')),
      );
  }, [selectedId]);

  useEffect(() => {
    loadChecks();
  }, [loadChecks]);

  /* Switching product clears the open critique here rather than in an effect:
     the picker is the only thing that changes `selectedId` after the first
     load, and resetting state from an effect makes the stale critique render
     once before it disappears. */
  const chooseProduct = useCallback((id: string) => {
    setActiveCheck(null);
    setChecksError('');
    setSelectedId(id);
  }, []);

  const openCheck = useCallback((id: string) => {
    setOpeningId(id);
    api
      .get<SiteCheck>(`/website/check/${id}`)
      .then((r) => setActiveCheck(r.data))
      .catch((err) =>
        setChecksError(getErrorMessage(err, 'We could not open that check.')),
      )
      .finally(() => setOpeningId(''));
  }, []);

  return (
    <div className="px-5 py-6 md:px-8 md:py-8">
      <div className="max-w-4xl space-y-6">
        <header>
          <h1 className="text-[22px] font-semibold text-saibyl-ink">
            Website check
          </h1>
          <p className="text-[13px] text-saibyl-muted mt-2 leading-relaxed max-w-2xl">
            Six reviewers read your page the way a stranger would &mdash; the
            reading order, the trust signals, the route to action, the words,
            the phone experience, the look &mdash; and tell you what they take
            away. Then we rewrite it and let the same six score the difference.
          </p>
        </header>

        {productsError && <StageError message={productsError} retry={loadProducts} />}

        {productsLoading ? (
          <p className="text-[12.5px] text-saibyl-muted" aria-live="polite">
            Loading&hellip;
          </p>
        ) : products.length === 0 ? (
          <EmptyState
            headline="There is nothing to check yet"
            body="A check is stored against one thing you are building, so it can be rebuilt when the page changes. Add what you are building and this fills in."
            action={{ label: 'Add what you are building', href: '/app/products/new' }}
          />
        ) : (
          <>
            {products.length > 1 && (
              <div>
                <label
                  htmlFor="website-product"
                  className="block text-[12.5px] text-saibyl-silver mb-1.5"
                >
                  Which one is this for?
                </label>
                <select
                  id="website-product"
                  value={selectedId}
                  onChange={(e) => chooseProduct(e.target.value)}
                  className="w-full max-w-sm rounded-lg border border-saibyl-border bg-white px-3 py-2 text-[13px] text-saibyl-ink"
                >
                  {products.map((p) => (
                    <option key={p.id} value={p.id}>
                      {p.name}
                    </option>
                  ))}
                </select>
              </div>
            )}

            {selectedId && (
              <div className="rounded-2xl border border-saibyl-border bg-white p-5">
                <SiteCheckForm productId={selectedId} onStarted={loadChecks} />
              </div>
            )}

            {checksError && <StageError message={checksError} retry={loadChecks} />}

            {checks.length > 0 && (
              <div className="space-y-2">
                <h2 className="text-[13px] font-medium text-saibyl-ink">
                  Checks you have run
                </h2>
                <ul className="space-y-1.5">
                  {checks.map((check) => (
                    <li key={check.id}>
                      <button
                        type="button"
                        onClick={() => openCheck(check.id)}
                        className={`w-full flex flex-wrap items-center justify-between gap-2 rounded-xl border px-4 py-3 text-left transition ${
                          activeCheck?.id === check.id
                            ? 'border-saibyl-gold bg-saibyl-gold/[0.06]'
                            : 'border-saibyl-border bg-white hover:border-saibyl-gold/40'
                        }`}
                      >
                        <span className="text-[13px] text-saibyl-ink truncate">
                          {check.url}
                        </span>
                        <span className="flex items-center gap-2 shrink-0">
                          {typeof check.overall_score === 'number' && (
                            <span className="font-mono text-[12px] tabular-nums text-saibyl-muted">
                              {check.overall_score}/100
                            </span>
                          )}
                          <SiteStatusChip status={check.status} />
                        </span>
                      </button>
                    </li>
                  ))}
                </ul>
                {openingId && (
                  <p className="text-[12px] text-saibyl-muted" aria-live="polite">
                    Opening&hellip;
                  </p>
                )}
              </div>
            )}

            {activeCheck && (
              <div className="space-y-4">
                <SiteCritique check={activeCheck} />
                {/* Keyed on the check, so opening a different one gets a fresh
                    panel rather than inheriting the previous draft. */}
                <SiteRevisionPanel
                  key={activeCheck.id}
                  snapshotId={activeCheck.id}
                  productId={selectedId}
                />
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
}
