/**
 * The three outside numbers this product is allowed to quote.
 *
 * **Every external number here has a primary source, linked, with its
 * methodology and date stated.** That rule is not decoration. These render on
 * advertising surfaces, this codebase has already shipped a 1,000x
 * overstatement on one of those, and a marketing statistic is the easiest place
 * in a product to launder a guess into a fact.
 *
 * In `lib/` because two surfaces quote them — the landing page's argument for
 * why testing a message first is cheap, and `components/billing/ValueCase.tsx`
 * on the page that asks for money. They were declared inside `ValueCase` when
 * only that page needed them; a second copy on the landing page would be the
 * same shape as the four tier arrays that drifted apart in `LandingPage.tsx`
 * and left a "1M agents" card standing for months. A claim duplicated across
 * two surfaces gets corrected on one.
 *
 * ── TWO FIGURES RESEARCHED AND DELIBERATELY NOT USED ───────────────────────
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
 */

export interface Benchmark {
  stat: string;
  claim: string;
  /** Who published it, over what sample, and when. Shown, not just held. */
  provenance: string;
  href: string;
  /** A three-word version for the landing page, where the card is narrower. */
  short: string;
}

export const BENCHMARKS: readonly Benchmark[] = [
  {
    stat: '43%',
    short: 'die of the wrong message',
    claim:
      'of startups that shut down cite poor product-market fit — the second most common reason after running out of money, which the same study calls the final cause rather than the root one.',
    provenance:
      'CB Insights, analysis of 431 VC-backed companies that shut down since 2023 (385 with a stated reason)',
    href: 'https://www.cbinsights.com/research/report/startup-failure-reasons-top/',
  },
  {
    stat: '$26.8bn',
    short: 'lost before anyone reads it',
    claim:
      'in global media value is lost every year to programmatic inefficiency — before anyone has read a word of your message.',
    provenance:
      'Association of National Advertisers, Q2 2025 Programmatic Transparency Benchmark',
    href: 'https://www.ana.net/content/show/id/pr-2025-08-programmatictrans',
  },
  {
    stat: '56.7%',
    short: 'reaches a real person',
    claim:
      'is the share of programmatic spend that reaches a qualified impression even for advertisers running disciplined quality controls. The rest of the budget is spent before the message is tested at all.',
    provenance:
      'Association of National Advertisers, Q4 2025 Programmatic Transparency Benchmark',
    href: 'https://www.ana.net/content/show/id/pr-2026-02-programatic',
  },
];
