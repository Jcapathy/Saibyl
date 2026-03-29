-- Migration 010: Media ingestion — project_assets table + project columns

CREATE TABLE IF NOT EXISTS project_assets (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    project_id      UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    title           TEXT NOT NULL,
    media_type      TEXT NOT NULL,
    file_extension  TEXT,
    storage_path    TEXT NOT NULL,
    processed_text_path TEXT,
    source_url      TEXT,
    file_size_bytes BIGINT NOT NULL DEFAULT 0,
    status          TEXT NOT NULL DEFAULT 'uploaded',
    error_message   TEXT,
    metadata        JSONB DEFAULT '{}',
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_project_assets_project ON project_assets(project_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_project_assets_org ON project_assets(organization_id);

ALTER TABLE project_assets ENABLE ROW LEVEL SECURITY;
CREATE POLICY "project_assets_org_isolation" ON project_assets
    USING (organization_id = ANY(public.user_organization_ids()));

-- Project persistence columns
ALTER TABLE projects ADD COLUMN IF NOT EXISTS last_opened_at TIMESTAMPTZ;
ALTER TABLE projects ADD COLUMN IF NOT EXISTS is_archived BOOLEAN DEFAULT FALSE;
ALTER TABLE projects ADD COLUMN IF NOT EXISTS thumbnail_url TEXT;
ALTER TABLE projects ADD COLUMN IF NOT EXISTS asset_count INT DEFAULT 0;
ALTER TABLE projects ADD COLUMN IF NOT EXISTS simulation_count INT DEFAULT 0;
ALTER TABLE projects ADD COLUMN IF NOT EXISTS storage_bytes BIGINT DEFAULT 0;

-- Storage tracking on organizations
ALTER TABLE organizations ADD COLUMN IF NOT EXISTS storage_bytes_used BIGINT DEFAULT 0;
ALTER TABLE organizations ADD COLUMN IF NOT EXISTS storage_pack_ids TEXT[] DEFAULT '{}';

-- Trigger for updated_at on project_assets
CREATE TRIGGER set_updated_at BEFORE UPDATE ON project_assets
    FOR EACH ROW EXECUTE FUNCTION public.update_updated_at();
