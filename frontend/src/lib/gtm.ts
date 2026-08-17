/**
 * Prospect discovery, as the frontend presents it.
 *
 * Mirrors `backend/app/services/gtm/`. Nothing here computes a finding — it
 * translates the backend's vocabulary into sentences a solo founder can read.
 *
 * Three rules are enforced by what this module does and does not export.
 *
 * **1. There is no percentage formatter for `match_score`, and there must not
 * be one.** `scoring.py` states it plainly: the number is "0..1 rank ordering
 * against this archetype. Not a probability and not a fit score in any
 * calibrated sense." Rendering `0.73` as "73% match" would invent precision the
 * number does not carry, which is the exact defect class this product exists to
 * remove. The list is ordered by it and shows a position; `SCORE_COMPONENT_COPY`
 * explains *why this ranked here* without asserting a measurement. If a future
 * reader wants a percentage, the thing to change is `scoring.py` — by deriving
 * the weights from qualification feedback — not this file.
 *
 * **2. An unevidenced field is absent, not "Unknown".** `present()` is the only
 * way a nullable candidate field reaches a component, and it returns `null`
 * rather than a placeholder. Extraction populates a field only when a quote from
 * a retrieved URL says so; a dash in that slot would read as data.
 *
 * **3. A failed run and an empty run are different facts.** `runOutcome()` is
 * the single place that distinction is drawn, so no screen can accidentally
 * collapse "the search provider was unreachable" into "there is nobody out
 * there" — the second is a real and useful finding about a market, the first is
 * an outage.
 */

import type {
  DiscoveryAngle,
  DiscoveryRun,
  DiscoveryRunStatus,
} from '@/types';

/* ── Backend limits, mirrored ───────────────────────────────────────── */

/**
 * `query_compiler.MAX_QUERIES_PER_DISCOVERY`. The server caps rather than
 * erroring, so this bounds the picker instead of validating it — a client
 * asking for more gets the cap back, not a 422.
 */
export const MAX_QUERIES_PER_DISCOVERY = 12;

/**
 * `discovery.DISCOVERY_DEADLINE_SECONDS` — the server's *ceiling*, for the
 * largest discovery the estimate offers. Discovery runs inline in the request
 * that starts it, so this is also the longest the founder waits.
 *
 * The server's actual deadline scales with the query count
 * (`discovery_deadline_seconds`); a three-query run gives up far sooner. Only
 * the ceiling is mirrored, because this is used to size a timeout and to decide
 * when a run has stopped responding — both of which need the upper bound.
 *
 * `test_the_client_waits_longer_than_the_server_deadline` fails if this drifts
 * from the backend constant.
 */
export const DISCOVERY_DEADLINE_SECONDS = 360;

/**
 * How long to let `POST /gtm/discover` hang before giving up on the response.
 *
 * Comfortably above the server's own deadline: the run closes `partial` at 180s
 * and still has to write its counters and reply. A client timeout below that
 * would abandon a run that is about to succeed — and the credits are already
 * spent, so the founder would pay for a result they never saw.
 */
export const DISCOVER_REQUEST_TIMEOUT_MS = (DISCOVERY_DEADLINE_SECONDS + 60) * 1000;

/* ── Vocabulary ─────────────────────────────────────────────────────── */

/**
 * The three angles, in words a founder can act on.
 *
 * Never shown as `firmographic`. The reader may have shipped a product without
 * ever meeting the term, and a label nobody can parse makes the query preview —
 * the whole point of showing the searches before spending — unreadable.
 */
export const ANGLE_COPY: Record<DiscoveryAngle, { label: string; hint: string }> = {
  firmographic: {
    label: 'Who they are',
    hint: 'Companies that look like your buyers on paper — the sort of business, the sort of person running it.',
  },
  incumbent_tooling: {
    label: 'What they already use',
    hint: 'Companies visibly running the tools your buyers would be switching off. Usually the strongest signal.',
  },
  pain_trigger: {
    label: 'What they complain about',
    hint: 'Companies saying in public that they have the problem you solve.',
  },
};

