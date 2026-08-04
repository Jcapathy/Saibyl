/**
 * Canonical shapes of the backend's JSON responses.
 *
 * Every page that reads an API response imports from here. A locally
 * redeclared response shape has nothing to disagree with, so it never fails —
 * which is how `key_prefix` became `prefix` in the settings page and how
 * `sentiment_score` outlived the column it was named after. One declaration
 * per response means one place to correct when the backend moves.
 *
 * Each interface below is the subset of a response the UI reads, and every
 * field name and nullability was checked against the route that produces it.
 * Routes that `select("*")` return the whole row, so widening one of these is
 * a schema check rather than a backend change.
 */

/** `GET /auth/me` → `.organization`; `GET /organizations/{id}`. */
export interface Organization {
  id: string;
  name: string;
  slug: string;
  plan: string;
}

/** `GET /projects`, `GET /projects/{id}` — the `projects` row. */
export interface Project {
  id: string;
  organization_id: string;
  name: string;
  description: string | null;
  status: string;
  asset_count: number;
  created_at: string;
}

/**
 * `GET /simulations`, `GET /simulations/{id}` — the `simulations` row.
 *
 * There is no sentiment or valence field on this row under any name. A
 * per-simulation sentiment reading lives at `GET /simulations/{id}/analysis`
 * (`artifact.headline.valence`), which is addressable by one id at a time and
 * 404s until the artifact is built — so a list view cannot show one.
 */
export interface Simulation {
  id: string;
  project_id: string;
  organization_id: string;
  name: string;
  description: string | null;
  prediction_goal: string;
  status: string;
  platforms: string[];
  max_rounds: number;
  variants: number;
  /** Null until the prepare pass has generated the swarm. */
  agent_count: number | null;
  persona_pack_ids: string[];
  /** Set only alongside `status: 'failed'`. */
  error_message: string | null;
  created_at: string;
  completed_at: string | null;
  /** Set when this run is an inoculation re-simulation of another. */
  parent_simulation_id: string | null;
}

/** One section of a generated report, as embedded in the report response. */
export interface ReportSection {
  title: string;
  content: string;
}

/** A project document the report was written against. */
export interface ReportSourceDocument {
  filename: string;
  file_type: string;
  word_count: number;
  text: string;
}

/**
 * `GET /reports/by-simulation/{simulation_id}`.
 *
 * Hand-assembled by the route, not the `reports` row: `markdown_content` is
 * renamed to `full_markdown`, the embedded sections carry only `title` and
 * `content`, and `title`, `variant`, `section_count` and `created_at` are
 * absent. The route also returns a `polarization` block that nothing renders;
 * it is left out here rather than declared and ignored.
 */
export interface SimulationReport {
  id: string;
  simulation_id: string;
  status: string | null;
  sections: ReportSection[];
  full_markdown: string;
  source_documents?: ReportSourceDocument[];
}

/** `GET /persona-packs` — the pack summary, not the full pack. */
export interface PersonaPack {
  id: string;
  name: string;
  category: string;
  description: string;
  archetype_count: number;
  archetype_labels: string[];
}

/** `GET /billing/status`. */
export interface BillingStatus {
  plan: string;
  status: string;
  simulations_used: number;
  simulations_limit: number;
  agents_used: number;
  agents_limit: number;
  team_members: number;
  team_members_limit: number;
  /** Declared by the backend but never populated — always null. */
  current_period_end: string | null;
}

/**
 * `GET /api-keys`.
 *
 * The prefix field is `key_prefix`. There is no `prefix` field on either the
 * list or the create response.
 */
export interface ApiKey {
  id: string;
  name: string;
  /** First 12 characters of the key — all that survives creation. */
  key_prefix: string;
  scopes: string[];
  last_used_at: string | null;
  expires_at: string | null;
  revoked_at: string | null;
  created_at: string;
}

/** `POST /api-keys` — the only response that ever carries the full key. */
export interface CreatedApiKey {
  id: string;
  /** The full secret, returned once and never again. */
  key: string;
  key_prefix: string;
  name: string;
  scopes: string[];
  message: string;
}
