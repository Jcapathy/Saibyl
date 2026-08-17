-- 032: Drop `projects.asset_count` and both single-argument RPCs.
--
-- ============================================================================
-- DO NOT APPLY until the deploy that removed the RPC callers
-- (`api/documents.py`) is serving. That code calls `increment_asset_count` /
-- `decrement_asset_count` on every upload and delete — applying this first
-- breaks every upload and delete in production. Safe order: deploy code →
-- apply this. This is HANDOFF_POLISH §5 item 1's ordering constraint, the
-- same one that made 025 create before 017's overload was dropped: never
-- leave a window in which running code calls a function that is not there.
-- ============================================================================
--
-- Why this exists
-- ---------------
-- `asset_count` was a denormalised counter kept by RPC on upload and delete,
-- and it drifted: wrong on 12 of 35 production projects when checked
-- (HANDOFF_POLISH §7) — a third of production trusting a number that had been
-- wrong since March. The fix that shipped stopped reading it everywhere and
-- counts documents directly, so the column is now read by nothing. Leaving it
-- costs nothing today; leaving it *and* forgetting why is how the next reader
-- trusts it again. Dropped, per PRD_V3 §8 item 1.
--
-- The single-argument functions are the ones from 025 (transcribed there from
-- production). The two-argument ancestor from 017 was already dropped at the
-- end of 025, so these two are the only ones left to remove.

ALTER TABLE projects DROP COLUMN IF EXISTS asset_count;

DROP FUNCTION IF EXISTS increment_asset_count(UUID);
DROP FUNCTION IF EXISTS decrement_asset_count(UUID);
