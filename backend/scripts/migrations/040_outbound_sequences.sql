-- 040 — outbound_sequences (the GTM module's multi-touch sequences)
--
-- Additive. No column is added to an existing table and nothing is
-- backfilled, so this is safe to apply before the deploy that writes it —
-- which is the order this repo uses, because a deploy that writes a column
-- the database does not have fails on the customer's first click.
--
-- One row per build, not one per simulation: a founder who rewrites the
-- sequences after answering an objection wants to compare, and UNIQUE
-- (simulation_id) would make the second build destroy the record of what was
-- being sent before it. The reader takes the newest complete row.
--
-- **THERE ARE NO CONTACT COLUMNS HERE AND THERE MUST NEVER BE.** This table
-- holds copy a founder sends themselves. Names, email addresses, phone numbers
-- and postal addresses of the people it is sent to are stored nowhere in this
-- product — `gtm_contacts` (migration 027) is the only table that may ever hold
-- a named person, it is gated off by default, and it may hold only name, role,
-- employer and a public profile URL. Read `app/services/gtm/privacy.py` before
-- adding any column to this table; it is the boundary between Saibyl being a
-- tool its customer points at a market and Saibyl being a controller of
-- personal data.

CREATE TABLE IF NOT EXISTS outbound_sequences (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    simulation_id       UUID NOT NULL REFERENCES simulations(id) ON DELETE CASCADE,
    organization_id     UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,

    -- queued | building | complete | failed
    status              TEXT NOT NULL DEFAULT 'queued',

    -- One entry per buyer archetype: the archetype it is written to, the
    -- ordered steps (channel, day offset, purpose, subject, body), which
    -- measured objection each pain-carrying step answers with the verbatim
    -- quotes that prove it, and how many [TODO: …] placeholders the founder
    -- still has to fill before sending.
    sequences           JSONB NOT NULL DEFAULT '[]'::jsonb,
    notes               JSONB NOT NULL DEFAULT '[]'::jsonb,

    -- How many measured objections filled the sequence's pain slots. Rendered,
    -- so a founder can see the touches answer what the room actually raised
    -- rather than three pains we chose for them.
    built_from_objections INTEGER NOT NULL DEFAULT 0,

    -- The variant the scoreboard named, if a message test ran and the
    -- measurement was willing to name one. Columns rather than fields inside
    -- the JSONB because this is provenance for the whole build — "your opening
    -- touches lead with the version your room picked" is a claim the UI makes
    -- above the sequences, and NULL is the common and honest state: the
    -- scoreboard refuses to name a winner whenever the top two arenas overlap.
    winning_variant_key TEXT,
    winning_message     TEXT,

    credits_charged     BIGINT NOT NULL DEFAULT 0,
    -- A founder-readable sentence, never a Python exception. The worker is
    -- responsible for keeping it that way.
    error_message       TEXT,

    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    completed_at        TIMESTAMPTZ
);

-- The reader's query: the newest build for this run, inside this org.
CREATE INDEX IF NOT EXISTS idx_outbound_sequences_simulation
    ON outbound_sequences (simulation_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_outbound_sequences_org
    ON outbound_sequences (organization_id, created_at DESC);

ALTER TABLE outbound_sequences ENABLE ROW LEVEL SECURITY;

-- Org isolation, matching every other artifact table in this schema. The API
-- reads through the service role and filters by org itself; this is the
-- backstop for anything that ever reaches the table with a user token.
DROP POLICY IF EXISTS outbound_sequences_org_isolation ON outbound_sequences;
CREATE POLICY outbound_sequences_org_isolation ON outbound_sequences
    USING (
        organization_id IN (
            SELECT organization_id FROM organization_members
            WHERE user_id = auth.uid()
        )
    );
