export interface Organization {
  id: string;
  name: string;
  slug: string;
  plan: string;
}

export interface Project {
  id: string;
  organization_id: string;
  name: string;
  description: string;
  status: string;
  created_at: string;
}

export interface Simulation {
  id: string;
  project_id: string;
  name: string;
  prediction_goal: string;
  status: string;
  is_ab_test: boolean;
  platforms: string[];
  max_rounds: number;
  created_at: string;
  completed_at: string | null;
}

export interface Report {
  id: string;
  simulation_id: string;
  title: string;
  status: string;
  variant: string;
  markdown_content: string | null;
  created_at: string;
  completed_at: string | null;
}

export interface ReportSection {
  id: string;
  report_id: string;
  section_index: number;
  title: string;
  content: string | null;
  status: string;
}

export interface PersonaPack {
  id: string;
  name: string;
  category: string;
  description: string;
  archetype_count: number;
  archetype_labels: string[];
}

export interface PlatformInfo {
  platform_id: string;
  platform_name: string;
  supports_reactions: boolean;
  supports_dms: boolean;
  max_post_length: number;
}

export interface BillingStatus {
  plan: string;
  status: string;
  simulations_used: number;
  simulations_limit: number;
  team_members: number;
  team_members_limit: number;
}

export interface ApiKey {
  id: string;
  name: string;
  key_prefix: string;
  scopes: string[];
  last_used_at: string | null;
  created_at: string;
  revoked_at: string | null;
}
