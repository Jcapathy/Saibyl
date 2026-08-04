-- 025: Bring the asset-count RPCs into the migrations.
--
-- NOT YET APPLIED. Written to close a drift, not to change behaviour.
--
-- Why this exists
-- ---------------
-- `api/documents.py` calls `increment_asset_count(p_project_id)` on upload and
-- `decrement_asset_count(p_project_id)` on delete. Neither of those signatures
-- appears in any migration:
--
--   * 017 created `increment_asset_count(project_uuid UUID, delta INT)` — a
--     different parameter name and a different arity. PostgREST resolves an RPC
--     by the argument *names* in the JSON body, so a call sending
--     `{"p_project_id": ...}` does not match it.
--   * `decrement_asset_count` was never written in a migration at all.
--
-- Both single-argument functions nevertheless exist in production, added by
-- hand. Verified 2026-08-03 against project txmvwuekkiedgxwovorp:
--
--   select p.proname, pg_get_function_identity_arguments(p.oid)
--   from pg_proc p join pg_namespace n on n.oid = p.pronamespace
--   where n.nspname = 'public' and p.proname like '%_asset_count';
--
--   decrement_asset_count | p_project_id uuid
--   increment_asset_count | p_project_id uuid
--   increment_asset_count | project_uuid uuid, delta integer
--
-- So uploads and deletes work today, and would break the moment the database is
-- rebuilt from migrations — a restored dump, a staging clone, a fresh
-- environment. The bodies below are transcribed from `pg_get_functiondef` on
-- the deployed functions, so applying this to production is a no-op and
-- applying it to a fresh database reproduces production.
--
-- Standing lesson this migration is written under: `IF NOT EXISTS` guards hide
-- type drift. `CREATE OR REPLACE FUNCTION` has the same property for bodies, so
-- the definitions here were read out of production rather than reconstructed
-- from the call sites, and `projects.asset_count` was confirmed to be `integer`
-- in `information_schema.columns` before relying on it.

-- ---------------------------------------------------------------------------
-- The two functions the application actually calls.
-- ---------------------------------------------------------------------------

CREATE OR REPLACE FUNCTION increment_asset_count(p_project_id UUID)
RETURNS VOID AS $$
    UPDATE projects
    SET asset_count = COALESCE(asset_count, 0) + 1
    WHERE id = p_project_id;
$$ LANGUAGE sql;

CREATE OR REPLACE FUNCTION decrement_asset_count(p_project_id UUID)
RETURNS VOID AS $$
    UPDATE projects
    SET asset_count = GREATEST(0, COALESCE(asset_count, 0) - 1)
    WHERE id = p_project_id;
$$ LANGUAGE sql;

-- ---------------------------------------------------------------------------
-- Retire the two-argument overload from 017.
-- ---------------------------------------------------------------------------
--
-- Nothing calls it. Grepped for the name across `backend/app`, `backend/tests`,
-- `backend/scripts`, `frontend/src`, `shared` and `docs`: the only two call
-- sites are `api/documents.py:95` and `services/ingestion/asset_processor.py`,
-- and both send `{"p_project_id": ...}`.
--
-- Dropped rather than left in place because two same-named functions
-- distinguished only by parameter name is the exact hazard that produced this
-- migration: the next person to read 017 will believe they have found the
-- definition the application uses, and they will be wrong. It is also how the
-- `simulation_llm_cost(sim_uuid)` vs `sim_id` defect happened.
--
-- Order matters if this is ever run alongside a deploy: the single-argument
-- functions above are created first, so there is no window in which neither
-- exists.

DROP FUNCTION IF EXISTS increment_asset_count(UUID, INT);
