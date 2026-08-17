import { useCallback, useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { Loader2, Plus } from 'lucide-react';

import api, { unwrapList } from '@/lib/api';
import { getErrorMessage } from '@/lib/errors';
import type { AttentionLine, ProductState } from '@/lib/stages';
import { EmptyState, StageError } from '@/components/stages/StagePrimitives';

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
 */

function Attention({ line, productId }: { line: AttentionLine; productId: string }) {
  const body = (
    <>
      <span
        className={`mt-[0.42rem] w-1.5 h-1.5 rounded-full shrink-0 ${
          line.weight === 'high' ? 'bg-saibyl-gold' : 'bg-[#14294a]/20'
        }`}
      />
      <span
        className={`text-[12.5px] leading-relaxed ${
          line.weight === 'high' ? 'text-saibyl-platinum' : 'text-saibyl-muted'
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
    <div className="glass rounded-2xl p-6">
      <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
        <Link
          /* The product's own URL. Its index route decides which step to open
             on, so the choice lives in one place instead of in every link that
             points at a product. */
          to={`/app/products/${product.id}`}
          className="text-[18px] font-medium text-saibyl-white hover:text-saibyl-gold transition-colors"
        >
          {product.name}
        </Link>
        <span className="text-[12px] text-saibyl-gold">
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

        <Link
          to={nextStep.href}
          className="inline-flex items-center gap-1.5 mt-4 px-4 py-1.5 rounded-lg border border-saibyl-border-light text-[12.5px] text-saibyl-platinum hover:bg-[#14294a]/[0.04] transition-colors"
        >
          {nextStep.number}. {nextStep.label} — {nextStep.blurb}
        </Link>
      </div>
    </div>
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
    <div className="p-6 lg:p-8 bg-saibyl-void min-h-full">
      <div className="max-w-4xl mx-auto">
        <div className="flex flex-wrap items-center justify-between gap-3 mb-6">
          <div>
            <h1 className="text-h1 text-saibyl-white">Your products</h1>
            <p className="text-[13px] text-saibyl-muted mt-1">
              Each one carries its own audience, its own objections and its own
              buyer list.
            </p>
          </div>
          <Link
            to="/app/products/new"
            className="inline-flex items-center gap-1.5 px-4 py-2 rounded-xl bg-saibyl-gold text-saibyl-void font-semibold text-[13px] hover:bg-saibyl-gold-hover transition-colors"
          >
            <Plus className="w-4 h-4" />
            New product
          </Link>
        </div>

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
            {products.map((product) => (
              <ProductCard key={product.id} product={product} />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
