-- 031: One-off credit top-ups.
--
-- Additive: one new table, one new function. Nothing existing changes.
--
-- Why this exists
-- ---------------
-- A founder deciding whether this product is worth $99 a month should be able
-- to spend $10 first and find out. The top-up is a `mode="payment"` Stripe
-- Checkout with an **ad-hoc amount** — it needs no Price ID, which is why it
-- can ship while the tier migration is still blocked on Stripe Products.
--
-- ---------------------------------------------------------------------------
-- Part A: the ledger
-- ---------------------------------------------------------------------------
--
-- A row per top-up, written when Checkout opens and claimed when Stripe says it
-- was paid. It exists so the credit can be idempotent and so "this customer
-- paid us $20" is a fact with a row behind it rather than an inference from a
-- balance that moved.
--
-- `stripe_session_id` is UNIQUE and that uniqueness is load-bearing: it is the
-- key the webhook claims on. Stripe retries a webhook until it gets a 200, and
-- it can deliver the same event twice even after one — so "credited twice" is
-- not a hypothetical, it is the default behaviour of the system we are
-- integrating with.

CREATE TABLE IF NOT EXISTS credit_topups (
    id                       UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id          UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    -- The Checkout session. UNIQUE because it is the idempotency key.
    stripe_session_id        TEXT NOT NULL UNIQUE,
    stripe_payment_intent    TEXT,
    -- What the founder chose to pay, in cents. Integer because money in a float
    -- drifts, and this number is reconciled against Stripe.
    amount_cents             INTEGER NOT NULL CHECK (amount_cents > 0),
    -- What they get for it, computed at Checkout time and stored. Stored rather
    -- than recomputed on credit, because the rate is a published commercial
    -- number and a founder must receive what the screen quoted them, not what
    -- the rate happens to be when the webhook lands.
    credits                  BIGINT NOT NULL CHECK (credits > 0),
    -- `pending` until Stripe confirms. Never `paid` on our say-so.
    status                   TEXT NOT NULL DEFAULT 'pending'
                             CHECK (status IN ('pending', 'paid', 'expired')),
    created_by               UUID,
    created_at               TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    -- The claim flag. NULL means the balance has not moved for this row.
    credited_at              TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_credit_topups_org
    ON credit_topups (organization_id, created_at DESC);

COMMENT ON COLUMN credit_topups.credits IS
    'Credits quoted at checkout and owed on payment. Stored, not recomputed: '
    'the founder receives what the screen said, not what the rate became.';
COMMENT ON COLUMN credit_topups.credited_at IS
    'Set once, by apply_credit_topup. NULL means the balance has not moved.';

-- Org isolation, matching every other org-scoped table in this schema.
ALTER TABLE credit_topups ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS credit_topups_org_isolation ON credit_topups;
CREATE POLICY credit_topups_org_isolation ON credit_topups
    FOR ALL
    USING (
        organization_id IN (
            SELECT organization_id FROM organization_members
             WHERE user_id = auth.uid()
        )
    );

-- ---------------------------------------------------------------------------
-- Part B: applying it
-- ---------------------------------------------------------------------------
--
-- Deliberately **not** `grant_credits`. That RPC sets `credits_granted = amount`
-- and `credit_cycle_start = NOW()` — it starts a new billing cycle *at* the
-- amount. Putting a $10 top-up through it would take a founder org from 19,800
-- granted to 1,500 and reset their month. A top-up adds to the balance and
-- touches nothing else, which is the same reasoning migration 028 wrote down
-- for refunds.
--
-- **Idempotency is the WHERE clause**, as in 028. `credited_at IS NULL` is a
-- compare-and-set: the first caller wins the row and every later one — a Stripe
-- retry, a duplicate delivery, two API processes handling the same event —
-- updates zero rows and credits nothing. Postgres serialises them on the row
-- lock, so "both saw NULL" is not a reachable state.
--
-- Returns (credited, balance). `credited = 0` with a NULL balance means the
-- session was already applied. That is a normal outcome and what a retry is
-- supposed to do; the caller logs it and returns 200 so Stripe stops asking.
CREATE OR REPLACE FUNCTION apply_credit_topup(session_id TEXT, payment_intent TEXT)
RETURNS TABLE (credited BIGINT, balance BIGINT) AS $$
DECLARE
    v_org     UUID;
    v_credits BIGINT;
    v_balance BIGINT;
BEGIN
    UPDATE credit_topups
       SET status = 'paid',
           credited_at = NOW(),
           stripe_payment_intent = COALESCE(payment_intent, stripe_payment_intent)
     WHERE stripe_session_id = session_id
       AND credited_at IS NULL
    RETURNING organization_id, credits INTO v_org, v_credits;

    IF v_org IS NULL THEN
        -- Either already applied, or a session we never opened. The caller
        -- distinguishes the two by looking the row up; both are 200s to Stripe.
        RETURN QUERY SELECT 0::BIGINT, NULL::BIGINT;
        RETURN;
    END IF;

    UPDATE organizations
       SET credits_balance = COALESCE(credits_balance, 0) + v_credits
     WHERE id = v_org
    RETURNING credits_balance INTO v_balance;

    RETURN QUERY SELECT v_credits, v_balance;
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION apply_credit_topup(TEXT, TEXT) IS
    'Credit a paid top-up exactly once. Claims the row on credited_at IS NULL '
    'and adds to credits_balance in the same transaction. Returns (0, NULL) '
    'when already applied - a normal retry outcome, not an error.';
