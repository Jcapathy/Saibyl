/**
 * Scroll-reveal presets for the landing page.
 *
 * Kept in a `.ts` file with no components in it so `react-refresh` has nothing
 * to complain about, and so the two presets cannot drift between sections the
 * way four copies of the same object would.
 *
 * No `ease` is specified anywhere: framer-motion's default is already an
 * ease-out, and naming one as a bare string is the one thing in these objects
 * that needs a type annotation to stay assignable.
 *
 * Motion is opt-out at the root — `LandingPage` wraps the page in
 * `<MotionConfig reducedMotion="user">`, so a visitor with "reduce motion" set
 * gets the opacity change and none of the travel, without either preset here
 * knowing about it.
 */

export const fadeUp = {
  initial: { opacity: 0, y: 24 },
  whileInView: { opacity: 1, y: 0 },
  viewport: { once: true, amount: 0.15 },
  transition: { duration: 0.5 },
};

/**
 * `fadeUp` with a delay for the nth item in a row.
 *
 * Capped at the 6th item: an uncapped index makes the last card of a long grid
 * arrive most of a second after the first, which reads as jank rather than as
 * choreography.
 */
export const stagger = (index: number) => ({
  ...fadeUp,
  transition: { duration: 0.5, delay: Math.min(index, 5) * 0.08 },
});
