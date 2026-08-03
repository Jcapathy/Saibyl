-- Migration 018: The measurement layer
--
-- Phase 1 exists to make every number real. That requires three things this
-- migration creates:
--
--   Part A  Per-event measurement columns. Event sentiment used to be
--           `sentiment_baseline * (1 + round/max_rounds * 1.5)` — a function of
--           the archetype preset and the round index that never read what the
--           agent said. It lived in the metadata JSONB blob. Its replacement is
--           measured from event content and gets typed columns, because these
--           are aggregated on every analysis build and drilled into from every
--           finding.
--
--   Part B  canonical_objections + simulation_analysis. The analysis artifact is
--           the single source for every number rendered in the UI or a report.
--           Canonical objections get their own table rather than living inside
--           the artifact JSON: they are the object the Founder lens is built on,
--           they are joined against for drill-down, and Phase 2's inoculation
--           loop compares them across two runs.
--
--   Part C  Credits and signed run quotes. Grants are denominated in credits
--           (COGS dollars), not agent-rounds — see DECISIONS_V2.md §15b. A run
--           varies 56x in cost across the tier caps, so an agent-round allowance
--           rations nothing.

-- ---------------------------------------------------------------------------
-- Part A: per-event measurement
-- ---------------------------------------------------------------------------

-- valence: -1..1, how negative/positive the event's content actually is.
-- stance:  support | oppose | undecided | off_topic, relative to the subject.
-- intensity: 0..1, how strongly held — separates a shrug from a threat to churn.
-- intent: objective-specific decision (click/visit/purchase/trial/share/none).
--         Free-form text in Phase 1; the Marketing lens (Phase 3) constrains it
--         per objective.
-- is_novel_claim: did this event introduce an assertion not already in the feed.
--         Distinguishes an originating flashpoint from an echo of one.
ALTER TABLE simulation_events ADD COLUMN IF NOT EXISTS valence        REAL;
ALTER TABLE simulation_events ADD COLUMN IF NOT EXISTS stance         TEXT;
ALTER TABLE simulation_events ADD COLUMN IF NOT EXISTS intensity      REAL;
ALTER TABLE simulation_events ADD COLUMN IF NOT EXISTS intent         TEXT;
ALTER TABLE simulation_events ADD COLUMN IF NOT EXISTS is_novel_claim BOOLEAN;
ALTER TABLE simulation_events ADD COLUMN IF NOT EXISTS objections     JSONB DEFAULT '[]'::jsonb;
ALTER TABLE simulation_events ADD COLUMN IF NOT EXISTS measured_at    TIMESTAMPTZ;
ALTER TABLE simulation_events ADD COLUMN IF NOT EXISTS measure_model  TEXT;

-- Bounds are enforced in the database, not only in the classifier's schema. A
-- model that returns 3.7 for a -1..1 field must not be able to poison an
-- aggregate that a customer will act on.
ALTER TABLE simulation_events DROP CONSTRAINT IF EXISTS simulation_events_valence_range;
ALTER TABLE simulation_events ADD CONSTRAINT simulation_events_valence_range
    CHECK (valence IS NULL OR (valence >= -1 AND valence <= 1));

ALTER TABLE simulation_events DROP CONSTRAINT IF EXISTS simulation_events_intensity_range;
ALTER TABLE simulation_events ADD CONSTRAINT simulation_events_intensity_range
    CHECK (intensity IS NULL OR (intensity >= 0 AND intensity <= 1));

ALTER TABLE simulation_events DROP CONSTRAINT IF EXISTS simulation_events_stance_values;
ALTER TABLE simulation_events ADD CONSTRAINT simulation_events_stance_values
    CHECK (stance IS NULL OR stance IN ('support', 'oppose', 'undecided', 'off_topic'));

-- The measurement pass claims batches of unmeasured events; the analysis build
-- aggregates by round and platform. Both are covered here.
CREATE INDEX IF NOT EXISTS idx_simulation_events_unmeasured
    ON simulation_events (simulation_id)
    WHERE measured_at IS NULL;

CREATE INDEX IF NOT EXISTS idx_simulation_events_measured
    ON simulation_events (simulation_id, round_number, platform)
    WHERE measured_at IS NOT NULL;

-- Run shape fields the Run Configurator sets and the quote is priced against.
-- `variants` is 1 for every existing run: V1's A/B path called run_simulation
-- once and never ran variant B, so no historical run has more than one arena.
-- Real N-way is Phase 3 — this column exists now so the quote, the caps, and
-- the stored shape agree from the start rather than being retrofitted.
ALTER TABLE simulations ADD COLUMN IF NOT EXISTS variants INT NOT NULL DEFAULT 1;
ALTER TABLE simulations ADD COLUMN IF NOT EXISTS depth TEXT NOT NULL DEFAULT 'standard';

