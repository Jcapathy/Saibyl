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

/**
 * Schema version this client knows how to render.
 *
 * 2 — Phase 2 adds `by_cohort` and `adversarial`. Both are additive, but the
 *     version still moved: a client that renders a Founder-lens run without the
 *     adversarial disclosure presents incumbent-aligned synthetic agents as
 *     ordinary market voices, which is the one thing PRD §4 forbids. Refusing to
 *     render is the correct failure there.
 *
 * 3 — Phase 3 adds `scoreboard`. Additive again, and again the version moved for
 *     more than the new field: on a multi-variant run the `headline` stops being
 *     the thing to read, because it averages every arena into one number that
 *     describes none of them. A client rendering v3 without the scoreboard would
 *     show a marketer one confident sentiment figure for a test whose entire
 *     purpose was to separate six alternatives.
 *
 * **This constant must move in the same commit as the server's SCHEMA_VERSION.**
 * The client refuses to render an unknown version, so a server bump without this
 * mirror blanks every report in the product.
 */
export const SUPPORTED_SCHEMA_VERSION = 3;

export type Stance = 'support' | 'oppose' | 'undecided' | 'off_topic';
export type Confidence = 'low' | 'moderate' | 'high';
export type Trajectory = 'improving' | 'declining' | 'flat';
export type Cohort = 'buyer' | 'adversarial';

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

/**
 * One side of the room: buyers, or incumbent-aligned agents.
 *
 * Separate from the archetype breakdown because it answers a different
 * question. An archetype table says which kind of person reacted how; this says
 * how much of the negativity came from agents constructed to argue against the
 * switch. A founder reading a −0.4 headline needs to know whether that is the
 * market or the 40% of the swarm they configured to be hostile.
 */
export interface CohortSlice extends GroupSlice {
  cohort: Cohort;
  /** Agents allocated to this cohort, whether or not they spoke. */
  agents_total: number;
  archetypes: string[];
}

/**
 * What the adversarial cohort was, stated wherever the run is presented.
 *
 * `disclosure` is composed once on the server so the viewer, the print page,
 * the PDF and the JSON export say the same words. Render it verbatim — do not
 * rewrite it here.
 */
export interface AdversarialDisclosure {
  enabled: boolean;
  share_configured: number;
  share_realised: number;
  agents_total: number;
  agents_active: number;
  archetypes: string[];
  roles: Record<string, number>;
  named_competitors: string[];
  disclosure: string;
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
  /**
   * Did this objection start on the incumbent's side of the room, and did it
   * get out? One that starts adversarial and stays there is a competitor
   * talking to themselves. One that crosses into buyers is the thing the
   * inoculation loop exists to answer.
   */
  originated_adversarial: boolean;
  adversarial_agent_count: number;
  buyer_agent_count: number;
}

