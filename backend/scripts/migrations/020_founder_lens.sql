-- Migration 020: the Founder lens — synthesized ICPs, the adversarial cohort,
-- and stage-aware runs
--
-- SAFE TO APPLY WHILE master IS DEPLOYED. Everything here is additive: one new
-- table, new nullable columns, and new columns with defaults that reproduce
-- today's behaviour. `master` reads none of it and writes none of it, so a
-- master-served run behaves exactly as it does now. This is deliberately unlike
-- migration 019, which must wait for the merge — see that file's header.
--
-- Three things Phase 2 needs from the schema:
--
--   Part A  icp_profiles. DECISIONS_V2 §3: the ICP is *derived from the
--           founder's own material*, not picked from a library of 16 packs. A
--           synthesized profile is both a human-editable object (the founder
--           corrects what the model proposed) and a compiled persona pack (what
--           the engine consumes). Both live in one row so an edit and the pack
--           the next run uses cannot drift apart.
--
--   Part B  The adversarial cohort's grounding. PRD §4 permits incumbent-aligned
--           agents only when they are grounded in competitor material the user
--           uploaded — never in model memory. That guardrail is unenforceable
--           unless the database can say which uploaded document is competitor
--           material, so `documents.material_kind` records it.
--
--   Part C  Run shape: which lens, which founder stage, which ICP, and how much
--           of the swarm is adversarial.

