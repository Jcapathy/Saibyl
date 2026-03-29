-- Migration 009: Billing columns for agent pricing

ALTER TABLE organizations ADD COLUMN IF NOT EXISTS agent_credits_balance BIGINT DEFAULT 0;
ALTER TABLE organizations ADD COLUMN IF NOT EXISTS agent_pack_ids TEXT[] DEFAULT '{}';
ALTER TABLE organizations ADD COLUMN IF NOT EXISTS persona_pack_ids TEXT[] DEFAULT '{}';

ALTER TABLE simulations ADD COLUMN IF NOT EXISTS agent_count INT DEFAULT 0;
ALTER TABLE simulations ADD COLUMN IF NOT EXISTS agent_rounds_consumed BIGINT DEFAULT 0;
ALTER TABLE simulations ADD COLUMN IF NOT EXISTS retail_cost_usd NUMERIC DEFAULT 0;