/** Mirrors ObjectionSummary.crossed_into_buyers on the server. */
export function crossedIntoBuyers(objection: ObjectionSummary): boolean {
  return objection.originated_adversarial && objection.buyer_agent_count > 0;
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

export type Objective =
  | 'clicks'
  | 'foot_traffic'
  | 'product_sale'
  | 'service_sale'
  | 'signup'
  | 'awareness';

/**
 * The Virality Potential Score and its six components.
 *
 * **A separate axis from the objective metric, never blended into it.** A
 * variant can spread widely and convert terribly, and one score hides the two
 * cases a marketer must act on.
 *
 * **`null` is not zero anywhere in here.** A component that could not be
 * measured is null and was dropped from the weighting; zero means measured and
 * nothing happened. Rendering a null as 0 would show a variant failing at
 * something the run never measured.
 */
export interface ViralityComponents {
  score: number | null;
  components_used: number;
  components_total: number;
  share_intent_rate: Interval;
  /** The heaviest-weighted component — spread confined to one cohort is an echo chamber. */
  cross_archetype_reach: number;
  archetypes_reached: number;
  archetypes_total: number;
  /** null on a single-platform run: there was nowhere to jump to. */
  cross_platform_jump: number | null;
  restatement_rate: number | null;
  /** Branching, not depth — adapters have no reply-to-reply, so the graph is two levels. */
  cascade_branching: number | null;
  velocity_rounds_to_peak: number | null;
  velocity_normalised: number | null;
}

export interface VariantArchetypeSlice {
  archetype: string;
  objective_rate: Interval;
  valence: Interval;
  agent_count: number;
  event_count: number;
}

export interface VariantScore {
  variant_key: string;
  label: string;
  content: string;
  /** The headline for this run's objective. A proportion over agents, not events. */
  objective_rate: Interval;
  /** Supporting, not headline — a variant that converts while everyone resents it is a finding. */
  valence: Interval;
  stance: StanceSplit;
  virality: ViralityComponents;
  /** Lexical overlap, deliberately crude. Label it as approximate wherever shown. */
  takeaway_accuracy: number | null;
  viral_but_off_message: boolean;
  converts_but_wont_travel: boolean;
  agent_count: number;
  event_count: number;
  event_ids: string[];
  by_archetype: VariantArchetypeSlice[];
}

/**
 * The N-way comparison. Absent on every single-arena run.
 *
 * `winner_variant_key` is null whenever the top two variants' intervals
 * overlap, and `verdict` says so in words. **Render the verdict, not just the
 * ordering** — the list is display order, and presenting row one as the winner
 * when the server declined to name one puts a number the product refused to
 * stand behind in front of a spend decision.
 */
export interface VariantScoreboard {
  objective: Objective | null;
  objective_intents: string[];
  variants: VariantScore[];
  winner_variant_key: string | null;
  verdict: string;
  viral_score_threshold: number;
  off_message_threshold: number;
}

export interface SimulationAnalysis {
  schema_version: number;
  simulation_id: string;
  generated_at: string;
  headline: Headline;
  sentiment_timeline: TimelinePoint[];
  by_platform: PlatformSlice[];
  by_archetype: ArchetypeSlice[];
  /** Empty when the run had no adversarial cohort — a one-sided split is noise. */
  by_cohort: CohortSlice[];
  objections: ObjectionSummary[];
  flashpoints: Flashpoint[];
  propagation: PropagationEdge[];
  adversarial: AdversarialDisclosure;
  /**
   * Null on every single-arena run. **When present, this is the headline** —
   * `headline` above averages every arena into one number that describes none
   * of them.
   */
  scoreboard: VariantScoreboard | null;
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

/**
 * Whether this client can render the artifact it was handed.
 *
 * **Older is fine; newer is not.** The two directions are not symmetric and
 * treating them as one rule was a mistake this caught at the merge.
 *
 * An artifact *older* than this client is missing fields the client knows
 * about, and every one of them was added additively — a v1 artifact has no
 * `scoreboard` and no `by_cohort`, which is exactly what a single-arena run
 * with no adversarial cohort looks like anyway. Rendering it is correct.
 *
 * An artifact *newer* than this client carries fields the client has never
 * heard of, and the failure there is silent: the page renders, looks complete,
 * and quietly omits a block it does not know exists. That is the case the
 * refusal is for — a v2 client showing a v3 matched-swarm run would present one
 * pooled sentiment figure for a test whose whole purpose was to separate six
 * messages, with nothing on screen to say so.
 *
 * Strict equality blanked every report written before the current version. On
 * the day it shipped that was four artifacts in internal orgs; the next time it
 * would have been every report a customer had ever run.
 */
export function isSupportedSchema(version: number): boolean {
  return Number.isFinite(version) && version >= 1 && version <= SUPPORTED_SCHEMA_VERSION;
}

/**
 * Fill in the collections an older artifact predates.
 *
 * Applied once at the load boundary rather than guarded at each of the six
 * places that read these — a guard per call site is a guard someone forgets on
 * the seventh, and the failure is a white screen from `undefined.length`.
 *
 * Only ever substitutes *empty*, never a value. An absent `by_cohort` means the
 * run had no cohort split, which is what an empty list already means; it does
 * not mean zero, and nothing here invents a number.
 */
export function withSchemaDefaults(analysis: SimulationAnalysis): SimulationAnalysis {
  return {
    ...analysis,
    sentiment_timeline: analysis.sentiment_timeline ?? [],
    by_platform: analysis.by_platform ?? [],
    by_archetype: analysis.by_archetype ?? [],
    by_cohort: analysis.by_cohort ?? [],
    objections: analysis.objections ?? [],
    flashpoints: analysis.flashpoints ?? [],
    propagation: analysis.propagation ?? [],
    scoreboard: analysis.scoreboard ?? null,
  };
}
