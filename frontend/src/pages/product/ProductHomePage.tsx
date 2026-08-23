import { useCallback, useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { Loader2, Plus } from 'lucide-react';

import api, { unwrapList } from '@/lib/api';
import { getErrorMessage } from '@/lib/errors';
import type { AttentionLine, ProductState } from '@/lib/stages';
import { EmptyState, StageError } from '@/components/stages/StagePrimitives';
import { Action, Card, Deal, Ground, PageHeader, Rise } from '@/components/design';

/**
 * Home leads with the product.
 *
 * One card per product, and the card carries the attention. A founder with one
 * product sees one card and knows exactly what to do next; a founder with four
 * sees which one has gone cold.
 *
 * **Nothing on a card is invented to fill it.** Every attention line comes from
 * a row the server read — a completed run, an unresolved comparison, a stale
 * candidate list, a document still being read. A product with nothing to report
 * says so and offers the next step, because a card padded with filler teaches a
 * founder to stop reading the cards.
 *
 * ---
 *
 * **This was the worst-looking screen in the app, and the reasons were
 * mechanical rather than aesthetic.** The founder's word for it, on
 * 2026-08-23, was "sterile". Four things were wrong and all four are fixed
 * here:
 *
 * 1. It painted `bg-saibyl-void` on its own root — a flat `#f8fbff` laid
 *    *over* the radial wash `<body>` carries. Canvas rule 1, actively undone
 *    by the one page every founder lands on first.
 * 2. Every colour it used was a **legacy dark-theme alias** — `saibyl-white`,
 *    `saibyl-platinum`, `saibyl-void`, `saibyl-gold`. Those names still
 *    resolve, because the token file remapped them to light values when the
 *    theme flipped, so the page kept rendering and nobody noticed it had never
 *    been converted. It read as ink on paper and was never *designed* as ink
 *    on paper.
 * 3. Its cards were `.glass` with no depth class, so nothing on the screen
 *    claimed to matter more than anything else on it.
 * 4. No eyebrow, no accent phrase, no arrival motion. The four rules had
 *    simply never been applied here.
 */

function Attention({ line, productId }: { line: AttentionLine; productId: string }) {
  const body = (
    <>
      {/* The dot carries the weight, and it is the artboard's own pair: the
          blue that means "this is the live thing" against the amber that means
          "this will still run, and thinner". Both were `bg-saibyl-gold` and a
          70%-opacity warning before — two greys apart at a glance. */}
      <span
        className={`mt-[0.42rem] w-[7px] h-[7px] rounded-full shrink-0 ${
          line.weight === 'high'
            ? 'bg-saibyl-blue shadow-[0_0_0_4px_rgba(40,108,240,0.12)]'
            : 'bg-[#b45309] shadow-[0_0_0_4px_rgba(180,83,9,0.10)]'
        }`}
      />
      <span
        className={`text-[12.5px] leading-relaxed ${
          line.weight === 'high' ? 'text-saibyl-ink' : 'text-saibyl-silver'
        }`}
      >
        {line.text}
      </span>
    </>
  );

  if (!line.href) {
    return <div className="flex items-start gap-2">{body}</div>;
  }
  return (
    <Link
      to={line.href}
      key={`${productId}-${line.kind}`}
      className="flex items-start gap-2 hover:opacity-80 transition-opacity"
    >
      {body}
    </Link>
  );
}

function ProductCard({ product }: { product: ProductState }) {
  /*
    The next thing to do: the earliest step, in rail order, that has produced
    nothing yet.

    Blocked-first was the obvious rule and it was wrong. A product with a
    confirmed audience and no run offered "3. Answers", because Answers is
    blocked — but it is blocked *precisely because* step 2 has not run, so
    naming it sends the founder to the screen that tells them to go back. The
    earliest unproduced step is the one that unblocks whatever is behind it.

    When every step has produced something there is nothing outstanding, so the
    card offers the last one — Messages, which is the step a founder returns to
    before every campaign.
  */
  const nextStep =
    product.stages.find((s) => s.produced === null) ??
    product.stages[product.stages.length - 1];

  return (
    /* `meaning`, and it lifts. A product card is a claim a founder has to
       weigh — what has changed here, and is it the one to open — and it goes
       somewhere, which is the only condition under which the artboard's hover
       rise is honest. */
    <Card carries="meaning" lift className="p-6">
      <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
        <Link
          /* The product's own URL. Its index route decides which step to open
             on, so the choice lives in one place instead of in every link that
             points at a product. */
          to={`/app/products/${product.id}`}
          className="text-[18px] font-semibold text-saibyl-ink hover:text-saibyl-blue transition-colors"
        >
          {product.name}
        </Link>
        {/* Category metadata, not a link — mono silver so blue stays spent on
            actions only. */}
        <span className="font-mono text-[11px] text-saibyl-silver">
          {product.moment.label}
          {product.moment.source === 'default' && (
            <span className="text-saibyl-muted"> · not set yet</span>
          )}
        </span>
        <span className="text-[12px] text-saibyl-muted">
          {product.stages_ready} of {product.stages.length} steps have what they need
        </span>
      </div>

      {product.description && (
        <p className="text-[12.5px] text-saibyl-muted mt-1.5 leading-relaxed">
          {product.description}
        </p>
      )}

      <div className="mt-4 pt-4 border-t border-saibyl-border">
        {product.attention.length > 0 ? (
          <div className="space-y-2">
            {product.attention.map((line) => (
              <Attention
                key={`${line.kind}-${line.text}`}
                line={line}
                productId={product.id}
              />
            ))}
          </div>
        ) : (
          /* Nothing has happened here yet, and saying so is more useful than a
             row of zeroes. The offer is the next real step, not a generic CTA. */
          <p className="text-[12.5px] text-saibyl-muted leading-relaxed">
            Nothing to report yet.
          </p>
        )}

        {/* `quiet`, not `primary`. There is one of these per card, and on a
            page with four products four gradient buttons would each be
            shouting that they are the thing to do next. The one gradient on
            this screen is "New product", in the header. */}
        <Action as={Link} to={nextStep.href} kind="quiet" className="mt-4">
          {nextStep.number}. {nextStep.label} &mdash; {nextStep.blurb}
        </Action>
      </div>
    </Card>
  );
}

export default function ProductHomePage() {
  const [products, setProducts] = useState<ProductState[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  const load = useCallback(() => {
    api
      .get('/products')
      .then((r) => {
        setProducts(unwrapList<ProductState>(r.data).items);
        setError('');
      })
      .catch((err) =>
        setError(getErrorMessage(err, 'We could not load your products.')),
      )
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  /* Retrying is a click, so it says so. `load` itself never sets this: an
     effect that sets state synchronously on mount is a cascading render, and
     `loading` already starts true. */
  const retry = useCallback(() => {
    setLoading(true);
    load();
  }, [load]);


  return (
    /* `Ground`, not `bg-saibyl-void`. The old root painted a flat `#f8fbff`
       panel across the whole page, on top of the radial wash `<body>` already
       carries — so the first screen every founder sees was the one screen with
       canvas rule 1 switched off. */
    <Ground className="p-6 lg:p-8 min-h-full">
      <div className="max-w-4xl mx-auto">
        <Rise className="flex flex-wrap items-end justify-between gap-4 mb-7">
          <PageHeader
            eyebrow="Your workspace"
            title="Your products"
            phrase="One product, five steps, in the order each one feeds the next."
          >
            <p>
              Everything you are building lives here, and each one carries its
              own audience, its own objections and its own buyer list. A card
              tells you what has changed since you last looked and what the
              next step is &mdash; never a row of zeroes, because a card padded
              with filler teaches you to stop reading the cards.
            </p>
          </PageHeader>
          {/* The one gradient on this screen. There is exactly one thing a
              founder can do here that is not "open something that already
              exists", and the artboard says that thing is never a flat fill. */}
          <Action as={Link} to="/app/products/new" className="shrink-0">
            <Plus className="w-4 h-4" />
            New product
          </Action>
        </Rise>

        {error && (
          <div className="mb-5">
            <StageError message={error} retry={retry} />
          </div>
        )}

        {loading && products.length === 0 ? (
          <div className="flex items-center gap-2.5 text-saibyl-muted text-[13px]">
            <Loader2 className="w-4 h-4 animate-spin" />
            Loading…
          </div>
        ) : products.length === 0 && !error ? (
          <EmptyState
            headline="Nothing here yet"
            body="A product is whatever you are trying to sell. Add one, upload the deck or the landing page, and we will work out who buys it."
            action={{ label: 'Add your first product', href: '/app/products/new' }}
          />
        ) : (
          <div className="space-y-4">
            {/* Dealt, at the artboard's 70ms — the same arrival the rail has,
                because this list is the rail's equivalent on a page that shows
                several products rather than one. Capped inside `dealDelayMs`,
                so a founder with thirty products does not wait for the tail. */}
            {products.map((product, i) => (
              <Deal key={product.id} index={i}>
                <ProductCard product={product} />
              </Deal>
            ))}
          </div>
        )}
      </div>
    </Ground>
  );
}
