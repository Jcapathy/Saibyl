import { stageDef, type StageState } from '@/lib/stages';
import { Inherited, Missing } from '@/components/stages/StagePrimitives';

/**
 * The top of every stage: what it is asking, what it inherited, what is missing.
 *
 * **Every stage renders this, and it always says one of the two things.** Either
 * it lists what arrived from an earlier step, or it names the input that did not
 * and what its absence costs the answer. Never neither — a stage that silently
 * inherits nothing is indistinguishable on screen from one that had nothing to
 * inherit, and that is precisely the confusion the rail exists to remove.
 *
 * The invariant is enforced on the server (`services/stages/product_state.py`)
 * and asserted in both suites, but it is also *structural* here: this component
 * is the only way a stage page renders its head, so there is no page-shaped hole
 * to fall through.
 */
export default function StageHeader({ stage }: { stage: StageState }) {
  const def = stageDef(stage.id);
  const tone = stage.runnable === 'blocked' ? 'blocking' : 'degrading';

  return (
    <header className="space-y-4">
      <div>
        <p className="font-mono text-[10px] uppercase tracking-[0.16em] text-saibyl-gold">
          Step {stage.number} of 5
        </p>
        <h1 className="text-h1 text-saibyl-white mt-1.5">{stage.label}</h1>
        <p className="text-[13.5px] text-saibyl-silver mt-1.5 italic">{def.ask}</p>
      </div>

      {stage.inherited.length > 0 && <Inherited lines={stage.inherited} />}

      {stage.missing.map((input) => (
        <Missing key={input.headline} input={input} tone={tone} />
      ))}

      {/*
        The case the two blocks above cannot cover between them: a stage with
        nothing inherited and nothing missing. It should be unreachable — the
        server asserts it, and `_check_invariants` logs at ERROR if it ever
        happens — so this says so plainly rather than rendering an empty header
        that reads as "nothing to tell you".
      */}
      {stage.inherited.length === 0 && stage.missing.length === 0 && (
        <p className="text-[12.5px] text-saibyl-muted">
          This step has nothing recorded about what it received. That is a fault
          on our side, not a state you caused — nothing you do here is at risk.
        </p>
      )}
    </header>
  );
}
