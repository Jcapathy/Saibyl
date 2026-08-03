/**
 * The `simulation_analysis` artifact, as the frontend sees it.
 *
 * These types mirror `backend/app/services/intelligence/analysis_schema.py`.
 * They are the *only* source of numbers in the report UI. The previous viewer
 * regex-scraped one scalar out of the report markdown and then generated the
 * sentiment timeline, per-platform sentiment, persona metrics and risk matrix
 * with `Math.sin()` and `Math.random()` — risk likelihood was literally
 * `0.3 + Math.random() * 0.5`.
 *
 * Nothing in this file computes a metric. It types what the server measured and
 * formats it for display. If a value is not on one of these interfaces, it does
 * not get rendered.
 */

/** Schema version this client knows how to render. */
export const SUPPORTED_SCHEMA_VERSION = 1;

export type Stance = 'support' | 'oppose' | 'undecided' | 'off_topic';
export type Confidence = 'low' | 'moderate' | 'high';
export type Trajectory = 'improving' | 'declining' | 'flat';

/** A mean with its 95% interval. `n` is agents — never events. */
export interface Interval {
  mean: number;
  lower: number;
  upper: number;
  n: number;
}

export interface StanceSplit {
  support_pct: number;
  oppose_pct: number;
  undecided_pct: number;
  off_topic_pct: number;
}

export interface TimelinePoint {
  round_number: number;
  valence: Interval;
  stance: StanceSplit;
  mean_intensity: number;
  event_count: number;
  agent_count: number;
  novel_claim_count: number;
}

/** Shared shape of the per-platform and per-archetype breakdowns. */
export interface GroupSlice {
  valence: Interval;
  stance: StanceSplit;
  mean_intensity: number;
  event_count: number;
  agent_count: number;
  top_objection_keys: string[];
}

export interface PlatformSlice extends GroupSlice {
  platform: string;
}

export interface ArchetypeSlice extends GroupSlice {
  archetype: string;
}

export interface ObjectionQuote {
  event_id: string;
  agent_username: string;
  archetype: string | null;
  platform: string | null;
  round_number: number | null;
  text: string;
}

export interface PropagationPoint {
  round_number: number;
  event_count: number;
  agent_count: number;
}

export interface ObjectionSummary {
  key: string;
  label: string;
  summary: string;
  quotes: ObjectionQuote[];
  event_ids: string[];
  agent_count: number;
  event_count: number;
  first_round_seen: number | null;
  originating_cohort: string | null;
  cohort_spread: Record<string, number>;
  propagation: PropagationPoint[];
  mean_intensity: number;
  load_bearing_score: number;
}

export interface Flashpoint {
  round_number: number;
  platform: string | null;
  valence_before: number;
  valence_after: number;
  delta: number;
  significant: boolean;
  trigger_event_ids: string[];
  objection_keys: string[];
  description: string;
}

export interface PropagationEdge {
  objection_key: string;
  from_group: string;
  to_group: string;
  group_kind: 'archetype' | 'platform';
  first_round: number;
  event_ids: string[];
}

export interface QualityBlock {
  events_total: number;
  events_measured: number;
  coverage_pct: number;
  agents_total: number;
  agents_active: number;
  rounds: number;
  measurement_model: string;
  mean_ci_width: number;
  confidence: Confidence;
  caveats: string[];
}

export interface Headline {
  valence: Interval;
  stance: StanceSplit;
  mean_intensity: number;
  polarization_pct: number;
  novel_claim_pct: number;
  trajectory: Trajectory;
  trajectory_delta: number;
  top_objection_key: string | null;
}

export interface SimulationAnalysis {
  schema_version: number;
  simulation_id: string;
  generated_at: string;
  headline: Headline;
  sentiment_timeline: TimelinePoint[];
  by_platform: PlatformSlice[];
  by_archetype: ArchetypeSlice[];
  objections: ObjectionSummary[];
  flashpoints: Flashpoint[];
  propagation: PropagationEdge[];
  quality: QualityBlock;
}

/** Response from GET /api/simulations/{id}/analysis */
export interface AnalysisResponse {
  simulation_id: string;
  schema_version: number;
  artifact: SimulationAnalysis;
  generated_at: string;
}

/** An event with its measurement, from GET /api/simulations/{id}/evidence */
export interface EvidenceEvent {
  id: string;
  platform: string | null;
  round_number: number | null;
  event_type: string;
  content: string | null;
  valence: number | null;
  stance: Stance | null;
  intensity: number | null;
  intent: string | null;
  is_novel_claim: boolean | null;
  objections: string[];
  agent: {
    username?: string;
    display_name?: string;
    archetype?: string;
  };
}

/* ── Formatting ────────────────────────────────────────────────────── */

export function formatSigned(value: number, digits = 2): string {
  return `${value >= 0 ? '+' : ''}${value.toFixed(digits)}`;
}

/**
 * A mean with its interval and n, in the one format used everywhere.
 *
 * The interval is never dropped for brevity. A bare mean from a synthetic swarm
 * claims a precision the swarm does not have, and the whole point of measuring
 * rather than generating is that the uncertainty is now knowable.
 */
export function formatInterval(interval: Interval): string {
  if (interval.n === 0) return 'no measured opinion';
  if (interval.n === 1) return `${formatSigned(interval.mean)} (1 agent — not resolvable)`;
  return `${formatSigned(interval.mean)} (95% CI ${formatSigned(interval.lower)} to ${formatSigned(
    interval.upper,
  )}, ${interval.n} agents)`;
}

/** Compact form for chart labels and table cells. */
export function formatIntervalShort(interval: Interval): string {
  if (interval.n === 0) return '—';
  if (interval.n === 1) return `${formatSigned(interval.mean)} ±?`;
  return `${formatSigned(interval.mean)} ±${((interval.upper - interval.lower) / 2).toFixed(2)}`;
}

/**
 * Whether two measured groups actually differ.
 *
 * Overlapping intervals mean the difference is unresolved at this swarm size.
 * The UI must not rank two groups whose bands overlap — that is exactly the
 * false precision the fabricated charts used to imply.
 */
export function differsSignificantly(a: Interval, b: Interval): boolean {
  if (a.n < 2 || b.n < 2) return false;
  return a.lower > b.upper || a.upper < b.lower;
}

export const CONFIDENCE_COPY: Record<Confidence, string> = {
  low: 'Low confidence — intervals are wide at this swarm size. Treat differences smaller than the bands as unresolved.',
  moderate: 'Moderate confidence — large differences are resolvable, small ones are not.',
  high: 'High confidence — the swarm is large enough to resolve modest differences.',
};

export const TRAJECTORY_COPY: Record<Trajectory, string> = {
  improving: 'Sentiment improved over the run',
  declining: 'Sentiment declined over the run',
  flat: 'Sentiment did not move beyond its confidence bands',
};

/** Whether this client can render the artifact it was handed. */
export function isSupportedSchema(version: number): boolean {
  return version === SUPPORTED_SCHEMA_VERSION;
}
