import { useEffect, useState } from 'react';

import api from '@/lib/api';
import { BENCHMARKS } from '@/lib/benchmarks';

/**
 * Why this is worth paying for, argued rather than asserted.
 *
 * A founder looking at $99 a month compares it to their other subscriptions.
 * The right comparison is not to a SaaS bill — it is to the campaign they are
 * about to run, and to the quarter they are about to spend positioned wrongly.
 * This block makes that comparison explicit.
 *
 * The three outside figures live in `lib/benchmarks.ts`, with the sourcing rule
 * they are held to and the two figures that were researched and rejected. The
 * landing page quotes the same three, and a second copy of an advertising claim
 * is the failure `LandingPage.tsx` already shipped once.
 */

interface RunPrice {
  credits: number;
  definition: string;
  usd_at_topup_rate: number | null;
}

export default function ValueCase() {
  /*
    The run price is read from `/billing/topup/options`, which is where the
    top-up rate lives. Deliberately **not** the serving cost: what a run costs
    us is internal, and a page asking a founder for money should quote the
    price they would actually pay at the rate this very page charges.
  */
  const [run, setRun] = useState<RunPrice | null>(null);

  useEffect(() => {
    let cancelled = false;
    api
      .get<{ standard_run?: RunPrice }>('/billing/topup/options')
      .then(({ data }) => {
        if (!cancelled) setRun(data.standard_run ?? null);
      })
      .catch(() => {
        // Absent, not guessed. The sentence that would have quoted a price is
        // dropped instead — inventing one on the billing page is the worst
        // place in the product to invent a number.
        if (!cancelled) setRun(null);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <section className="rounded-2xl border border-saibyl-border bg-white p-6">
      <h3 className="text-[17px] font-semibold text-saibyl-ink">
        What this is actually competing with
      </h3>
      <p className="text-[13px] text-saibyl-silver mt-1.5 leading-relaxed max-w-2xl">
        Not your other subscriptions. The campaign you are about to run, and the
        quarter you are about to spend saying the wrong thing to the right
        people.
      </p>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-3 mt-5">
        {BENCHMARKS.map((b) => (
          <div
            key={b.href + b.stat}
            className="rounded-xl border border-saibyl-border bg-saibyl-elevated p-4"
          >
            <p className="text-[24px] font-semibold text-saibyl-blue leading-none tabular-nums">
              {b.stat}
            </p>
            <p className="text-[12.5px] text-saibyl-silver mt-2 leading-relaxed">
              {b.claim}
            </p>
            {/* The source is shown, not footnoted. A statistic whose
                provenance a reader has to hunt for is one they are being asked
                to take on faith. */}
            <a
              href={b.href}
              target="_blank"
              rel="noreferrer noopener"
              className="block text-[11px] text-saibyl-muted mt-3 leading-relaxed hover:text-saibyl-blue transition-colors"
            >
              {b.provenance} ↗
            </a>
          </div>
        ))}
      </div>

      <div className="mt-5 rounded-xl border border-saibyl-blue/25 bg-saibyl-blue/[0.06] p-4">
        <p className="text-[13.5px] text-saibyl-ink leading-relaxed">
          Testing the message first is the cheapest thing in that list.
        </p>
        <p className="text-[12.5px] text-saibyl-silver mt-2 leading-relaxed max-w-2xl">
          {run && run.usd_at_topup_rate !== null ? (
            <>
              A full-size run &mdash; {run.definition} &mdash; costs you about{' '}
              <span className="text-saibyl-ink tabular-nums">
                ${run.usd_at_topup_rate.toFixed(2)}
              </span>{' '}
              and finishes in minutes. Set that against a campaign budget and
              the arithmetic is not close. The point is not that the run is
              cheap; it is that finding out in minutes costs a rounding error,
              and finding out in a quarter costs the quarter.
            </>
          ) : (
            /* The figure is absent rather than guessed. A made-up price on the
               page that is asking for money is the worst place to invent one. */
            <>
              A full-size run &mdash; 100 simulated buyers, five rounds, two
              places &mdash; finishes in minutes. Set that against a campaign
              budget and the arithmetic is not close: finding out in minutes
              costs a rounding error, and finding out in a quarter costs the
              quarter.
            </>
          )}
        </p>
      </div>

      <p className="text-[11px] text-saibyl-muted mt-4 leading-relaxed max-w-2xl">
        Saibyl does not run your campaign and does not promise it will work.
        What it does is tell you what a room of your buyers argues about before
        you have paid to find out, and show you the quote behind every number so
        you can disagree with it.
      </p>
    </section>
  );
}
