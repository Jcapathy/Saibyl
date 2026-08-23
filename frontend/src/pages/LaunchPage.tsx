import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useSearchParams } from 'react-router-dom';

import api, { unwrapList } from '@/lib/api';
import { getErrorMessage } from '@/lib/errors';
import { findStage, type ProductState } from '@/lib/stages';
import type { Simulation } from '@/types';
import { Ground, PageHeader, Rise, dealDelayMs } from '@/components/design';
import { EmptyState, StageError } from '@/components/stages/StagePrimitives';
import MessagingDocPanel from '@/components/gtm/MessagingDocPanel';
import OutboundPanel from '@/components/gtm/OutboundPanel';
import MessageTests from '@/components/launch/MessageTests';
import { isHeadToHead } from '@/components/launch/launch';

/**
 * Launch — the go-to-market stage.
 *
 * The landing page sells this moment in one sentence: *"Up to eight versions of
 * the message, head to head, in front of the same room — the winner earns your
 * budget."* This is the screen that sentence was a promise about, and it holds
 * the three things a founder taking something to market actually needs, in the
 * order they need them:
 *
 *   1. **Which way of saying it wins** — several wordings, one shared room, and
 *      a scoreboard that refuses to name a winner when the leading two do not
 *      separate.
 *   2. **The messaging document** — the problem, the solution, who it is for,
 *      the value props and the pitch, filled in from what buyers said rather
 *      than from memory. Everything else a founder writes inherits from it.
 *   3. **The outreach** — a fortnight of copy per kind of buyer, each step built
 *      on a pain the room measured, with their own sentences attached.
 *
 * ── Nothing here is new, and that is the point ───────────────────────────────
 *
 * Every one of the three was built, priced and deployed already. They were
 * simply scattered: the comparison lived on a page called "Messages" that a
 * founder reached by guessing, and the other two behind a nav item called "What
 * to say" — the label the founder called unintuitive, because it describes a
 * sentence rather than a stage of a company. The pages they came from are
 * retired by this one.
 *
 * ── Two decisions worth knowing about ────────────────────────────────────────
 *
 * **The run is chosen by the server, not by this page.** The document and the
 * outreach are built from measured objections, and objections are produced at
 * step 2 — so the run is that step's own `produced_by`. `GET /simulations`
 * orders on `created_at` while the rail sorts on `completed_at or created_at`,
 * so a page picking "the latest run" for itself would eventually disagree with
 * the rail about which answer a founder is looking at. `CapitalPage` and the
 * sales toolkit both settled this the same way.
 *
 * **This page creates no runs.** Every control that would start one is a route
 * to the screen that already prices, gates and starts them. A second creation
 * path is how two surfaces end up disagreeing about what a run is, and the way
 * that failure presents is a founder billed for work the engine never did.
 */

/** Each of the three blocks arrives one deal-step after the one above it. */
const AFTER_THE_TESTS_MS = dealDelayMs(1);
const AFTER_THE_DOCUMENT_MS = dealDelayMs(2);

