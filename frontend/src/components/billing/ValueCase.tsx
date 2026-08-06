import { useEffect, useState } from 'react';

import api from '@/lib/api';

/**
 * Why this is worth paying for, argued rather than asserted.
 *
 * A founder looking at $99 a month compares it to their other subscriptions.
 * The right comparison is not to a SaaS bill — it is to the campaign they are
 * about to run, and to the quarter they are about to spend positioned wrongly.
 * This block makes that comparison explicit.
 *
 * ────────────────────────────────────────────────────────────────────────────
 * **Every external number on this page has a primary source, linked, with its
 * methodology and date stated.** That rule is not decoration. This is an
 * advertising surface, the codebase has already shipped a 1,000x overstatement
 * on one of those, and a marketing statistic is the easiest place in a product
 * to launder a guess into a fact.
 *
 * Two figures were researched and **deliberately not used**:
 *
 *  - "37% of digital ad budgets produce no measurable business impact,
 *    attributed to Forrester." It appears only in vendor blogs. No Forrester
 *    publication carrying it could be found, so it is not a citation, it is a
 *    rumour with a brand name attached.
 *  - Forrester's real, findable figure — $7.4bn lost to fraudulent or
 *    unviewable display inventory — is from **2016** and states no methodology.
 *    Ten years stale is not a current claim.
 *
 * If a figure below cannot be re-verified at its link, delete it. Do not
 * replace it with one that "sounds about right".
 * ────────────────────────────────────────────────────────────────────────────
 */

interface Benchmark {
  stat: string;
  claim: string;
  /** Who published it, over what sample, and when. Shown, not just held. */
  provenance: string;
  href: string;
}

const BENCHMARKS: Benchmark[] = [
  {
    stat: '43%',
    claim:
      'of startups that shut down cite poor product-market fit — the second most common reason after running out of money, which the same study calls the final cause rather than the root one.',
    provenance:
      'CB Insights, analysis of 431 VC-backed companies that shut down since 2023 (385 with a stated reason)',
    href: 'https://www.cbinsights.com/research/report/startup-failure-reasons-top/',
  },
  {
    stat: '$26.8bn',
    claim:
      'in global media value is lost every year to programmatic inefficiency — before anyone has read a word of your message.',
    provenance:
      'Association of National Advertisers, Q2 2025 Programmatic Transparency Benchmark',
    href: 'https://www.ana.net/content/show/id/pr-2025-08-programmatictrans',
  },
  {
    stat: '56.7%',
    claim:
      'is the share of programmatic spend that reaches a qualified impression even for advertisers running disciplined quality controls. The rest of the budget is spent before the message is tested at all.',
    provenance:
      'Association of National Advertisers, Q4 2025 Programmatic Transparency Benchmark',
    href: 'https://www.ana.net/content/show/id/pr-2026-02-programatic',
  },
];

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
    <section className="rounded-2xl border border-white/[0.08] bg-white/[0.02] p-6">
      <h3 className="text-[17px] font-semibold text-[#E8ECF2]">
        What this is actually competing with
      </h3>
      <p className="text-[13px] text-[#8B97A8] mt-1.5 leading-relaxed max-w-2xl">
        Not your other subscriptions. The campaign you are about to run, and the
        quarter you are about to spend saying the wrong thing to the right
        people.
      </p>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-3 mt-5">
        {BENCHMARKS.map((b) => (
          <div
            key={b.href + b.stat}
            className="rounded-xl border border-white/[0.06] bg-white/[0.02] p-4"
          >
            <p className="text-[24px] font-semibold text-[#C9A227] leading-none">
              {b.stat}
            </p>
            <p className="text-[12.5px] text-[#C6D0DE] mt-2 leading-relaxed">
              {b.claim}
            </p>
            {/* The source is shown, not footnoted. A statistic whose
                provenance a reader has to hunt for is one they are being asked
                to take on faith. */}
            <a
              href={b.href}
              target="_blank"
              rel="noreferrer noopener"
              className="block text-[11px] text-[#8B97A8] mt-3 leading-relaxed hover:text-[#C9A227] transition-colors"
            >
              {b.provenance} &nearr;
            </a>
          </div>
        ))}
      </div>

      <div className="mt-5 rounded-xl border border-[#C9A227]/25 bg-[#C9A227]/[0.06] p-4">
        <p className="text-[13.5px] text-[#E8ECF2] leading-relaxed">
          Testing the message first is the cheapest thing in that list.
        </p>
        <p className="text-[12.5px] text-[#8B97A8] mt-2 leading-relaxed max-w-2xl">
          {run && run.usd_at_topup_rate !== null ? (
            <>
              A full-size run &mdash; {run.definition} &mdash; costs you about{' '}
              <span className="text-[#C6D0DE]">
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

      <p className="text-[11px] text-[#5A6578] mt-4 leading-relaxed max-w-2xl">
        Saibyl does not run your campaign and does not promise it will work.
        What it does is tell you what a room of your buyers argues about before
        you have paid to find out, and show you the quote behind every number so
        you can disagree with it.
      </p>
    </section>
  );
}
