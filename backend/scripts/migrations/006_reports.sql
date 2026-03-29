-- Migration 006: Reports

CREATE TABLE reports (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    simulation_id UUID NOT NULL REFERENCES simulations(id) ON DELETE CASCADE,
    organization_id UUID NOT NULL REFERENCES organizations(id),
    title TEXT,
    status TEXT DEFAULT 'pending',
    variant TEXT DEFAULT 'a',
    react_config JSONB DEFAULT '{}',
    section_count INT DEFAULT 0,
    markdown_content TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    completed_at TIMESTAMPTZ
);

CREATE TABLE report_sections (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    report_id UUID NOT NULL REFERENCES reports(id) ON DELETE CASCADE,
    organization_id UUID NOT NULL REFERENCES organizations(id),
    section_index INT NOT NULL,
    title TEXT NOT NULL,
    content TEXT,
    tool_calls JSONB DEFAULT '[]',
    status TEXT DEFAULT 'pending',
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- RLS
ALTER TABLE reports ENABLE ROW LEVEL SECURITY;
ALTER TABLE report_sections ENABLE ROW LEVEL SECURITY;

CREATE POLICY "reports_org_isolation" ON reports
    USING (organization_id = ANY(public.user_organization_ids()));

CREATE POLICY "report_sections_org_isolation" ON report_sections
    USING (organization_id = ANY(public.user_organization_ids()));
