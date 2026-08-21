import { Link } from 'react-router-dom';
import { ArrowRight, ShieldCheck, Globe } from 'lucide-react';

import PriceTag from '@/components/billing/PriceTag';
import { usePrices } from '@/lib/prices';

/**
 * The two questions a finished evaluation raises and cannot answer.
 *
 * The free evaluation is the loss leader: a founder brings an idea, a room of
 * buyers argues about it, and they leave knowing what will be objected to.
 * The checks that follow — is this already owned, does my page say any of this
 * — are what they pay for, and they are the point at which the product stops
 * being interesting and starts being worth money.
 *
 * Until this existed there was no bridge between the two halves. Nothing in
 * the app linked to the USPTO check except the sidebar, and no surface
 * anywhere after a run said the words patent or trademark. The founder read
 * their objections and was offered nothing, at exactly the moment they are
 * asking themselves whether the idea is theirs to build.
 *
 * It states prices rather than hiding them (`PriceTag`), because a paywall a
 * founder walks into is worse than one they can see coming — and because the
 * argument for paying is strongest right here, next to the evidence that the
 * free half was real.
 */
export default function WhatNext({ productId }: { productId?: string | null }) {
  const prices = usePrices();

  return (
    <section className="mt-8 rounded-2xl border border-saibyl-border bg-white p-6">
      <p className="font-mono text-[10px] uppercase tracking-[0.16em] text-saibyl-muted">
        After this run
      </p>
      <h2 className="text-h2 text-saibyl-ink mt-1.5">
        Two things this room could not tell you
      </h2>
      <p className="text-[13px] text-saibyl-silver mt-2 max-w-2xl leading-relaxed">
        The buyers argued about your idea and told you where it loses them.
        They could not tell you whether somebody already owns it, or whether
        the page a stranger lands on says any of what you just read.
      </p>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mt-5">
        <div className="rounded-xl border border-saibyl-border bg-saibyl-elevated p-5 flex flex-col">
          <ShieldCheck className="w-5 h-5 text-saibyl-blue" />
          <h3 className="text-[15px] font-semibold text-saibyl-ink mt-3">
            Is this already someone else&rsquo;s?
          </h3>
          <p className="text-[12.5px] text-saibyl-silver mt-1.5 leading-relaxed flex-1">
            We search the USPTO &mdash; trademarks, granted patents, and what is
            still pending &mdash; and name what stands closest to your idea,
            with the filing attached. Finding out now costs a search. Finding
            out after you build costs the build.
          </p>
          <div className="mt-3">
            <PriceTag entry={prices?.clearance?.STANDARD} />
          </div>
          <Link
            to="/app/ip-check"
            className="inline-flex items-center gap-1.5 mt-3 px-4 py-2 rounded-xl bg-saibyl-blue text-white font-semibold text-[12.5px] hover:bg-saibyl-gold-hover transition-colors self-start"
          >
            Check who owns it
            <ArrowRight className="w-3.5 h-3.5" />
          </Link>
        </div>

        <div className="rounded-xl border border-saibyl-border bg-saibyl-elevated p-5 flex flex-col">
          <Globe className="w-5 h-5 text-saibyl-blue" />
          <h3 className="text-[15px] font-semibold text-saibyl-ink mt-3">
            Does your page land the way this pitch did?
          </h3>
          <p className="text-[12.5px] text-saibyl-silver mt-1.5 leading-relaxed flex-1">
            We load your site the way a buyer&rsquo;s browser would and judge
            what a stranger actually takes away &mdash; then show you the gap,
            one named element at a time.
          </p>
          <div className="mt-3">
            <PriceTag entry={prices?.website_check} />
          </div>
          {/* The site check lives on the product's first step, where the page's
              own words become material the room can read. Without a product to
              attach it to there is nowhere honest to send them, so the card
              states the offer and stops rather than linking into a dead end. */}
          {productId ? (
            <Link
              to={`/app/products/${productId}/audience`}
              className="inline-flex items-center gap-1.5 mt-3 px-4 py-2 rounded-xl bg-saibyl-blue text-white font-semibold text-[12.5px] hover:bg-saibyl-gold-hover transition-colors self-start"
            >
              Read my page
              <ArrowRight className="w-3.5 h-3.5" />
            </Link>
          ) : (
            <p className="text-[12px] text-saibyl-muted mt-3">
              Open this from one of your products to point it at a page.
            </p>
          )}
        </div>
      </div>
    </section>
  );
}
