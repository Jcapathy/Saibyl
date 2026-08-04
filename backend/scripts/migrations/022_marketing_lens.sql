-- Migration 022: the Marketing lens — N-way matched swarms
--
-- SAFE TO APPLY WHILE master IS DEPLOYED. Additive only: one new table and new
-- nullable columns. `master` reads none of it, and the one column added to the
-- hot table (`simulation_events.target_event_id`) is nullable with no default,
-- so existing inserts are unaffected.
--
-- DECISIONS_V2 §5: 2–8 variants judged by the *same* generated audience —
-- identical agents, identical seeds — each in an isolated arena. The audience is
-- shared; that sharing is the entire basis of the comparison. If each variant
-- faced a differently-drawn swarm, differences would be confounded by audience
-- draw and the scoreboard would be noise dressed as signal.

-- ---------------------------------------------------------------------------
-- The variants
-- ---------------------------------------------------------------------------

-- A variant is a row rather than a jsonb blob on `simulations`. V1 modelled this
-- as `variant_a_config` / `variant_b_config`, which is why the A/B could never
-- become an N-way: two columns cannot hold six variants, and `winner_variant`
-- as a bare text column cannot express "the top two overlap and neither wins".
--
-- Those three columns still exist and are still read by `master`. They are left
-- alone here and go at the Phase 4 merge, not before.
CREATE TABLE IF NOT EXISTS simulation_variants (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    simulation_id       UUID NOT NULL REFERENCES simulations(id) ON DELETE CASCADE,
    organization_id     UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,

    -- Stable short key stamped onto every event this arena produces: 'a', 'b',
    -- 'c'… Text rather than an index so an event's arena is legible in the
    -- table without a join, and so the existing `simulation_events.variant`
    -- column — which every run already writes 'a' into — keeps its meaning.
    variant_key         TEXT NOT NULL,

    -- What the marketer calls it. Never generated: an unnamed variant is
    -- unreportable, and "Variant C" in a scoreboard is not a finding.
    label               TEXT NOT NULL DEFAULT '',

    -- The copy under test. This becomes the arena's subject line — it replaces
    -- `simulations.prediction_goal` for the agents in this arena and nowhere
    -- else, which is what makes the arenas comparable and isolated at once.
    content             TEXT NOT NULL,

    -- Display order in the scoreboard. Not the ranking — the ranking is
    -- measured, and a stored rank would go stale the moment the artifact is
    -- rebuilt.
    position            INTEGER NOT NULL DEFAULT 0,

    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    -- One arena per key per run. The runner keys arenas on this, and a
    -- duplicate would silently merge two variants' events into one column of
    -- the scoreboard — which reads as a result rather than as a bug.
    UNIQUE (simulation_id, variant_key)
);

CREATE INDEX IF NOT EXISTS idx_simulation_variants_sim
    ON simulation_variants (simulation_id, position);

-- ---------------------------------------------------------------------------
-- The objective
-- ---------------------------------------------------------------------------

-- DECISIONS_V2 §6: the objective chosen at setup determines the headline
-- metric, and sentiment demotes to a supporting one. An ad meant to drive foot
-- traffic and an ad meant to sell a service succeed differently; scoring both
-- on sentiment measures neither.
--
-- Nullable, because every Founder- and Crisis-lens run has no objective and
-- must not acquire one. NULL reads as "sentiment is the headline", which is the
-- pre-Phase-3 behaviour of every existing run.
ALTER TABLE simulations ADD COLUMN IF NOT EXISTS objective TEXT;

ALTER TABLE simulations DROP CONSTRAINT IF EXISTS simulations_objective_values;
ALTER TABLE simulations ADD CONSTRAINT simulations_objective_values
    CHECK (objective IS NULL OR objective IN (
        'clicks', 'foot_traffic', 'product_sale', 'service_sale',
        'signup', 'awareness'
    ));

-- ---------------------------------------------------------------------------
-- The event graph
-- ---------------------------------------------------------------------------

-- What an event was a reply or reaction to, as a real foreign key.
--
-- The adapters have always emitted this — `SimulationEvent.target_id` — and the
-- runner has always dropped it on write, because the adapter's id is internal
-- to the adapter ('post_3') and means nothing outside the arena that minted it.
-- Resolving it costs a second pass at write time and buys the propagation
-- structure that the Virality Potential Score's cascade component and the
-- Crisis lens both need.
--
-- ON DELETE SET NULL rather than CASCADE: losing a parent event should orphan a
-- reply, not delete it. The reply is still a measured thing an agent said.
ALTER TABLE simulation_events ADD COLUMN IF NOT EXISTS target_event_id UUID
    REFERENCES simulation_events(id) ON DELETE SET NULL;

-- Partial, like the measurement-layer indexes in 018: the overwhelming majority
-- of events are top-level posts with no parent, and indexing their NULLs buys
-- nothing.
CREATE INDEX IF NOT EXISTS idx_simulation_events_target
    ON simulation_events (simulation_id, target_event_id)
    WHERE target_event_id IS NOT NULL;

-- ---------------------------------------------------------------------------
-- RLS — the established org-isolation pattern
-- ---------------------------------------------------------------------------

ALTER TABLE simulation_variants ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS simulation_variants_org_isolation ON simulation_variants;
CREATE POLICY simulation_variants_org_isolation ON simulation_variants
    FOR ALL USING (organization_id = ANY(public.user_organization_ids()));
