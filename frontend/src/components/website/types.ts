/**
 * The site check, as the API spells it.
 *
 * `POST /website/check` starts one; the row moves queued → capturing → judging
 * and lands on complete or failed. When it completes it carries a `critique`
 * and a `document_id` — the page's text has been written up as a document, so
 * the audience step reads it exactly the way it reads an uploaded deck.
 *
 * The dimension keys are the API's words, not the founder's. The renaming
 * lives here in one map rather than at each render site, so a key the backend
 * adds later degrades to its own name instead of to a blank.
 */

export type SiteCheckStatus =
  | 'queued'
  | 'capturing'
  | 'judging'
  | 'complete'
  | 'failed';

export type SiteCheckUnderwayStatus = 'queued' | 'capturing' | 'judging';

export type SiteFindingSeverity = 'critical' | 'major' | 'minor';

/** One thing a critic saw on the page, with the evidence and the way out. */
export interface SiteFinding {
  severity: SiteFindingSeverity;
  /** Where on the page — a selector or a named area. Shown as-is. */
  region: string | null;
  /** The page's own words, verbatim. */
  quote: string | null;
  why: string;
  fix: string;
}

export interface SiteDimension {
  key: string;
  score: number;
  findings: SiteFinding[];
  strengths: string[];
}

export interface SiteCritiqueResult {
  overall_score: number;
  page_takeaway: string;
  dimensions: SiteDimension[];
}

/** `POST /website/check`, `GET /website/check/{id}` — the snapshot row. */
export interface SiteCheck {
  id: string;
  url: string;
  status: SiteCheckStatus;
  /** Present once the check is complete. */
  critique?: SiteCritiqueResult | null;
  /** The document the page's text became, once complete. */
  document_id?: string | null;
  error_message?: string | null;
  screenshot_paths?: Record<string, string> | string[] | null;
  /** The site the founder asked to be measured against, when they named one. */
  reference_url?: string | null;
  reference_screenshot_path?: string | null;
  /** Where the page's craft sits on the seven-level ladder, when judged. */
  maturity_level?: number | null;
  created_at: string;
}

/** `GET /website/check?project_id=…` — one row of the listing. */
export interface SiteCheckListItem {
  id: string;
  url: string;
  status: SiteCheckStatus;
  overall_score?: number | null;
  created_at: string;
}

/* ------------------------------------------------------------------ */
/*  Status words                                                       */
/* ------------------------------------------------------------------ */

export function isCheckUnderway(
  status: string | null | undefined,
): status is SiteCheckUnderwayStatus {
  return status === 'queued' || status === 'capturing' || status === 'judging';
}

/** The sentence shown while the worker is on each leg of the check. */
export const CHECK_PROGRESS: Record<SiteCheckUnderwayStatus, string> = {
  queued: 'Your site is in the queue — reading starts in a moment.',
  capturing: 'Loading your page the way a buyer’s browser would…',
  judging: 'Reading it the way a first-time buyer would…',
};

/* ------------------------------------------------------------------ */
/*  Dimension names                                                    */
/* ------------------------------------------------------------------ */

const DIMENSION_WORDS: Record<string, { name: string; help: string }> = {
  hierarchy: {
    name: 'First impression',
    help: 'Can a stranger tell what this is — and what to do — in five seconds?',
  },
  credibility: {
    name: 'Trust',
    help: 'Whether the page gives a stranger a reason to believe you.',
  },
  conversion: {
    name: 'Path to action',
    help: 'The route from landing to acting, and what gets in the way.',
  },
  copy: {
    name: 'The words',
    help: 'What the page says, and what a reader actually takes away.',
  },
  mobile: {
    name: 'On a phone',
    help: 'How the page holds up on a small screen.',
  },
  design: {
    name: 'The look',
    help: 'Type, color, spacing — measured in numbers, not judged by feel.',
  },
};

/** Spellings the backend could plausibly use for the same six. */
const DIMENSION_ALIASES: Record<string, string> = {
  conversion_path: 'conversion',
  copy_clarity: 'copy',
  clarity: 'copy',
  accessibility: 'mobile',
  accessibility_mobile: 'mobile',
  mobile_accessibility: 'mobile',
  design_system: 'design',
  design_craft: 'design',
};

/** One spelling per dimension, whichever spelling the backend used. */
function canonicalKey(key: string): string {
  const normalized = key.trim().toLowerCase().replace(/[^a-z0-9]+/g, '_');
  return DIMENSION_ALIASES[normalized] ?? normalized;
}

/**
 * The founder-facing name and one-line reading of a dimension key.
 *
 * An unknown key falls through to its own words rather than to a blank — a
 * dimension the backend adds later should arrive readable, not invisible.
 */
export function dimensionWords(key: string): { name: string; help: string } {
  const named = DIMENSION_WORDS[canonicalKey(key)];
  if (named) return named;
  const readable = key.replace(/[_-]+/g, ' ').trim();
  return {
    name: readable.charAt(0).toUpperCase() + readable.slice(1),
    help: '',
  };
}

/**
 * Whether a dimension is the design one, under any of its spellings. The
 * design card is the one that renders measured values and leads the grid
 * when a reference site was named, so its identity has to survive a backend
 * spelling change the same way its display name does.
 */
export function isDesignDimension(key: string): boolean {
  return canonicalKey(key) === 'design';
}

/* ------------------------------------------------------------------ */
/*  Design maturity                                                    */
/* ------------------------------------------------------------------ */

/**
 * The design maturity level of a finished check, if the backend sent one.
 *
 * The contract for where this number lives is still settling — it may arrive
 * on the row itself, on the critique, or inside the design dimension's own
 * payload. This looks in each place in that order and takes the first value
 * that reads as a level: a finite number from 1 to 7 (a numeric string
 * counts). Anything else — absent, out of range, unparseable — is treated as
 * "the backend did not judge this", and the caller renders nothing.
 */
export function maturityLevel(check: SiteCheck): number | null {
  const candidates: unknown[] = [check.maturity_level];

  const critique = check.critique;
  if (critique) {
    const extra = critique as unknown as Record<string, unknown>;
    candidates.push(extra.maturity_level);
    const designPayload = extra.design;
    if (designPayload && typeof designPayload === 'object') {
      candidates.push((designPayload as Record<string, unknown>).maturity_level);
    }
    for (const dimension of critique.dimensions) {
      if (!isDesignDimension(dimension.key)) continue;
      const carried = dimension as unknown as Record<string, unknown>;
      candidates.push(carried.maturity_level, carried.maturity);
    }
  }

  for (const value of candidates) {
    if (value === null || value === undefined || value === '') continue;
    const level = Math.round(Number(value));
    if (Number.isFinite(level) && level >= 1 && level <= 7) return level;
  }
  return null;
}
