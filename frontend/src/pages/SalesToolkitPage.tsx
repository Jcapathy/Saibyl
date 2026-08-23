import { useCallback, useEffect, useState } from 'react';

import api, { unwrapList } from '@/lib/api';
import { getErrorMessage } from '@/lib/errors';
import { EmptyState, StageError } from '@/components/stages/StagePrimitives';
import { findStage, type ProductState } from '@/lib/stages';
import AnswerPackPanel from '@/components/gtm/AnswerPackPanel';
import MessagingDocPanel from '@/components/gtm/MessagingDocPanel';
import OutboundPanel from '@/components/gtm/OutboundPanel';

type Tab = 'answers' | 'messaging' | 'outbound';

const TABS: { key: Tab; label: string; blurb: string }[] = [
  {
    key: 'answers',
    label: 'Objection answers',
    blurb:
      'What to say when a buyer raises the objection the room actually raised, ranked by how much weight it carried.',
  },
  {
    key: 'messaging',
    label: 'Messaging',
    blurb:
      'The problem, the solution, three value props and three differentiators — filled from what buyers said rather than from memory.',
  },
  {
    key: 'outbound',
    label: 'Outbound',
    blurb:
      'A sequence per kind of buyer, each step built on a pain the room measured, with their own words attached.',
  },
];

/**
 * The three sales artifacts, reachable in one click.
 *
 * All three are also steps on a product's rail — answers, buyers, messages —
 * and that was the only way to reach them. A founder on `/app/home` had no
 * path to any of it.
 *
 * Global for the same reason the website check is: these are things a founder
 * goes looking for by name ("where are my objection answers"), not stages they
 * walk through in order. The product picker ties the answer to one product;
 * the run is the one that produced the objections, chosen by the server via
 * `produced_by` rather than by this page guessing at "the latest".
 *
 * The panels are the same components the stage pages render, with the same
 * single `simulationId` prop — no second implementation to drift.
 */
export default function SalesToolkitPage() {
  const [products, setProducts] = useState<ProductState[]>([]);
  const [productsLoading, setProductsLoading] = useState(true);
  const [productsError, setProductsError] = useState('');
  const [selectedId, setSelectedId] = useState('');
  const [tab, setTab] = useState<Tab>('answers');

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

  const selected = products.find((p) => p.id === selectedId) ?? null;
  /* The run that produced the objections these are built from. Step 2 is where
     objections are measured, so its `produced_by` is the run that has them —
     the same reasoning `CapitalPage` uses, and for the same reason: this page
     picking "the latest run" would disagree with the rail. */
  const runId = selected ? (findStage(selected, 'reactions')?.produced_by ?? null) : null;

  const active = TABS.find((t) => t.key === tab) ?? TABS[0];

  return (
    <div className="px-5 py-6 md:px-8 md:py-8">
      <div className="max-w-4xl space-y-6">
        <header>
          <h1 className="text-[22px] font-semibold text-saibyl-ink">
            What to say
          </h1>
          <p className="text-[13px] text-saibyl-muted mt-2 leading-relaxed max-w-2xl">
            Everything here is built from objections real buyers raised in your
            run, with their verbatim words attached. Where a claim needs a
            number the run never measured, you will see a blank rather than an
            invented figure &mdash; those are counted, and they are yours to
            fill.
          </p>
        </header>

        {productsError && <StageError message={productsError} retry={loadProducts} />}

        {productsLoading ? (
          <p className="text-[12.5px] text-saibyl-muted" aria-live="polite">
            Loading&hellip;
          </p>
        ) : products.length === 0 ? (
          <EmptyState
            headline="There is nothing to build from yet"
            body="These are written from what buyers said about one thing you are building. Add it, run the room, and this fills in."
            action={{ label: 'Add what you are building', href: '/app/products/new' }}
          />
        ) : (
          <>
            {products.length > 1 && (
              <div>
                <label
                  htmlFor="sales-product"
                  className="block text-[12.5px] text-saibyl-silver mb-1.5"
                >
                  Which one is this for?
                </label>
                <select
                  id="sales-product"
                  value={selectedId}
                  onChange={(e) => setSelectedId(e.target.value)}
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

            <div className="flex flex-wrap gap-1.5" role="tablist">
              {TABS.map((t) => (
                <button
                  key={t.key}
                  type="button"
                  role="tab"
                  aria-selected={tab === t.key}
                  onClick={() => setTab(t.key)}
                  className={`rounded-lg px-3 py-1.5 text-[12.5px] transition ${
                    tab === t.key
                      ? 'bg-saibyl-ink text-white'
                      : 'border border-saibyl-border text-saibyl-silver hover:border-saibyl-gold/40'
                  }`}
                >
                  {t.label}
                </button>
              ))}
            </div>

            <p className="text-[12.5px] text-saibyl-muted leading-relaxed max-w-2xl">
              {active.blurb}
            </p>

            {!runId ? (
              <EmptyState
                headline="This one has not been through the room yet"
                body="These are written from measured objections, so there is nothing honest to build until buyers have reacted. Run the room first and come back."
                action={{
                  label: 'Open this product',
                  href: `/app/products/${selectedId}/reactions`,
                }}
              />
            ) : (
              /* Keyed on the run as well as the tab: switching product must
                 mount a fresh panel rather than leave the previous product's
                 artifact on screen while the new one loads. */
              <div key={`${runId}-${tab}`}>
                {tab === 'answers' && <AnswerPackPanel simulationId={runId} />}
                {tab === 'messaging' && <MessagingDocPanel simulationId={runId} />}
                {tab === 'outbound' && <OutboundPanel simulationId={runId} />}
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
}
