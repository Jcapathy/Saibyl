# PUBLIC INTERFACE
# ─────────────────────────────────────────────────────────
# manager.connect(websocket, simulation_id, auth)
# manager.disconnect(websocket, simulation_id)
# manager.broadcast(simulation_id, event)
# ─────────────────────────────────────────────────────────
from __future__ import annotations

import structlog
from fastapi import WebSocket

from app.core.database import get_supabase_admin

logger = structlog.get_logger()

CATCHUP_EVENT_COUNT = 50


class ConnectionManager:
    """Manages WebSocket connections per simulation."""

    def __init__(self):
        self.connections: dict[str, list[WebSocket]] = {}

    async def connect(self, ws: WebSocket, sim_id: str, org_id: str) -> bool:
        """Accept connection, verify access, send catch-up events."""
        await ws.accept()

        # Verify org has access to this simulation
        admin = get_supabase_admin()
        sim = admin.table("simulations").select("organization_id").eq(
            "id", sim_id
        ).execute().data

        if not sim or sim[0]["organization_id"] != org_id:
            await ws.close(code=4003, reason="Access denied")
            return False

        self.connections.setdefault(sim_id, []).append(ws)

        # Send catch-up events
        await self._send_catchup(ws, sim_id)

        logger.info("ws_connected", simulation_id=sim_id, clients=len(self.connections[sim_id]))
        return True

    def disconnect(self, ws: WebSocket, sim_id: str) -> None:
        """Remove a WebSocket connection."""
        if sim_id in self.connections:
            try:
                self.connections[sim_id].remove(ws)
            except ValueError:
                pass
            if not self.connections[sim_id]:
                del self.connections[sim_id]
        logger.info("ws_disconnected", simulation_id=sim_id)

    async def broadcast(self, sim_id: str, event: dict) -> None:
        """Send event to all clients subscribed to this simulation."""
        dead: list[WebSocket] = []
        for ws in self.connections.get(sim_id, []):
            try:
                await ws.send_json(event)
            except Exception:
                dead.append(ws)
        for ws in dead:
            try:
                self.connections[sim_id].remove(ws)
            except (ValueError, KeyError):
                pass

    async def _send_catchup(self, ws: WebSocket, sim_id: str) -> None:
        """Send the last N events for clients connecting mid-simulation."""
        admin = get_supabase_admin()
        events = admin.table("simulation_events").select("*").eq(
            "simulation_id", sim_id
        ).order("created_at", desc=True).limit(CATCHUP_EVENT_COUNT).execute().data

        # Send in chronological order
        for event in reversed(events):
            try:
                await ws.send_json({
                    "event_type": event["event_type"],
                    "simulation_id": sim_id,
                    "timestamp": event.get("created_at", ""),
                    "variant": event.get("variant", "a"),
                    "round_number": event.get("round_number"),
                    "platform": event.get("platform"),
                    "content": event.get("content"),
                    "metadata": event.get("metadata", {}),
                    "catchup": True,
                })
            except Exception:
                break

    @property
    def active_connections(self) -> int:
        return sum(len(v) for v in self.connections.values())


# Singleton instance
manager = ConnectionManager()
