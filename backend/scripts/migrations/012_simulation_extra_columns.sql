-- Migration 012: Add extra columns to simulations table

ALTER TABLE simulations ADD COLUMN IF NOT EXISTS persona_pack_id TEXT;
ALTER TABLE simulations ADD COLUMN IF NOT EXISTS agent_count INT;
ALTER TABLE simulations ADD COLUMN IF NOT EXISTS description TEXT;
