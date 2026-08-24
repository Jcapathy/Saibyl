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

    /* Queried on every call, never captured once.
       The landing page is static markup, so a single `querySelectorAll` at
       mount saw everything it would ever need to. **Every page behind the login
       is not**: the lists, tables and cards arrive after a fetch, seconds after
       this effect ran. A captured array would leave each of those nodes at
       `opacity: 0` with nothing watching them — permanently invisible content
       on a page that reported no error, which is the worst rendering of this
       whole idea. */
    const found = () => Array.from(el.querySelectorAll<HTMLElement>(selector));
    const revealAll = () => {
      for (const target of found()) target.classList.add('is-visible');
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
    /* Once the fallback has fired, this stops observing and starts revealing.
       Otherwise the fallback only rescues the nodes that existed when it ran:
       in an environment where intersection callbacks never arrive, a list that
       loads at t=5s would be observed by a dead observer and stay invisible
       forever — the exact failure the fallback exists to prevent, moved four
       seconds later. */
    let gaveUp = false;

    /* `observe` is idempotent per element, so re-observing one already being
       watched is a no-op rather than a duplicate callback. That is what lets
       this be called again on every mutation without bookkeeping. */
    const track = () => {
      for (const target of found()) {
        if (gaveUp) target.classList.add('is-visible');
        else observer.observe(target);
      }
    };
    track();

    /* Content that arrives later gets tracked when it arrives.
       Watching `childList` on the subtree covers every way React can add a
       node: a resolved fetch, a tab switch, an expanded row. Attributes are
       deliberately not watched — `is-visible` is itself an attribute change,
       and observing those would have this re-enter on its own writes. */
    const mutations = new MutationObserver((records) => {
      // Only re-query when something was actually added. A removal cannot
      // produce a node that needs watching, and this runs on every keystroke
      // in a filter box.
      if (records.some((r) => r.addedNodes.length > 0)) track();
    });
    mutations.observe(el, { childList: true, subtree: true });

    let fallbackTimer: number | undefined;
    const armFallback = () => {
      fallbackTimer = window.setTimeout(() => {
        gaveUp = true;
        revealAll();
      }, 2500);
    };
    if (document.readyState === 'complete') armFallback();
    else window.addEventListener('load', armFallback, { once: true });

    return () => {
      window.removeEventListener('load', armFallback);
      if (fallbackTimer !== undefined) window.clearTimeout(fallbackTimer);
      mutations.disconnect();
      observer.disconnect();
    };
  }, [root, selector]);
}
