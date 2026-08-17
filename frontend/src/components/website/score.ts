/**
 * The one place the score thresholds live. The critique and the draft view
 * both colour their numbers through this, so 74 and 75 read the same on every
 * surface — and a threshold change is one edit, not a hunt.
 *
 * Its own module rather than an export of `SiteCritique.tsx` because a
 * component file that also exports a plain function loses fast refresh.
 */
export function scoreText(score: number): string {
  if (score >= 75) return 'text-saibyl-positive';
  if (score >= 50) return 'text-saibyl-warning';
  return 'text-saibyl-negative';
}
