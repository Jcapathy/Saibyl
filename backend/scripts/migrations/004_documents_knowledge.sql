-- Migration 004: Documents & Knowledge

CREATE TABLE documents (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    organization_id UUID NOT NULL REFERENCES organizations(id),
    filename TEXT NOT NULL,
    file_type TEXT NOT NULL,
    storage_path TEXT NOT NULL,
    file_size_bytes INT,
    processing_status TEXT DEFAULT 'pending',
    error_message TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE ontologies (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    organization_id UUID NOT NULL REFERENCES organizations(id),
    entity_types JSONB NOT NULL DEFAULT '[]',
    relationship_types JSONB NOT NULL DEFAULT '[]',
    pydantic_models TEXT,
    refinement_round INT DEFAULT 1,
    human_approved BOOLEAN DEFAULT FALSE,
    approved_by UUID REFERENCES auth.users(id),
    approved_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE knowledge_graphs (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    organization_id UUID NOT NULL REFERENCES organizations(id),
    zep_graph_id TEXT,
    node_count INT DEFAULT 0,
    edge_count INT DEFAULT 0,
    build_status TEXT DEFAULT 'pending',
    built_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- RLS
ALTER TABLE documents ENABLE ROW LEVEL SECURITY;
ALTER TABLE ontologies ENABLE ROW LEVEL SECURITY;
ALTER TABLE knowledge_graphs ENABLE ROW LEVEL SECURITY;

CREATE POLICY "documents_org_isolation" ON documents
    USING (organization_id = ANY(public.user_organization_ids()));

CREATE POLICY "ontologies_org_isolation" ON ontologies
    USING (organization_id = ANY(public.user_organization_ids()));

CREATE POLICY "knowledge_graphs_org_isolation" ON knowledge_graphs
    USING (organization_id = ANY(public.user_organization_ids()));
