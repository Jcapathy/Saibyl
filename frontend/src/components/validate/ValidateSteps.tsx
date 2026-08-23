import { Link } from 'react-router-dom';
import { MessageSquare, PenLine, Users, ArrowRight } from 'lucide-react';
import type { LucideIcon } from 'lucide-react';

import { Card, Deal, Eyebrow } from '@/components/design';
import { findStage, stageHref, type ProductState } from '@/lib/stages';

/**
 * Three doors onto machinery that already exists.
 *
 * The founder's own words for this stage are the three questions: *"Does the
 * pain exist, who feels it most, and what would they pay?"* Each one is already
 * answered somewhere in the app — the idea brief and the audience on step 1,
 * the room on step 2 — and until now the only way in was to know that a rail
 * lived under a product you had already created.
 *
 * So these cards create nothing. They name the question, say what the founder
 * has to write to get it answered, and hand off. The line at the foot of each
 * card is the **server's** sentence about what that step has produced
 * (`StageState.produced`), not this component's guess: the rail and this page
 * must never disagree about whether something has run, and the only way to
 * guarantee that is to have one of them do no thinking.
 *
 * Dealt at the canvas's 70ms, per its motion note.
 */

interface Door {
  id: string;
  icon: LucideIcon;
  /** The mono label. Which piece of machinery this is. */
  eyebrow: string;
  /** The founder's question, verbatim from the journey. */
  title: string;
  body: string;
  /** What the founder clicks through to do. */
  cta: string;
  href: string;
  /**
   * What this step has produced, in the server's words. `null` when it has
   * produced nothing yet — or, for the brief, always: a written-up brief is an
   * input to step 1 rather than something step 1 reports back, so claiming a
   * state for it here would be this component inventing one.
   */
  produced: string | null;
  /** Shown instead of `produced`. What the founder needs to have ready. */
  note: string;
  /** The ink-coloured word before `note`, where one earns its place. */
  noteLabel?: string;
}

function doors(product: ProductState): Door[] {
  const audience = findStage(product, 'audience');
  const reactions = findStage(product, 'reactions');
  const step1 = stageHref(product.id, 'audience');

  return [
    {
      id: 'brief',
      icon: PenLine,
      eyebrow: 'The brief',
      title: 'Does the pain exist?',
      body: 'Five short questions — what hurts, who it hurts, and what they do about it today. Your answers are written up and become the first thing the room reads. A deck, a pricing page or your live site work just as well if you already have one.',
      cta: 'Answer the five questions',
      href: `${step1}#idea-brief`,
      produced: null,
      note: 'the pain, who has it, what they use instead, and what you would charge.',
      noteLabel: 'What to write',
    },
    {
      id: 'audience',
      icon: Users,
      eyebrow: 'The audience',
      title: 'Who feels it most?',
      body: 'One pass reads what you wrote and proposes the groups of people most likely to buy this — what they do, what they already use, and what would make them doubt you. You confirm it, or correct the parts that look wrong.',
      cta: 'See who buys this',
      href: step1,
      produced: audience?.produced ?? null,
      note: 'Nothing worked out yet — this reads whatever the brief produced.',
    },
    {
      id: 'room',
      icon: MessageSquare,
      eyebrow: 'The room',
      title: 'What would they pay?',
      body: 'Those buyers read your material and argue about it. You get back what they said, and the things they pushed back on ranked by how much of the room actually carried each one — price among them, and rarely at the top.',
      cta: 'Put it in front of them',
      href: stageHref(product.id, 'reactions'),
      produced: reactions?.produced ?? null,
      note: 'Nothing has run yet — the room is built from the audience above.',
    },
  ];
}

export default function ValidateSteps({ product }: { product: ProductState }) {
  return (
    <section className="space-y-4">
      <div>
        <Eyebrow>Getting the idea into a room</Eyebrow>
        <p className="text-[13px] text-saibyl-ink mt-2 leading-relaxed max-w-2xl">
          Three things in order, and each one feeds the next. Write the idea
          down, agree on who it is for, then put it in front of them. Nothing
          here needs a finished product &mdash; the first two take a paragraph
          and a read-through.
        </p>
      </div>

      <div className="grid gap-3 sm:grid-cols-3">
        {doors(product).map((door, index) => {
          const Icon = door.icon;
          const label = door.produced ? 'So far' : door.noteLabel;
          const foot = door.produced ?? door.note;
          return (
            <Deal key={door.id} index={index} className="h-full">
              <Link to={door.href} className="block h-full">
                <Card carries="meaning" lift className="flex h-full flex-col p-5">
                  <Icon className="w-4 h-4 text-saibyl-blue" aria-hidden="true" />
                  <Eyebrow className="mt-3">{door.eyebrow}</Eyebrow>
                  <h3 className="text-[15px] font-medium text-saibyl-ink mt-2">
                    {door.title}
                  </h3>
                  <p className="text-[12.5px] text-saibyl-muted mt-1.5 leading-relaxed">
                    {door.body}
                  </p>
                  <p className="text-[12px] text-saibyl-silver mt-3 leading-relaxed border-t border-saibyl-border pt-3">
                    {label && <span className="text-saibyl-ink">{label}: </span>}
                    {foot}
                  </p>
                  <span className="inline-flex items-center gap-1.5 text-[12.5px] text-saibyl-blue mt-auto pt-3">
                    {door.cta}
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
