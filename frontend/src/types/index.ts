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
  /**
   * ⚠ Never a count of documents. Kept only because `GET /projects` returns
   * `select("*")`; nothing should read it and the column is scheduled to be
   * dropped once this release is serving. Use `document_count`.
   */
  asset_count: number;
  /** Files in this product, counted from `documents` on every request. */
  document_count?: number;
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
  /**
   * How many report sections the write-up gets.
   *
   * `NOT NULL DEFAULT 'standard'` since migration 018, with no CHECK
   * constraint — so it is always present but not guaranteed to be one of the
   * three the API accepts. Narrow before feeding it back to a priced shape.
   */
  depth: string;
  persona_pack_ids: string[];
  /** Set only alongside `status: 'failed'`. */
  error_message: string | null;
  created_at: string;
  completed_at: string | null;
  /** Set when this run is an inoculation re-simulation of another. */
  parent_simulation_id: string | null;
}

/**
 * What a document was uploaded as.
 *
 * NULL reads as `own` — the column was added after documents existed, so the
 * absence of a value means "nobody said", and the safe reading of that is the
 * founder's own material. Only `competitor` licenses the model to name a
 * company by name in published copy, which is why the value is a deliberate
 * choice at upload rather than a tag applied afterwards.
 */
export type MaterialKind = 'own' | 'competitor' | 'market';

