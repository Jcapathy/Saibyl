import { useCallback, useEffect, useMemo, useState } from 'react';

import api, { unwrapList } from '@/lib/api';
import { getErrorMessage } from '@/lib/errors';
import { findStage, stageHref, type ProductState } from '@/lib/stages';
import { Ground, PageHeader, Rise, dealDelayMs } from '@/components/design';
import { EmptyState, StageError } from '@/components/stages/StagePrimitives';
import AnswerPackPanel from '@/components/gtm/AnswerPackPanel';
import SiteCheckPanel from '@/components/position/SiteCheckPanel';
import { useSiteChecks } from '@/components/position/checks';

/**
 * Position — the moment before launch, when the pitch exists and nobody has
 * pushed back on it yet.
 *
 * The landing page sells five moments and this is the second of them. Its
 * promise, verbatim:
 *
 *   "Which objections kill the pitch — and which answers actually move them.
 *    Test the fix on the same room, and watch the delta."
 *
 * Two sentences, and they are two halves of one job rather than two features.
 * The first is the objection matrix: what real buyers said against this, in the
 * order the room said it matters, with what to say back. The second is the
 * website check and its revision — the page a stranger reads, rewritten, put in
 * front of the same six readers, scored both ways.
 *
 * ── Why the site check lives here and not on a tab of its own ───────────────
 *
 * It had one: `/app/website`, a global page in the primary nav, built because
 * the flagship module was otherwise three clicks deep behind a nav item called
 * "Everything you uploaded". That fixed findability by adding a noun to the
 * sidebar the landing page never sold, and a founder who had just read about
 * five moments arrived to a nav listing tools.
 *
 * "Test the fix on the same room, and watch the delta" *is* the check, the
 * revision, and the before/after. It belongs to this moment, described in the
 * words the founder was sold in, and it is still one click from anywhere —
 * which is the property the global page existed to guarantee.
 *
 * ── The run this page reads is the server's choice, not this page's ─────────
 *
 * The answers are built from measured objections, and objections are produced
 * at step 2. So the run is `reactions.produced_by`, which the server sets,
 * rather than "the latest run" picked here. `GET /simulations` orders on
 * `created_at` and the rail sorts on `completed_at or created_at`: a run that
 * started earlier and finished later is the latest to one of them and not the
 * other, and a page that chooses for itself eventually shows answers from a
 * different run than the step it is standing next to.
 */

/** The answers arrive after the check panel and its findings have landed. */
const AFTER_THE_CHECK_MS = dealDelayMs(3);

export default function PositionPage() {
  const [products, setProducts] = useState<ProductState[]>([]);
  const [productsLoading, setProductsLoading] = useState(true);
  const [productsError, setProductsError] = useState('');
  const [selectedId, setSelectedId] = useState('');

  /* ── What you are building ── */
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
        setProductsError(
          getErrorMessage(err, 'We could not load what you are building.'),
        ),
      )
      .finally(() => setProductsLoading(false));
  }, []);

  useEffect(() => {
    loadProducts();
  }, [loadProducts]);

  /* Held here rather than inside the panel because the heading reads it too:
     the mark counts what has been checked, and the eyebrow's dot only pulses
     while a page is actually being read. */
  const checks = useSiteChecks(selectedId);

  const selected = useMemo(
    () => products.find((p) => p.id === selectedId) ?? null,
    [products, selectedId],
  );

  const runId = selected
    ? (findStage(selected, 'reactions')?.produced_by ?? null)
    : null;

  const checked = checks.rows.length;

  return (
    <Ground className="min-h-full p-6 lg:p-8">
      <div className="max-w-4xl mx-auto space-y-8">
        <Rise>
          <PageHeader
            eyebrow="Pre-launch"
            title="Position"
            phrase="Which objections kill the pitch — and which answers actually move them."
            mark={
              checked > 0
                ? `${checked} ${checked === 1 ? 'page' : 'pages'} checked`
                : undefined
            }
          >
            <p>Test the fix on the same room, and watch the delta.</p>
          </PageHeader>
        </Rise>

        {/* ── Which product this is about ── */}
        {productsError && (
          <StageError message={productsError} retry={loadProducts} />
        )}

        {productsLoading ? (
          <p className="text-[12.5px] text-saibyl-muted" aria-live="polite">
            Loading&hellip;
          </p>
        ) : products.length === 0 ? (
          <EmptyState
            headline="There is nothing to position yet"
            body="A check and its answers are stored against one thing you are building, so they can be rebuilt when the pitch changes. Add what you are building and this fills in."
            action={{
              label: 'Add what you are building',
              href: '/app/products/new',
            }}
          />
        ) : (
          <>
            {products.length > 1 && (
              <div>
                <label
                  htmlFor="position-product"
                  className="block text-[12.5px] text-saibyl-silver mb-1.5"
                >
                  Which one are you positioning?
                </label>
                <select
                  id="position-product"
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
              <>
                {/* ── Test the fix on the same room, and watch the delta ── */}
                <SiteCheckPanel productId={selected.id} checks={checks} />

                {/* ── Which objections kill the pitch ──
                    The panel is self-contained down to its own label and
                    heading, so it is handed the run and left to speak for
                    itself rather than given a second heading to argue with. */}
                <Rise delayMs={AFTER_THE_CHECK_MS}>
                  {runId ? (
                    <AnswerPackPanel simulationId={runId} />
                  ) : (
                    <EmptyState
                      headline="Nothing has pushed back on this yet"
                      body="The answers are built from what buyers actually objected to, hardest first, with the sentence each of them used. Put this in front of a room once and it fills in."
                      action={{
                        label: 'Put it in front of a room',
                        href: stageHref(selected.id, 'reactions'),
                      }}
                    />
                  )}
                </Rise>
              </>
            )}
          </>
        )}
      </div>
    </Ground>
  );
}
