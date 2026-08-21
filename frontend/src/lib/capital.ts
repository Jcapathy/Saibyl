/**
 * The family-office bank, as the client reads it.
 *
 * Types first, and they mirror `backend/app/services/capital/schema.py` field
 * for field — including the three fields a list vendor would have dropped.
 * `refusals`, `withheld_stale` and `unreadable` are answers, not error
 * channels: a founder told "four firms publish a position that rules you out"
 * and "we hold three more records we will not stand behind" can go and check
 * both. A founder handed a shorter list learns nothing and reads the shorter
 * list as the whole market.
 *
 * Two rules this file exists to keep on the client side:
 *
 * 1. **Every firm renders its `source_url`.** A recommendation a founder
 *    cannot trace back to a published page is one they cannot check, so there
 *    is no rendering here that omits it.
 * 2. **A refused inbound route is a stated position, not a missing field.**
 *    `warm_intro_only` and `no_inbound` carry no `value` by construction, and
 *    `inboundRoute` below returns them as refusals so no caller can render one
 *    as a lead with a hole in it.
 *
 * There is no contact affordance anywhere in this module, and there must not
 * be one. Saibyl holds no personal email address or phone number for anyone in
 * this bank — the privacy gate refuses to store them — so a UI implying we do
 * would be lying about our own database.
 *
 * Helpers live here rather than beside a component because a file that exports
 * both a hook and a component breaks React Fast Refresh, and because these are
 * facts about the record rather than about any one panel that shows it.
 */

/* ------------------------------------------------------------------ */
/*  The stored record                                                  */
/* ------------------------------------------------------------------ */

export type FirmType = 'single_family' | 'multi_family' | 'foundation';

export type InboundKind =
  | 'submission_form'
  | 'firm_address'
  | 'warm_intro_only'
  | 'no_inbound';

/** Public professional information only — `privacy.ALLOWED_CONTACT_FIELDS`. */
export interface FirmPerson {
  full_name: string;
  role_title: string;
  employer: string;
  public_profile_url: string | null;
  source_url: string;
  retrieved_at: string;
}

export interface InboundPath {
  kind: InboundKind;
  /** Null on both refusal kinds, by construction in the schema. */
  value: string | null;
  source_url: string;
}

export interface FamilyOffice {
  firm_name: string;
  domain: string | null;
  firm_type: FirmType;
  thesis: string;
  sectors: string[];
  stages: string[];
  check_size_low: number | null;
  check_size_high: number | null;
  geography: string[];
  notable_investments: string[];
  inbound_path: InboundPath;
  people: FirmPerson[];
  source_url: string;
  source_title: string;
  retrieved_at: string;
  verified_at: string | null;
  stale_after: string;
}

/* ------------------------------------------------------------------ */
/*  The result                                                         */
/* ------------------------------------------------------------------ */

export type MatchDimension =
  | 'sector'
  | 'stage'
  | 'check_size'
  | 'geography'
  | 'thesis'
  | 'objection_bridge';

export type Verdict = 'match' | 'refusal';

/** Why this firm, in both sides' actual words. Both quotes are verbatim. */
export interface MatchReason {
  dimension: MatchDimension;
  firm_quote: string;
  founder_quote: string;
  explanation: string;
}

export interface StaleRecord {
  firm_name: string;
  retrieved_at: string;
  stale_after: string;
  reason: string;
}

export interface ShortlistEntry {
  firm: FamilyOffice;
  verdict: Verdict;
  reasons: MatchReason[];
  objection_bridge: MatchReason | null;
  refusal_reason: string | null;
  access_note: string | null;
  score: number;
  score_components: Record<string, number>;
  retrieved_at: string;
  stale_after: string;
}

/** `GET /capital/firms` — the bank, with what it would not assert. */
export interface BankPage {
  firms: FamilyOffice[];
  withheld_stale: StaleRecord[];
  /** Rows that no longer satisfy the schema. Counted, logged, never served. */
  unreadable: number;
  as_of: string;
}

export type ShortlistStatus = 'building' | 'complete' | 'failed';

