-- Migration 019: agent usernames are unique within a simulation
--
-- ############################################################################
-- ##  DO NOT APPLY TO PRODUCTION UNTIL v2 IS MERGED TO master.              ##
-- ##                                                                        ##
-- ##  master's run_prepare_agents does not dedupe usernames, and 100% of    ##
-- ##  runs since April 2026 produced collisions. Adding this index while    ##
-- ##  master is the deployed branch would make agent insertion fail on      ##
-- ##  essentially every new simulation — an immediate outage of the live    ##
-- ##  product. Apply it in the same window as the merge, after the deploy   ##
-- ##  that carries the generation-time dedup.                               ##
-- ############################################################################
--
-- THE BUG. Platform adapters address agents by username. Asked for 100 handles
-- the model produced 45 distinct ones — nine agents called `mchen_itdir`. The
-- runner mapped events back through the username, so all nine agents' events
-- landed on one row and the nine shared a single memory. Confidence intervals
-- are computed across agents, so nine independent observations counted as one
-- and every band in the artifact was drawn from a swarm less than half its
-- true size.
--
-- SCOPE. Measured on production 2026-08-02: 248 colliding username groups
-- across 44 of 63 simulations, 377 agent rows affected out of 2,512. Every
-- simulation from April 2026 onward is affected. This is a long-standing V1
-- defect, not a Phase 1 regression — Phase 1 is simply the first thing that
-- depended on agent identity being real, and so the first thing to notice.
--
-- THREE LAYERS now prevent it, of which this is the last:
--   1. Generation dedupes usernames with a numeric suffix, re-checking after
--      each attempt so a suffixed name cannot collide with a literal one.
--   2. Identity flows to adapters as `agent_id` and rides on every event;
--      `username` is a display handle. Adapters key memory on the id.
--   3. This constraint — because 1 and 2 are conventions enforced by code that
--      somebody will eventually change, and the database is the only place an
--      invariant holds regardless of who writes the next caller.
--
-- WHAT THIS DOES NOT FIX. Renaming duplicates does not repair historical event
-- attribution. There is no record of which of nine identically-named agents
-- produced a given event, so those runs' agent counts stay understated and
-- their confidence intervals stay wider than truth. **Do not use any run
-- created before this migration as a calibration baseline for agent counts.**

-- ---------------------------------------------------------------------------
-- Repair existing duplicates, or the unique index cannot be built
-- ---------------------------------------------------------------------------
--
-- The suffix separator is '~', which the agent generator cannot emit: handles
-- come from an LLM instructed to produce lowercase, space-free social handles,
-- and are otherwise built from `{archetype_id}_{platform}_{index}`. Because
-- (simulation_id, base_username, occurrence) is unique by construction and no
-- existing username can contain '~', one pass is provably sufficient — unlike
-- a plain numeric suffix, which can collide with a literal `name2`.
WITH ranked AS (
    SELECT
        id,
        username,
        ROW_NUMBER() OVER (
            PARTITION BY simulation_id, username ORDER BY created_at, id
        ) AS occurrence
    FROM simulation_agents
)
UPDATE simulation_agents a
SET username = ranked.username || '~' || ranked.occurrence::text
FROM ranked
WHERE a.id = ranked.id
  AND ranked.occurrence > 1;

-- ---------------------------------------------------------------------------
-- The invariant
-- ---------------------------------------------------------------------------

CREATE UNIQUE INDEX IF NOT EXISTS idx_simulation_agents_unique_username
    ON simulation_agents (simulation_id, username);
