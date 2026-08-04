-- Migration 024: drop the V1 A/B columns
--
-- Safe now and not before. These four were readable until 2026-08-04 because
-- `master` was a different branch from `v2` and still wrote them. `master` and
-- `v2` are now the same commit, nothing reads or writes any of them, and the
-- code removing them ships in the same deploy.
--
-- WHAT THEY WERE. V1 modelled a two-variant test as two jsonb blobs plus a
-- winner string on `simulations`. It is the shape that made the defect
-- inevitable: two columns cannot hold six variants, so an N-way test was
-- unrepresentable; and `winner_variant TEXT` cannot express "the top two
-- overlap and neither wins", so the schema had no way to record the honest
-- answer. `run_simulation_ab` then called `run_simulation` once and variant B
-- was never executed at all.
--
-- WHAT REPLACES THEM. `simulation_variants` (022) holds 2-8 arenas as rows, and
-- the scoreboard in `simulation_analysis.artifact` carries the comparison with
-- a confidence interval per variant and a null winner when they overlap.
--
-- DESTRUCTIVE, and deliberately so. Keeping four columns that describe a
-- feature the product no longer has is how the next person builds against them
-- by mistake.
--
-- Measured on production before dropping, across 70 simulations:
--
--   variant_a_config IS NOT NULL     0
--   variant_b_config IS NOT NULL     0
--   winner_variant   IS NOT NULL     0
--   is_ab_test = true                2
--
-- **Two runs carry the flag**, and what is lost by dropping it is the record
-- that someone once ticked a box. Both have NULL configs and NULL winner,
-- because the flag never did anything: it selected between two functions that
-- were the same function. No variant data exists to migrate, because none was
-- ever captured.

ALTER TABLE simulations DROP COLUMN IF EXISTS variant_a_config;
ALTER TABLE simulations DROP COLUMN IF EXISTS variant_b_config;
ALTER TABLE simulations DROP COLUMN IF EXISTS winner_variant;
ALTER TABLE simulations DROP COLUMN IF EXISTS is_ab_test;
