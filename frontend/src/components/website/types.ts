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
};

/** Spellings the backend could plausibly use for the same five. */
const DIMENSION_ALIASES: Record<string, string> = {
  conversion_path: 'conversion',
  copy_clarity: 'copy',
  clarity: 'copy',
  accessibility: 'mobile',
  accessibility_mobile: 'mobile',
  mobile_accessibility: 'mobile',
};

/**
 * The founder-facing name and one-line reading of a dimension key.
 *
 * An unknown key falls through to its own words rather than to a blank — a
 * dimension the backend adds later should arrive readable, not invisible.
 */
export function dimensionWords(key: string): { name: string; help: string } {
  const normalized = key.trim().toLowerCase().replace(/[^a-z0-9]+/g, '_');
  const named =
    DIMENSION_WORDS[normalized] ??
    DIMENSION_WORDS[DIMENSION_ALIASES[normalized] ?? ''];
  if (named) return named;
  const readable = key.replace(/[_-]+/g, ' ').trim();
  return {
    name: readable.charAt(0).toUpperCase() + readable.slice(1),
    help: '',
  };
}
