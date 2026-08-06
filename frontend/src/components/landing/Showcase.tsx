import type { ReactNode } from 'react';
import { motion } from 'framer-motion';

import { DEMO_OBJECTIONS } from './demoRun';
import { fadeUp } from './motion';

/**
 * Product imagery, and the section shapes that carry it.
 *
 * The page had none. Every section was a centred heading over a grid of cards,
 * 6,910px of it, and the founder's reading was "an internal tool that somebody
 * built over a weekend" — which is what a page looks like when it describes
 * software without ever showing it. Nothing here changes the argument; it gives
 * the argument something to point at.
 *
 * ── THE SCREENSHOTS ARE REAL ───────────────────────────────────────────────
 * `public/demo/` is output from an actual run on **Tallyhook**, an invoice
 * chaser for freelancers that does not exist. A fictional product on purpose:
 * a real customer's run is their commercial information, and a mockup is a
 * drawing of a product rather than the product. Tallyhook was written, uploaded
 * and run through the same five steps a visitor would walk, and the 26
 * objections on the page are the ones that came back.
 *
 * If the app's chrome changes, retake them rather than editing them. A
 * touched-up screenshot is a claim about a screen that does not exist.
 */

/* ── One product shot, framed ─────────────────────────────────────────────── */

/**
 * A screenshot in a frame that reads as a window rather than as an image.
 *
 * `width`/`height` are the intrinsic pixel dimensions of each 2x asset, so the
 * browser reserves the right box before the file lands. Without them a
 * three-image page reflows twice under the reader as it loads, which is the
 * cheapest possible way to look unfinished.
 */
export function Shot({
  src,
  alt,
  width,
  height,
  priority = false,
  crop,
  className = '',
}: {
  src: string;
  alt: string;
  width: number;
  height: number;
  /** The hero shot. Everything else waits until it is scrolled towards. */
  priority?: boolean;
  /**
   * Fractions to cut off the left and the top, each 0 to 1.
   *
   * `audience.png` and `objections.png` were clipped to the content column but
   * still carry a sliver of the step rail down their left edge, and
   * `objections.png` opens on a row of stage chips that mean nothing without
   * the page around them. In a half-width column that is a third of the frame
   * spent on furniture, and everything a reader is meant to notice shrinks to
   * make room for it.
   *
   * Cropped in CSS rather than by re-cutting the files, so the same asset
   * serves the full-width hero uncropped. Two versions of one screenshot is two
   * things to retake, and the one that gets forgotten is the one that starts
   * lying about the product.
   */
  crop?: { left?: number; top?: number };
  className?: string;
}) {
  const cropLeft = crop?.left ?? 0;
  const cropTop = crop?.top ?? 0;
  const keptW = 1 - cropLeft;
  const keptH = 1 - cropTop;
  return (
    <div
      className={`overflow-hidden rounded-2xl border border-saibyl-border bg-saibyl-deep shadow-[0_24px_80px_-24px_rgba(0,0,0,0.9)] ${className}`}
    >
      {/* Three dots and nothing else. A fake URL bar would be a claim about a
          route, and this product's routes are not the point of the image. */}
      <div
        className="flex items-center gap-1.5 border-b border-saibyl-border bg-saibyl-void/60 px-4 py-2.5"
        aria-hidden="true"
      >
        <span className="h-2.5 w-2.5 rounded-full bg-white/10" />
        <span className="h-2.5 w-2.5 rounded-full bg-white/10" />
        <span className="h-2.5 w-2.5 rounded-full bg-white/10" />
      </div>
      {/* `aspectRatio` on the frame, not `height`, so the browser reserves the
          right box before the file lands. Without it a three-image page reflows
          twice under the reader, which is the cheapest way to look unfinished. */}
      <div
        className="relative w-full overflow-hidden"
        style={{ aspectRatio: `${width * keptW} / ${height * keptH}` }}
      >
        {/*
          Both axes are scaled by their own 1/kept and offset with `left`/`top`
          percentages, which resolve against the frame's width and height
          respectively. `marginTop` would have been the obvious spelling and is
          the wrong one: a percentage margin resolves against the containing
          block's *width* on both axes, so a top crop would have slid by the
          wrong distance on every viewport. Because the frame's aspect ratio is
          set to the cropped region's, scaling both axes leaves the image's own
          proportions untouched.
        */}
        <img
          src={src}
          alt={alt}
          width={width}
          height={height}
          loading={priority ? 'eager' : 'lazy'}
          decoding="async"
          className="absolute block max-w-none"
          style={{
            width: `${100 / keptW}%`,
            height: `${100 / keptH}%`,
            left: `-${(cropLeft / keptW) * 100}%`,
            top: `-${(cropTop / keptH) * 100}%`,
          }}
        />
      </div>
    </div>
  );
}

/* ── Copy on one side, the screen on the other ────────────────────────────── */

/**
 * The alternating section shape.
 *
 * `flip` puts the image first on wide screens and changes nothing on narrow
 * ones: the copy leads on mobile in both directions, because a reader who has
 * to scroll past a screenshot to find out what they are looking at has been
 * given a puzzle rather than an explanation.
 */
export function Split({
  eyebrow,
  title,
  children,
  shot,
  flip = false,
}: {
  eyebrow: string;
  title: ReactNode;
  children: ReactNode;
  shot: ReactNode;
  flip?: boolean;
}) {
  return (
    <div className="grid grid-cols-1 items-center gap-12 lg:grid-cols-2 lg:gap-16">
      <motion.div {...fadeUp} className={flip ? 'lg:order-2' : ''}>
        <span className="font-mono text-xs uppercase tracking-[0.2em] text-saibyl-signal-blue">
          {eyebrow}
        </span>
        <h3 className="font-display mt-4 text-2xl font-extrabold leading-[1.15] tracking-tight text-saibyl-platinum text-balance sm:text-3xl">
          {title}
        </h3>
        <div className="mt-5 space-y-4 text-sm leading-relaxed text-saibyl-silver sm:text-base">
          {children}
        </div>
      </motion.div>

      <motion.div {...fadeUp} className={flip ? 'lg:order-1' : ''}>
        {shot}
      </motion.div>
    </div>
  );
}

/* ── What came back from the demo run ─────────────────────────────────────── */

/**
 * The top six objections the demo run produced, verbatim.
 *
 * The list itself is in `demoRun.ts`, with the reasoning for showing a
 * fictional product's real output instead of a logo wall.
 */
export function ObjectionList() {
  return (
    <ul className="space-y-2.5">
      {DEMO_OBJECTIONS.map((objection) => (
        <li
          key={objection.label}
          className="flex items-baseline justify-between gap-4 rounded-xl border border-saibyl-border bg-saibyl-void px-4 py-3"
        >
          <span className="text-sm text-saibyl-platinum">{objection.label}</span>
          <span className="shrink-0 font-mono text-xs text-saibyl-muted">
            {objection.people} people
          </span>
        </li>
      ))}
    </ul>
  );
}
