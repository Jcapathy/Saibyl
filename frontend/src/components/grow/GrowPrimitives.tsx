import { Info } from 'lucide-react';

import { Card, Eyebrow } from '@/components/design';

/**
 * The two blocks the Grow surface builds out of what the server already knows.
 *
 * Both read the `growth` entry in the server's stage registry
 * (`GET /api/simulations/founder-stages`) rather than restating it. That
 * registry is the same object the finished write-up is planned from, so a limit
 * a founder reads here before spending and the limit stated afterwards cannot
 * drift apart. Restating either of them in this file would be the "two sources
 * of truth for one value" class, whose symptom is a caveat quietly missing from
 * the one surface where it would have changed somebody's mind.
 *
 * ⚠️ The registry's `report_questions` are deliberately **not** rendered
 * anywhere on this surface, and `grow.test.ts` holds that line. They are
 * written for the report planner and one of them carries a discipline word the
 * house rules ban from anything a founder reads. Server copy is not exempt from
 * the vocabulary rule — it is simply invisible to a scan that reads this repo's
 * own source, which makes it the easier half to get wrong.
 *
 * Design comes from `@/components/design` — composed, not re-typed.
 */

/* ------------------------------------------------------------------ */
/*  The honesty floor                                                  */
/* ------------------------------------------------------------------ */

/**
 * What a rehearsal here will not be able to tell you, said before it is paid for.
 *
 * Violet, not red. This is the product working correctly and saying so — the
 * same tone the rest of the app uses for a refusal, kept distinct from the red
 * that means something went wrong.
 */
export function Limits({ items }: { items: string[] }) {
  if (items.length === 0) return null;
  return (
    <div className="rounded-xl border border-[#8b73ee]/30 bg-[#8b73ee]/[0.07] p-4">
      <p className="flex items-start gap-2 text-[13px] font-medium text-[#6a4fe0]">
        <Info className="w-4 h-4 shrink-0 mt-px" />
        What this will not be able to tell you
      </p>
      <ul className="text-[12.5px] text-saibyl-muted mt-1.5 leading-relaxed space-y-1.5">
        {items.map((item) => (
          <li key={item}>{item}</li>
        ))}
      </ul>
      <p className="text-[11.5px] text-saibyl-muted mt-2.5 leading-relaxed">
        You are reading this before anything is charged, and the finished
        write-up says it again in the same words.
      </p>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  Who is in the room, and what it needs from you                     */
/* ------------------------------------------------------------------ */

/**
 * The room this stage builds, and the material it expects.
 *
 * The share is the substance of the stage rather than a setting. It is the
 * highest of the five moments a founder can run, and the registry gives the
 * reason: once you have shipped, the buyer already has something that works, so
 * the sunk-cost and already-solved-it arguments are the real ones. A founder
 * who does not know that is reading a friendlier room than the one they paid
 * for.
 *
 * `expected_inputs` is advisory on the server and advisory here — a founder
 * holding only a pricing page should not be stopped. But a room reacting to the
 * wrong material gives a confidently wrong answer, which is worse than no
 * answer, so it is named.
 */
export function RoomNote({
  inputs,
  defendingShare,
  rounds,
}: {
  inputs: string[];
  /** 0–1. The share of the room that already has something that works. */
  defendingShare: number;
  rounds: number;
}) {
  return (
    <Card carries="meaning" className="p-5 space-y-4">
      <div>
        <Eyebrow>The room this builds</Eyebrow>
        <p className="text-[13px] text-saibyl-ink mt-2 leading-relaxed">
          About {Math.round(defendingShare * 100)}% of it already has something
          that works and would rather not move. That is the highest of any
          moment you can run, and it is deliberate: once you have shipped, the
          people whose objection actually costs you money are the ones who have
          already solved the problem some other way.
        </p>
        <p className="text-[12.5px] text-saibyl-muted mt-1.5 leading-relaxed">
          They argue it out over {rounds} rounds rather than the usual five,
          because the already-solved-it argument takes a while to surface and
          longer to spread.
        </p>
      </div>

      {inputs.length > 0 && (
        <div className="border-t border-saibyl-border pt-3.5">
          <Eyebrow>What to have ready</Eyebrow>
          <div className="flex flex-wrap gap-1.5 mt-2">
            {inputs.map((item) => (
              <span
                key={item}
                className="rounded-full border border-saibyl-border bg-white px-2.5 py-0.5 text-[11.5px] text-saibyl-silver"
              >
                {item}
              </span>
            ))}
          </div>
        </div>
      )}
    </Card>
  );
}