/** Candidate fields, as evidence entries name them. */
export const EVIDENCE_FIELD_COPY: Record<string, string> = {
  one_liner: 'What they do',
  domain: 'Website',
  employee_count_range: 'Company size',
  industry: 'Industry',
  hq_location: 'Where they are',
  incumbent_tooling: 'What they already use',
};

/**
 * The five ingredients of the ordering.
 *
 * Shown as reasons this company landed where it did in the list — never as
 * scores out of anything. The weights behind them are declared priors with no
 * outcome data behind them yet, which is exactly why the founder sees the parts
 * rather than a single number with no referent.
 */
export const SCORE_COMPONENT_COPY: Record<string, string> = {
  incumbent_overlap: 'Already uses the tools your buyers use',
  evidence_density: 'How much of this record came from a source we can show you',
  firmographic_completeness: 'How much we could actually find out about them',
  criteria_signal: 'Talks about the things your buyers judge on',
  pain_signal: 'Mentions the problem your buyers have',
};

/** Audience fields, as `DiscoveryQuery.derived_from` names them. */
export const DERIVED_FROM_COPY: Record<string, string> = {
  role: 'their job',
  label: 'what you call them',
  industry: 'their industry',
  category: 'your category',
  seniority: 'how senior they are',
  incumbent_tooling: 'what they use today',
  evaluation_criteria: 'what they judge you on',
  pains: 'what frustrates them',
  goals: 'what they want to get done',
  skepticism_triggers: 'what would make them doubt you',
  product_summary: 'what your product does',
};

/** Plain-English rendering of one `derived_from` entry, unknown keys included. */
export function derivedFromLabel(field: string): string {
  return DERIVED_FROM_COPY[field] ?? field.replace(/_/g, ' ');
}

/* ── Absence ────────────────────────────────────────────────────────── */

/**
 * A nullable candidate field, or `null` when no source stated it.
 *
 * The empty string is folded into `null` on purpose: `one_liner` is `NOT NULL
 * DEFAULT ''` in migration 027, so "" is the same fact as a null `industry` —
 * nothing was evidenced. Both must render as nothing at all.
 */
export function present(value: string | null | undefined): string | null {
  const trimmed = (value ?? '').trim();
  return trimmed.length > 0 ? trimmed : null;
}

/** A non-empty list, or `null`. Same reasoning as `present`. */
export function presentList(values: string[] | null | undefined): string[] | null {
  const kept = (values ?? []).map((v) => v.trim()).filter(Boolean);
  return kept.length > 0 ? kept : null;
}

/**
 * The host of a URL, for showing where a claim came from at a glance.
 *
 * Returns `null` rather than throwing on a malformed URL — the link itself is
 * still rendered from the raw string, because a URL this cannot parse is still
 * the URL the record cites and hiding it would break traceability.
 */
export function sourceHost(url: string): string | null {
  try {
    return new URL(url).hostname.replace(/^www\./, '');
  } catch {
    return null;
  }
}

/* ── Run outcomes ───────────────────────────────────────────────────── */

/**
 * What actually happened on a run, as a closed set.
 *
 * `failed` and `empty` are separate members and no caller may merge them. A
 * `failed` run reached no provider and therefore learned nothing; a `completed`
 * run with zero candidates searched the market and found nobody, which is a
 * finding the founder can act on. Showing the same empty state for both would
 * tell a founder their market is empty when the truth is that a vendor was down.
 */
export type RunOutcome =
  | { kind: 'running'; stalled: boolean }
  | { kind: 'failed' }
  | { kind: 'partial' }
  | { kind: 'empty' }
  | { kind: 'found' };

/** Seconds since a run was created. */
export function runAgeSeconds(run: DiscoveryRun, now: number = Date.now()): number {
  const started = new Date(run.created_at).getTime();
  if (!Number.isFinite(started)) return 0;
  return Math.max(0, (now - started) / 1000);
}

/**
 * Is this run past the point where it should have closed itself?
 *
 * There is no reaper. If the API process dies mid-run the row stays `running`
 * with a null `completed_at` forever — `discovery.py` names this as the honest
 * limit of the current infrastructure. This is what makes that visible rather
 * than leaving a founder watching a spinner that will never resolve. A generous
 * multiple of the deadline, so a genuinely slow run is not accused of dying.
 */
