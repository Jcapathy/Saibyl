import { useCallback, useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';

import api, { unwrapList } from '@/lib/api';
import { getErrorMessage } from '@/lib/errors';
import { findStage, stageHref, type ProductState } from '@/lib/stages';
import {
  Action,
  Chapter,
  Ground,
  Hero,
  Longform,
  Reveal,
} from '@/components/design';
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
 * told which one thing it is about. The clearance card sits in a chapter of its
 * own, **outside** the picker on purpose — the check needs no product to run,
 * and a founder with nothing created yet is exactly the founder who should be
 * asking whether the name is already taken.
 *
 * ── The frame, 2026-08-23: this page opens like the landing page ────────────
 *
 * The founder read the app against the public site and called it "very sterile,
 * mechanical, and looks AI-generated". His instruction was to treat every page
 * behind the login the way the landing page treats itself — a hero, large type,
 * then scroll, with the content arriving as the reader reaches it. So the frame
 * is `Longform` / `Hero` / `Chapter` / `Reveal`, whose values are
 * `pages/landing.css`'s own, and `GuidePage` is the built example this copies.
 *
 * **Nothing inside a chapter changed.** The doors, the clearance card and the
 * picker are the same density they were; the canvas's constraint was about
 * those and it still holds. The hero is never wrapped in `Reveal` — it is the
 * first screen, and a page whose opening fades in looks broken for 700ms.
 */

/** The two steps of the rail this stage is made of. */
const IDEA_STEPS = 2;

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
    <Ground className="min-h-full pb-24">
      <Longform>
        <Hero
          eyebrow="Idea stage"
          title="Find out if anyone"
          serif="actually wants it."
          actions={
            /* One gradient on the screen, and it is the thing this stage is
               for. Before there is anything to put in a room the only honest
               next step is naming what you are building. */
            <>
              {selected ? (
                <Action as={Link} to={stageHref(selected.id, 'reactions')}>
                  Put it in front of a room
                </Action>
              ) : (
                <Action as={Link} to="/app/products/new">
                  Add what you are building
                </Action>
              )}
              <Action as={Link} to="/app/guide" kind="quiet">
                How this works
              </Action>
            </>
          }
        >
          <p>
            Founders everywhere are turning ideas into products, and most find
            out far too late that nobody felt the problem badly enough to pay
            for it. This is where you find out first. Describe what you are
            building and Saibyl assembles the room of buyers you think you have
            &mdash; then you read what they actually say: whether the pain is
            real, which of them feels it hardest, and what being rid of it would
            be worth. Five answers are enough to build that first room.{' '}
            <b className="text-saibyl-ink font-semibold">
              Does the pain exist? Who feels it most? What would they pay?
            </b>
          </p>
          {/* The artboard's line beside the title, kept: how far along this
              idea is, in the server's own reckoning. */}
          {selected && (
            <p className="mt-5 text-[12.5px] text-saibyl-muted">
              {ready} of {IDEA_STEPS} steps have what they need
            </p>
          )}
        </Hero>

        {/* ── Getting the idea into a room ──
            One chapter, and every branch of the load renders inside it — the
            hero above is rendered once and only the body changes, so a founder
            who is loading, errored or has nothing yet still lands on the same
            page as everybody else. */}
        <Chapter
          kicker="Step by step"
          title={
            <>
              Three things, <em>in the order they matter</em>
            </>
          }
          lead="None of it asks for a finished product. You write the idea down, you agree on who it is for, and then a room of those buyers argues about it while being wrong is still cheap."
        >
          <div className="space-y-6">
            {productsError && (
              <Reveal>
                <StageError message={productsError} retry={loadProducts} />
              </Reveal>
            )}

            {productsLoading ? (
              <Reveal>
                <p className="text-[12.5px] text-saibyl-muted" aria-live="polite">
                  Loading&hellip;
                </p>
              </Reveal>
            ) : products.length === 0 ? (
              <Reveal>
                <EmptyState
                  headline="There is nothing to validate yet"
                  body="A room is built against one thing you are making, so it is stored against it. Name what you are building — a sentence is enough — and the three steps below fill in."
                  action={{ label: 'Add what you are building', href: '/app/products/new' }}
                />
              </Reveal>
            ) : (
              <>
                {products.length > 1 && (
                  <Reveal>
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
                  </Reveal>
                )}

                {selected && (
                  <Reveal step={1}>
                    <ValidateSteps key={selected.id} product={selected} />
                  </Reveal>
                )}
              </>
            )}
          </div>
        </Chapter>

        {/* ── The question that comes before any of it ──
            Outside the picker, as it was: the check needs no product to run. */}
        <Chapter
          kicker="Before you build it"
          title={
            <>
              The name might <em>already be taken</em>
            </>
          }
          lead="This is the one question you can answer today with no product, no buyers and nothing spent — and the only one where being late is expensive in a way no room can warn you about."
        >
          <Reveal>
            <ClearanceCard products={productOptions} />
          </Reveal>
        </Chapter>
      </Longform>
    </Ground>
  );
}