-- ---------------------------------------------------------------------------
-- Part B: canonical objections and the analysis artifact
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS canonical_objections (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    simulation_id       UUID NOT NULL REFERENCES simulations(id) ON DELETE CASCADE,
    organization_id     UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,

    -- Stable within a simulation and deterministic from the label, so a
    -- re-simulation in the inoculation loop can line up "did this objection
    -- shrink" without fuzzy matching. Slug form, e.g. 'price-too-high'.
    objection_key       TEXT NOT NULL,
    label               TEXT NOT NULL,
    summary             TEXT,

    -- Verbatim agent quotes. Never paraphrased: the quote is the evidence.
    quotes              JSONB NOT NULL DEFAULT '[]'::jsonb,
    -- Every event that expressed this objection. This is the drill-down target.
    event_ids           UUID[] NOT NULL DEFAULT '{}',

    agent_count         INTEGER NOT NULL DEFAULT 0,
    event_count         INTEGER NOT NULL DEFAULT 0,
    first_round_seen    INTEGER,
    originating_cohort  TEXT,
    -- Share of agents holding this objection, per archetype. Cohort spread is
    -- what separates a load-bearing objection from one cohort's pet complaint.
    cohort_spread       JSONB NOT NULL DEFAULT '{}'::jsonb,
    -- Events mentioning this objection per round: [{round, events, agents}, …]
    propagation         JSONB NOT NULL DEFAULT '[]'::jsonb,

    mean_intensity      REAL,
    -- propagation reach x intensity x cohort spread. The Founder lens ranks on
    -- this rather than raw frequency, because the loudest objection and the one
    -- that actually kills the deal are usually not the same objection.
    load_bearing_score  REAL NOT NULL DEFAULT 0,

    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    UNIQUE (simulation_id, objection_key)
);

CREATE INDEX IF NOT EXISTS idx_canonical_objections_sim
    ON canonical_objections (simulation_id, load_bearing_score DESC);

