"""WebSocket endpoint for run log streaming via Redis pub/sub."""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, WebSocket

ws_router = APIRouter()


@ws_router.websocket("/ws/runs/{run_id}/logs")
async def ws_logs(websocket: WebSocket, run_id: str) -> None:
    await websocket.accept()
    await websocket.send_json(
        {
            "ts": datetime.now(UTC).isoformat(),
            "level": "info",
            "stage": None,
            "agent": None,
            "message": f"Connected to log stream for run {run_id}",
        }
    )
    try:
        import redis.asyncio as aioredis

        from src.config import get_settings

        async with aioredis.from_url(get_settings().redis_url) as r:
            async with r.pubsub() as pubsub:
                await pubsub.subscribe(f"logs:{run_id}")
                async for msg in pubsub.listen():
                    if msg["type"] == "message":
                        await websocket.send_text(msg["data"].decode())
    except Exception:
        pass
    finally:
        try:
            await websocket.close()
        except Exception:
            pass
