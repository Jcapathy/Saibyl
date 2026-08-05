import { useState } from 'react';
import { motion } from 'framer-motion';
import { Plus } from 'lucide-react';
import { stagger } from './motion';

export interface FaqItem {
  q: string;
  a: string;
}

/**
 * The landing page's questions.
 *
 * Two things the previous version got wrong that this one is built not to:
 *
 * 1. **Answers are plain strings, not nodes.** A collapsed panel is animated
 *    rather than unmounted, so anything focusable inside it would stay in the
 *    tab order while invisible. Keeping answers to text makes `aria-hidden` a
 *    complete answer instead of half of one. Where a question needs to send the
 *    reader somewhere, the destination goes *after* the list, in the open.
 *
 * 2. **The panel grows to fit.** The old markup animated `max-h-96`, which
 *    silently clipped any answer longer than 24rem — a bug that only appears
 *    once someone writes a longer answer, which is to say later, to someone
 *    else. `grid-rows-[0fr]` → `[1fr]` animates to the content's real height
 *    whatever that turns out to be.
 */
export default function Faq({ items }: { items: readonly FaqItem[] }) {
  const [open, setOpen] = useState<number[]>([]);

  const toggle = (index: number) =>
    setOpen((prev) =>
      prev.includes(index) ? prev.filter((i) => i !== index) : [...prev, index],
    );

  return (
    <div className="space-y-2">
      {items.map((item, i) => {
        const isOpen = open.includes(i);
        return (
          <motion.div
            key={item.q}
            {...stagger(i)}
            className="bg-saibyl-surface border border-saibyl-border rounded-2xl overflow-hidden"
          >
            <h3>
              <button
                type="button"
                onClick={() => toggle(i)}
                aria-expanded={isOpen}
                aria-controls={`faq-panel-${i}`}
                id={`faq-button-${i}`}
                className="w-full flex items-center justify-between gap-4 px-6 py-5 text-left cursor-pointer focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-saibyl-gold/60 rounded-2xl"
              >
                <span className="font-sans font-semibold text-base text-saibyl-platinum">
                  {item.q}
                </span>
                <Plus
                  aria-hidden="true"
                  className={`w-5 h-5 text-saibyl-silver shrink-0 transition-transform duration-300 ${
                    isOpen ? 'rotate-45' : ''
                  }`}
                />
              </button>
            </h3>
            <div
              id={`faq-panel-${i}`}
              role="region"
              aria-labelledby={`faq-button-${i}`}
              aria-hidden={!isOpen}
              className={`grid transition-[grid-template-rows] duration-300 ease-out ${
                isOpen ? 'grid-rows-[1fr]' : 'grid-rows-[0fr]'
              }`}
            >
              <div className="overflow-hidden">
                <p className="px-6 pb-5 text-sm text-saibyl-silver leading-relaxed max-w-2xl">
                  {item.a}
                </p>
              </div>
            </div>
          </motion.div>
        );
      })}
    </div>
  );
}
