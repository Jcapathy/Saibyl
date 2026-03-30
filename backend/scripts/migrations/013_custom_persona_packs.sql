-- Custom persona packs created by users via LLM generation
CREATE TABLE IF NOT EXISTS custom_persona_packs (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  organization_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
  created_by UUID NOT NULL REFERENCES auth.users(id),
  pack_id TEXT NOT NULL,
  name TEXT NOT NULL,
  description TEXT NOT NULL,
  category TEXT NOT NULL DEFAULT 'custom',
  pack_data JSONB NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE(organization_id, pack_id)
);

ALTER TABLE custom_persona_packs ENABLE ROW LEVEL SECURITY;

CREATE POLICY "org_members_can_read_custom_packs"
  ON custom_persona_packs FOR SELECT
  USING (organization_id IN (
    SELECT organization_id FROM organization_members WHERE user_id = auth.uid()
  ));

CREATE POLICY "org_members_can_insert_custom_packs"
  ON custom_persona_packs FOR INSERT
  WITH CHECK (organization_id IN (
    SELECT organization_id FROM organization_members WHERE user_id = auth.uid()
  ));

CREATE POLICY "org_members_can_delete_custom_packs"
  ON custom_persona_packs FOR DELETE
  USING (organization_id IN (
    SELECT organization_id FROM organization_members WHERE user_id = auth.uid()
  ));