-- ---------------------------------------------------------------------------
-- Part A: synthesized ICP profiles
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS icp_profiles (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id          UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    organization_id     UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,

    name                TEXT NOT NULL,
    -- One-paragraph read of what the product is, from the uploaded material.
    -- Shown to the founder as the first check on whether synthesis understood
    -- the input at all: if this is wrong, every archetype below it is wrong,
    -- and that is much cheaper to notice here than after a run.
    product_summary     TEXT NOT NULL DEFAULT '',

    -- The editable object. Buyer/user archetypes with role, seniority, budget
    -- authority, incumbent tooling, switching cost, evaluation criteria and
    -- skepticism triggers. Validated by
    -- app.services.engine.personas.icp_schema.ICPProfile before it is written.
    profile             JSONB NOT NULL,

    -- The same profile compiled into a PersonaPack, which is what the engine
    -- actually runs. Stored rather than compiled on read so that a run is
    -- reproducible: recompiling from an edited profile would silently change
    -- the audience of a re-simulation, and the inoculation loop's whole claim
    -- is that the audience did not change between the two runs.
    pack_data           JSONB NOT NULL,
    -- Pack id, 'icp_<uuid-hex>'. get_pack() resolves this prefix here.
    pack_id             TEXT NOT NULL UNIQUE,

    -- Which built-in packs were used as demographic and psychometric priors.
    -- The 16 packs are priors and blend targets, not the answer (DECISIONS §3);
    -- recording which ones were leaned on makes that auditable rather than a
    -- claim in a doc.
    prior_pack_ids      TEXT[] NOT NULL DEFAULT '{}',
    -- Documents the synthesis actually read. An ICP whose sources were later
    -- deleted is still explainable.
    source_document_ids UUID[] NOT NULL DEFAULT '{}',
    -- Competitor names found *in the uploaded material*. Empty means the
    -- adversarial cohort must be generated with no named entity.
    competitors         JSONB NOT NULL DEFAULT '[]'::jsonb,

    -- False until a human touches it. Synthesis proposes, the founder corrects
    -- (DECISIONS §3) — and if founders correct everything, that is the signal
    -- to fall back to form-first, so it is worth being able to measure.
    edited_by_user      BOOLEAN NOT NULL DEFAULT FALSE,
    synthesis_model     TEXT,

    created_by          UUID REFERENCES auth.users(id),
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_icp_profiles_project
    ON icp_profiles (project_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_icp_profiles_org
    ON icp_profiles (organization_id, created_at DESC);

-- ---------------------------------------------------------------------------
-- Part B: grounding for the adversarial cohort
-- ---------------------------------------------------------------------------

-- 'own'        — the founder's own material: PRD, landing page, deck, pricing.
-- 'competitor' — a competitor's material, uploaded deliberately. The ONLY
--                admissible source for a named-incumbent adversarial agent.
-- 'market'     — analyst notes, category writing, forum threads. Context, but
--                not a licence to name a competitor.
--
-- NULL means a document uploaded before this column existed. It is treated as
-- 'own', which is the conservative reading: an unlabelled document can never
-- authorise naming a competitor.
ALTER TABLE documents ADD COLUMN IF NOT EXISTS material_kind TEXT;

ALTER TABLE documents DROP CONSTRAINT IF EXISTS documents_material_kind_values;
ALTER TABLE documents ADD CONSTRAINT documents_material_kind_values
    CHECK (material_kind IS NULL OR material_kind IN ('own', 'competitor', 'market'));

CREATE INDEX IF NOT EXISTS idx_documents_competitor_material
    ON documents (project_id)
    WHERE material_kind = 'competitor';

-- ---------------------------------------------------------------------------
-- Part C: run shape
-- ---------------------------------------------------------------------------

-- Deliberately nullable with no backfill. The 63 existing simulations were run
-- before lenses existed; stamping them 'crisis' or 'founder' would be inventing
-- an attribute nobody recorded, which is the exact failure mode Phase 1 spent
-- itself removing. NULL reads as "legacy, no lens", and the code treats it that
-- way rather than guessing.
ALTER TABLE simulations ADD COLUMN IF NOT EXISTS lens TEXT;

ALTER TABLE simulations DROP CONSTRAINT IF EXISTS simulations_lens_values;
ALTER TABLE simulations ADD CONSTRAINT simulations_lens_values
    CHECK (lens IS NULL OR lens IN ('founder', 'marketing', 'crisis'));

-- The five Founder-lens entry points (PRD §5). NULL for every other lens.
ALTER TABLE simulations ADD COLUMN IF NOT EXISTS founder_stage TEXT;

ALTER TABLE simulations DROP CONSTRAINT IF EXISTS simulations_founder_stage_values;
ALTER TABLE simulations ADD CONSTRAINT simulations_founder_stage_values
    CHECK (founder_stage IS NULL OR founder_stage IN (
        'concept_validation', 'pre_launch_positioning', 'launch_gtm',
        'growth', 'fundraise'
    ));

ALTER TABLE simulations ADD COLUMN IF NOT EXISTS icp_profile_id UUID
    REFERENCES icp_profiles(id) ON DELETE SET NULL;

-- Share of the swarm that is incumbent-aligned. 0 reproduces today's behaviour
-- exactly, which is why every existing run can carry this column truthfully.
--
-- The ceiling is 0.5 and it is enforced here rather than only in the API. Past
-- half the swarm the run stops being a market simulation and becomes a
-- competitor focus group: the headline valence is then a function of the share
-- the user picked, and it will read as a measurement of the market.
ALTER TABLE simulations ADD COLUMN IF NOT EXISTS adversarial_share REAL NOT NULL DEFAULT 0;

ALTER TABLE simulations DROP CONSTRAINT IF EXISTS simulations_adversarial_share_range;
ALTER TABLE simulations ADD CONSTRAINT simulations_adversarial_share_range
    CHECK (adversarial_share >= 0 AND adversarial_share <= 0.5);

-- Adversarial agents must be identifiable after the fact, not inferred from
-- their archetype label. Every report and export labels them synthetic
-- (PRD §4), the analysis artifact splits cohorts on this, and the objection
-- ranking needs to know an objection came from the incumbent's side of the room.
ALTER TABLE simulation_agents ADD COLUMN IF NOT EXISTS is_adversarial BOOLEAN NOT NULL DEFAULT FALSE;
-- 'incumbent_employee' | 'incumbent_power_user' | 'sunk_cost_consultant' |
-- 'category_skeptic' | 'free_alternative_advocate', or NULL for a buyer agent.
ALTER TABLE simulation_agents ADD COLUMN IF NOT EXISTS adversarial_role TEXT;

CREATE INDEX IF NOT EXISTS idx_simulation_agents_adversarial
    ON simulation_agents (simulation_id)
    WHERE is_adversarial;

-- ---------------------------------------------------------------------------
-- RLS — the established org-isolation pattern
-- ---------------------------------------------------------------------------

ALTER TABLE icp_profiles ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS icp_profiles_org_isolation ON icp_profiles;
CREATE POLICY icp_profiles_org_isolation ON icp_profiles
    FOR ALL USING (organization_id = ANY(public.user_organization_ids()));
