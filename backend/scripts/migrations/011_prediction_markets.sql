-- Migration 011: Prediction markets tables

CREATE TABLE IF NOT EXISTS prediction_markets (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id     UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    project_id          UUID REFERENCES projects(id) ON DELETE SET NULL,
    platform            TEXT NOT NULL,
    external_id         TEXT NOT NULL,
    external_url        TEXT NOT NULL,
    title               TEXT NOT NULL,
    description         TEXT,
    resolution_rules    TEXT,
    closes_at           TIMESTAMPTZ,
    market_type         TEXT NOT NULL,
    outcomes            JSONB NOT NULL DEFAULT '[]',
    volume_usd          NUMERIC,
    open_interest_usd   NUMERIC,
    last_fetched_at     TIMESTAMPTZ DEFAULT NOW(),
    status              TEXT DEFAULT 'open',
    resolution_value    TEXT,
    created_at          TIMESTAMPTZ DEFAULT NOW()
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_markets_platform_external
    ON prediction_markets(organization_id, platform, external_id);

CREATE TABLE IF NOT EXISTS market_predictions (
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id         UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    market_id               UUID NOT NULL REFERENCES prediction_markets(id) ON DELETE CASCADE,
    simulation_id           UUID REFERENCES simulations(id) ON DELETE SET NULL,
    report_id               UUID REFERENCES reports(id) ON DELETE SET NULL,
    predicted_outcome       TEXT,
    predicted_probability   NUMERIC,
    confidence_interval     TEXT,
    recommended_position    TEXT,
    edge_vs_market          NUMERIC,
    reasoning_summary       TEXT,
    full_report_json        JSONB,
    market_price_at_prediction NUMERIC,
    created_at              TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_market_predictions_market
    ON market_predictions(market_id, created_at DESC);

CREATE TABLE IF NOT EXISTS market_api_keys (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE UNIQUE,
    platform        TEXT NOT NULL,
    encrypted_key   TEXT NOT NULL,
    key_preview     TEXT NOT NULL,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

-- RLS
ALTER TABLE prediction_markets ENABLE ROW LEVEL SECURITY;
ALTER TABLE market_predictions ENABLE ROW LEVEL SECURITY;
ALTER TABLE market_api_keys ENABLE ROW LEVEL SECURITY;

CREATE POLICY "markets_org_isolation" ON prediction_markets
    USING (organization_id = ANY(public.user_organization_ids()));
CREATE POLICY "predictions_org_isolation" ON market_predictions
    USING (organization_id = ANY(public.user_organization_ids()));
CREATE POLICY "mkt_keys_org_isolation" ON market_api_keys
    USING (organization_id = ANY(public.user_organization_ids()));
