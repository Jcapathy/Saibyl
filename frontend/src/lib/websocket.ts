type EventHandler = (event: Record<string, unknown>) => void;

export class SimulationSocket {
  private ws: WebSocket | null = null;
  private handlers: Map<string, EventHandler[]> = new Map();
  private pingInterval: ReturnType<typeof setInterval> | null = null;

  connect(simulationId: string) {
    const wsUrl = import.meta.env.VITE_WS_URL || `ws://${window.location.host}`;
    this.ws = new WebSocket(`${wsUrl}/ws/simulations/${simulationId}`);

    this.ws.onmessage = (e) => {
      try {
        const event = JSON.parse(e.data);
        this.dispatch(event.event_type || 'message', event);
      } catch {
        // ignore non-JSON messages (e.g. "pong")
      }
    };

    this.ws.onclose = () => {
      this.dispatch('disconnect', {});
      this.cleanup();
    };

    this.ws.onerror = () => {
      this.dispatch('error', {});
    };

    this.pingInterval = setInterval(() => {
      if (this.ws?.readyState === WebSocket.OPEN) {
        this.ws.send('ping');
      }
    }, 30000);
  }

  on(eventType: string, handler: EventHandler) {
    const list = this.handlers.get(eventType) || [];
    list.push(handler);
    this.handlers.set(eventType, list);
  }

  off(eventType: string, handler: EventHandler) {
    const list = this.handlers.get(eventType) || [];
    this.handlers.set(eventType, list.filter((h) => h !== handler));
  }

  disconnect() {
    this.ws?.close();
    this.cleanup();
  }

  private dispatch(eventType: string, event: Record<string, unknown>) {
    for (const handler of this.handlers.get(eventType) || []) {
      handler(event);
    }
    // Also dispatch to wildcard listeners
    for (const handler of this.handlers.get('*') || []) {
      handler(event);
    }
  }

  private cleanup() {
    if (this.pingInterval) {
      clearInterval(this.pingInterval);
      this.pingInterval = null;
    }
  }
}
