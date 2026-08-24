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
 * front of the same six readers, scored both ways. One chapter each.
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
 *
 * ── The frame, 2026-08-23: this page opens like the landing page ────────────
 *
 * The founder read the app against the public site and called it "very sterile,
 * mechanical, and looks AI-generated"; the instruction was to treat every page
 * behind the login the way the landing page treats itself — hero, large type,
 * then scroll, with the content arriving as the reader reaches it. So the frame
 * is `Longform` / `Hero` / `Chapter` / `Reveal` and `GuidePage` is the built
 * example it copies. What is *inside* each chapter is the same density it was:
 * the panels, the picker and the empty states are untouched.
 */

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

  /* Held here rather than inside the panel because the hero reads it too: the
     mark under the lead counts what has been checked. */
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
    <Ground className="min-h-full pb-24">
      <Longform>
        <Hero
          eyebrow="Pre-launch"
          title="Find the objection"
          serif="that kills the pitch."
          actions={
            /* The one gradient on this screen. Everything on the page is built
               from what a room said, so the control that unblocks all of it is
               the room — the same handoff the empty state below offers. */
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
            A good product still loses to the one objection nobody rehearsed.
            Your page has a few seconds to answer it, and you are the last
            person alive who can read that page fresh. So the room reads it for
            you and says what stopped them, in their own words, ranked by how
            many it stopped. Then Saibyl rewrites the page to answer the worst
            of it and puts the new version in front of that same room &mdash; so
            what you get is a measured difference rather than a hope.{' '}
            <b className="text-saibyl-ink font-semibold">
              Which objection kills the pitch? What answer moves them? Did the
              fix actually work?
            </b>
          </p>
          {checked > 0 && (
            <p className="mt-5 text-[12.5px] text-saibyl-muted">
              {checked} {checked === 1 ? 'page' : 'pages'} checked
            </p>
          )}
        </Hero>

        {/* ── Test the fix on the same room, and watch the delta ──
            Every branch of the load renders inside this chapter: the hero is
            rendered once and only the body switches, so a founder who is
            loading, errored or has nothing yet still sees the same page. */}
        <Chapter
          kicker="The page they read"
          title={
            <>
              What a stranger takes away, <em>and where they stop</em>
            </>
          }
          lead="Paste the address and six readers tell you what they understood, what they did not believe, and the line they gave up on. Then the rewrite goes back to those same six, and the difference between the two readings is the answer."
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
                  headline="There is nothing to position yet"
                  body="A check and its answers are stored against one thing you are building, so they can be rebuilt when the pitch changes. Add what you are building and this fills in."
                  action={{
                    label: 'Add what you are building',
                    href: '/app/products/new',
                  }}
                />
              </Reveal>
            ) : (
              <>
                {products.length > 1 && (
                  <Reveal>
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
                  </Reveal>
                )}

                {selected && (
                  <Reveal step={1}>
                    <SiteCheckPanel productId={selected.id} checks={checks} />
                  </Reveal>
                )}
              </>
            )}
          </div>
        </Chapter>

        {/* ── Which objections kill the pitch ──
            The panel is self-contained down to its own label and heading, so it
            is handed the run and left to speak for itself rather than given a
            second heading to argue with. The chapter around it is gated on the
            product, exactly as the block it replaces was. */}
        {selected && (
          <Chapter
            kicker="What to say back"
            title={
              <>
                The objections, <em>hardest first</em>
              </>
            }
            lead="Ranked by how much of the room actually carried each one rather than by how often the words came up — with the sentence a buyer used, and the answer that has to survive it."
          >
            <Reveal>
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
            </Reveal>
          </Chapter>
        )}
      </Longform>
    </Ground>
  );
}