export default function LaunchPage() {
  const [params] = useSearchParams();
  /* A deep link may name the product. Three surfaces still send `?project=`,
     the spelling `/app/marketing` used before Launch absorbed it, and those
     links redirect here with the query intact — so both spellings are read and
     neither is written. Landing on the right stage showing the wrong product is
     the failure this exists to prevent. */
  const wanted = params.get('product') ?? params.get('project') ?? '';

  const [products, setProducts] = useState<ProductState[]>([]);
  const [productsLoading, setProductsLoading] = useState(true);
  const [productsError, setProductsError] = useState('');
  const [selectedId, setSelectedId] = useState('');

  /* The runs, carrying the product they were fetched for.
     Stored as one object rather than as a bare list because the two must move
     together: a list on its own stays on screen through a product switch until
     the next response lands, and for that render the page shows one product's
     name over another product's runs. Both are true statements and the pair is
     a lie. Guarded by deriving what to render, rather than by clearing the list
     in the effect below — a synchronous `setState` in an effect body is the
     cascading render this codebase has already been bitten by. */
  const [runs, setRuns] = useState<{ productId: string; items: Simulation[] }>({
    productId: '',
    items: [],
  });
  const [runsError, setRunsError] = useState('');

  /* ── What you are building ── */
  const loadProducts = useCallback(() => {
    api
      .get('/products')
      .then((r) => {
        const items = unwrapList<ProductState>(r.data).items;
        setProducts(items);
        setProductsError('');
        setSelectedId((current) => {
          /* What the founder already picked wins over the link that brought
             him here — a reload after a switch must not snap back. */
          const preferred = current || wanted;
          return preferred && items.some((p) => p.id === preferred)
            ? preferred
            : (items[0]?.id ?? '');
        });
      })
      .catch((err) =>
        setProductsError(
          getErrorMessage(err, 'We could not load what you are building.'),
        ),
      )
      .finally(() => setProductsLoading(false));
  }, [wanted]);

  useEffect(() => {
    loadProducts();
  }, [loadProducts]);

  /* ── The runs this product has, so the head-to-head panel can list them ──
     Ticketed, because two switches in quick succession can land out of order:
     a slower earlier response would otherwise overwrite a faster later one and
     leave the page showing nothing for a product that has runs, with no error
     and no way for the founder to tell why. Same guard as `CapitalPage`. */
  const request = useRef(0);
  const loadRuns = useCallback((productId: string) => {
    if (!productId) return;
    const ticket = (request.current += 1);
    api
      .get('/simulations', { params: { project_id: productId, limit: 100 } })
      .then((r) => {
        if (ticket !== request.current) return;
        setRuns({ productId, items: unwrapList<Simulation>(r.data).items });
        setRunsError('');
      })
      .catch((err) => {
        if (ticket !== request.current) return;
        setRunsError(getErrorMessage(err, 'We could not read your runs.'));
      });
  }, []);

  useEffect(() => {
    loadRuns(selectedId);
  }, [loadRuns, selectedId]);

  const selected = useMemo(
    () => products.find((p) => p.id === selectedId) ?? null,
    [products, selectedId],
  );

  /* The runs that belong to the product on screen, and only those. Empty while
     a freshly-picked product's runs are still in flight, which reads as "we do
     not know yet" rather than as somebody else's answer. */
  const shown = useMemo(
    () => (runs.productId === selectedId ? runs.items : []),
    [runs, selectedId],
  );

  /* How many sets of wordings this product has already put in front of a room.
     Counted from the same predicate the panel filters on, so the figure beside
     the title and the rows underneath it can never disagree. */
  const tested = useMemo(() => shown.filter(isHeadToHead).length, [shown]);

  /* The run whose measured objections the document and the outreach are written
     from. Step 2 is where objections are produced, so its `produced_by` is the
     run that has them — chosen by the server rather than by this page picking
     "the latest" and getting a different answer from the rail. */
  const runId = selected
    ? (findStage(selected, 'reactions')?.produced_by ?? null)
    : null;

  return (
    <Ground className="min-h-full p-6 lg:p-8">
      <div className="max-w-4xl mx-auto space-y-8">
        <Rise>
          <PageHeader
            eyebrow="Go to market"
            title="Launch"
            phrase="Up to eight versions of the message, head to head, in front of the same room — the winner earns your budget."
            mark={tested > 0 ? `${tested} tested so far` : undefined}
          >
            <p>
              This is the stage where you take it to market, and it answers the
              three questions that decide how that goes: which way of saying it
              wins, what your messaging actually is once you have decided, and
              what goes out on Monday morning.
            </p>
            <p className="mt-2">
              None of it is written from memory. The wording is picked by a room
              of buyers rather than settled in a meeting, and everything under
              it is built from the objections those buyers raised, in their own
              words. Where a line needs a figure nobody measured, you get a
              blank you can fill rather than a number we made up.
            </p>
          </PageHeader>
        </Rise>

        {/* ── Which product this is for ── */}
        {productsError && (
          <StageError message={productsError} retry={loadProducts} />
        )}

        {productsLoading ? (
          <p className="text-[12.5px] text-saibyl-muted" aria-live="polite">
            Loading&hellip;
          </p>
        ) : products.length === 0 ? (
          <EmptyState
            headline="There is nothing here to launch yet"
            body="Everything on this page is written about one thing you are taking to market, so it is stored against it. Add what you are building and this fills in."
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
                  htmlFor="launch-product"
                  className="block text-[12.5px] text-saibyl-silver mb-1.5"
                >
                  Which one are you launching?
                </label>
                <select
                  id="launch-product"
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
                {runsError && (
                  <StageError
                    message={runsError}
                    retry={() => loadRuns(selected.id)}
                  />
                )}

                {/* The centrepiece: what the landing page sells this stage on. */}
                <MessageTests
                  key={selected.id}
                  productId={selected.id}
                  runs={shown}
                />

                {/* ── The two artifacts written from measured objections ──
                    Gated on the run rather than rendered empty, because both
                    panels would otherwise open with a price and a button for a
                    build with nothing honest to build from. Keyed on the run so
                    changing product mounts a fresh panel instead of leaving the
                    previous product's document on screen while the new one
                    loads. */}
                {!runId ? (
                  <EmptyState
                    headline="Nothing has been in front of a room yet"
                    body="Your messaging and your outreach are written from objections real buyers raised, so there is nothing honest to build until a room has reacted to this. Put it in front of one and both fill in."
                    action={{
                      label: 'Put it in front of a room',
                      href: `/app/products/${selected.id}/reactions`,
                    }}
                  />
                ) : (
                  <>
                    <Rise delayMs={AFTER_THE_TESTS_MS}>
                      <MessagingDocPanel key={runId} simulationId={runId} />
                    </Rise>
                    <Rise delayMs={AFTER_THE_DOCUMENT_MS}>
                      <OutboundPanel key={runId} simulationId={runId} />
                    </Rise>
                  </>
                )}
              </>
            )}
          </>
        )}
      </div>
    </Ground>
  );
}
