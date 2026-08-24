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
import { Chapter, Ground, Hero, Longform, Reveal } from '@/components/design';

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
 * themselves. `NO_CONTACT_DETAILS` says so in the hero, above everything it is
 * a promise about, and `ShortlistPanel` says it again beside the button that
 * spends credits. Both renders are deliberate.
 *
 * ---
 *
 * **The shape, 2026-08-23: this page is a landing page.**
 *
 * The founder read the app against the public site and called it "very sterile,
 * mechanical, and looks AI-generated"; the instruction was to treat every page
 * behind the login the way the landing page treats itself — a hero, large type,
 * then scroll, with the content arriving as you reach it. `GuidePage` is the
 * approved example and this follows its shape: `Longform` owns the measure and
 * runs the reveal observer, `Hero` opens, one `Chapter` per section.
 *
 * What is *inside* a chapter did not change. `ShortlistPanel` and `BankPanel`
 * still style from `capital.css` at exactly the density they had — the canvas's
 * density constraint is about those, and it still holds. The frame around them
 * is what grew.
 *
 * **One trap, and it is the reason the panels are not wrapped in `Reveal`.**
 * `useReveal` collects its targets once, in a mount effect, and never looks
 * again. A `Reveal` that mounts *after* a fetch resolves is therefore never
 * observed and never gets `is-visible` — it stays at `opacity: 0` forever, and
 * the 2.5s fallback does not save it either, because that iterates the same
 * captured list. So `Reveal` is used here only around markup that exists on the
 * first render; everything the API fills in keeps the arrival motion it already
 * had (`capital-arrive` inside the bank). See the report at the bottom of this
 * change — the hook is shared code and not this page's to fix.
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
    /* The shared wash, not `capital-ground`. Both are the landing page's two
       radial washes — `capital.css` ported them here before the app-wide
       system existed — and one of the two copies had to go. */
    <Ground className="min-h-full pb-24">
      <Longform>
        {/* The hero is never wrapped in `Reveal`: it is the first screen, and a
            page whose opening fades in looks broken for 700ms. */}
        <Hero
          eyebrow="Fundraise"
          title="Know the questions"
          serif="before the meeting."
        >
          <p>
            Investors ask the questions your buyers already asked, in a harder
            register and with far less patience. This is where you see both
            halves before the meeting: which firms actually fit what you are
            building &mdash; matched on your sector, your stage and the
            objections real buyers raised &mdash; and how your story reads to
            them. A firm whose published position rules you out is reported
            saying so, because a short list you can trust is worth more than a
            long one you cannot.{' '}
            <b className="text-saibyl-ink font-semibold">
              How does the story read? Who would fund it? What will they ask?
            </b>
          </p>
          {/* The promise about what Saibyl does not hold, above everything it
              is a promise about. It is not a disclaimer — it is the reason the
              recommendation is worth reading, and the reason there is no
              "send" button anywhere on this page. */}
          <p className="mt-4 text-[12.5px] leading-relaxed">{NO_CONTACT_DETAILS}</p>
        </Hero>

        {/* ── Which product this answer is for ──
            No `Reveal` around this body: every branch in it arrives from a
            fetch, and a `Reveal` that mounts late is never observed. */}
        <Chapter
          kicker="The one you are raising for"
          title={
            <>
              Every shortlist is stored <em>against one thing</em>
            </>
          }
          lead="A match is built from what Saibyl already measured about a single product, so it is kept with that product and can be rebuilt when the evidence changes."
        >
          {productsError && (
            <div className="mb-4">
              <StageError message={productsError} retry={loadProducts} />
            </div>
          )}

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
          ) : products.length > 1 ? (
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
          ) : (
            /* One product, so there is nothing to choose between — but the
               chapter still has to say what the answer below is about, or a
               founder reads a shortlist without knowing what it was matched
               against. The picker itself renders on exactly the same condition
               it did before: more than one product. */
            selected && (
              <p className="text-[12.5px] text-saibyl-muted leading-relaxed">
                Everything below is matched against{' '}
                <b className="text-saibyl-ink font-semibold">{selected.name}</b>.
                Add another and a picker appears here.
              </p>
            )
          )}
        </Chapter>

        {/* ── The shortlist ── */}
        <Chapter
          kicker="The shortlist"
          title={
            <>
              Who would <em>fund this one</em>
            </>
          }
          lead="Twenty firms you can check beat five thousand you cannot. One whose published position rules you out is reported saying so, quoting the words it published."
        >
          {selected ? (
            <ShortlistPanel
              key={selected.id}
              product={{ id: selected.id, name: selected.name }}
              runId={runId}
              bankCurrent={unfiltered ? unfiltered.firms.length : null}
              bankWithheld={unfiltered ? unfiltered.withheld_stale.length : 0}
              now={now}
            />
          ) : productsLoading ? null : (
            <p className="text-[12.5px] text-saibyl-muted leading-relaxed">
              This fills in once there is something here to raise for.
            </p>
          )}
        </Chapter>

        {/* ── The bank the match reads from ──
            `BankPanel` renders its own heading and filters on the first pass,
            so this one body is safe to reveal: the element exists when the
            observer goes looking for it. */}
        <Chapter
          kicker="Before you pay for a match"
          title={
            <>
              Read the bank <em>for yourself</em>
            </>
          }
          lead="The match is what costs credits; reading what it will match against costs nothing. What is current, what is withheld past the date we would stand behind it, and what is flagged as unreadable are all counted in the open."
        >
          <Reveal>
            <BankPanel
              bank={bank}
              filters={filters}
              onFilters={setFilters}
              loading={bankLoading}
              error={bankError}
              onRetry={() => loadBank(filters)}
              now={now}
            />
          </Reveal>
        </Chapter>
      </Longform>
    </Ground>
  );
}
