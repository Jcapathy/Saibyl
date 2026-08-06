/**
 * What each side of the room is called on screen.
 *
 * The server hands these keys back in three shapes — as a slice, as a key in
 * `cohort_spread`, and as `originating_cohort` on an objection — and rendering
 * the raw key anywhere puts the literal word "adversarial" in front of a
 * founder. One map, so there is one answer.
 *
 * In `lib/` rather than beside the component that first needed it: a file that
 * exports both a component and a constant loses fast refresh, and the four
 * call sites are spread across three components anyway.
 */

export const GROUP_LABELS: Record<string, string> = {
  buyer: 'Your buyers',
  adversarial: 'People happy with what they already use',
};

/**
 * A group name a founder can read.
 *
 * Falls through to whatever the server sent rather than to a placeholder. An
 * unknown key is something to notice; a blank reads as "this group has no
 * name", which is a different and untrue claim.
 */
export function groupLabel(key: string): string {
  return GROUP_LABELS[key] ?? key;
}
