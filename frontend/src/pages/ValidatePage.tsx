import { useCallback, useEffect, useMemo, useState } from 'react';

import api, { unwrapList } from '@/lib/api';
import { getErrorMessage } from '@/lib/errors';
import { findStage, type ProductState } from '@/lib/stages';
import { Ground, PageHeader, Rise, dealDelayMs } from '@/components/design';
import { EmptyState, StageError } from '@/components/stages/StagePrimitives';
import ClearanceCard from '@/components/validate/ClearanceCard';
import ValidateSteps from '@/components/validate/ValidateSteps';

/**
 * Validate — the idea stage, as the landing page sells it.
 *
 * The public site promises five stages of a company and names the first one:
 *
 *   > **Validate** — IDEA STAGE — *"Does the pain exist, who feels it most, and
 *   > what would they pay? Five answers are enough to build your first room."*
 *
 * Behind the login that promise had no door. The machinery all existed — the
 * idea brief and the audience on step 1, the room on step 2 — but it was
 * reachable only by first creating a product and then finding the rail
 * underneath it, which is the same defect that hid the site check from the home
 * page and the message comparison until it got a page of its own. A capability
 * a founder cannot find is a capability nobody bought.
 *
 * So this page builds nothing new. It is a door, and everything behind it is
 * composed:
 *
 *   · `ValidateSteps` links to `AudienceStagePage` and `ReactionsStagePage`,
 *     and reports what they have produced using the server's own sentences.
 *   · `ClearanceCard` embeds the USPTO check — `components/clearance/`,
 *     unchanged — because "is this even mine to build?" is an idea-stage
 *     question. It was a top-level module only because it had nowhere else to
 *     live.
 *
 * The product picker is the `CapitalPage` pattern: a global page that has to be
 * told which one thing it is about. The clearance card sits **outside** it on
 * purpose — the check needs no product to run, and a founder with nothing
 * created yet is exactly the founder who should be asking whether the name is
 * already taken.
 */

/** The two steps of the rail this stage is made of. */
const IDEA_STEPS = 2;

/** How long the clearance card waits, so it arrives after the three doors deal. */
const AFTER_THE_DOORS_MS = dealDelayMs(3);

export default function ValidatePage() {
  const [products, setProducts] = useState<ProductState[]>([]);
  const [productsLoading, setProductsLoading] = useState(true);
  const [productsError, setProductsError] = useState('');
  const [selectedId, setSelectedId] = useState('');

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

  const selected = useMemo(
    () => products.find((p) => p.id === selectedId) ?? null,
    [products, selectedId],
  );

  /* How far along this idea is, counted the way the server counts it: `ready`
     means every wanted input is present, and `degraded` deliberately does not
     qualify. Reading `stages_ready` instead would fold in the three later
     stages, which belong to Position and Launch rather than to this page. */
  const ready = useMemo(() => {
    if (!selected) return 0;
    return [findStage(selected, 'audience'), findStage(selected, 'reactions')].filter(
      (stage) => stage?.runnable === 'ready',
    ).length;
  }, [selected]);

  /* `ClearanceRunForm` takes only the name and the id, and it takes them for an
     optional attachment rather than as this page's selection. Narrowed here so
     the form cannot read a stage state it has no business reading. */
  const productOptions = useMemo(
    () => products.map((p) => ({ id: p.id, name: p.name })),
    [products],
  );

  return (
    <Ground className="min-h-full p-6 lg:p-8">
      <div className="max-w-4xl mx-auto space-y-8">
        <Rise>
          <PageHeader
            eyebrow="Idea stage"
            title="Validate"
            phrase="Does the pain exist, who feels it most, and what would they pay?"
            mark={
              selected
                ? `${ready} of ${IDEA_STEPS} steps have what they need`
                : undefined
            }
          >
            <p>Five answers are enough to build your first room.</p>
          </PageHeader>
        </Rise>

        {/* ── Which idea this is about ── */}
        {productsError && <StageError message={productsError} retry={loadProducts} />}

        {productsLoading ? (
          <p className="text-[12.5px] text-saibyl-muted" aria-live="polite">
            Loading&hellip;
          </p>
        ) : products.length === 0 ? (
          <EmptyState
            headline="There is nothing to validate yet"
            body="A room is built against one thing you are making, so it is stored against it. Name what you are building — a sentence is enough — and the three steps below fill in."
            action={{ label: 'Add what you are building', href: '/app/products/new' }}
          />
        ) : (
          <>
            {products.length > 1 && (
              <div>
                <label
                  htmlFor="validate-product"
                  className="block text-[12.5px] text-saibyl-silver mb-1.5"
                >
                  Which one are you validating?
                </label>
                <select
                  id="validate-product"
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

            {selected && <ValidateSteps key={selected.id} product={selected} />}
          </>
        )}

        {/* Outside the picker: the one question that comes before there is
            anything to pick. Arrives after the doors have dealt — one
            orchestrated arrival per screen, per the canvas. */}
        <Rise delayMs={selected ? AFTER_THE_DOORS_MS : 0}>
          <ClearanceCard products={productOptions} />
        </Rise>
      </div>
    </Ground>
  );
}
