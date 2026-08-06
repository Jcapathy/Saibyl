import { Link } from 'react-router-dom';
import { ArrowRight, CircleAlert, CircleCheck, Info } from 'lucide-react';

import type { InheritedLine, MissingInput, StageAction, StaleResult } from '@/lib/stages';

/**
 * The pieces every stage is built from.
 *
 * They live together because they encode one rule between them and splitting
 * them would let a caller satisfy half of it:
 *
 *   Never a grey button. A stage either runs and states what the answer will be
 *   missing, or it is blocked with the button that unblocks it.
 *
 * `Guarded` is how that is enforced rather than remembered. It has no `disabled`
 * prop. If an action cannot be taken, you do not pass a disabled flag — you pass
 * `blockedBy`, and the component renders the reason and the way out. There is no
 * spelling of "greyed out with no explanation" available to a caller.
 *
 * `EmptyState` requires an `action`. TypeScript will not let you render a screen
 * that tells a founder there is nothing here and offers no way forward, which is
 * where they close the tab.
 */

/* ------------------------------------------------------------------ */
/*  Inherited state                                                    */
/* ------------------------------------------------------------------ */

/**
 * "Audience — 6 buyer types, confirmed 4 Aug", as a line you can click.
 *
 * This is the binding made visible. It is what stops a founder wondering
 * whether stage 4 knew about stage 1.
 */
