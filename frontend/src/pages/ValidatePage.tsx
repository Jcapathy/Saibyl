import { useCallback, useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';

import api, { unwrapList } from '@/lib/api';
import { getErrorMessage } from '@/lib/errors';
import { findStage, type ProductState } from '@/lib/stages';
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
 * Validate — the idea stage.
 *
 * ── Re-aimed 2026-08-24. Read this before reordering anything ───────────────
 *
 * This page used to open with *"Does the pain exist, who feels it most, and
 * what would they pay?"* and answer it with a room, with the prior-art check
 * as the last chapter. **That order was backwards**, and PRD_V3 §12 reverses
 * it.
 *
 * The founder's own account of building ParryAI is the reason: he hit the
 * problem inside his own business, built the fix for himself, and only
 * *afterwards* asked whether other companies had it too and whether anyone had
 * already patented it. A founder who built their product out of a pain they
 * personally hit **already knows the pain is real** — they lived it. Offering
 * them a synthetic room's opinion on it is offering the weakest available
 * evidence about the one thing they have ground truth on.
 *
 * What they genuinely cannot answer is *does this generalise* and *has someone
 * already built it*. So:
 *
 *   1. **Clearance opens the stage.** `ClearanceCard` embeds the USPTO check.
 *      It is the only thing on this page whose answer comes from a public
 *      record rather than from a model's reaction, which is exactly why it goes
 *      first — it earns the credibility the room's claims spend later.
 *   2. **The room comes second**, and is asked only what a room can answer:
 *      how the idea reads. `ValidateSteps` links to `AudienceStagePage` and
 *      `ReactionsStagePage` and reports what they produced in the server's own
 *      sentences.
 *
 * **The missing middle, named rather than faked.** PRD §12c specifies a step
 * between the two — real evidence that other people have this pain, so the
 * founder learns whether their n=1 generalises. No surface returns that today;
 * `gtm/discovery` is the nearest machinery but is aimed at *who do I sell to*.
 * It is deliberately **not** stubbed here: a chapter promising something
 * unbuilt is a dead end, and a dead end is a defect.
 *
 * The clearance chapter sits **outside** the product picker on purpose — the
 * check needs no product to run, and a founder with nothing created yet is
 * exactly the founder who should be asking whether the name is already taken.
 * The picker belongs to the room chapter, which does need one.
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
          title="Find out who"
          serif="already built it."
          actions={
            /* One gradient on the screen, and it is now the check rather than
               the room. The clearance card needs no product, so this is the one
               action on the page that works on a founder's first minute here. */
            <>
              <Action as="a" href="#clearance">
                Check the record first
              </Action>
              <Action as={Link} to="/app/guide" kind="quiet">
                How this works
              </Action>
            </>
          }
        >
          <p>
            You built this because you ran into the problem yourself &mdash;
            that part you already know, and no room of strangers is going to
            tell you otherwise. What you cannot know yet is whether anybody
            filed a patent on it two years ago, and whether the pain you felt is
            felt by enough other people to be a business. So Saibyl checks the
            public record first: trademarks, granted patents, and the
            applications nobody reads. Then it builds the room, and you find out
            how the idea actually lands.{' '}
            <b className="text-saibyl-ink font-semibold">
              Is it just you &mdash; and has anyone already built it?
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

        {/* ── The check that opens the stage ──
            First on the page since 2026-08-24 (PRD §12c). Outside the picker,
            because it needs no product to run — which also makes it the one
            thing here a founder can use in their first minute. */}
        <div id="clearance" className="scroll-mt-24">
          <Chapter
            kicker="Start here"
            title={
              <>
                Somebody may have <em>already filed it</em>
              </>
            }
            lead="This is the one question you can answer today with no product, no buyers and nothing spent — and the only one on this page whose answer comes out of a public record instead of somebody's opinion. Being late here is expensive in a way no room can warn you about."
          >
            <Reveal>
              <ClearanceCard products={productOptions} />
            </Reveal>
          </Chapter>
        </div>

        {/* ── Then the room ──
            One chapter, and every branch of the load renders inside it — the
            hero above is rendered once and only the body changes, so a founder
            who is loading, errored or has nothing yet still lands on the same
            page as everybody else. */}
        <Chapter
          kicker="Then, the room"
          title={
            <>
              How the idea <em>actually lands</em>
            </>
          }
          lead="Once you know the ground is clear, you find out how it reads. This is what a room is genuinely good for — not telling you the problem is real, which you already know, but showing you which parts of the idea land as written and which have to be explained first."
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
      </Longform>
    </Ground>
  );
}
