/**
 * ⚠ EVERY NUMBER IN THIS FILE IS AN ADVERTISED CLAIM.
 *
 * This is the **only** place the landing page writes a tier number. It used to
 * be four separate arrays in `LandingPage.tsx` — a features grid, a hero stats
 * bar, a pricing block and an enterprise footnote — and they drifted apart
 * exactly as you would expect: the pricing block was corrected to the enforced
 * caps while a "1M agents" card sat two sections above it, unnoticed, for
 * months. A claim duplicated across four surfaces gets fixed on one.
 *
 * ── SOURCE OF TRUTH ────────────────────────────────────────────────────────
 * `backend/app/services/billing/agent_pricing.py`
 *
 *   TIER_CAPS            line 134   the run shape a tier may configure
 *   TIER_CREDIT_GRANTS   line 106   the monthly credit grant
 *   MAX_RUNNABLE_VARIANTS line 162  clamps `max_variants`; every tier is <= 8,
 *                                   so no `messages` figure below is clamped
 *
 * The values are transcribed rather than imported because this page renders
 * before auth and has no org to ask. **That makes this comment the only thing
 * keeping them honest.** If you change `TIER_CAPS` or `TIER_CREDIT_GRANTS`,
 * change this file in the same commit.
 *
 * ── WHERE THE PRICES COME FROM ─────────────────────────────────────────────
 * The dollar prices are not free-floating marketing numbers. Each one is the
 * retail price of its tier's monthly grant, priced at `TARGET_MARGIN_PCT` in
 * agent_pricing.py — open that file and the three prices below fall out of
 * `TIER_CREDIT_GRANTS` and `CREDITS_PER_USD` arithmetically. Do not move a
 * price here without moving the grant it is derived from.
 *
 * ── WHAT IS DELIBERATELY NOT HERE ──────────────────────────────────────────
 * A **runs-per-month figure.** A run's cost varies by more than an order of
 * magnitude across these shapes, so "N runs" is not a property of a plan and
 * PRICING_GUIDE.md §1.3 forbids printing one without the reference shape it was
 * quoted against. The Run Configurator prices each run before it starts; that
 * is the honest answer and it is the one the page gives.
 *
 * A **credit-to-dollar conversion.** Credits are what a customer's balance
 * reads in the app, which is why the grants are shown. The rate underneath them
 * is the serving-cost model and is internal.
 */

/** A run shape, in the words a founder uses rather than the ones the API does. */
export interface RunShape {
  /** `max_agents` — people in the room. */
  people: number;
  /** `max_rounds` — passes of back-and-forth. */
  rounds: number;
  /** `max_platforms` — where it happens. */
  places: number;
  /** `max_variants` — versions of a message run against the same people. */
  messages: number;
}

export interface Tier {
  id: string;
  name: string;
  price: string;
  /** Empty for a one-off grant, so nothing renders a stray "/mo". */
  period: string;
  blurb: string;
  /** Monthly credit grant, already formatted. */
  credits: string;
  creditsNote: string;
  shape: RunShape;
  cta: string;
  ctaTo: string;
  /** The plan the page pushes. This is Free, on purpose — the free run is the
   *  call to action, so it gets the emphasis everywhere including here. */
  featured: boolean;
}

export const TIERS: readonly Tier[] = [
  {
    id: 'free',
    name: 'Free',
    price: '$0',
    period: '',
    blurb: 'One full run, to see whether any of this is worth paying for.',
    // TIER_CREDIT_GRANTS["free"] = 1_500 (agent_pricing.py:107). Sized to cover
    // exactly one free-shape run that carries uploaded material, and pinned by
    // `test_the_free_grant_covers_one_free_run`.
    credits: '1,500',
    creditsNote: 'credits, once, at signup',
    // TIER_CAPS["free"] (agent_pricing.py:135)
    shape: { people: 25, rounds: 3, places: 2, messages: 1 },
    cta: 'Start a free run',
    ctaTo: '/signup',
    featured: true,
  },
  {
    id: 'founder',
    name: 'Founder',
    price: '$99',
    period: '/mo',
    blurb: 'For one founder working out whether the thing they’re building sells.',
    // TIER_CREDIT_GRANTS["founder"] = 19_800 (agent_pricing.py:109)
    credits: '19,800',
    creditsNote: 'credits a month',
    // TIER_CAPS["founder"] (agent_pricing.py:137)
    shape: { people: 100, rounds: 8, places: 3, messages: 3 },
    cta: 'Start free, upgrade later',
    ctaTo: '/signup',
    featured: false,
  },
  {
    id: 'growth',
    name: 'Growth',
    price: '$299',
    period: '/mo',
    blurb: 'For a team testing messages before it spends money running them.',
    // TIER_CREDIT_GRANTS["growth"] = 59_800 (agent_pricing.py:111)
    credits: '59,800',
    creditsNote: 'credits a month',
    // TIER_CAPS["growth"] (agent_pricing.py:139)
    shape: { people: 150, rounds: 10, places: 4, messages: 5 },
    cta: 'Start free, upgrade later',
    ctaTo: '/signup',
    featured: false,
  },
  {
    id: 'agency',
    name: 'Agency',
    price: '$999',
    period: '/mo',
    blurb: 'For a shop running this across several clients at once.',
    // TIER_CREDIT_GRANTS["agency"] = 199_800 (agent_pricing.py:113)
    credits: '199,800',
    creditsNote: 'credits a month',
    // TIER_CAPS["agency"] (agent_pricing.py:141)
    shape: { people: 250, rounds: 12, places: 6, messages: 8 },
    cta: 'Start free, upgrade later',
    ctaTo: '/signup',
    featured: false,
  },
];

/**
 * TIER_CAPS["enterprise"] (agent_pricing.py:142).
 *
 * A footnote rather than a card. It is a real enforced cap, so it can be
 * stated — but it is not a plan a founder self-serves onto, and giving it a
 * column pulls the page's emphasis away from the free run.
 */
export const ENTERPRISE_SHAPE: RunShape = {
  people: 1_000,
  rounds: 20,
  places: 12,
  messages: 8,
};

export const CONTACT_EMAIL = 'info@saidolabs.com';

/**
 * The places a run can happen.
 *
 * One entry per adapter module in `backend/app/services/platforms/adapters/`.
 * Twelve of them, which is where `ENTERPRISE_SHAPE.places` gets its ceiling —
 * the two numbers are the same fact and must move together. "One you define"
 * is `custom.py`.
 */
export const PLACES: readonly string[] = [
  'Reddit',
  'X',
  'Hacker News',
  'LinkedIn',
  'YouTube',
  'TikTok',
  'Instagram',
  'Facebook',
  'Threads',
  'Discord',
  'news comment sections',
  'or one you define',
];

/** The run shape as sentence fragments, so a shape reads the same everywhere. */
export function shapeLines(shape: RunShape): string[] {
  return [
    `Up to ${shape.people.toLocaleString()} people in the room`,
    `Up to ${shape.rounds} rounds of back-and-forth`,
    shape.places === 1 ? 'One place per run' : `Up to ${shape.places} places at once`,
    shape.messages === 1
      ? 'One message per run'
      : `${shape.messages} versions of a message, head to head`,
  ];
}
