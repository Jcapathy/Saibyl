-- Migration 016: Atomic billing RPC functions
-- Prevents race conditions in concurrent storage/credit updates

CREATE OR REPLACE FUNCTION increment_storage(org_uuid UUID, delta BIGINT)
RETURNS VOID AS $$
    UPDATE organizations
    SET storage_bytes_used = GREATEST(0, COALESCE(storage_bytes_used, 0) + delta)
    WHERE id = org_uuid;
$$ LANGUAGE sql;

CREATE OR REPLACE FUNCTION deduct_agent_credits(org_uuid UUID, amount BIGINT)
RETURNS VOID AS $$
    UPDATE organizations
    SET agent_credits_balance = GREATEST(0, COALESCE(agent_credits_balance, 0) - amount)
    WHERE id = org_uuid;
$$ LANGUAGE sql;
