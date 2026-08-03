-- Migration 017: Reconcile schema drift and add the LLM usage ledger
--
-- Part A fixes columns the application already writes but that no migration
-- ever created. On a database built purely from these migration files those
-- writes fail; production has them because they were added by hand.
--
-- Part B adds llm_usage, the per-call token ledger. Every cost figure the
-- product quotes is derived from real measured usage recorded here rather
-- than from a hardcoded per-agent-round constant.

-- ---------------------------------------------------------------------------
-- Part A: schema drift
-- ---------------------------------------------------------------------------

-- Written by workers/simulation_tasks.py (multiple packs per simulation).
-- The singular persona_pack_id from migration 012 is retained for existing rows.
ALTER TABLE simulations
    ADD COLUMN IF NOT EXISTS persona_pack_ids TEXT[] DEFAULT '{}';

-- Written by the _safe_task error handler in api/simulations.py.
ALTER TABLE simulations
    ADD COLUMN IF NOT EXISTS error_message TEXT;

-- Backfill the array from the singular column so existing simulations keep
-- their pack selection under the new field.
UPDATE simulations
SET persona_pack_ids = ARRAY[persona_pack_id]
WHERE persona_pack_id IS NOT NULL
  AND (persona_pack_ids IS NULL OR persona_pack_ids = '{}');

-- Called by api/documents.py after a successful upload.
CREATE OR REPLACE FUNCTION increment_asset_count(project_uuid UUID, delta INT)
RETURNS VOID AS $$
    UPDATE projects
    SET asset_count = GREATEST(0, COALESCE(asset_count, 0) + delta)
    WHERE id = project_uuid;
$$ LANGUAGE sql;

-- ---------------------------------------------------------------------------
-- Part B: LLM usage ledger
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS llm_usage (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id     UUID REFERENCES organizations(id) ON DELETE CASCADE,
    simulation_id       UUID REFERENCES simulations(id) ON DELETE CASCADE,

    -- Pipeline stage that issued the call. Cost per stage is what makes the
    -- run quote accurate, so this is not optional in practice.
    stage               TEXT NOT NULL,
    model               TEXT NOT NULL,

    input_tokens        INTEGER NOT NULL DEFAULT 0,
    output_tokens       INTEGER NOT NULL DEFAULT 0,
    cache_read_tokens   INTEGER NOT NULL DEFAULT 0,
    cache_write_tokens  INTEGER NOT NULL DEFAULT 0,

    -- Computed at write time from the model's price table. Stored rather than
    -- derived on read so historical rows keep the price that actually applied.
    cost_usd            NUMERIC(12, 6) NOT NULL DEFAULT 0,

    call_count          INTEGER NOT NULL DEFAULT 1,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_llm_usage_simulation
    ON llm_usage (simulation_id, stage);
CREATE INDEX IF NOT EXISTS idx_llm_usage_org_created
    ON llm_usage (organization_id, created_at DESC);

ALTER TABLE llm_usage ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS llm_usage_org_isolation ON llm_usage;
CREATE POLICY llm_usage_org_isolation ON llm_usage
    FOR ALL
    USING (organization_id = ANY(public.user_organization_ids()));

-- Aggregate a simulation's measured spend. Used to verify that what we
-- quoted covers what the run actually cost.
CREATE OR REPLACE FUNCTION simulation_llm_cost(sim_uuid UUID)
RETURNS TABLE (
    stage           TEXT,
    model           TEXT,
    calls           BIGINT,
    input_tokens    BIGINT,
    output_tokens   BIGINT,
    cost_usd        NUMERIC
) AS $$
    SELECT
        u.stage,
        u.model,
        SUM(u.call_count)::BIGINT,
        SUM(u.input_tokens)::BIGINT,
        SUM(u.output_tokens)::BIGINT,
        SUM(u.cost_usd)
    FROM llm_usage u
    WHERE u.simulation_id = sim_uuid
    GROUP BY u.stage, u.model
    ORDER BY SUM(u.cost_usd) DESC;
$$ LANGUAGE sql;