CREATE TABLE IF NOT EXISTS simulation_analysis (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    -- One artifact per simulation. Rebuilding replaces it rather than
    -- accumulating versions: the artifact is derived data and the events it was
    -- derived from are immutable, so an old version has no evidentiary value.
    simulation_id       UUID NOT NULL UNIQUE REFERENCES simulations(id) ON DELETE CASCADE,
    organization_id     UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,

    -- Bumped when the artifact's shape changes. The frontend refuses to render
    -- an artifact whose version it does not know rather than silently dropping
    -- fields it cannot find.
    schema_version      INTEGER NOT NULL DEFAULT 1,

    -- The typed artifact: headline, sentiment_timeline, by_platform,
    -- by_archetype, objections, flashpoints, propagation, quality.
    -- Validated by app.services.intelligence.analysis_schema.SimulationAnalysis
    -- before it is written.
    artifact            JSONB NOT NULL,

    -- Denormalised out of artifact.quality for cheap listing and for the
    -- phase gate that checks measurement coverage without parsing the blob.
    events_total        INTEGER NOT NULL DEFAULT 0,
    events_measured     INTEGER NOT NULL DEFAULT 0,
    agents_total        INTEGER NOT NULL DEFAULT 0,

    build_status        TEXT NOT NULL DEFAULT 'complete',
    error_message       TEXT,

    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_simulation_analysis_org
    ON simulation_analysis (organization_id, created_at DESC);

-- ---------------------------------------------------------------------------
-- Part C: credits and signed run quotes
-- ---------------------------------------------------------------------------

-- 1 credit = $0.001 of COGS. A standard run (100 agents / 5 rounds /
-- 2 platforms / 1 variant, $3.23 COGS) is 3,230 credits; the Founder tier's
-- $19.80 grant is 19,800. Milli-dollars rather than dollars so the balance is
-- an integer — a float balance that drifts by a cent per deduction is a
-- support ticket nobody can reproduce.
ALTER TABLE organizations ADD COLUMN IF NOT EXISTS credits_balance    BIGINT NOT NULL DEFAULT 0;
ALTER TABLE organizations ADD COLUMN IF NOT EXISTS credits_granted    BIGINT NOT NULL DEFAULT 0;
ALTER TABLE organizations ADD COLUMN IF NOT EXISTS credit_cycle_start TIMESTAMPTZ;
-- Set at subscription time from payment_method.card.country, never from IP.
-- See DECISIONS_V2.md §15 — a client-asserted region means no pricing integrity.
ALTER TABLE organizations ADD COLUMN IF NOT EXISTS pricing_region     TEXT;

-- Existing orgs have never had a credit balance. Seed them at their plan's
-- grant so the Run Configurator is usable the moment this ships, rather than
-- every existing account seeing "not enough credits" on their next run.
UPDATE organizations
SET credits_balance = CASE COALESCE(plan, 'starter')
        WHEN 'enterprise' THEN 199800
        WHEN 'pro'        THEN 59800
        WHEN 'starter'    THEN 19800
        ELSE 700
    END,
    credits_granted = CASE COALESCE(plan, 'starter')
        WHEN 'enterprise' THEN 199800
        WHEN 'pro'        THEN 59800
        WHEN 'starter'    THEN 19800
        ELSE 700
    END,
    credit_cycle_start = COALESCE(credit_cycle_start, DATE_TRUNC('month', NOW()))
WHERE credits_granted = 0;

CREATE OR REPLACE FUNCTION deduct_credits(org_uuid UUID, amount BIGINT)
RETURNS BIGINT AS $$
    UPDATE organizations
    SET credits_balance = GREATEST(0, COALESCE(credits_balance, 0) - amount)
    WHERE id = org_uuid
    RETURNING credits_balance;
$$ LANGUAGE sql;

CREATE OR REPLACE FUNCTION grant_credits(org_uuid UUID, amount BIGINT)
RETURNS BIGINT AS $$
    UPDATE organizations
    SET credits_balance = COALESCE(credits_balance, 0) + amount,
        credits_granted = amount,
        credit_cycle_start = NOW()
    WHERE id = org_uuid
    RETURNING credits_balance;
$$ LANGUAGE sql;

-- A quote is issued server-side, signed, and presented to the client. The
-- client displays it and hands the id back when starting the run; it never
-- computes a price. Without this a user can post any agent_count they like and
-- the run is priced from whatever the client claimed.
CREATE TABLE IF NOT EXISTS run_quotes (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id     UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    -- Null until the quote is redeemed: a quote is issued while the sliders
    -- move, before any simulation row exists.
    simulation_id       UUID REFERENCES simulations(id) ON DELETE SET NULL,

    agent_count         INTEGER NOT NULL,
    rounds              INTEGER NOT NULL,
    platforms           INTEGER NOT NULL,
    variants            INTEGER NOT NULL,
    depth               TEXT NOT NULL DEFAULT 'standard',

    estimated_cost_usd  NUMERIC(12, 6) NOT NULL,
    retail_price_usd    NUMERIC(12, 6) NOT NULL,
    credits             BIGINT NOT NULL,
    margin_pct          NUMERIC(6, 2) NOT NULL,
    -- What the price was derived from, kept so a disputed charge can be
    -- reconstructed after the token profiles are recalibrated.
    breakdown           JSONB NOT NULL DEFAULT '{}'::jsonb,

    -- HMAC over the quote's priced fields, keyed on SECRET_KEY.
    signature           TEXT NOT NULL,
    expires_at          TIMESTAMPTZ NOT NULL,
    consumed_at         TIMESTAMPTZ,

    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_run_quotes_org
    ON run_quotes (organization_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_run_quotes_simulation
    ON run_quotes (simulation_id);

-- ---------------------------------------------------------------------------
-- RLS — matches the established org-isolation pattern on every other table
-- ---------------------------------------------------------------------------

ALTER TABLE canonical_objections ENABLE ROW LEVEL SECURITY;
ALTER TABLE simulation_analysis  ENABLE ROW LEVEL SECURITY;
ALTER TABLE run_quotes           ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS canonical_objections_org_isolation ON canonical_objections;
CREATE POLICY canonical_objections_org_isolation ON canonical_objections
    FOR ALL USING (organization_id = ANY(public.user_organization_ids()));

DROP POLICY IF EXISTS simulation_analysis_org_isolation ON simulation_analysis;
CREATE POLICY simulation_analysis_org_isolation ON simulation_analysis
    FOR ALL USING (organization_id = ANY(public.user_organization_ids()));

DROP POLICY IF EXISTS run_quotes_org_isolation ON run_quotes;
CREATE POLICY run_quotes_org_isolation ON run_quotes
    FOR ALL USING (organization_id = ANY(public.user_organization_ids()));

-- ---------------------------------------------------------------------------
-- Measurement coverage — the Phase 1 verification gate queries this
-- ---------------------------------------------------------------------------

-- The gate is "no number is rendered without measurement behind it". This is
-- how that is checked for a given run without reading the artifact blob.
CREATE OR REPLACE FUNCTION simulation_measurement_coverage(sim_uuid UUID)
RETURNS TABLE (
    events_total    BIGINT,
    events_measured BIGINT,
    coverage_pct    NUMERIC
) AS $$
    SELECT
        COUNT(*)::BIGINT,
        COUNT(measured_at)::BIGINT,
        CASE WHEN COUNT(*) = 0 THEN 0
             ELSE ROUND(COUNT(measured_at)::NUMERIC * 100 / COUNT(*), 2)
        END
    FROM simulation_events
    WHERE simulation_id = sim_uuid;
$$ LANGUAGE sql;
