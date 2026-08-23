/**
 * The two design decisions that must not be re-made at a call site.
 *
 * They live in a plain module rather than inside the components so they can be
 * asserted directly — `test/design_primitives.test.ts` calls these functions,
 * which is a stronger check than reading the JSX and hoping.
 */

/* ------------------------------------------------------------------ */
/*  What a card carries, and therefore whether it has depth            */
/* ------------------------------------------------------------------ */

/**
 * What this card *is* — which is what decides whether it gets a shadow.
 *
 * The canvas says: "Soft blue shadows on cards that carry meaning — hairlines
 * stay on dense lists." That is a rule about content, not about looks, so the
 * prop names the content and the system derives the look:
 *
 *   `stage`    the one panel this screen is about. The deepest shadow, once
 *              per screen. Two of these on a page and neither is the subject.
 *   `meaning`  a card carrying a claim a founder has to weigh — a firm, a
 *              report, an objection. Soft blue shadow.
 *   `density`  a row in a dense list, or a step in the rail. Hairline only.
 *              Shadow every row and the page turns to soup.
 *
 * Naming it `elevation` or `variant` would have handed the call site a look to
 * pick from, and a call site picking a look is exactly how "shadows mean
 * something" stops being true by the fourth page.
 */
export type CardCarries = 'stage' | 'meaning' | 'density';

/**
 * Border, radius, ground and depth for each kind of card.
 *
 * No padding. The canvas's density constraint is explicit — "same type sizes,
 * same 13px body, same row rhythm" — and the fastest way to break it app-wide
 * would be a shared card that re-pads every call site it touches. Padding stays
 * where it already is, in the caller's own className.
 *
 * The backgrounds are defaults, not decisions: these strings go through
 * `twMerge`, so a caller passing `bg-saibyl-blue/[0.07]` for an active step
 * replaces the white rather than layering over it.
 */
const SURFACE: Record<CardCarries, string> = {
  stage:
    'sb-stage rounded-[20px] border border-saibyl-border bg-white/[0.72] backdrop-blur-[18px]',
  meaning: 'sb-meaning rounded-2xl border border-saibyl-border bg-white',
  /* Deliberately no `sb-*` depth class. The absence is the rule. */
  density: 'rounded-2xl border border-saibyl-border bg-white',
};

/** The classes a card of this kind wears. See {@link CardCarries}. */
export function cardSurface(carries: CardCarries): string {
  return SURFACE[carries];
}

/* ------------------------------------------------------------------ */
/*  The deal                                                           */
/* ------------------------------------------------------------------ */

/**
 * The gap between two dealt items, in milliseconds.
 *
 * The artboard's own number: `(n - 1) * 0.07s`. Fast enough not to be a wait,
 * slow enough to read as a sequence rather than a flicker.
 */
export const DEAL_STEP_MS = 70;

/**
 * How many items are allowed to stagger before the rest arrive together.
 *
 * The canvas describes a rail of five. A list of sixty dealt at 70ms apart is
 * a four-second wait for the tail, which is a different thing entirely — it
 * stops being an arrival and becomes a loading bar made of content. The cap
 * lives here rather than in a note asking callers to remember it, because the
 * caller who forgets is the one with the long list.
 */
export const DEAL_MAX_STEPS = 8;

/** The `animation-delay` for the item at `index` in a dealt sequence. */
export function dealDelayMs(index: number): number {
  if (!Number.isFinite(index)) return 0;
  const step = Math.max(0, Math.floor(index));
  return Math.min(step, DEAL_MAX_STEPS) * DEAL_STEP_MS;
}
