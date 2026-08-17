/**
 * The IP Check tab's contract with the backend.
 *
 * The artifact shape is the ip-clearance-search skill's output contract,
 * written down as types so a drifting field is a compile error here rather
 * than an empty section in a founder's report. PRD §11: the clearance report
 * is a first-class artifact — versioned JSON plus the search record — and
 * every render carries the disclaimer verbatim.
 */

/* ------------------------------------------------------------------ */
/*  The one founder-facing name (PRD §10.3 — one constant, no          */
/*  scattered strings). The sidebar and the page both read this.       */
/* ------------------------------------------------------------------ */

export const IP_CHECK_NAME = 'IP Check';

/**
 * Rendered near the risk banner on every screen that shows results. The full
 * disclaimer arrives on the artifact and is rendered verbatim in the report
 * footer — this line is the short form that must never be missing.
 */
export const NOT_LEGAL_ADVICE = 'Automated research support — not legal advice.';

/**
 * Only used if a run somehow arrives without its disclaimer. The report
 * footer must never be empty, so the skill's standard sentence is the floor.
 */
export const FALLBACK_DISCLAIMER =
  'This is automated research support, not legal advice, and not a clearance ' +
  'or freedom-to-operate opinion. Consult a registered patent or trademark ' +
  'attorney before filing, launch, or enforcement decisions.';

/* ------------------------------------------------------------------ */
/*  Run rows                                                           */
/* ------------------------------------------------------------------ */

export type ClearanceTier = 'QUICK' | 'STANDARD' | 'COMPREHENSIVE';
export type ClearanceStatus = 'queued' | 'running' | 'complete' | 'failed';
export type RiskTier = 'GREEN' | 'YELLOW' | 'RED';

/** How each tier is named to a founder, everywhere it appears. */
export const TIER_LABELS: Record<ClearanceTier, string> = {
  QUICK: 'Snapshot — free',
  STANDARD: 'Full search',
  COMPREHENSIVE: 'Deep search + watch-list',
};

/** The short form for chips and list rows. */
export const TIER_SHORT: Record<ClearanceTier, string> = {
  QUICK: 'Snapshot',
  STANDARD: 'Full search',
  COMPREHENSIVE: 'Deep search',
};

/** What a run row looks like in the list endpoint (no artifact bodies). */
export interface ClearanceListRow {
  id: string;
  item: string;
  tier: ClearanceTier;
  status: ClearanceStatus;
  risk: RiskTier | null;
  created_at: string;
}

/** The full row from POST /clearance and GET /clearance/{id}. */
export interface ClearanceRun {
  id: string;
  item: string;
  tier: ClearanceTier;
  status: ClearanceStatus;
  risk?: RiskTier | null;
  created_at: string;
  /** A sentence when status is `failed`. */
  error_message?: string | null;
  /** Present when status is `complete`. */
  artifact?: ClearanceArtifact | null;
  /** Present when status is `complete`; the fallback render if the artifact
   *  cannot be read. */
  report_markdown?: string | null;
}

/* ------------------------------------------------------------------ */
/*  The artifact — ip-clearance-search output contract v1.0            */
/* ------------------------------------------------------------------ */

export type TrademarkStatus =
  | 'CLEAR_ON_SEARCH'
  | 'CONFLICTS_FOUND'
  | 'NEEDS_REVIEW'
  | 'NOT_SEARCHED';

export interface TrademarkConflict {
  mark: string;
  serial_or_reg: string;
  owner: string;
  live: boolean;
  classes: number[];
  goods_services: string;
  similarity: 'identical' | 'close' | 'related-goods';
}

export interface TrademarkSection {
  status: TrademarkStatus;
  marks_checked: string[];
  conflicts: TrademarkConflict[];
  /** Where to run the official search when this run could not. */
  official_search_link: string | null;
}

export type ArtStatus = 'granted' | 'pending' | 'allowed' | 'abandoned' | 'expired';

export interface ClosestArt {
  /** US patent, application or publication number. */
  number: string;
  title: string;
  assignee: string;
  filed: string;
  priority: string | null;
  status: ArtStatus;
  /** Paraphrase of the independent claim elements. */
  claim_requirements: string;
  /** Elements the founder's item does not share. */
  differences: string;
  risk: RiskTier;
}

export interface PatentsSection {
  overall_risk: RiskTier;
  records_screened: number;
  closest_art: ClosestArt[];
  /** Mechanisms with zero relevant hits. */
  whitespace_signals: string[];
  /** Mechanisms with dense live art. */
  crowded_areas: string[];
}

export interface NotablePending {
  app: string;
  title: string;
  assignee: string;
  status: string;
}

export interface ProvisionalPriority {
  provisional: string;
  via: string;
}

export interface PendingLandscape {
  notable_pending: NotablePending[];
  provisional_priorities_revealed: ProvisionalPriority[];
  /** The explicit 18-month blind-spot sentence, rendered verbatim. */
  blind_spot_note: string;
}

export interface QueryRun {
  track: string;
  query: string;
  hits: number;
}

export interface WatchListEntry {
  target: string;
  reason: string;
}

export interface ClearanceArtifact {
  skill: string;
  version: string;
  search_date: string;
  item: string;
  assumptions: string[];
  tier: ClearanceTier;
  tracks_run: string[];
  trademark: TrademarkSection;
  patents: PatentsSection;
  pending_landscape: PendingLandscape;
  queries_run: QueryRun[];
  watch_list: WatchListEntry[];
  limitations: string[];
  disclaimer: string;
}
