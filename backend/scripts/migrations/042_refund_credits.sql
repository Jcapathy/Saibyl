-- Migration 042: give a charge back without restarting the billing cycle
--
-- APPLIED to production (txmvwuekkiedgxwovorp) 2026-08-23, before the backend
-- change that calls it. Order mattered: `agent_pricing.refund_credits` calls
-- this function, and until it existed that call raised, was logged as
-- `credits_refund_failed`, and the job closed without paying. That is the safe
-- failure direction — the same one migration 028 chose — but it is inert, not
-- correct.
--
-- Verified before applying: `grant_credits` in production really does
-- `credits_granted = amount, credit_cycle_start = NOW()`, and no `refund_credits`
-- existed. Verified after: no customer org's `credits_granted` had been
-- corrupted — every one still matched its plan tier — so the bug was live but
-- never hit a real account.
--
-- ---------------------------------------------------------------------------
-- WHY NOT `grant_credits`
-- ---------------------------------------------------------------------------
-- The third time this has had to be written down. Migration 028's header said
-- it for the GTM discovery refund, migration 031's said it for top-ups, and
-- `gtm/store.refund_run`'s docstring says it again — and the two refund paths
-- that shipped on 2026-08-22 (`website_tasks`, `maintenance/reaper`, and every
-- caller of `agent_pricing.refund_credits`) went through `grant_credits`
-- anyway.
--
-- `grant_credits(org_uuid, amount)` is a *cycle* grant. Its body (018:203):
--
--     UPDATE organizations
--     SET credits_balance = COALESCE(credits_balance, 0) + amount,
--         credits_granted = amount,          -- OVERWRITES the plan's grant
--         credit_cycle_start = NOW()         -- RESTARTS the billing cycle
--     WHERE id = org_uuid
--
-- A Growth org with credits_granted = 59,800 that hits one empty-shortlist
-- refund of 3,000 ends with credits_granted = 3,000 and its month restarted
-- today. `get_credit_balance` reads `credits_granted or tier_grant(plan)`, so
-- 3,000 is truthy and the real grant is never recovered; `GET /billing/credits`
-- then reports a usage bar of 766.7%. A refund adjusts the balance and nothing
-- else.
--
-- ---------------------------------------------------------------------------
-- Idempotency lives in the caller's row, not here
-- ---------------------------------------------------------------------------
-- Unlike `refund_discovery_credits` (028) and `apply_credit_topup` (031), this
-- function has no claim row to compare-and-set on: it is called for artifacts
-- across seven tables, and they do not share a refund flag. The callers gate it
-- instead — a refund is paid only by whichever writer actually closed the row
-- (`website_tasks._record_failure` and `reaper.sweep_once` both check that
-- their guarded UPDATE matched), so exactly one of them pays.
CREATE OR REPLACE FUNCTION refund_credits(org_uuid UUID, amount BIGINT)
RETURNS BIGINT AS $$
    UPDATE organizations
    SET credits_balance = COALESCE(credits_balance, 0) + GREATEST(0, amount)
    WHERE id = org_uuid
    RETURNING credits_balance;
$$ LANGUAGE sql;
