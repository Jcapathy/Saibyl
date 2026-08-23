import { Link } from 'react-router-dom';
import { ArrowRight, PackagePlus, Tag, Compass } from 'lucide-react';
import type { LucideIcon } from 'lucide-react';

import { Card, Deal, Eyebrow } from '@/components/design';

import { rehearsalHref } from './grow';

/**
 * The three changes a founder with a live product actually makes.
 *
 * They are the landing page's own promise, in the same order: "pricing moves,
 * feature drops, expansion pitches". Underneath they are **one** action — a run
 * staged at growth with two things written into it — and these cards do not
 * pretend otherwise. What differs is what you write, and what to write is the
 * part a founder gets stuck on, which is the only reason three cards beat one
 * button.
 *
 * Every card goes to the same place. There is no third state where a card is
 * shown but cannot be taken: a founder reaching this component has a product
 * selected, because the page refuses to render it otherwise and offers the way
 * to make one instead.
 */

interface Move {
  id: string;
  icon: LucideIcon;
  eyebrow: string;
  title: string;
  body: string;
  /** What goes in the two boxes. The sentence founders get stuck on. */
  write: string;
}

const MOVES: Move[] = [
  {
    id: 'price',
    icon: Tag,
    eyebrow: 'Pricing',
    title: 'Put the price up',
    body: 'Show the people already paying the old price what the new one looks like, before they see it on your site. You hear what they say to each other about it, and which of them starts talking about leaving.',
    write: 'Your pricing as it stands today, and the pricing you are proposing.',
  },
  {
    id: 'feature',
    icon: PackagePlus,
    eyebrow: 'What you ship',
    title: 'Add it, or take it away',
    body: 'Put the announcement in front of people whose setup already works. The strongest thing said against a new feature is usually that nobody asked for it, and a removal is heard by the few people who used it loudest.',
    write: 'The announcement you were going to publish, and the version you would fall back to.',
  },
  {
    id: 'expansion',
    icon: Compass,
    eyebrow: 'New ground',
    title: 'Take it somewhere new',
    body: 'A bigger company, a different industry, another country. This is the one where founders are most often surprised: the pitch that works on the people who already agree with you is rarely the pitch that travels.',
    write: 'The pitch you use today, and the one you would use over there.',
  },
];

export default function MoveCards({ productId }: { productId: string }) {
  const href = rehearsalHref(productId);

  return (
    <section className="space-y-4">
      <div>
        <Eyebrow>Rehearse a change</Eyebrow>
        <p className="text-[13px] text-saibyl-ink mt-2 leading-relaxed max-w-2xl">
          Whichever of these you are doing, write it as two things &mdash; what
          you sell now, and what you are proposing. One room reads both, in the
          same order, so what changes between them is the change itself rather
          than who happened to be listening.
        </p>
        <p className="text-[12.5px] text-saibyl-muted mt-1.5 leading-relaxed max-w-2xl">
          If the two do not separate, you are told that. You are never handed an
          ordering drawn from a gap too small to stand behind, because that is
          how a decision gets made on noise.
        </p>
      </div>

      <div className="grid gap-3 sm:grid-cols-3">
        {MOVES.map((move, index) => {
          const Icon = move.icon;
          return (
            <Deal key={move.id} index={index} className="h-full">
              <Link to={href} className="block h-full">
                <Card
                  carries="meaning"
                  lift
                  className="flex h-full flex-col p-5"
                >
                  <Icon className="w-4 h-4 text-saibyl-blue" aria-hidden="true" />
                  <Eyebrow className="mt-3">{move.eyebrow}</Eyebrow>
                  <h3 className="text-[15px] font-medium text-saibyl-ink mt-2">
                    {move.title}
                  </h3>
                  <p className="text-[12.5px] text-saibyl-muted mt-1.5 leading-relaxed">
                    {move.body}
                  </p>
                  <p className="text-[12px] text-saibyl-silver mt-3 leading-relaxed border-t border-saibyl-border pt-3">
                    <span className="text-saibyl-ink">What to write:</span>{' '}
                    {move.write}
                  </p>
                  <span className="inline-flex items-center gap-1.5 text-[12.5px] text-saibyl-blue mt-auto pt-3">
                    Set it up
                    <ArrowRight className="w-3.5 h-3.5" />
                  </span>
                </Card>
              </Link>
            </Deal>
          );
        })}
      </div>
    </section>
  );
}
