import { create } from 'zustand';

/**
 * One event as it arrives over the simulation websocket.
 *
 * These are the keys the backend actually sends (`ws_manager._send_catchup`).
 * There is no sentiment field on this payload under any name: `valence` is
 * scored from event content *after* the run finishes and lives only on the
 * `simulation_events` row, reachable through `GET /simulations/{id}/evidence`.
 * A live sentiment reading is therefore not something this stream can carry,
 * and declaring one here only produced a chart that waited forever.
 */
export interface SimulationStreamEvent {
  event_type: string;
  simulation_id: string;
  timestamp: string;
  variant: string;
  round_number: number | null;
  platform: string | null;
  content: string | null;
  metadata?: Record<string, unknown>;
  [key: string]: unknown;
}

export interface VisualizerSnapshot {
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
