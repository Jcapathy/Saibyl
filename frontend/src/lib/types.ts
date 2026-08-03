/**
 * Shared domain types.
 *
 * Replaces the former top-level `shared/types.ts`, which was never imported and
 * had drifted from the API. Types here must reflect what the backend actually
 * returns — add fields as endpoints are consumed, not speculatively.
 */

export interface AgentProfile {
  display_name?: string;
  persona_type?: string;
  username?: string;
  bio?: string;
  age?: number;
  profession?: string;
  sentiment_baseline?: number;
  backstory?: string;
}

/** Row from GET /api/simulations/{id}/agents */
export interface SimulationAgent {
  id: string;
  username: string;
  platform?: string;
  variant?: string;
  persona_pack_id?: string;
  entity_name?: string;
  profile?: AgentProfile;
}

/** Response from POST /api/simulations/{id}/interview */
export interface InterviewResponse {
  agent_id: string;
  agent_username: string;
  persona_type: string;
  prompt: string;
  response: string;
  sentiment_score: number;
}
