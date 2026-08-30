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
  // The three counted dimensions. Until 2026-08-30 none of them was named
  // here, so each fell through to the fallback and rendered as its own bare
  // key — a founder read "Measured" and "Standard" as headings and had to
  // work out what they meant.
  measured: {
    name: 'Consistency',
    help: 'Whether the page uses one system — or whatever each piece shipped with.',
  },
  standard: {
    name: 'Craft',
    help: 'The things a good page does, held to one standard rather than to a rival.',
  },
  found: {
    name: 'Being found',
    help: 'What a model reads when someone asks it to recommend a tool like yours.',
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

/* ------------------------------------------------------------------ */
/*  The change list                                                    */
/* ------------------------------------------------------------------ */

const SEVERITY_RANK: Record<string, number> = { critical: 0, major: 1, minor: 2 };

export type RankedChange = {
  finding: SiteFinding;
  dimensionKey: string;
  dimensionName: string;
};

/**
 * Every finding across every dimension, worst first.
 *
 * **This is the list the report opens with, and that ordering is the point.**
 * Until 2026-08-30 the report led with the overall score — a mean across nine
 * dimensions — and the founder's reading of that was that the product had
 * become "a very mechanical scoring mechanism that ignores the original
 * intent". A mean is a summary of work already done: it tells a founder how
 * they did, never what to do. The score is still rendered, one block lower,
 * because it is how a revision is seen to move.
 *
 * Sorted by severity alone, then left in the order the dimensions arrived.
 * `sort` is stable in every engine this ships to, so two findings of equal
 * severity keep the backend's ordering — which matters because at least one
 * dimension orders its own findings as an argument rather than a list: "being
 * found" puts crawler access first, since nothing else on that card is worth
 * doing until a machine is allowed to read the page at all.
 *
 * **It lives here rather than beside the component that renders it** because
 * `npm run build` runs `tsc -b`, and a test importing a `.tsx` fails that pass
 * with `--jsx is not set` while `vitest` goes green. This file is the one the
 * tests can reach, and the function is pure data anyway.
 */
export function rankedChanges(dimensions: SiteDimension[]): RankedChange[] {
  return dimensions
    .flatMap((dimension) =>
      dimension.findings.map((finding) => ({
        finding,
        dimensionKey: dimension.key,
        dimensionName: dimensionWords(dimension.key).name,
      })),
    )
    .sort(
      (a, b) =>
        (SEVERITY_RANK[a.finding.severity] ?? 3) -
        (SEVERITY_RANK[b.finding.severity] ?? 3),
    );
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

/* ------------------------------------------------------------------ */
/*  The revised page                                                   */
/* ------------------------------------------------------------------ */

/**
 * `POST /website/revision {snapshot_id}` drafts an improved page and has the
 * same reviewers score it again. The row moves queued → generating → judging
 * and lands on complete or failed. The backend for this is being built beside
 * this frontend, so every reader below treats the contract as provisional:
 * absent fields degrade to "not shown", never to a crash or a fabricated zero.
 */
export const REVISION_PATH = '/website/revision';

/**
 * The room-run router, in one place. The backend's spelling of this prefix is
 * still settling — if it lands somewhere else, this constant is the only line
 * that changes. `GET {here}/eligibility?project_id=` and `POST {here}/run`.
 */
export const WEBSITE_ROOM_PATH = '/website-room';

export type SiteRevisionStatus =
  | 'queued'
  | 'generating'
  | 'judging'
  | 'complete'
  | 'failed';

/**
 * Anything that is not finished counts as underway, so a status the backend
 * adds mid-flight (a fourth working state) keeps the poll alive instead of
 * freezing the panel on an unknown word.
 */
export function isRevisionUnderway(status: string | null | undefined): boolean {
  return Boolean(status) && status !== 'complete' && status !== 'failed';
}

/** The founder's words for each leg of the draft. */
export const REVISION_STATUS_WORDS: Record<SiteRevisionStatus, string> = {
  queued: 'Waiting',
  generating: 'Writing the new page',
  judging: 'The reviewers are scoring it',
  complete: 'Done',
  failed: 'Did not finish',
};

export function revisionStatusWord(status: string): string {
  return (
    (REVISION_STATUS_WORDS as Record<string, string>)[status] ??
    'Working on the new page'
  );
}

/**
 * `scores_before` / `scores_after` — `{overall, <dimension>: int}`. Typed
 * loose because the exact keys are the judge's, not ours; the readers below
 * pull numbers out defensively.
 */
export type RevisionScores = Record<string, unknown>;

/** One paste-ready prompt for the founder's coding tool. */
export interface FixPrompt {
  title: string;
  scope: string;
  prompt: string;
}

/**
 * A statement on the new page with no basis in the founder's own page.
 *
 * The rewrite is told twice, in plain words, never to invent a fact. A live
 * fintech revision did it anyway — SOC 2, ISO 27001, PCI DSS, a banking
 * regulator, a whole fee table — and the six critics scored that page *up*,
 * because they judge a screenshot and never see the source page's facts. The
 * backend now scans every generated document and sends what it finds here.
 */
export interface UnsupportedClaim {
  /** `certification` is the dangerous one: a badge is acted on, not just read. */
  kind: 'certification' | 'figure' | 'scale' | string;
  /** The claim itself — "SOC 2", "2.9%", "4,000 teams". */
  text: string;
  /** The sentence it sits in, so the founder can find it on the page. */
  quote: string;
}

/** `POST /website/revision`, `GET /website/revision/{id}` — the draft row. */
export interface SiteRevisionRow {
  id: string;
  status: string;
  snapshot_id?: string;
  rounds?: number | null;
  best_round?: number | null;
  scores_before?: RevisionScores | null;
  scores_after?: RevisionScores | null;
  /** Same shape as a check's critique, for the page as it now reads. */
  critique_after?: SiteCritiqueResult | null;
  fix_prompts?: unknown;
  /**
   * Claims the new page makes that the founder's page never made. `null` on
   * rows written before the scan existed, `[]` once it has run and found
   * nothing — the two must not be conflated, since only the second is a
   * clean bill of health.
   */
  unsupported_claims?: unknown;
  error_message?: string | null;
  created_at?: string | null;
}

/** One row of `GET /website/revision?snapshot_id=`, after normalising. */
export interface SiteRevisionListItem {
  id: string;
  status: string;
  overall_before: number | null;
  overall_after: number | null;
  created_at: string;
}

const OVERALL_KEYS = ['overall', 'overall_score', 'total'];

/**
 * The per-dimension scores, whichever shape they arrived in.
 *
 * `revision_tasks.py` writes `{overall, dimensions: {credibility: 58, …}}`
 * while this file was written expecting the dimensions flat alongside
 * `overall`. Nothing reconciled the two, so `scoreDeltas` iterated top-level
 * keys, found only `overall` and `dimensions`, coerced the nested object with
 * `Number({...})` → NaN, and produced an empty list. **The entire
 * per-dimension before/after table has always rendered as nothing** — the
 * proof-of-improvement the revision loop exists to show.
 *
 * This is the same asymmetry that was fixed once already on the writer side
 * (see the comment at `revision_tasks.py:174`); the reader was missed. Both
 * shapes are accepted here rather than picking one, because rows written
 * before that fix carry the old shape and a founder's past revision should
 * not silently lose its table.
 */
function dimensionScores(
  scores: RevisionScores | null | undefined,
): Record<string, unknown> {
  if (!scores) return {};
  const nested = (scores as Record<string, unknown>).dimensions;
  if (nested && typeof nested === 'object' && !Array.isArray(nested)) {
    return nested as Record<string, unknown>;
  }
  return scores as Record<string, unknown>;
}

function scoreOf(
  scores: RevisionScores | null | undefined,
  key: string,
): number | null {
  if (!scores) return null;
  // `overall` stays at the top level in both shapes; dimensions may be nested.
  const source = OVERALL_KEYS.includes(key.toLowerCase())
    ? (scores as Record<string, unknown>)
    : dimensionScores(scores);
  const value = source[key];
  if (value === null || value === undefined || value === '') return null;
  const n = Number(value);
  return Number.isFinite(n) ? Math.round(n) : null;
}

/** The overall number out of a scores object, under any of its spellings. */
export function overallScore(
  scores: RevisionScores | null | undefined,
): number | null {
  for (const key of OVERALL_KEYS) {
    const n = scoreOf(scores, key);
    if (n !== null) return n;
  }
  return null;
}

export interface ScoreDelta {
  key: string;
  before: number | null;
  after: number | null;
}

/**
 * The per-dimension rows of the before/after header: every key either side
 * carries a number for, minus the overall. Order follows the after scores —
 * the page as it now stands — with before-only stragglers appended.
 */
export function scoreDeltas(
  before: RevisionScores | null | undefined,
  after: RevisionScores | null | undefined,
): ScoreDelta[] {
  const keys: string[] = [];
  for (const source of [after, before]) {
    if (!source) continue;
    // Read the dimension names from wherever they live, so a nested payload
    // contributes its dimensions rather than the literal key "dimensions".
    for (const key of Object.keys(dimensionScores(source))) {
      if (OVERALL_KEYS.includes(key.toLowerCase())) continue;
      if (key === 'dimensions') continue;
      if (scoreOf(after, key) === null && scoreOf(before, key) === null) continue;
      if (!keys.includes(key)) keys.push(key);
    }
  }
  return keys.map((key) => ({
    key,
    before: scoreOf(before, key),
    after: scoreOf(after, key),
  }));
}

/**
 * A list row as this frontend spells it, from whatever the backend sent.
 * The listing's field names are the loosest part of the contract, so each
 * number is probed under its plausible spellings and an unusable row (no id)
 * is dropped rather than rendered blank.
 */
export function asRevisionListItem(raw: unknown): SiteRevisionListItem | null {
  if (!raw || typeof raw !== 'object') return null;
  const row = raw as Record<string, unknown>;
  const id = typeof row.id === 'string' && row.id ? row.id : null;
  if (!id) return null;

  const first = (...values: unknown[]): number | null => {
    for (const value of values) {
      if (value === null || value === undefined || value === '') continue;
      const n = Number(value);
      if (Number.isFinite(n)) return Math.round(n);
    }
    return null;
  };

  return {
    id,
    status: typeof row.status === 'string' ? row.status : 'queued',
    overall_before:
      first(row.overall_before, row.before_overall, row.score_before) ??
      overallScore(row.scores_before as RevisionScores | null | undefined),
    overall_after:
      first(row.overall_after, row.after_overall, row.score_after) ??
      overallScore(row.scores_after as RevisionScores | null | undefined),
    created_at: typeof row.created_at === 'string' ? row.created_at : '',
  };
}

/**
 * The unsupported claims off a draft row, with malformed entries dropped.
 *
 * Kind is passed through rather than validated against a list: a kind this
 * build has never heard of still describes a real claim, and dropping it would
 * hide a fabrication from the one person who can check it.
 */
export function unsupportedClaims(row: SiteRevisionRow): UnsupportedClaim[] {
  const raw = row.unsupported_claims;
  if (!Array.isArray(raw)) return [];
  const out: UnsupportedClaim[] = [];
  for (const entry of raw) {
    if (!entry || typeof entry !== 'object') continue;
    const c = entry as Record<string, unknown>;
    const text = typeof c.text === 'string' ? c.text.trim() : '';
    if (!text) continue;
    out.push({
      kind: typeof c.kind === 'string' ? c.kind : 'figure',
      text,
      quote: typeof c.quote === 'string' ? c.quote.trim() : '',
    });
  }
  return out;
}

/** The prompt blocks off a draft row, with malformed entries dropped. */
export function fixPrompts(row: SiteRevisionRow): FixPrompt[] {
  const raw = row.fix_prompts;
  if (!Array.isArray(raw)) return [];
  const out: FixPrompt[] = [];
  for (const entry of raw) {
    if (!entry || typeof entry !== 'object') continue;
    const p = entry as Record<string, unknown>;
    const prompt =
      typeof p.prompt === 'string' && p.prompt.trim()
        ? p.prompt.trim()
        : typeof p.text === 'string'
          ? p.text.trim()
          : '';
    if (!prompt) continue;
    out.push({
      title:
        typeof p.title === 'string' && p.title.trim()
          ? p.title.trim()
          : `Fix ${out.length + 1}`,
      scope: typeof p.scope === 'string' ? p.scope.trim() : '',
      prompt,
    });
  }
  return out;
}

/* ------------------------------------------------------------------ */
/*  The room run                                                       */
/* ------------------------------------------------------------------ */

/** `GET /website-room/eligibility?project_id=` — may the room read the new page? */
export interface RoomEligibility {
  eligible: boolean;
  /** Why not, in the backend's own sentence, when not. */
  reason: string;
}

export function asEligibility(body: unknown): RoomEligibility | null {
  if (!body || typeof body !== 'object') return null;
  const row = body as Record<string, unknown>;
  if (typeof row.eligible !== 'boolean') return null;
  return {
    eligible: row.eligible,
    reason: typeof row.reason === 'string' ? row.reason.trim() : '',
  };
}

/**
 * The child run's id out of `POST /website-room/run`'s reply, under whichever
 * spelling it arrives. The simulation-flavoured keys are probed first because
 * the id's only use is the `/app/simulations/{id}/run` surface; the bare `id`
 * comes last since it could plausibly be some other row echoing itself.
 */
export function childRunId(body: unknown): string | null {
  if (!body || typeof body !== 'object') return null;
  const row = body as Record<string, unknown>;
  for (const key of [
    'child_simulation_id',
    'simulation_id',
    'child_run_id',
    'run_id',
    'child_id',
  ]) {
    const value = row[key];
    if (typeof value === 'string' && value) return value;
  }
  for (const key of ['simulation', 'child', 'run']) {
    const nested = row[key];
    if (nested && typeof nested === 'object') {
      const id = (nested as Record<string, unknown>).id;
      if (typeof id === 'string' && id) return id;
    }
  }
  const id = row.id;
  return typeof id === 'string' && id ? id : null;
}
