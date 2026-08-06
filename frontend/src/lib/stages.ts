/**
 * The five steps, as data.
 *
 * This is the single declaration of the rail. The sidebar reads it, the stage
 * pages read it, `App.tsx` builds its routes from it, and the reachability test
 * walks it. There is deliberately no second list anywhere: two declarations of
 * a navigation is the "two sources of truth" class, and the symptom is a
 * surface that ships with no route to it — which is the exact defect this whole
 * rail exists to fix. Audiences, Companies and the entire scoreboard were built,
 * deployed, and reachable only by typing a URL.
 *
 * The order is real. Each step consumes what the one before it produced, and
 * `number` is shown because a founder should be able to see that.
 */

export type StageId = 'audience' | 'reactions' | 'answers' | 'buyers' | 'messages';

export interface StageDef {
  id: StageId;
  number: number;
  /** The nav label. One word. */
  label: string;
  /** What it is for, in the founder's words. Shown under the label. */
  blurb: string;
  /** The question the founder is actually asking when they open it. */
  ask: string;
  /** Path segment under `/app/products/:id/`. */
  segment: string;
}

export const STAGES: StageDef[] = [
  {
    id: 'audience',
    number: 1,
    label: 'Audience',
    blurb: 'who reacts to this',
    ask: 'Who is going to react to this?',
    segment: 'audience',
  },
  {
    id: 'reactions',
    number: 2,
    label: 'Reactions',
    blurb: 'what they said, and what they object to',
    ask: 'Will anyone actually want this — and what will they say against it?',
    segment: 'reactions',
  },
  {
    id: 'answers',
    number: 3,
    label: 'Answers',
    blurb: 'what to say back, and whether it worked',
    ask: 'What do I say to the people who said no?',
    segment: 'answers',
  },
  {
    id: 'buyers',
    number: 4,
    label: 'Buyers',
    blurb: 'real companies that match',
    ask: 'Who do I actually contact on Monday?',
    segment: 'buyers',
  },
  {
    id: 'messages',
    number: 5,
    label: 'Messages',
    blurb: 'which version wins',
    ask: 'Which version of this should I spend money on?',
    segment: 'messages',
  },
];

export function stageHref(productId: string, stage: StageId): string {
  const def = STAGES.find((s) => s.id === stage);
  return `/app/products/${productId}/${def ? def.segment : 'audience'}`;
}

export function stageDef(stage: StageId): StageDef {
  const def = STAGES.find((s) => s.id === stage);
  // The list is exhaustive over StageId, so this cannot be reached from typed
  // code. Throwing rather than defaulting because a silent fallback to stage 1
  // would render the wrong screen under the right heading.
  if (!def) throw new Error(`Unknown stage: ${stage}`);
  return def;
}

/* ------------------------------------------------------------------ */
/*  What the server says about one product                             */
/* ------------------------------------------------------------------ */

/** Where the company is. Asked per run, defaulting to whatever last run used. */
export interface Moment {
  id: string;
  label: string;
  /** `default` means nothing has run yet — say so rather than imply a memory. */
  source: 'last_run' | 'default';
}

export interface InheritedLine {
  label: string;
  href: string;
}

export interface StageAction {
  label: string;
  href: string;
}

/**
 * An input a stage did not get, and what its absence costs the answer.
 *
 * `consequence` is shown before any credits move. It is the whole reason the
 * rail can be open without being a trap.
 */
export interface MissingInput {
  headline: string;
  consequence: string;
  action: StageAction | null;
}

/**
 * A stage's stored answer, and why it does not describe the inputs shown above it.
 *
 * The same three fields as `MissingInput` and a separate type on purpose,
 * because it makes the opposite statement. `MissingInput` says *the next run
 * will be worse without this*; this says *what you are already looking at was
 * produced without it*. Mirrors `StaleResult` in
 * `backend/app/services/stages/product_state.py`.
 */
export interface StaleResult {
  headline: string;
  consequence: string;
  action: StageAction | null;
}

export interface AttentionLine {
  kind: string;
  text: string;
  href: string | null;
  weight: 'high' | 'low';
}

export interface StageState {
  id: StageId;
  number: number;
  label: string;
  blurb: string;
  href: string;
  /**
   * Three values, never two, and never a fourth called `disabled`.
   * `ready` and `degraded` both run; they differ in whether an input is
   * missing. `blocked` is the one case where running is meaningless, and it
   * always carries the action that unblocks it.
   */
  runnable: 'ready' | 'degraded' | 'blocked';
  /** What it has produced, in words. Null means nothing yet — not "nothing". */
  produced: string | null;
  /**
   * The run `produced` and `stale` describe.
   *
   * Sent so a page does not choose one for itself. `GET /simulations` orders on
   * `created_at` and the rail sorts on `completed_at or created_at`, so a run
   * that started earlier and finished later is the latest to one of them and
   * not the other. Null when nothing has finished.
   */
  produced_by: string | null;
  inherited: InheritedLine[];
  missing: MissingInput[];
  /**
   * Set when `produced` describes a run that did not receive what `inherited`
   * says this stage has. Null on every stage that cannot go stale, and on every
   * run that read what it was supposed to.
   */
  stale: StaleResult | null;
}

export interface ProductState {
  id: string;
  name: string;
  description: string | null;
  moment: Moment;
  stages: StageState[];
  /** Stages whose every wanted input is present. `degraded` does not count. */
  stages_ready: number;
  attention: AttentionLine[];
}

export function findStage(product: ProductState, id: StageId): StageState | null {
  return product.stages.find((s) => s.id === id) ?? null;
}
