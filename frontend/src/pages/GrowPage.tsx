import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Link } from 'react-router-dom';

import api, { unwrapList } from '@/lib/api';
import { getErrorMessage } from '@/lib/errors';
import type { StageSpec } from '@/lib/founder';
import type { ProductState } from '@/lib/stages';
import {
  Action,
  Chapter,
  Ground,
  Hero,
  Longform,
  Reveal,
} from '@/components/design';
import { EmptyState, StageError } from '@/components/stages/StagePrimitives';
import { Limits, RoomNote } from '@/components/grow/GrowPrimitives';
import MoveCards from '@/components/grow/MoveCards';
import RehearsalList from '@/components/grow/RehearsalList';
import {
  GROWTH_STAGE_ID,
  growthRuns,
  rehearsalHref,
  type GrowthRun,
} from '@/components/grow/grow';

/**
 * Grow — rehearse a change before the market grades it.
 *
 * The founder who lands here has already shipped. They validated the idea, they
 * found their position, they launched, and now they want to move: put the price
 * up, add a feature, take one away, go after a customer who is not today's
 * customer. Every one of those is a change to what they sell, and every one of
 * them is normally made and *then* discovered to be wrong, from churn, three
 * months later, with no way to tell which part of the change did it.
 *
 * ── This page adds no machinery, and that is the point ──────────────────────
 *
 * Every capability it offers was already built and already deployed:
 *
 *   · `founder_stage: 'growth'` has been an entry in the server-side registry
 *     (`services/engine/founder_stages.py`) since the Founder lens shipped. It
 *     carries this moment's own defaults — the highest share of people who
 *     already have something that works, six rounds instead of five — and the
 *     limits the finished write-up must state.
 *   · `PUT /api/variants/{id}` puts what you sell today and what you propose in
 *     front of **one shared room**, so what differs between them is the change.
 *   · The scoreboard grades them and declines to name a winner whenever the top
 *     two intervals overlap.
 *
 * What did not exist was a **door**. All of the above was reachable only by
 * knowing that a query parameter on the run wizard existed, which is the same
 * defect that hid the message comparison until it got a page of its own, and
 * the same one that left the flagship site check unreachable from home. A
 * capability nobody can find is a capability nobody bought.
 *
 * So this creates no runs of its own. It says what the three changes are, says
 * what to write for each, hands off to the one screen that creates runs, and
 * reports what came back — including, prominently, when what came back was
 * "these two did not separate".
 *
 * ── The frame, 2026-08-23: this page opens like the landing page ────────────
 *
 * The founder read the app against the public site and called it "very sterile,
 * mechanical, and looks AI-generated"; the instruction was to treat every page
 * behind the login the way the landing page treats itself — hero, large type,
 * then scroll, with the content arriving as the reader reaches it. So the frame
 * is `Longform` / `Hero` / `Chapter` / `Reveal`, copied from `GuidePage`. What
 * is *inside* a chapter is the density it always was: the move cards, the room
 * note, the rehearsal list and the honesty floor are untouched.
 */

