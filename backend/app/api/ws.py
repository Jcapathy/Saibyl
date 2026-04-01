from __future__ import annotations

import asyncio
import json
from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, Query, WebSocket, WebSocketDisconnect
from fastapi.responses import StreamingResponse

from app.core.auth import get_current_org
from app.core.database import get_supabase, get_supabase_admin
from app.services.intelligence.report_agent import get_report_progress
from app.services.streaming.ws_manager import manager

logger = structlog.get_logger()

router = APIRouter()


async def _validate_ws_token(token: str) -> dict | None:
    """Validate a JWT token passed as WebSocket query param."""
    try:
        supabase = get_supabase()
        response = supabase.auth.get_user(token)
        if response.user is None:
            return None

        admin = get_supabase_admin()
        member = admin.table("organization_members").select(
            "organization_id"
        ).eq("user_id", response.user.id).limit(1).execute().data

        if not member:
            return None

        return {
            "user_id": response.user.id,
            "org_id": member[0]["organization_id"],
        }
    except Exception:
        return None


@router.websocket("/ws/simulations/{simulation_id}")
async def simulation_websocket(
    websocket: WebSocket,
    simulation_id: UUID,
    token: str = Query(...),
):
    """WebSocket endpoint for real-time simulation event streaming."""
    auth = await _validate_ws_token(token)
    if not auth:
        await websocket.close(code=4001, reason="Invalid token")
        return

    connected = await manager.connect(websocket, str(simulation_id), auth["org_id"], user_id=auth["user_id"])
    if not connected:
        return

    try:
        while True:
            data = await websocket.receive_text()
            if data == "ping":
                await websocket.send_text("pong")
    except WebSocketDisconnect:
        manager.disconnect(websocket, str(simulation_id))


@router.get("/api/simulations/{simulation_id}/stream")
async def simulation_stream_sse(
    simulation_id: UUID,
    auth: dict = Depends(get_current_org),
):
    """SSE fallback for WebSocket-incompatible environments."""
    import redis.asyncio as aioredis

    from app.core.config import settings

    async def event_generator():
        yield f"data: {json.dumps({'type': 'connected', 'simulation_id': str(simulation_id)})}\n\n"

        r = aioredis.from_url(settings.redis_url, decode_responses=True)
        pubsub = r.pubsub()
        channel = f"simulation:{simulation_id}:events"
        await pubsub.subscribe(channel)

        try:
            async for message in pubsub.listen():
                if message["type"] == "message":
                    yield f"data: {message['data']}\n\n"
        except asyncio.CancelledError:
            pass
        finally:
            await pubsub.unsubscribe(channel)
            await r.aclose()

    return StreamingResponse(event_generator(), media_type="text/event-stream")


@router.get("/api/reports/{report_id}/progress-stream")
async def report_progress_sse(
    report_id: UUID,
    auth: dict = Depends(get_current_org),
):
    """SSE stream for report generation progress."""

    async def generator():
        for _ in range(600):  # max 10 minutes
            progress = get_report_progress(report_id)
            yield f"data: {progress.model_dump_json()}\n\n"
            if progress.status in ("complete", "failed"):
                break
            await asyncio.sleep(1)

    return StreamingResponse(generator(), media_type="text/event-stream")
