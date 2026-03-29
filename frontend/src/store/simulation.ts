import { create } from 'zustand';

interface SimulationStreamEvent {
  event_type: string;
  simulation_id: string;
  timestamp: string;
  variant: string;
  round_number: number | null;
  agent_username: string | null;
  platform: string | null;
  content: string | null;
  sentiment_score: number | null;
  [key: string]: unknown;
}

interface VisualizerSnapshot {
  simulation_id: string;
  round_number: number;
  total_events: number;
  persona_activity: Record<string, unknown>[];
  platform_summary: Record<string, unknown>[];
  heatmap: Record<string, unknown>[];
  sentiment_timeline: number[];
  viral_posts: Record<string, unknown>[];
  active_agent_count: number;
}

interface SimulationLiveState {
  events: SimulationStreamEvent[];
  snapshot: VisualizerSnapshot | null;
  roundNumber: number;
  totalEvents: number;
  isRunning: boolean;
  addEvent: (event: SimulationStreamEvent) => void;
  updateSnapshot: (snapshot: VisualizerSnapshot) => void;
  setRunning: (running: boolean) => void;
  reset: () => void;
}

export const useSimulationLiveStore = create<SimulationLiveState>((set) => ({
  events: [],
  snapshot: null,
  roundNumber: 0,
  totalEvents: 0,
  isRunning: false,

  addEvent: (event) =>
    set((state) => ({
      events: [...state.events.slice(-500), event], // keep last 500
      totalEvents: state.totalEvents + 1,
      roundNumber: event.round_number ?? state.roundNumber,
    })),

  updateSnapshot: (snapshot) =>
    set({ snapshot, roundNumber: snapshot.round_number, totalEvents: snapshot.total_events }),

  setRunning: (running) => set({ isRunning: running }),

  reset: () => set({ events: [], snapshot: null, roundNumber: 0, totalEvents: 0, isRunning: false }),
}));
