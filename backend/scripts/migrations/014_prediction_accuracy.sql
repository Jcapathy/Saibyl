CREATE TABLE IF NOT EXISTS prediction_accuracy (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  simulation_id UUID NOT NULL REFERENCES simulations(id) ON DELETE CASCADE,
  organization_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
  created_by UUID NOT NULL REFERENCES auth.users(id),
  predicted_sentiment FLOAT,
  actual_sentiment FLOAT,
  predicted_engagement TEXT,
  actual_engagement TEXT,
  accuracy_score FLOAT,
  notes TEXT,
  actual_outcomes JSONB DEFAULT '{}',
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

ALTER TABLE prediction_accuracy ENABLE ROW LEVEL SECURITY;

CREATE POLICY "org_members_can_manage_accuracy"
  ON prediction_accuracy FOR ALL
  USING (organization_id IN (
    SELECT organization_id FROM organization_members WHERE user_id = auth.uid()
  ));
