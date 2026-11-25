"""WebSocket endpoint for conversation token streaming via Redis pub/sub."""

from __future__ import annotations

import contextlib
import uuid

from fastapi import APIRouter, Query, WebSocket

from src.api.auth import active_api_key
from src.api.ownership import conversations_query
from src.db.session import get_session_factory

ws_conv_router = APIRouter()


@ws_conv_router.websocket("/ws/conversations/{conversation_id}/stream")
async def ws_conversation_stream(
    websocket: WebSocket,
    conversation_id: str,
    api_key: str = Query(default=""),
) -> None:
    # Validate API key and conversation ownership before accepting.
    if not api_key:
        await websocket.close(code=4403)
        return

    from src.db.models.conversation import Conversation

    db = get_session_factory()()
    try:
        key_obj = active_api_key(db, api_key)
        if key_obj is None:
            await websocket.close(code=4403)
            return

        try:
            conv_uuid = uuid.UUID(conversation_id)
        except ValueError:
            await websocket.close(code=4404)
            return

        conv = (
            conversations_query(db, key_obj)
            .filter(Conversation.id == conv_uuid, Conversation.deleted_at.is_(None))
            .first()
        )
        if conv is None:
            await websocket.close(code=4404)
            return
    finally:
        db.close()

    await websocket.accept()

    try:
        import redis.asyncio as aioredis

        from src.config import get_settings

        channel = f"conv:{conversation_id}"
        async with aioredis.from_url(get_settings().redis_url) as r, r.pubsub() as pubsub:
            await pubsub.subscribe(channel)
            async for msg in pubsub.listen():
                if msg["type"] == "message":
                    await websocket.send_text(msg["data"].decode())
    except Exception:
        pass
    finally:
        with contextlib.suppress(Exception):
            await websocket.close()
