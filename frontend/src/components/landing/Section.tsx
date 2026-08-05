import type { ReactNode } from 'react';
import { motion } from 'framer-motion';
import { fadeUp } from './motion';

/**
 * The landing page's section shell and heading.
 *
 * Extracted because the page alternates two surfaces — the page background and
 * one step up from it — and the previous version wrote both out by hand at every
 * section boundary, in raw hex, which is how `#0D1424` ended up meaning "panel"
 * in six places and nothing in particular in the seventh. The palette tokens
 * exist in `tailwind.config.js`; this is what uses them.
 */

/**
 * `raised` is the panel surface; `page` is the page itself. Every section
 * carries its own top border so the alternation reads as a seam rather than as
 * a colour that happens to change.
 */
type Tone = 'page' | 'raised';

const TONE_CLASS: Record<Tone, string> = {
  page: 'bg-saibyl-void',
  raised: 'bg-saibyl-deep',
};

export function Section({
  id,
  tone = 'page',
  className = '',
  children,
}: {
  id?: string;
  tone?: Tone;
  className?: string;
  children: ReactNode;
}) {
  return (
    <section
      id={id}
      // `scroll-mt-16` clears the fixed 4rem nav. Without it every in-page
      // anchor lands with its own heading hidden behind the header, which is
      // the failure mode that makes people think a jump link is broken.
      className={`scroll-mt-16 border-t border-saibyl-border px-6 py-24 sm:py-28 ${TONE_CLASS[tone]} ${className}`}
    >
      {children}
    </section>
  );
}

export function SectionHead({
  eyebrow,
  title,
  lede,
  align = 'center',
}: {
  eyebrow: string;
  title: ReactNode;
  lede?: ReactNode;
  align?: 'center' | 'left';
}) {
  const centred = align === 'center';
  return (
    <motion.div
      {...fadeUp}
      className={centred ? 'text-center max-w-3xl mx-auto mb-14' : 'max-w-3xl mb-14'}
    >
      <span className="font-mono text-xs tracking-[0.2em] uppercase text-saibyl-signal-blue">
        {eyebrow}
      </span>
      <h2 className="font-display font-extrabold text-3xl sm:text-4xl lg:text-[2.75rem] text-saibyl-platinum mt-4 leading-[1.1] tracking-tight text-balance">
        {title}
      </h2>
      {lede && (
        <p className="text-base sm:text-lg text-saibyl-silver mt-5 leading-relaxed">{lede}</p>
      )}
    </motion.div>
  );
}
