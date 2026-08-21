import { useCallback, useEffect, useMemo, useRef, useState } from 'react';

import api, { unwrapList } from '@/lib/api';
import { getErrorMessage } from '@/lib/errors';
import { EmptyState, StageError } from '@/components/stages/StagePrimitives';
import { findStage, type ProductState } from '@/lib/stages';
import {
  EMPTY_FILTERS,
  NO_CONTACT_DETAILS,
  type BankFilters,
  type BankPage,
} from '@/lib/capital';
import BankPanel from '@/components/capital/BankPanel';
import ShortlistPanel from '@/components/capital/ShortlistPanel';
import { MonoLabel } from '@/components/capital/CapitalPrimitives';

/**
 * Access to capital — who would fund this, and who has published that they
 * would not.
 *
 * A curated recommendation bank of family offices matched against what Saibyl
 * already measured about this founder, rather than a contact dump. The
 * distinction is the product: anyone can buy a list, and a list is worth
 * nothing to a founder who cannot tell which twenty of the five thousand rows
 * would take the call.
 *
 * Global rather than a sixth step on a product's rail, for the same reason the
 * USPTO check is global: "who would fund this" is a question a founder asks at
 * any point, including before there is anything to run a room against. The
 * product picker below is what ties one answer to one product, because the
 * shortlist is stored against it.
 *
 * **There is no contact affordance on this page and there must not be one.**
 * Saibyl stores no personal email address or phone number — the privacy gate
 * refuses to — and the only routes shown are the ones firms published
 * themselves. The moment this app sends on a founder's behalf, deliverability,
 * consent and reputation become ours.
 */

/** Debounce on the bank filters — one request per pause, not per keystroke. */
const FILTER_DEBOUNCE_MS = 350;

export default function CapitalPage() {
  const now = useMemo(() => new Date(), []);

  const [products, setProducts] = useState<ProductState[]>([]);
  const [productsLoading, setProductsLoading] = useState(true);
  const [productsError, setProductsError] = useState('');
  const [selectedId, setSelectedId] = useState('');

  const [filters, setFilters] = useState<BankFilters>(EMPTY_FILTERS);
  const [bank, setBank] = useState<BankPage | null>(null);
  /* The filterless read, kept separate and never overwritten by a filtered
     one. "Is there anything current to match against?" has to be answered
     over the whole bank: a stage filter that returns nothing is not an empty
     bank, and blocking the build on it would refuse a founder a shortlist
     that would have worked. */
  const [unfiltered, setUnfiltered] = useState<BankPage | null>(null);
  const [bankLoading, setBankLoading] = useState(true);
  const [bankError, setBankError] = useState('');
  const request = useRef(0);

  /* ── Products ── */
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

  /* ── The bank ──
     Filters are applied server-side; the response also carries what was
     withheld, so the count of records we will not stand behind survives every
     filter rather than disappearing with them. */
  const loadBank = useCallback((active: BankFilters) => {
    const ticket = (request.current += 1);
    setBankLoading(true);
    setBankError('');
    const params: Record<string, string> = {};
    if (active.sector.trim()) params.sector = active.sector.trim();
    if (active.stage) params.stage = active.stage;
    if (active.firm_type) params.firm_type = active.firm_type;

    api
      .get<BankPage>('/capital/firms', { params })
      .then(({ data }) => {
        // A slower earlier request must not overwrite a faster later one.
        if (ticket !== request.current) return;
        setBank(data);
        if (Object.keys(params).length === 0) setUnfiltered(data);
      })
      .catch((err) => {
        if (ticket !== request.current) return;
        setBankError(getErrorMessage(err, 'We could not read the bank.'));
      })
      .finally(() => {
        if (ticket === request.current) setBankLoading(false);
      });
  }, []);

  useEffect(() => {
    const handle = window.setTimeout(() => loadBank(filters), FILTER_DEBOUNCE_MS);
    return () => window.clearTimeout(handle);
  }, [filters, loadBank]);

  const selected = products.find((p) => p.id === selectedId) ?? null;
  /* The run whose measured objections build the objection bridge. Step 2 is
     where objections are produced, so its `produced_by` is the run that has
     them — chosen by the server rather than by this page picking "the latest"
     and getting a different answer from the rail. */
  const runId = selected ? (findStage(selected, 'reactions')?.produced_by ?? null) : null;

  return (
    <div className="capital-ground min-h-full p-6 lg:p-8">
      <div className="max-w-4xl mx-auto space-y-8">
        {/* ── Header ── */}
        <header>
          <MonoLabel>Access to capital</MonoLabel>
          <h1 className="text-h1 text-saibyl-ink mt-2">
            Who would{' '}
            <em className="font-serif italic text-[#6a4fe0]">actually</em> fund
            this
          </h1>
          <p className="text-[13px] text-saibyl-muted mt-2 leading-relaxed max-w-2xl">
            A curated bank of family offices, matched against your sector, your
            stage and the objections real buyers raised &mdash; not a contact
            dump. Firms that publish a position ruling you out are reported
            saying so, because a padded list is worth less than a short one you
            can trust.
          </p>
          <p className="text-[12px] text-saibyl-muted mt-2 leading-relaxed max-w-2xl">
            {NO_CONTACT_DETAILS}
          </p>
        </header>

        {/* ── Which product this answer is for ── */}
        {productsError && <StageError message={productsError} retry={loadProducts} />}

        {productsLoading ? (
          <p className="text-[12.5px] text-saibyl-muted" aria-live="polite">
            Loading&hellip;
          </p>
        ) : products.length === 0 ? (
          <EmptyState
            headline="There is nothing here to match yet"
            body="A shortlist is built against one thing you are raising for, so it is stored against it and can be rebuilt when the evidence changes. Add what you are building and this fills in."
            action={{ label: 'Add what you are building', href: '/app/products/new' }}
          />
        ) : (
          <>
            {products.length > 1 && (
              <div>
                <label
                  htmlFor="capital-product"
                  className="block text-[12.5px] text-saibyl-silver mb-1.5"
                >
                  Which one are you raising for?
                </label>
                <select
                  id="capital-product"
                  value={selectedId}
                  onChange={(e) => setSelectedId(e.target.value)}
                  className="w-full sm:max-w-sm rounded-xl border border-saibyl-border-light bg-white px-3 py-2.5 text-[13.5px] text-saibyl-ink focus:outline-none focus:border-saibyl-blue focus:ring-2 focus:ring-saibyl-blue/20"
                  style={{ colorScheme: 'light' }}
                >
                  {products.map((p) => (
                    <option key={p.id} value={p.id}>
                      {p.name}
                    </option>
                  ))}
                </select>
              </div>
            )}

            {selected && (
              <ShortlistPanel
                key={selected.id}
                product={{ id: selected.id, name: selected.name }}
                runId={runId}
                bankCurrent={unfiltered ? unfiltered.firms.length : null}
                bankWithheld={unfiltered ? unfiltered.withheld_stale.length : 0}
                now={now}
              />
            )}
          </>
        )}

        {/* ── What the match reads ── */}
        <BankPanel
          bank={bank}
          filters={filters}
          onFilters={setFilters}
          loading={bankLoading}
          error={bankError}
          onRetry={() => loadBank(filters)}
          now={now}
        />
      </div>
    </div>
  );
}
