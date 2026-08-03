-- Migration 021: the inoculation loop
--
-- SAFE TO APPLY WHILE master IS DEPLOYED. Additive only: two new tables and
-- new nullable columns on `simulations`. `master` reads none of it.
--
-- DECISIONS_V2 §4: detect -> draft a counter-asset -> **re-simulate with the
-- asset pre-seeded** -> report the measured before/after delta per objection.
-- Step 3 is the entire product. Without it, "here's what to pre-position" is an
-- LLM opinion that every competitor can generate and no founder should trust.
-- With it, Saibyl can say *this specific disclosure moved this specific
-- objection from 34% of the swarm to 9%, and here are the agents who changed
-- their mind* — which cannot be faked without the Phase 1 measurement layer.
--
-- The schema exists to make one claim defensible: **the audience did not
-- change between the two runs.** Everything below follows from that.

-- ---------------------------------------------------------------------------
-- The assets
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS inoculation_assets (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    -- The run whose objections this answers. Not the run it is tested in —
    -- that is the child, and it points back here.
    simulation_id       UUID NOT NULL REFERENCES simulations(id) ON DELETE CASCADE,
    organization_id     UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,

    -- The canonical objection this is written against. Deliberately a text key
    -- rather than a foreign key to canonical_objections: the key is stable and
    -- deterministic from the label, and the whole point of the loop is to line
    -- the same objection up across two different simulations, whose
    -- canonical_objections rows have different ids.
    objection_key       TEXT NOT NULL,
    objection_label     TEXT NOT NULL DEFAULT '',

    -- disclosure | roadmap | pricing_rationale | security_page |
    -- migration_guide | faq_entry | comparison_page
    asset_type          TEXT NOT NULL,
    title               TEXT NOT NULL,
    -- The asset itself, as it would be published. Agents read this verbatim.
    body                TEXT NOT NULL,

    -- What this asset is predicted to do, stated BEFORE the re-simulation runs.
    -- Written down here rather than inferred afterwards, because an unstated
    -- hypothesis is one that is always retroactively correct — and "the asset
    -- did not work" is a finding this product has to be able to deliver.
    hypothesis          TEXT NOT NULL DEFAULT '',

    -- draft    — generated, not yet chosen
    -- selected — chosen for the next re-simulation
    -- tested   — has appeared in a completed re-simulation
    status              TEXT NOT NULL DEFAULT 'draft',

    -- False until a human edits it. A founder rewriting every generated asset
    -- is the signal that drafting is not pulling its weight.
    edited_by_user      BOOLEAN NOT NULL DEFAULT FALSE,

    created_by          UUID REFERENCES auth.users(id),
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

ALTER TABLE inoculation_assets DROP CONSTRAINT IF EXISTS inoculation_assets_type_values;
ALTER TABLE inoculation_assets ADD CONSTRAINT inoculation_assets_type_values
    CHECK (asset_type IN (
        'disclosure', 'roadmap', 'pricing_rationale', 'security_page',
        'migration_guide', 'faq_entry', 'comparison_page'
    ));

ALTER TABLE inoculation_assets DROP CONSTRAINT IF EXISTS inoculation_assets_status_values;
ALTER TABLE inoculation_assets ADD CONSTRAINT inoculation_assets_status_values
    CHECK (status IN ('draft', 'selected', 'tested'));

CREATE INDEX IF NOT EXISTS idx_inoculation_assets_sim
    ON inoculation_assets (simulation_id, objection_key);

-- ---------------------------------------------------------------------------
-- The re-simulation
-- ---------------------------------------------------------------------------

-- A re-simulation is an ordinary simulation with a parent. Making it a real
-- `simulations` row rather than a special object means it measures, analyses,
-- reports, prices and reconciles through exactly the same code — and the
-- before/after comparison is then two artifacts built by one builder, which is
-- the only way the two numbers are actually comparable.
ALTER TABLE simulations ADD COLUMN IF NOT EXISTS parent_simulation_id UUID
    REFERENCES simulations(id) ON DELETE SET NULL;

-- Assets pre-seeded into this run's environment. Empty on every ordinary run.
ALTER TABLE simulations ADD COLUMN IF NOT EXISTS inoculation_asset_ids UUID[]
    NOT NULL DEFAULT '{}';

CREATE INDEX IF NOT EXISTS idx_simulations_parent
    ON simulations (parent_simulation_id)
    WHERE parent_simulation_id IS NOT NULL;

-- ---------------------------------------------------------------------------
-- The measured delta
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS inoculation_results (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    parent_simulation_id UUID NOT NULL REFERENCES simulations(id) ON DELETE CASCADE,
    child_simulation_id  UUID NOT NULL REFERENCES simulations(id) ON DELETE CASCADE,
    organization_id      UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,

    -- Per-objection before/after, validated by
    -- app.services.intelligence.inoculation_schema.InoculationResult.
    -- [{objection_key, label, before: {...}, after: {...}, verdict, ...}]
    deltas              JSONB NOT NULL DEFAULT '[]'::jsonb,

    -- Headline valence before and after, with their intervals. Reported even
    -- when it did not move: an asset that kills an objection without shifting
    -- the headline is a real and useful outcome, and hiding the headline would
    -- make it look like more than it was.
    headline_before     JSONB NOT NULL DEFAULT '{}'::jsonb,
    headline_after      JSONB NOT NULL DEFAULT '{}'::jsonb,

    -- How many of the tested assets actually moved their target objection
    -- beyond the confidence bands. This is the number the product is sold on,
    -- and it is allowed to be zero.
    assets_tested       INTEGER NOT NULL DEFAULT 0,
    assets_effective    INTEGER NOT NULL DEFAULT 0,

    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    -- One result per (parent, child) pair. Re-running the comparison replaces
    -- it: it is derived from two immutable artifacts, so an old copy has no
    -- evidentiary value.
    UNIQUE (parent_simulation_id, child_simulation_id)
);

CREATE INDEX IF NOT EXISTS idx_inoculation_results_parent
    ON inoculation_results (parent_simulation_id, created_at DESC);

-- ---------------------------------------------------------------------------
-- RLS — the established org-isolation pattern
-- ---------------------------------------------------------------------------

ALTER TABLE inoculation_assets  ENABLE ROW LEVEL SECURITY;
ALTER TABLE inoculation_results ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS inoculation_assets_org_isolation ON inoculation_assets;
CREATE POLICY inoculation_assets_org_isolation ON inoculation_assets
    FOR ALL USING (organization_id = ANY(public.user_organization_ids()));

DROP POLICY IF EXISTS inoculation_results_org_isolation ON inoculation_results;
CREATE POLICY inoculation_results_org_isolation ON inoculation_results
    FOR ALL USING (organization_id = ANY(public.user_organization_ids()));