export default function GrowPage() {
  const [products, setProducts] = useState<ProductState[]>([]);
  const [productsLoading, setProductsLoading] = useState(true);
  const [productsError, setProductsError] = useState('');
  const [selectedId, setSelectedId] = useState('');

  const [spec, setSpec] = useState<StageSpec | null>(null);

  /**
   * The rehearsals, carrying the product they belong to.
   *
   * Stored together rather than as a bare array, because the two states are
   * only ever read as a pair. Switching product leaves the previous answer in
   * state until the next one lands, and a bare array would render one
   * product's rehearsals under another product's name for as long as the
   * request takes — every row of it plausible, none of it about the thing on
   * screen. Tagging the answer makes the mismatch unrepresentable instead of
   * relying on a synchronous clear, which is the cascading render this codebase
   * has been bitten by.
   */
  const [answer, setAnswer] = useState<{ productId: string; runs: GrowthRun[] }>({
    productId: '',
    runs: [],
  });
  const [runsError, setRunsError] = useState('');
  /* A slower earlier request must not overwrite a faster later one. */
  const request = useRef(0);

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
        setProductsError(getErrorMessage(err, 'We could not load what you are building.')),
      )
      .finally(() => setProductsLoading(false));
  }, []);

  useEffect(() => {
    loadProducts();
  }, [loadProducts]);

  /* ── What this moment is, according to the server ──
     Fetched rather than restated. The defaults shown here, the audience the run
     is actually built with, and the limits the finished write-up states are one
     object on the server; a copy in this file is a copy that will eventually
     disagree with the report a founder paid for. A failure is quiet: the notes
     below simply do not render, which is honest, where a made-up default would
     not be. */
  useEffect(() => {
    let cancelled = false;
    api
      .get<StageSpec[]>('/simulations/founder-stages')
      .then((r) => {
        if (cancelled) return;
        const found = (r.data ?? []).find((s) => s.id === GROWTH_STAGE_ID) ?? null;
        setSpec(found);
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, []);

  /* ── Changes already rehearsed for this product ── */
  const loadRuns = useCallback((productId: string) => {
    if (!productId) return;
    const ticket = (request.current += 1);
    api
      .get('/simulations', { params: { project_id: productId, limit: 100 } })
      .then((r) => {
        if (ticket !== request.current) return;
        setAnswer({ productId, runs: growthRuns(unwrapList<GrowthRun>(r.data).items) });
        setRunsError('');
      })
      .catch((err) => {
        if (ticket !== request.current) return;
        setRunsError(getErrorMessage(err, 'We could not read what you have rehearsed.'));
      });
  }, []);

  useEffect(() => {
    loadRuns(selectedId);
  }, [loadRuns, selectedId]);

  /* Only ever the rehearsals for the product on screen. `settled` is the
     difference between "there are none" and "we have not been told yet" —
     collapsing those two into an empty array is how a founder who has run six
     rehearsals gets shown "you have not rehearsed anything" every time they
     switch products. */
  const settled = answer.productId === selectedId;
  const runs = settled ? answer.runs : [];

  const selected = useMemo(
    () => products.find((p) => p.id === selectedId) ?? null,
    [products, selectedId],
  );

  return (
    <Ground className="min-h-full pb-24">
      <Longform>
        <Hero
          eyebrow="Twelve users in"
          title="Rehearse the move"
          serif="before it costs you."
          actions={
            /* The one gradient on this screen, and it leads to the screen that
               already quotes and starts a run. This page starts none. */
            <>
              {selected ? (
                <Action as={Link} to={rehearsalHref(selected.id)}>
                  Rehearse a change
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
            You have twelve users. Is that good? Nobody will tell you, and the
            people who could have all forgotten what twelve felt like. So you
            decide to move: put the price up, add something, take something
            away, go after a buyer who is not today&rsquo;s buyer. Each of those
            is a change to what you sell, and each is normally made first and
            understood three months later, from churn, with no way to tell which
            part of it did the damage.
          </p>
          <p className="mt-4">
            This puts the change in front of a room built for the moment you are
            in, and reports what they said. It is not a forecast. It is the
            argument you were going to have anyway, held a week early, in front
            of people who cannot cost you a customer.{' '}
            <b className="text-saibyl-ink font-semibold">
              Will they pay more? Do they want this next? Will a new market buy
              it?
            </b>
          </p>
          {runs.length > 0 && (
            <p className="mt-5 text-[12.5px] text-saibyl-muted">
              {runs.length} rehearsed so far
            </p>
          )}
        </Hero>

        {/* ── The three moves ──
            Every branch of the load renders inside this chapter, so the hero is
            rendered once and only the body switches. A founder who is loading,
            errored or has nothing yet lands on the same page as everybody
            else. */}
        <Chapter
          kicker="Three kinds of move"
          title={
            <>
              Price, feature, <em>or a market you have not sold to</em>
            </>
          }
          lead="Pick the one you are weighing and write two things: what you sell today, and what you are proposing instead. Both go to the same room, so the only difference between them is the change itself."
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
                  headline="There is nothing here to change yet"
                  body="A rehearsal is a change to one thing you sell, so it is stored against it. Add what you are building and this fills in."
                  action={{ label: 'Add what you are building', href: '/app/products/new' }}
                />
              </Reveal>
            ) : (
              <>
                {products.length > 1 && (
                  <Reveal>
                    <div>
                      <label
                        htmlFor="grow-product"
                        className="block text-[12.5px] text-saibyl-silver mb-1.5"
                      >
                        Which one are you changing?
                      </label>
                      <select
                        id="grow-product"
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
                  <>
                    <Reveal step={1}>
                      <MoveCards productId={selected.id} />
                    </Reveal>

                    {/* Who the room is, straight from the registry that builds
                        it — arriving after the three cards. */}
                    {spec && (
                      <Reveal step={2}>
                        <RoomNote
                          inputs={spec.expected_inputs}
                          defendingShare={spec.default_adversarial_share}
                          rounds={spec.default_rounds}
                        />
                      </Reveal>
                    )}
                  </>
                )}
              </>
            )}
          </div>
        </Chapter>

        {/* ── What came back ── */}
        {selected && (
          <Chapter
            kicker="What came back"
            title={
              <>
                Every change you have <em>put in front of a room</em>
              </>
            }
            lead="Open one to read the argument that produced the number. Where the two did not separate it says so in the same weight as a win, because a change the room could not tell apart is an answer rather than an absence."
          >
            <div className="space-y-6">
              {runsError && (
                <Reveal>
                  <StageError message={runsError} retry={() => loadRuns(selected.id)} />
                </Reveal>
              )}

              <Reveal>
                <RehearsalList
                  key={selected.id}
                  productId={selected.id}
                  runs={runs}
                  settled={settled}
                />
              </Reveal>
            </div>
          </Chapter>
        )}

        {/* ── The honesty floor ──
            Last and unmissable rather than in a footnote: what this will not be
            able to tell you, in the server's own words — the same ones the
            finished write-up uses. Gated on the registry having said something,
            because `Limits` renders nothing for an empty list and a chapter
            heading with nothing under it is its own kind of broken page. */}
        {selected && spec && spec.cannot_conclude.length > 0 && (
          <Chapter
            kicker="The honesty floor"
            title={
              <>
                What a rehearsal <em>cannot tell you</em>
              </>
            }
            lead="Read before anything is charged, in the server's own sentences — the same ones the finished write-up says back to you afterwards."
          >
            <Reveal>
              <Limits items={spec.cannot_conclude} />
            </Reveal>
          </Chapter>
        )}
      </Longform>
    </Ground>
  );
}
