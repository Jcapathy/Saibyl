-- Migration 028: refund a discovery for the queries it never ran
--
-- NOT APPLIED. Apply before deploying the backend change that accompanies it —
-- `services/gtm/store.refund_run` calls `refund_discovery_credits`, and until
-- this lands that call raises, is logged as `gtm_refund_unavailable`, and the
-- run simply closes without a refund. That is the safe failure direction: no
-- money moves in either direction on a missing function.
--
-- SAFE TO APPLY WHILE master IS DEPLOYED. Two additive columns with NOT NULL
-- DEFAULTs that reproduce today's behaviour (nothing refunded, nothing
-- reconciled) and one new function. `master` reads none of it.
--
-- Verified against production `information_schema` before writing:
-- `gtm_discovery_runs` has 22 columns and none matching `%refund%`, and
-- `pg_proc` holds no function named `refund_discovery_credits`.
--
--   Part A  gtm_discovery_runs.credits_refunded / refunded_at
--   Part B  refund_discovery_credits() — atomic, idempotent
--
-- ---------------------------------------------------------------------------
-- WHY NOT `grant_credits`
-- ---------------------------------------------------------------------------
-- `grant_credits(org_uuid, amount)` is a *cycle* grant, not a credit. Its real
-- body in production (verified, not assumed):
--
--     UPDATE organizations
--     SET credits_balance = COALESCE(credits_balance, 0) + amount,
--         credits_granted = amount,          -- OVERWRITES the plan's grant
--         credit_cycle_start = NOW()         -- RESTARTS the billing cycle
--     WHERE id = org_uuid
--
-- Refunding 522 credits through it would set a starter org's `credits_granted`
-- from 19,800 to 522 and move `credit_cycle_start` to now. Every downstream
-- reader of the grant — the balance warnings in the Run Configurator, the usage
-- bars, the monthly reset — would then be describing a plan the customer is not
-- on. A refund adjusts the balance and nothing else.

-- ---------------------------------------------------------------------------
-- Part A: what was given back, and whether it has been
-- ---------------------------------------------------------------------------

-- `credits_refunded` is the amount returned; `refunded_at` is the claim flag the
-- idempotency check reads. They are separate columns because a legitimate
-- reconciliation can refund zero — a run that delivered everything it charged
-- for is reconciled and owes nothing, and that is a different fact from a run
-- nobody has reconciled yet.
ALTER TABLE gtm_discovery_runs
    ADD COLUMN IF NOT EXISTS credits_refunded INTEGER NOT NULL DEFAULT 0;

ALTER TABLE gtm_discovery_runs
    ADD COLUMN IF NOT EXISTS refunded_at TIMESTAMPTZ;

COMMENT ON COLUMN gtm_discovery_runs.credits_refunded IS
    'Credits returned for queries this run never ran. credits_charged minus '
    'this is what the customer actually paid.';
COMMENT ON COLUMN gtm_discovery_runs.refunded_at IS
    'Set once, by refund_discovery_credits. NULL means not yet reconciled; a '
    'non-NULL value with credits_refunded = 0 means reconciled and nothing owed.';

-- ---------------------------------------------------------------------------
-- Part B: the refund itself
-- ---------------------------------------------------------------------------
--
-- One function rather than two statements from Python, because the two halves
-- must not be separable. The claim (`refunded_at IS NULL` -> NOW()) and the
-- balance credit run in one transaction, so there is no window in which a run
-- is marked refunded and the balance has not moved, and none in which the
-- balance has moved and the run is not marked.
--
-- **Idempotency is the WHERE clause.** `refunded_at IS NULL` is a
-- compare-and-set: the first caller wins the row, every later caller — a retry,
-- a double callback, two API processes reconciling the same run at once —
-- updates zero rows, takes the early return, and credits nothing. Postgres
-- serialises the two UPDATEs on the row lock, so "both saw NULL" cannot happen.
--
-- Returns (refunded, balance). `refunded = 0` with a NULL balance means the run
-- was already reconciled; the caller logs that and moves on rather than
-- treating it as an error.
CREATE OR REPLACE FUNCTION refund_discovery_credits(run_uuid UUID, amount BIGINT)
RETURNS TABLE (refunded BIGINT, balance BIGINT) AS $$
DECLARE
    v_org     UUID;
    v_balance BIGINT;
BEGIN
    IF amount IS NULL OR amount <= 0 THEN
        -- Still claims the row, so a run that owes nothing is recorded as
        -- reconciled rather than being re-examined on every read.
        UPDATE gtm_discovery_runs
           SET credits_refunded = 0,
               refunded_at = NOW()
         WHERE id = run_uuid
           AND refunded_at IS NULL
        RETURNING organization_id INTO v_org;
        RETURN QUERY SELECT 0::BIGINT, NULL::BIGINT;
        RETURN;
    END IF;

    UPDATE gtm_discovery_runs
       SET credits_refunded = amount,
           refunded_at = NOW()
     WHERE id = run_uuid
       AND refunded_at IS NULL
    RETURNING organization_id INTO v_org;

    IF v_org IS NULL THEN
        -- Already reconciled, or the run row is gone. Either way nothing is
        -- credited. This is the branch a retry lands in.
        RETURN QUERY SELECT 0::BIGINT, NULL::BIGINT;
        RETURN;
    END IF;

    -- Deliberately not `grant_credits` — see the header. Only the balance moves.
    UPDATE organizations
       SET credits_balance = COALESCE(credits_balance, 0) + amount
     WHERE id = v_org
    RETURNING credits_balance INTO v_balance;

    RETURN QUERY SELECT amount, v_balance;
END;
$$ LANGUAGE plpgsql;

-- ---------------------------------------------------------------------------
-- Part C: the one run this defect has already reached
-- ---------------------------------------------------------------------------
--
-- Run 534353e7-a3ab-4f42-852f-da53103f9f2b, org ac1b90b7 (Beta Test Org):
-- 12 queries requested, 6 completed and 1 empty (7 delivered), 0 failed,
-- closed `partial` on "deadline of 180s reached", charged 1,254 credits.
--
--   charged  estimate_discovery_cost(12).credits = 1,254
--   kept     estimate_discovery_cost(7).credits  =   732
--   refund   1,254 - 732                         =   522
--
-- Run this once, after the function above exists. It is idempotent by the same
-- compare-and-set as every other refund, so re-running it credits nothing.
--
--   SELECT * FROM refund_discovery_credits(
--       '534353e7-a3ab-4f42-852f-da53103f9f2b'::uuid, 522);
--
-- Left commented rather than executed inline: a migration that moves money
-- should be read by a person before it runs.