export function Inherited({ lines }: { lines: InheritedLine[] }) {
  if (lines.length === 0) return null;
  return (
    <div className="space-y-1.5" data-stage-declares="inherited">
      {lines.map((line) => (
        <Link
          key={`${line.label}-${line.href}`}
          to={line.href}
          className="group flex items-center gap-2 text-[12px] text-saibyl-silver hover:text-saibyl-platinum transition-colors"
        >
          <CircleCheck className="w-3.5 h-3.5 text-saibyl-positive shrink-0" />
          <span className="underline decoration-white/15 underline-offset-2 group-hover:decoration-white/40">
            {line.label}
          </span>
        </Link>
      ))}
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  Missing input                                                      */
/* ------------------------------------------------------------------ */

/**
 * What a missing input will cost the answer, stated before any credits move.
 *
 * Two tones. `blocking` is the stage that cannot run at all; `degrading` is the
 * stage that will run and give a thinner answer. They are visually different
 * because they ask for different decisions — one is "do this first", the other
 * is "carry on if you want, here is what you lose".
 */
export function Missing({
  input,
  tone,
}: {
  input: MissingInput;
  tone: 'blocking' | 'degrading';
}) {
  const blocking = tone === 'blocking';
  return (
    <div
      data-stage-declares="missing"
      className={`rounded-xl border p-4 ${
        blocking
          ? 'border-[#8B5CF6]/30 bg-[#8B5CF6]/[0.07]'
          : 'border-saibyl-gold/25 bg-saibyl-gold/[0.06]'
      }`}
    >
      <p
        className={`flex items-start gap-2 text-[13px] font-medium ${
          blocking ? 'text-[#B79BF7]' : 'text-saibyl-gold'
        }`}
      >
        {blocking ? (
          <CircleAlert className="w-4 h-4 shrink-0 mt-px" />
        ) : (
          <Info className="w-4 h-4 shrink-0 mt-px" />
        )}
        {input.headline}
      </p>
      <p className="text-[12px] text-saibyl-muted mt-1.5 leading-relaxed">
        {input.consequence}
      </p>
      {input.action && (
        <Link
          to={input.action.href}
          className="inline-flex items-center gap-1.5 mt-3 px-3.5 py-1.5 rounded-lg bg-saibyl-gold text-saibyl-void text-[12px] font-semibold hover:bg-saibyl-gold-hover transition-colors"
        >
          {input.action.label}
          <ArrowRight className="w-3.5 h-3.5" />
        </Link>
      )}
    </div>
  );
}

/**
 * The answer already on this page was produced without something it is shown
 * as having.
 *
 * Deliberately not a `Missing`, though the fields are the same shape. `Missing`
 * warns about the *next* run; this describes the one whose output is on screen
 * now. Rendering them alike would let a founder read a finished, wrong answer
 * as a caution about a future one — which is the reading that produced this
 * component. Step 2 showed "Your material — 1 file" directly above objections
 * from a run that never saw the file, and both lines were true.
 *
 * Red rather than gold: gold on this rail means "you can still fix this before
 * it costs you", and this one already cost.
 */
export function Stale({ result }: { result: StaleResult }) {
  return (
    <div
      data-stage-declares="stale"
      className="rounded-xl border border-saibyl-negative/30 bg-saibyl-negative/[0.07] p-4"
    >
      <p className="flex items-start gap-2 text-[13px] font-medium text-saibyl-negative">
        <CircleAlert className="w-4 h-4 shrink-0 mt-px" />
        {result.headline}
      </p>
      <p className="text-[12px] text-saibyl-muted mt-1.5 leading-relaxed">
        {result.consequence}
      </p>
      {result.action && (
        <Link
          to={result.action.href}
          className="inline-flex items-center gap-1.5 mt-3 px-3.5 py-1.5 rounded-lg bg-saibyl-gold text-saibyl-void text-[12px] font-semibold hover:bg-saibyl-gold-hover transition-colors"
        >
          {result.action.label}
          <ArrowRight className="w-3.5 h-3.5" />
        </Link>
      )}
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  Guarded action                                                     */
/* ------------------------------------------------------------------ */

/**
 * A button that cannot be greyed out silently.
 *
 * There is no `disabled` prop, on purpose. `blockedBy` takes the reason in the
 * founder's words and the way out; passing it renders the explanation *and* the
 * unblocking control instead of the action. `busy` is separate and does not
 * disable anything conceptually — it says the click already landed.
 */
export function Guarded({
  label,
  onClick,
  to,
  blockedBy,
  busy,
  busyLabel,
  tone = 'primary',
}: {
  label: string;
  onClick?: () => void;
  to?: string;
  /** Why this cannot be done, and the control that fixes it. */
  blockedBy?: { reason: string; action?: StageAction } | null;
  busy?: boolean;
  busyLabel?: string;
  tone?: 'primary' | 'quiet';
}) {
  const classes =
    tone === 'primary'
      ? 'inline-flex items-center gap-1.5 px-5 py-2 rounded-xl bg-saibyl-gold text-saibyl-void font-semibold text-[13px] hover:bg-saibyl-gold-hover transition-colors'
      : 'inline-flex items-center gap-1.5 px-4 py-2 rounded-xl border border-white/[0.12] text-saibyl-platinum text-[13px] hover:bg-white/[0.05] transition-colors';

  if (blockedBy) {
    return (
      <div
        className="rounded-xl border border-[#8B5CF6]/30 bg-[#8B5CF6]/[0.07] p-4"
        data-guard="blocked"
      >
        <p className="text-[12px] text-saibyl-muted leading-relaxed">
          {blockedBy.reason}
        </p>
        {blockedBy.action && (
          <Link
            to={blockedBy.action.href}
            className="inline-flex items-center gap-1.5 mt-3 px-3.5 py-1.5 rounded-lg bg-saibyl-gold text-saibyl-void text-[12px] font-semibold hover:bg-saibyl-gold-hover transition-colors"
          >
            {blockedBy.action.label}
            <ArrowRight className="w-3.5 h-3.5" />
          </Link>
        )}
      </div>
    );
  }

  if (busy) {
    // Not disabled — announced. The click landed and the work is running; a
    // grey rectangle with no words is what this replaces.
    return (
      <span className={`${classes} opacity-70`} aria-live="polite">
        {busyLabel ?? `${label}…`}
      </span>
    );
  }

  if (to) {
    return (
      <Link to={to} className={classes}>
        {label}
        <ArrowRight className="w-3.5 h-3.5" />
      </Link>
    );
  }

  return (
    <button type="button" onClick={onClick} className={classes}>
      {label}
    </button>
  );
}

/* ------------------------------------------------------------------ */
/*  Empty state                                                        */
/* ------------------------------------------------------------------ */

/**
 * Nothing here yet — and exactly one thing to do about it.
 *
 * `action` is required. A screen that says there is nothing here and offers no
 * way forward is where a founder closes the tab, so the type system refuses to
 * build one.
 */
export function EmptyState({
  headline,
  body,
  action,
  secondary,
}: {
  headline: string;
  body: string;
  action: StageAction;
  secondary?: StageAction;
}) {
  return (
    <div
      className="glass rounded-2xl p-10 text-center"
      data-empty-state="true"
    >
      <p className="text-[15px] font-medium text-saibyl-platinum">{headline}</p>
      <p className="text-[13px] text-saibyl-muted mt-2 max-w-md mx-auto leading-relaxed">
        {body}
      </p>
      <div className="flex items-center justify-center gap-3 mt-5">
        <Link
          to={action.href}
          className="inline-flex items-center gap-1.5 px-5 py-2 rounded-xl bg-saibyl-gold text-saibyl-void font-semibold text-[13px] hover:bg-saibyl-gold-hover transition-colors"
        >
          {action.label}
          <ArrowRight className="w-3.5 h-3.5" />
        </Link>
        {secondary && (
          <Link
            to={secondary.href}
            className="text-[13px] text-saibyl-muted hover:text-saibyl-platinum transition-colors"
          >
            {secondary.label}
          </Link>
        )}
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  Errors                                                             */
/* ------------------------------------------------------------------ */

/** Something went wrong, said plainly, with a way to try again. */
export function StageError({
  message,
  retry,
}: {
  message: string;
  retry?: () => void;
}) {
  return (
    <div className="rounded-xl border border-saibyl-negative/25 bg-saibyl-negative/[0.07] p-4">
      <p className="text-[13px] text-saibyl-negative leading-relaxed">{message}</p>
      {retry && (
        <button
          type="button"
          onClick={retry}
          className="mt-2.5 text-[12px] text-saibyl-gold hover:underline"
        >
          Try again
        </button>
      )}
    </div>
  );
}
