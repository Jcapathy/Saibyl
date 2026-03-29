export interface TimestampedEntity {
  id: string;
  created_at: string;
  updated_at: string;
}

export interface Organization extends TimestampedEntity {
  name: string;
  slug: string;
}

export interface UserProfile extends TimestampedEntity {
  user_id: string;
  org_id: string;
  display_name: string;
  role: 'owner' | 'admin' | 'member' | 'viewer';
}

export interface Project extends TimestampedEntity {
  org_id: string;
  name: string;
  description: string;
  status: 'active' | 'archived';
}

export interface Simulation extends TimestampedEntity {
  project_id: string;
  name: string;
  status: 'draft' | 'running' | 'completed' | 'failed';
  config: Record<string, unknown>;
}

export interface SimulationEvent {
  id: string;
  simulation_id: string;
  agent_id: string;
  platform: string;
  event_type: string;
  content: string;
  metadata: Record<string, unknown>;
  created_at: string;
}

export interface Report extends TimestampedEntity {
  simulation_id: string;
  title: string;
  status: 'generating' | 'completed' | 'failed';
  format: 'pdf' | 'pptx' | 'json';
}