/** `GET /documents?project_id=…`, `POST /documents/upload` — the `documents` row. */
export interface ProjectDocument {
  id: string;
  project_id: string;
  filename: string;
  file_type: string;
  processing_status: string;
  file_size_bytes: number;
  /** Null on every row uploaded before the column existed. Reads as `own`. */
  material_kind: MaterialKind | null;
  created_at: string;
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

/**
 * `GET /packs` — one entry in the org's reusable persona-pack library.
 *
 * The library is org-level: a pack promoted out of one project's synthesized
 * ICP is selectable from every other project, which is the whole reason it is a
 * separate object from `icp_profiles.pack_data`.
 *
 * Only `id` and `name` are required, because only those two are needed to list,
 * rename, delete and select. Everything else is optional and is rendered only
 * when the server actually sends it — an absent archetype count shows nothing
 * rather than a zero, because "we did not receive it" and "this pack has no
 * archetypes" are different facts and one of them is alarming.
 */
export interface OrgPersonaPack {
  id: string;
  name: string;
  description?: string | null;
  category?: string | null;
  archetype_count?: number | null;
  archetype_labels?: string[] | null;
  created_at?: string | null;
}

/* `BillingStatus` was here, typing `GET /billing/status` — a plan, a
 * subscription state, a monthly run allowance and a seat count. The endpoint
 * and every field on it went with the subscription tiers on 2026-08-25
 * (PRD_V3 §6). What a founder needs is their balance and what a given run
 * costs: `GET /billing/credits` and `GET /billing/prices`. */

/* `ApiKey` and `CreatedApiKey` were here. Removed with the API-keys tab:
 * `verify_api_key` had zero callers, so a key issued from that screen
 * authenticated nothing. Nothing in this product needs one. */

/* ── Prospect discovery ───────────────────────────────────────────────
 *
 * `backend/app/api/gtm.py`, mounted at `/api/gtm`. The row shapes below are
 * migration 027's three tables as PostgREST returns them, and the request
 * shapes are the Pydantic bodies in the route module.
 *
 * ⚠ Migration 027 is marked NOT APPLIED in
 * `backend/scripts/migrations/027_gtm_discovery.sql`. Until it is applied every
 * route here fails at the database, and `GET /gtm/settings` answers 503 by
 * design rather than reporting the gate as off.
 */

/** One of the three ways a compiled search looks for the same buyer. */
export type DiscoveryAngle = 'firmographic' | 'incumbent_tooling' | 'pain_trigger';

/**
 * Terminal and in-flight states of a discovery run.
 *
 * The value is `completed`, not `complete` — `store.RUN_STATUSES` and the
 * `gtm_discovery_runs_status_values` CHECK constraint both spell it that way,
 * and `simulations` uses the *other* spelling, so the two must not share a
 * normaliser.
 *
 * `partial` is a first-class outcome and `failed` is not the same as finding
 * nothing: `failed` means the search provider was unreachable, while a
 * `completed` run with `candidates_found: 0` is a real finding about the
 * market. Nothing may render the two the same way.
 */
export type DiscoveryRunStatus = 'running' | 'completed' | 'partial' | 'failed';

/**
 * One search a compiled audience asks for.
 *
 * Returned by `GET /gtm/estimate` before anything is spent, and stored verbatim
 * on the run row — the compiler is deterministic, so the previewed queries are
 * the ones that ran.
 */
export interface DiscoveryQuery {
  archetype_id: string;
  archetype_label: string;
  angle: DiscoveryAngle;
  query: string;
  /** Which audience fields produced this query. */
  derived_from: string[];
}

/** `GET /gtm/estimate` → `estimate`. Priced per compiled query. */
export interface DiscoveryCostEstimate {
  queries: number;
  searches: number;
  token_cost_usd: number;
  search_fee_usd: number;
  actual_cost_usd: number;
  retail_cost_usd: number;
  credits: number;
  margin_pct: number;
  standard_run_equivalents: number;
  /** False until the token profiles are re-derived from live usage rows. */
  measured: boolean;
}

/** `GET /gtm/estimate` → `budget`. The `BudgetCheck` shape from billing. */
export interface DiscoveryBudget {
  allowed: boolean;
  credits_required: number;
  credits_remaining: number;
  credits_after: number;
  balance_share_pct: number;
  estimated_cost_usd: number;
  retail_price_usd: number;
  /** Written server-side for a person to read. Shown verbatim. */
  message: string;
}

/** `GET /gtm/estimate?icp_profile_id=&max_queries=`. */
export interface DiscoveryEstimate {
  queries: DiscoveryQuery[];
  estimate: DiscoveryCostEstimate;
  budget: DiscoveryBudget;
}

/**
 * `GET /gtm/runs` (enveloped), `GET /gtm/runs/{id}`, `POST /gtm/discover` — the
 * `gtm_discovery_runs` row.
 *
 * A run whose API process died stays `running` with `completed_at: null`
 * forever; there is no reaper. `created_at` is what makes that legible instead
 * of mysterious, so it is never optional here.
 */
export interface DiscoveryRun {
  id: string;
  project_id: string;
  organization_id: string;
  /** Null once the audience it was found from is deleted. */
  icp_profile_id: string | null;
  status: DiscoveryRunStatus;
  queries: DiscoveryQuery[];
  query_count: number;
  queries_completed: number;
  queries_failed: number;
  queries_empty: number;
  /** Whether *this run* was authorised to collect named people. */
  contacts_enabled: boolean;
  candidates_found: number;
  contacts_found: number;
  credits_charged: number;
  estimated_cost_usd: number;
  searches_performed: number;
  search_fee_usd: number;
  /** The provider's reason on `failed`, or what cut a `partial` short. */
  error: string | null;
  /** Set when the org purged its candidates. The run itself survives. */
  purged_at: string | null;
  created_by: string | null;
  created_at: string;
  /** Null while running, and on a run whose process died. */
  completed_at: string | null;
}

/** One field, the page it came from, and the text that supports it. */
export interface EvidenceItem {
  /** The candidate field this quote evidences. */
  field: string;
  source_url: string;
  /** Verified to appear verbatim in that source before the row was written. */
  quote: string;
}

/**
 * A named person, from `GET /gtm/candidates/{id}` → `contacts`.
 *
 * Personal data, and only ever public professional information. There is no
 * email, phone or address field on this row and adding one is a privacy
 * decision rather than a schema change.
 */
export interface GtmContact {
  id: string;
  candidate_id: string;
  organization_id: string;
  full_name: string;
  role_title: string;
  employer: string;
  public_profile_url: string | null;
  source_url: string;
  retrieved_at: string;
  created_at: string;
}

/**
 * `GET /gtm/candidates` → `items` — the columns a grid needs.
 *
 * **Every nullable field below is null because no retrieved source stated it.**
 * That is a real answer and must render as nothing at all: not a dash, not
 * "Unknown", not an estimated band. A fabricated firmographic is the defect
 * class this feature exists to remove.
 *
 * This shape deliberately carries **no `evidence`, no `match_reasons`, no
 * `query` and no `contacts`** — `store._LIST_COLUMNS` does not select them, so
 * a list view that reads any of them reads `undefined`. `GET
 * /gtm/candidates/{id}` returns them.
 */
export interface CandidateListItem {
  id: string;
  discovery_run_id: string;
  project_id: string;
  company_name: string;
  domain: string | null;
  /** Empty string when no source described them. Renders as nothing. */
  one_liner: string;
  employee_count_range: string | null;
  industry: string | null;
  hq_location: string | null;
  incumbent_tooling: string[];
  archetype_id: string;
  archetype_label: string;
  angle: DiscoveryAngle;
  /**
   * A 0..1 **rank ordering** against one archetype. Not a probability, not a
   * confidence, and not a fit score in any calibrated sense — `scoring.py` says
   * so in as many words.
   *
   * Use it to order and for nothing else. Rendering `0.73` as "73% match"
   * invents precision the number does not carry. `lib/gtm.ts` deliberately
   * exports no percentage formatter for it.
   */
  match_score: number;
  source_url: string;
  source_title: string;
  retrieved_at: string;
  /** Denormalised so a grid never has to query the contacts table. */
  contact_count: number;
  created_at: string;
}

/**
 * `GET /gtm/candidates/{id}` — the whole row, with evidence and contacts.
 *
 * The evidence is the product. A field that does not appear in `evidence` is
 * null on the record: no source stated it, and nothing estimated one.
 */
export interface CandidateDetail extends CandidateListItem {
  organization_id: string;
  /** The compiled search that found them. */
  query: string;
  /** Why this company matches, in the extraction model's words. */
  match_reasons: string[];
  /**
   * The five parts of `match_score`, each 0..1. Shown as *why this ranked
   * here* — still an ordering, still not a calibrated measure of anything.
   */
  score_components: Record<string, number>;
  evidence: EvidenceItem[];
  contacts: GtmContact[];
}

/**
 * `GET /gtm/settings`.
 *
 * A failed read is a 503, never a `false`. An unreadable setting and a
 * deliberate opt-out are different facts and the UI must not render one as the
 * other.
 */
export interface GtmSettings {
  contact_discovery_enabled: boolean;
  /** What "on" means, authored server-side. Shown verbatim. */
  note: string;
}

/** `PATCH /gtm/settings` ← `{ enabled }`. */
export interface GtmSettingsUpdate {
  contact_discovery_enabled: boolean;
}

/** `POST /gtm/purge` ← `{ confirm: true }`. Irreversible. */
export interface GtmPurgeResult {
  status: string;
  candidates_deleted: number;
  contacts_deleted: number;
}

/** `DELETE /gtm/candidates/{id}`. Rows, not flags. */
export interface CandidateDeleteResult {
  status: string;
  id: string;
  company_name: string | null;
  contacts_deleted: number;
}
