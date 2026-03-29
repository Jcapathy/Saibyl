-- Migration 005: Simulations

CREATE TABLE simulations (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    organization_id UUID NOT NULL REFERENCES organizations(id),
    created_by UUID NOT NULL REFERENCES auth.users(id),
    name TEXT NOT NULL,
    prediction_goal TEXT NOT NULL,
    status TEXT DEFAULT 'draft',
    is_ab_test BOOLEAN DEFAULT FALSE,
    variant_a_config JSONB,
    variant_b_config JSONB,
    max_rounds INT DEFAULT 10,
    platforms TEXT[] DEFAULT '{}',
    timezone TEXT DEFAULT 'America/New_York',
    scheduled_start_at TIMESTAMPTZ,
    winner_variant TEXT,
    completed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE simulation_agents (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    simulation_id UUID NOT NULL REFERENCES simulations(id) ON DELETE CASCADE,
    organization_id UUID NOT NULL REFERENCES organizations(id),
    entity_id TEXT NOT NULL,
    entity_name TEXT NOT NULL,
    persona_pack_id TEXT,
    variant TEXT DEFAULT 'a',
    platform TEXT NOT NULL,
    profile JSONB NOT NULL,
    username TEXT NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE simulation_events (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    simulation_id UUID NOT NULL REFERENCES simulations(id) ON DELETE CASCADE,
    organization_id UUID NOT NULL REFERENCES organizations(id),
    event_type TEXT NOT NULL,
    agent_id UUID REFERENCES simulation_agents(id),
    platform TEXT,
    variant TEXT DEFAULT 'a',
    round_number INT,
    content TEXT,
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_simulation_events_sim_id ON simulation_events(simulation_id, created_at DESC);

-- RLS
ALTER TABLE simulations ENABLE ROW LEVEL SECURITY;
ALTER TABLE simulation_agents ENABLE ROW LEVEL SECURITY;
ALTER TABLE simulation_events ENABLE ROW LEVEL SECURITY;

CREATE POLICY "simulations_org_isolation" ON simulations
    USING (organization_id = ANY(public.user_organization_ids()));

CREATE POLICY "simulation_agents_org_isolation" ON simulation_agents
    USING (organization_id = ANY(public.user_organization_ids()));

CREATE POLICY "simulation_events_org_isolation" ON simulation_events
    USING (organization_id = ANY(public.user_organization_ids()));
