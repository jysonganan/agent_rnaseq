"""WebSocket endpoint for run log streaming via Redis pub/sub."""

from __future__ import annotations

import contextlib
import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Query, WebSocket

from src.api.auth import active_api_key
from src.db.session import get_session_factory

ws_router = APIRouter()

# Close codes (sent before accept, so nothing is streamed to an unauthorized client).
WS_CLOSE_UNAUTHORIZED = 4403  # missing, unknown, expired or revoked API key
WS_CLOSE_NOT_FOUND = 4404  # malformed run id, unknown run, or a run of another principal


def _authorize(api_key: str, run_id: str) -> int | None:
    """Return a close code if the caller may not stream *run_id*'s logs, else ``None``.

    Unknown runs and runs of another principal get the same code, so the endpoint does not
    reveal which run ids exist.
    """
    from src.api.ownership import runs_query
    from src.db.models.run import AnalysisRun

    db = get_session_factory()()
    try:
        key = active_api_key(db, api_key)
        if key is None:
            return WS_CLOSE_UNAUTHORIZED
        try:
            run_uuid = uuid.UUID(run_id)
        except ValueError:
            return WS_CLOSE_NOT_FOUND
        owned = runs_query(db, key).filter(AnalysisRun.id == run_uuid).first()
        return None if owned is not None else WS_CLOSE_NOT_FOUND
    finally:
        db.close()


@ws_router.websocket("/ws/runs/{run_id}/logs")
async def ws_logs(websocket: WebSocket, run_id: str, api_key: str = Query(default="")) -> None:
    # Validate the API key and run ownership before accepting or subscribing to Redis.
    close_code = _authorize(api_key, run_id)
    if close_code is not None:
        await websocket.close(code=close_code)
        return

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

        async with aioredis.from_url(get_settings().redis_url) as r, r.pubsub() as pubsub:
            await pubsub.subscribe(f"logs:{run_id}")
            async for msg in pubsub.listen():
                if msg["type"] == "message":
                    await websocket.send_text(msg["data"].decode())
    except Exception:
        pass
    finally:
        with contextlib.suppress(Exception):
            await websocket.close()