/** One stored `capital_shortlists` row, as the API returns it. */
export interface CapitalShortlist {
  id: string;
  project_id: string;
  simulation_id: string | null;
  status: ShortlistStatus;
  sector: string;
  stage: string;
  check_size_needed: number | null;
  matches: ShortlistEntry[];
  refusals: ShortlistEntry[];
  withheld_stale: StaleRecord[];
  notes: string[];
  firms_considered: number;
  matches_count: number;
  refusals_count: number;
  as_of: string;
  credits_charged: number;
  error_message: string | null;
  created_at: string;
  completed_at: string | null;
}

/* ------------------------------------------------------------------ */
/*  Labels                                                             */
/* ------------------------------------------------------------------ */

export const FIRM_TYPE_LABEL: Record<FirmType, string> = {
  single_family: 'One family',
  multi_family: 'Several families',
  foundation: 'Foundation',
};

/**
 * What each dimension of a match is, said as the founder would ask it.
 *
 * `objection_bridge` leads everywhere it appears, because it is the one signal
 * no list vendor can produce: the thing real buyers keep pushing back on,
 * meeting a firm that has published that it invests into exactly that.
 */
export const DIMENSION_LABEL: Record<MatchDimension, string> = {
  objection_bridge: 'They already take on what buyers push back on',
  thesis: 'What they publish, against what you wrote',
  sector: 'Sector',
  stage: 'Stage',
  check_size: 'Cheque size',
  geography: 'Where they invest',
};

/**
 * The stages a founder can pick from.
 *
 * A free-text box would let one typo turn every firm in the bank into a
 * refusal, because the backend decides a refusal by comparing the founder's
 * stage against the firm's *published* stages. The comparison is normalised
 * (`Pre-Seed`, `pre seed` and `preseed` are one stage), so this list only has
 * to carry the words, not their punctuation.
 */
/** The same six, short enough to read in a row of what counted toward a score. */
export const DIMENSION_SHORT: Record<MatchDimension, string> = {
  objection_bridge: 'the objection bridge',
  thesis: 'their thesis',
  sector: 'sector',
  stage: 'stage',
  check_size: 'cheque size',
  geography: 'geography',
};

export const STAGE_CHOICES: string[] = [
  'Pre-seed',
  'Seed',
  'Series A',
  'Series B',
  'Series C',
  'Growth',
];

/** What `GET /capital/firms` will filter on. Empty strings mean "everything". */
export interface BankFilters {
  sector: string;
  stage: string;
  firm_type: string;
}

export const EMPTY_FILTERS: BankFilters = { sector: '', stage: '', firm_type: '' };

export function hasFilters(filters: BankFilters): boolean {
  return (
    filters.sector.trim() !== '' || filters.stage !== '' || filters.firm_type !== ''
  );
}

export const FIRM_TYPE_CHOICES: { value: FirmType; label: string }[] = [
  { value: 'single_family', label: 'One family' },
  { value: 'multi_family', label: 'Several families' },
  { value: 'foundation', label: 'Foundation' },
];

/**
 * The sentence this whole module is built around, in one place.
 *
 * Rendered on every surface that shows a firm. It is not a disclaimer: it is
 * the reason the recommendation is worth reading, and the reason there is no
 * "send" button anywhere near it.
 */
export const NO_CONTACT_DETAILS =
  'We hold no personal email address or phone number for anyone here, and we ' +
  'never make contact for you. Every route below is one the firm published ' +
  'itself.';

/* ------------------------------------------------------------------ */
/*  Reading a record                                                   */
/* ------------------------------------------------------------------ */

export interface InboundRouteRead {
  /** True when the firm's published position is that it takes no inbound. */
  refused: boolean;
  /** What the firm says, in the UI's words. Always present. */
  headline: string;
  /** The route itself, or null when the firm refuses inbound. */
  value: string | null;
  /** Whether `value` is a URL that can be opened, rather than an address. */
  isUrl: boolean;
  source_url: string;
}

/**
 * One `inbound_path` as something a screen can render without deciding
 * anything.
 *
 * **The two refusal kinds are the reason this exists.** `warm_intro_only` and
 * `no_inbound` are the firm's stated position and carry no route — the schema
 * refuses to store one beside them, because a route stored next to "they take
 * no inbound" is a route somebody uses anyway. A renderer that reached for
 * `value` and found null would show a lead with a missing field. This returns
 * a refusal with the reason instead, so that rendering is not available.
 */