export function isStalled(run: DiscoveryRun, now: number = Date.now()): boolean {
  if (run.status !== 'running' || run.completed_at) return false;
  return runAgeSeconds(run, now) > DISCOVERY_DEADLINE_SECONDS * 2;
}

export function runOutcome(run: DiscoveryRun, now: number = Date.now()): RunOutcome {
  if (run.status === 'running') return { kind: 'running', stalled: isStalled(run, now) };
  if (run.status === 'failed') return { kind: 'failed' };
  if (run.status === 'partial') return { kind: 'partial' };
  return run.candidates_found > 0 ? { kind: 'found' } : { kind: 'empty' };
}

export type RunTone = 'positive' | 'negative' | 'warning' | 'neutral' | 'active';

export interface RunPresentation {
  /** Four or five words. Never the raw status value. */
  headline: string;
  /** A sentence saying what the founder is actually looking at. */
  detail: string;
  tone: RunTone;
}

/**
 * How to describe one run.
 *
 * Deliberately one function rather than a lookup keyed on `status`: the
 * interesting distinction — a completed run that found nobody — is not
 * expressible as a status, and a `Record<DiscoveryRunStatus, …>` would have
 * quietly forced it to share a cell with a successful run.
 */
export function describeRun(run: DiscoveryRun, now: number = Date.now()): RunPresentation {
  const outcome = runOutcome(run, now);
  const found = `${run.candidates_found} ${run.candidates_found === 1 ? 'company' : 'companies'}`;

  switch (outcome.kind) {
    case 'running':
      return outcome.stalled
        ? {
            headline: 'Stopped responding',
            detail:
              'This search started but never reported back, which usually means the server restarted while it was working. Anything it had already found was saved and is in your list. Nothing more will arrive — start a new search when you are ready.',
            tone: 'warning',
          }
        : {
            headline: 'Searching now',
            detail: `Working through ${run.query_count} ${run.query_count === 1 ? 'search' : 'searches'}. Companies are saved as each one finishes, so anything found so far is already yours.`,
            tone: 'active',
          };

    case 'failed':
      return {
        headline: 'The search could not run',
        detail:
          'We could not reach the search service, so nothing was looked up. This says nothing about your market — it is our side that failed. Try again shortly.',
        tone: 'negative',
      };

    case 'partial':
      return {
        headline: 'Finished early',
        detail: `${run.queries_completed} of ${run.query_count} searches finished before this ran out of time, and ${found} were saved. What you have is real; there is just less of it than a full search would have found.`,
        tone: 'warning',
      };

    case 'empty':
      return {
        headline: 'Searched everything, found nobody',
        detail: `All ${run.query_count} ${run.query_count === 1 ? 'search' : 'searches'} ran and came back with no companies matching what you described. That is a real answer about this market, not an error — the searches worked, there was simply nothing to return.`,
        tone: 'neutral',
      };

    case 'found':
      return {
        headline: `Found ${found}`,
        detail: `All ${run.query_count} ${run.query_count === 1 ? 'search' : 'searches'} ran.${
          run.queries_empty > 0
            ? ` ${run.queries_empty} of them came back with nothing, which is normal.`
            : ''
        }`,
        tone: 'positive',
      };
  }
}

/** The palette a tone maps to. Kept beside the tones so the two cannot drift. */
/* Light-ground values: RunCard paints headline text and icons from these
   directly, so each must hold ≥4.5:1 on a white card. */
export const TONE_COLOR: Record<RunTone, string> = {
  positive: '#0e7d55',
  negative: '#d92d3c',
  warning: '#b45309',
  neutral: '#60718e',
  active: '#286cf0',
};

/* ── Money ──────────────────────────────────────────────────────────── */

/**
 * A credit count, grouped.
 *
 * Credits are what the founder is actually charged and the only figure quoted
 * before a run. The dollar estimates on `DiscoveryCostEstimate` are Saibyl's
 * serving cost and margin — internal numbers that would mean nothing next to a
 * "start" button, so no screen here renders them.
 */
export function formatCredits(credits: number): string {
  return credits.toLocaleString();
}

/** Statuses that mean the run is over, whatever the outcome. */
export function isTerminal(status: DiscoveryRunStatus): boolean {
  return status !== 'running';
}
