-- 038 — answer_packs (the GTM module's objection matrix)
--
-- Additive. No column is added to an existing table and nothing is
-- backfilled, so this is safe to apply before the deploy that writes it —
-- which is the order this repo uses, because a deploy that writes a column
-- the database does not have fails on the customer's first click.
--
-- One pack per build, not one per simulation: a founder who re-runs the
-- matrix after answering an objection wants to compare, and UNIQUE
-- (simulation_id) would make the second build destroy the evidence of the
-- first. The reader takes the newest complete row.

CREATE TABLE IF NOT EXISTS answer_packs (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    simulation_id       UUID NOT NULL REFERENCES simulations(id) ON DELETE CASCADE,
    organization_id     UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,

    -- queued | building | complete | failed
    status              TEXT NOT NULL DEFAULT 'queued',

    -- The matrix itself: one row per measured objection, each carrying the
    -- four moves and the verbatim quotes that prove the objection is real.
    rows                JSONB NOT NULL DEFAULT '[]'::jsonb,
    -- One card per alternative the buyer is really choosing between,
    -- including doing nothing and building it in-house.
    battlecards         JSONB NOT NULL DEFAULT '[]'::jsonb,
    notes               JSONB NOT NULL DEFAULT '[]'::jsonb,

    -- How many measured objections the pack was built from. Rendered, so a
    -- founder can see the matrix covers what the room actually raised rather
    -- than a number we chose.
    built_from_objections INTEGER NOT NULL DEFAULT 0,

    credits_charged     BIGINT NOT NULL DEFAULT 0,
    -- A founder-readable sentence, never a Python exception. The worker is
    -- responsible for keeping it that way.
    error_message       TEXT,

    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    completed_at        TIMESTAMPTZ
);

-- The reader's query: the newest pack for this run, inside this org.
CREATE INDEX IF NOT EXISTS idx_answer_packs_simulation
    ON answer_packs (simulation_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_answer_packs_org
    ON answer_packs (organization_id, created_at DESC);

ALTER TABLE answer_packs ENABLE ROW LEVEL SECURITY;

-- Org isolation, matching every other artifact table in this schema. The API
-- reads through the service role and filters by org itself; this is the
-- backstop for anything that ever reaches the table with a user token.
DROP POLICY IF EXISTS answer_packs_org_isolation ON answer_packs;
CREATE POLICY answer_packs_org_isolation ON answer_packs
    USING (
        organization_id IN (
            SELECT organization_id FROM organization_members
            WHERE user_id = auth.uid()
        )
    );