export function inboundRoute(path: InboundPath): InboundRouteRead {
  switch (path.kind) {
    case 'submission_form':
      return {
        refused: false,
        headline: 'They ask you to use their own form',
        value: path.value,
        isUrl: true,
        source_url: path.source_url,
      };
    case 'firm_address':
      return {
        refused: false,
        headline: 'They publish a firm address for approaches',
        value: path.value,
        isUrl: false,
        source_url: path.source_url,
      };
    case 'warm_intro_only':
      return {
        refused: true,
        headline: 'This firm takes introductions only',
        value: null,
        isUrl: false,
        source_url: path.source_url,
      };
    case 'no_inbound':
      return {
        refused: true,
        headline: 'This firm takes no inbound at all',
        value: null,
        isUrl: false,
        source_url: path.source_url,
      };
  }
}

/** `$250,000 to $2,000,000`, or null when the firm publishes no range. */
export function checkRange(firm: FamilyOffice): string | null {
  const { check_size_low: low, check_size_high: high } = firm;
  if (low !== null && high !== null) return `${money(low)} to ${money(high)}`;
  if (low !== null) return `${money(low)} and up`;
  if (high !== null) return `up to ${money(high)}`;
  // None beats a guess: a founder who finds one invented range has no reason
  // to believe any other field on the record.
  return null;
}

export function money(value: number): string {
  return `$${value.toLocaleString()}`;
}

/** `20 Aug 2026`. Invalid or missing dates render as an em dash, never as today. */
export function formatDay(value: string | null | undefined): string {
  if (!value) return '—';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return '—';
  return date.toLocaleDateString(undefined, {
    day: 'numeric',
    month: 'short',
    year: 'numeric',
  });
}

/** Whole days from `value` to `now`. Negative when `value` is in the future. */
export function daysSince(value: string, now: Date): number | null {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return null;
  return Math.floor((now.getTime() - date.getTime()) / 86_400_000);
}

/**
 * How old a claim is, in words.
 *
 * Rendered next to every record, because hiding the date is how a list
 * launders decay into confidence. A founder who can see that a thesis was read
 * eight months ago can weigh it; one shown a bare firm name cannot.
 */
export function ageInWords(retrievedAt: string, now: Date): string {
  const days = daysSince(retrievedAt, now);
  if (days === null) return 'date unknown';
  if (days <= 0) return 'read today';
  if (days === 1) return 'read yesterday';
  if (days < 60) return `read ${days} days ago`;
  const months = Math.round(days / 30);
  return `read about ${months} months ago`;
}

/**
 * When this record stops being asserted, in words — and how close that is.
 *
 * A record inside its last month is worth flagging: it is still current, and
 * the founder is about to lose it. Saying so beats a founder returning to find
 * a firm silently gone from a list they were working through.
 */
export function freshnessNote(staleAfter: string, now: Date): {
  text: string;
  closing: boolean;
} {
  const days = daysSince(staleAfter, now);
  if (days === null) return { text: 'no verification date on record', closing: false };
  const left = -days;
  if (left <= 0) {
    return { text: 'past its verification date', closing: true };
  }
  if (left <= 30) {
    return {
      text: `withheld from ${formatDay(staleAfter)} unless re-checked`,
      closing: true,
    };
  }
  return { text: `stands until ${formatDay(staleAfter)}`, closing: false };
}

/** `verrillfamily.com` from a URL, or the URL itself when it will not parse. */
export function hostOf(url: string): string {
  try {
    return new URL(url).hostname.replace(/^www\./, '');
  } catch {
    return url;
  }
}

/**
 * The dimensions that actually carried a score, in the order they were
 * weighted.
 *
 * Rendered so the ranking is legible rather than magic. The weights order the
 * list and gate nothing — no firm is hidden by a low score, and a refusal is
 * decided by the firm's published position rather than by a number falling
 * under a bar.
 */
const COMPONENT_ORDER: MatchDimension[] = [
  'objection_bridge',
  'thesis',
  'sector',
  'stage',
  'check_size',
  'geography',
];

export function countedDimensions(
  components: Record<string, number>,
): MatchDimension[] {
  return COMPONENT_ORDER.filter((name) => (components[name] ?? 0) > 0);
}
