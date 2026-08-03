/**
 * The Founder lens, as the frontend sees it.
 *
 * Mirrors `backend/app/services/engine/founder_stages.py`,
 * `personas/icp_schema.py` and `intelligence/inoculation_schema.py`.
 *
 * Nothing here computes anything. In particular the stage list is **fetched**
 * from `/api/simulations/founder-stages` rather than duplicated as a constant:
 * a stage's audience defaults, the questions its report answers, and the limits
 * it states in that report all live in one server-side registry, and a copy in
 * the picker is a copy that will eventually disagree with the report.
 */

import type { Interval } from './analysis';

/* ── Stages ─────────────────────────────────────────────────────────── */

export type FounderStage =
  | 'concept_validation'
  | 'pre_launch_positioning'
  | 'launch_gtm'
  | 'growth'
  | 'fundraise';

export type Lens = 'founder' | 'marketing' | 'crisis';

export interface StageSpec {
  id: FounderStage;
  label: string;
  question: string;
  expected_inputs: string[];
  default_adversarial_share: number;
  default_rounds: number;
  report_questions: string[];
  /** What a run at this stage cannot support. Shown before the run, not after. */
  cannot_conclude: string[];
}

/* ── ICP ────────────────────────────────────────────────────────────── */

export interface ICPArchetype {
  id: string;
  label: string;
  weight: number;
  role: string;
  seniority: string;
  budget_authority: string;
  /** What they use today. The field that does the most work in the whole ICP. */
  incumbent_tooling: string[];
  switching_cost: string;
  evaluation_criteria: string[];
  skepticism_triggers: string[];
  goals: string[];
  pains: string[];
  platforms: string[];
  prior_pack_id: string | null;
  prior_archetype_id: string | null;
  disposition: number;
}

export interface AdversarialArchetype {
  id: string;
  label: string;
  weight: number;
  role: string;
  /** Null unless uploaded competitor material licensed the name. */
  competitor_name: string | null;
  grounded_in: string[];
  core_argument: string;
  talking_points: string[];
  platforms: string[];
  disposition: number;
}

export interface ICPCompetitor {
  name: string;
  positioning: string;
  /** Empty means the model produced the name from memory. Never usable. */
  mentioned_in: string[];
}

export interface ICPProfileBody {
  schema_version: number;
  name: string;
  product_summary: string;
  category: string;
  archetypes: ICPArchetype[];
  adversarial: AdversarialArchetype[];
  competitors: ICPCompetitor[];
  /** What the material never said. Surfaced instead of guessed at. */
  gaps: string[];
}

export interface ICPProfile {
  id: string;
  project_id: string;
  name: string;
  product_summary: string;
  profile: ICPProfileBody;
  pack_id: string;
  prior_pack_ids: string[];
  competitors: ICPCompetitor[];
  edited_by_user: boolean;
  created_at: string;
}

/* ── Inoculation ────────────────────────────────────────────────────── */

export type AssetType =
  | 'disclosure'
  | 'roadmap'
  | 'pricing_rationale'
  | 'security_page'
  | 'migration_guide'
  | 'faq_entry'
  | 'comparison_page';

export type AssetStatus = 'draft' | 'selected' | 'tested';

export interface InoculationAsset {
  id: string;
  simulation_id: string;
  objection_key: string;
  objection_label: string;
  asset_type: AssetType;
  title: string;
  body: string;
  /** Recorded before the test runs, so it can turn out to be wrong. */
  hypothesis: string;
  status: AssetStatus;
  edited_by_user: boolean;
}

export type Verdict =
  | 'died'
  | 'shrank'
  | 'unresolved'
  | 'unchanged'
  | 'grew'
  | 'emerged';

export interface ObjectionMeasurement {
  agent_count: number;
  agents_active: number;
  event_count: number;
  mean_intensity: number;
  load_bearing_score: number;
  /** Share of active agents voicing it, with an interval on the proportion. */
  reach: Interval;
}

export interface ObjectionDelta {
  objection_key: string;
  label: string;
  before: ObjectionMeasurement;
  after: ObjectionMeasurement;
  reach_delta_pct: number;
  /** True only when the two proportions' intervals do not overlap. */
  significant: boolean;
  verdict: Verdict;
  asset_ids: string[];
  asset_titles: string[];
  converted_agent_usernames: string[];
}

export interface InoculationResult {
  parent_simulation_id: string;
  child_simulation_id: string;
  deltas: ObjectionDelta[];
  headline_before: Interval;
  headline_after: Interval;
  assets_tested: number;
  assets_effective: number;
}

/**
 * Mirrors `ObjectionDelta.effective` on the server.
 *
 * `unresolved` is deliberately excluded. A move inside the confidence bands is
 * not a result, and counting it would turn the one number this product is sold
 * on into noise.
 */
export function isEffective(delta: ObjectionDelta): boolean {
  return delta.significant && (delta.verdict === 'died' || delta.verdict === 'shrank');
}

export const VERDICT_COPY: Record<Verdict, string> = {
  died: 'Nobody raised it after the asset was published',
  shrank: 'Measurably fewer agents raised it',
  unresolved: 'Moved, but inside the confidence bands — not a result either way',
  unchanged: 'Did not move',
  grew: 'Measurably more agents raised it — the asset drew attention to it',
  emerged: 'New: absent before, present after',
};

export const VERDICT_TONE: Record<Verdict, 'good' | 'bad' | 'neutral'> = {
  died: 'good',
  shrank: 'good',
  unresolved: 'neutral',
  unchanged: 'neutral',
  grew: 'bad',
  emerged: 'bad',
};

export const ASSET_TYPE_LABELS: Record<AssetType, string> = {
  disclosure: 'Disclosure',
  roadmap: 'Roadmap',
  pricing_rationale: 'Pricing rationale',
  security_page: 'Security page',
  migration_guide: 'Migration guide',
  faq_entry: 'FAQ entry',
  comparison_page: 'Comparison page',
};

/** Share of active agents, as a percentage string. */
export function formatReach(measurement: ObjectionMeasurement): string {
  if (measurement.reach.n === 0) return 'no active agents';
  const pct = (measurement.reach.mean * 100).toFixed(0);
  const upper = (measurement.reach.upper * 100).toFixed(0);
  if (measurement.agent_count === 0) {
    // Zero observed is not certainty — the band is what the run can support.
    return `0% (up to ${upper}% at this swarm size)`;
  }
  return `${pct}% of ${measurement.reach.n} agents`;
}
