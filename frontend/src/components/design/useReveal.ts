import { useEffect, type RefObject } from 'react';

/**
 * Reveal each `selector` element as the reader scrolls it into view.
 *
 * **Lifted out of `LandingPage`, which now calls it too**, so there is one
 * implementation of this behaviour rather than one on the public site and a
 * second, subtly different one behind the login. That divergence is the whole
 * failure mode the founder named on 2026-08-23: a landing page that feels alive
 * and an app that does not.
 *
 * Three things it gets right that a five-line `IntersectionObserver` does not,
 * and all three are why this is shared code rather than a snippet to copy:
 *
 * 1. **Reduced motion shows everything immediately.** The CSS collapses the
 *    transition, so waiting for scroll positions a non-scrolling reader will
 *    never produce would leave the page permanently blank. This is not a nicety
 *    — a reveal that does not fire is a page with no content on it.
 * 2. **It unobserves on reveal.** An element that has arrived does not need
 *    watching, and a page of forty observed nodes is forty callbacks per scroll.
 * 3. **It has a fallback.** 2.5s after `load`, anything still hidden is shown.
 *    Not a capture hack: an environment that suppresses intersection callbacks
 *    — printing, a full-page screenshot with a virtual viewport — must not
 *    render an empty page. `docs/CRITICS_LOG.md` 2026-08-16 records the
 *    screenshot case, where a scroll-reveal page photographed as blank and was
 *    reported as a broken deploy.
 *
 * @param root      the subtree to search. Nothing outside it is touched.
 * @param selector  what counts as revealable. Defaults to the design system's
 *                  class; `LandingPage` passes its own `.reveal`.
 */
export function useReveal(
  root: RefObject<HTMLElement | null>,
  selector = '.sb-reveal',
): void {
  /* `selector` is a plain dependency. An earlier version parked it in a ref to
     avoid re-running on a new string — which was solving nothing: dependencies
     are compared with `Object.is`, and two identical strings are identical, so
     a caller passing the same literal every render never re-runs this. Writing
     the ref during render, on the other hand, is exactly what
     `react-hooks/refs` forbids. */
  useEffect(() => {
    const el = root.current;
    if (!el) return;

    const targets = Array.from(el.querySelectorAll<HTMLElement>(selector));
    const revealAll = () => {
      for (const target of targets) target.classList.add('is-visible');
    };

    if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
      revealAll();
      return;
    }

    const observer = new IntersectionObserver(
      (entries) => {
        for (const entry of entries) {
          if (entry.isIntersecting) {
            entry.target.classList.add('is-visible');
            observer.unobserve(entry.target);
          }
        }
      },
      { threshold: 0.12 },
    );
    for (const target of targets) observer.observe(target);

    let fallbackTimer: number | undefined;
    const armFallback = () => {
      fallbackTimer = window.setTimeout(revealAll, 2500);
    };
    if (document.readyState === 'complete') armFallback();
    else window.addEventListener('load', armFallback, { once: true });

    return () => {
      window.removeEventListener('load', armFallback);
      if (fallbackTimer !== undefined) window.clearTimeout(fallbackTimer);
      observer.disconnect();
    };
  }, [root, selector]);
}
