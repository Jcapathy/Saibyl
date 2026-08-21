-- 039 — messaging_docs (GTM Module 1: the filled messaging worksheet)
--
-- Additive. No column is added to an existing table and nothing is
-- backfilled, so this is safe to apply before the deploy that writes it —
-- which is the order this repo uses, because a deploy that writes a column
-- the database does not have fails on the customer's first click.
--
-- One row per build, not one per simulation. The playbook's own standing rule
-- is that messaging is never finished — it is revised against customer-facing
-- feedback, market shifts and product changes — so a founder will rebuild
-- this, and UNIQUE (simulation_id) would make the second build destroy the
-- record of what the messaging said before. The reader takes the newest.

CREATE TABLE IF NOT EXISTS messaging_docs (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    simulation_id       UUID NOT NULL REFERENCES simulations(id) ON DELETE CASCADE,
    organization_id     UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,

    -- queued | building | complete | failed
    status              TEXT NOT NULL DEFAULT 'queued',

    -- The worksheet itself: problem, solution, ICP line, exactly three value
    -- propositions, three differentiators with the three-way test's verdict,
    -- the elevator pitch, the objections section and the message test.
    --
    -- One column rather than one per section: the document is read whole and
    -- its shape is owned by
    -- app.services.gtm.messaging_doc.MessagingDoc, so splitting it would put
    -- the schema in two places and let them disagree.
    document            JSONB NOT NULL DEFAULT '{}'::jsonb,

    -- How many measured objections the document was built from. Denormalised
    -- out of the blob because it is rendered next to the document — a founder
    -- can see the worksheet was filled from what the room raised rather than
    -- from a number we chose, without parsing JSON to find out.
    built_from_objections INTEGER NOT NULL DEFAULT 0,

    credits_charged     BIGINT NOT NULL DEFAULT 0,
    -- A founder-readable sentence, never a Python exception. The worker is
    -- responsible for keeping it that way.
    error_message       TEXT,

    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    completed_at        TIMESTAMPTZ
);

-- The reader's query: the newest document for this run, inside this org.
CREATE INDEX IF NOT EXISTS idx_messaging_docs_simulation
    ON messaging_docs (simulation_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_messaging_docs_org
    ON messaging_docs (organization_id, created_at DESC);

ALTER TABLE messaging_docs ENABLE ROW LEVEL SECURITY;

-- Org isolation, matching every other artifact table in this schema. The API
-- reads through the service role and filters by org itself; this is the
-- backstop for anything that ever reaches the table with a user token.
DROP POLICY IF EXISTS messaging_docs_org_isolation ON messaging_docs;
CREATE POLICY messaging_docs_org_isolation ON messaging_docs
    USING (
        organization_id IN (
            SELECT organization_id FROM organization_members
            WHERE user_id = auth.uid()
        )
    );
