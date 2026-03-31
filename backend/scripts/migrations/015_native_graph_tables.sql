-- Migration 015: Replace Zep with native graph storage
-- Adds graph_nodes and graph_edges tables, drops zep_graph_id column

CREATE TABLE IF NOT EXISTS graph_nodes (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    knowledge_graph_id UUID NOT NULL REFERENCES knowledge_graphs(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    labels JSONB NOT NULL DEFAULT '[]',
    summary TEXT DEFAULT '',
    attributes JSONB NOT NULL DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS graph_edges (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    knowledge_graph_id UUID NOT NULL REFERENCES knowledge_graphs(id) ON DELETE CASCADE,
    source_node_id UUID NOT NULL REFERENCES graph_nodes(id) ON DELETE CASCADE,
    target_node_id UUID NOT NULL REFERENCES graph_nodes(id) ON DELETE CASCADE,
    relationship_type TEXT NOT NULL DEFAULT 'RELATED_TO',
    facts JSONB NOT NULL DEFAULT '[]',
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Indexes for query performance
CREATE INDEX idx_graph_nodes_kg ON graph_nodes(knowledge_graph_id);
CREATE INDEX idx_graph_nodes_name ON graph_nodes USING gin(name gin_trgm_ops);
CREATE INDEX idx_graph_edges_kg ON graph_edges(knowledge_graph_id);
CREATE INDEX idx_graph_edges_source ON graph_edges(source_node_id);
CREATE INDEX idx_graph_edges_target ON graph_edges(target_node_id);

-- Drop Zep reference
ALTER TABLE knowledge_graphs DROP COLUMN IF EXISTS zep_graph_id;

-- RLS
ALTER TABLE graph_nodes ENABLE ROW LEVEL SECURITY;
ALTER TABLE graph_edges ENABLE ROW LEVEL SECURITY;

CREATE POLICY "graph_nodes_via_kg" ON graph_nodes
    USING (knowledge_graph_id IN (
        SELECT id FROM knowledge_graphs
        WHERE organization_id = ANY(public.user_organization_ids())
    ));

CREATE POLICY "graph_edges_via_kg" ON graph_edges
    USING (knowledge_graph_id IN (
        SELECT id FROM knowledge_graphs
        WHERE organization_id = ANY(public.user_organization_ids())
    ));
