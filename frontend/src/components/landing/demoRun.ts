/**
 * What the demo run actually returned.
 *
 * This is the page's honest substitute for social proof. There are no customer
 * logos because there are no customers yet, and inventing either a logo or a
 * testimonial is the class of thing this page spent a week having removed from
 * it — "87% probability of negative sentiment spike" and its three siblings
 * were invented report output presented as sample results.
 *
 * What can be shown instead is a run anyone could reproduce: **Tallyhook**, an
 * invoice chaser for freelancers that does not exist, written and uploaded and
 * put through the same five steps a visitor would walk. A fictional product on
 * purpose — a real customer's run is their commercial information, and a mockup
 * is a drawing of a product rather than the product.
 *
 * Every line below is copied from the run behind `public/demo/objections.png`,
 * counts included. If the screenshots are retaken, retake these from the same
 * run: a list that no longer matches the image beside it is worse than no list,
 * because the image is the thing a reader checks it against.
 *
 * In a `.ts` file with no components in it so `react-refresh` has nothing to
 * complain about — the same reason `motion.ts` is separate from `Section.tsx`.
 */

export interface DemoObjection {
  /** People who carried it, not comments. Somebody who says it five times counts once. */
  people: number;
  label: string;
}

export const DEMO_OBJECTIONS: readonly DemoObjection[] = [
  { people: 3, label: 'risk of damaging client relationships' },
  { people: 3, label: 'won’t work on clients who intentionally delay payment' },
  { people: 2, label: 'too expensive for what it does' },
  { people: 2, label: 'real problem is the client relationship not the tool' },
  { people: 2, label: 'automated messages sound robotic or impersonal' },
  { people: 2, label: 'guilt about bothering clients for money' },
];

/** Objections the same run produced in total. The six above are the top of it. */
export const DEMO_OBJECTIONS_TOTAL = 26;
