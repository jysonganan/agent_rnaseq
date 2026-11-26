"""WebSocket endpoint for conversation token streaming via Redis pub/sub."""

from __future__ import annotations

import contextlib
import uuid

from fastapi import APIRouter, WebSocket

from src.api.auth import active_api_key
from src.api.ownership import conversations_query
from src.api.ws_auth import (
    WS_CLOSE_NOT_FOUND,
    WS_CLOSE_UNAUTHORIZED,
    key_in_url,
    receive_api_key,
)
from src.db.session import get_session_factory

ws_conv_router = APIRouter()


def _authorize(api_key: str, conversation_id: str) -> int | None:
    """Return a close code if the caller may not stream this conversation, else ``None``."""
    from src.db.models.conversation import Conversation

    db = get_session_factory()()
    try:
        key_obj = active_api_key(db, api_key)
        if key_obj is None:
            return WS_CLOSE_UNAUTHORIZED
        try:
            conv_uuid = uuid.UUID(conversation_id)
        except ValueError:
            return WS_CLOSE_NOT_FOUND
        conv = (
            conversations_query(db, key_obj)
            .filter(Conversation.id == conv_uuid, Conversation.deleted_at.is_(None))
            .first()
        )
        return None if conv is not None else WS_CLOSE_NOT_FOUND
    finally:
        db.close()


@ws_conv_router.websocket("/ws/conversations/{conversation_id}/stream")
async def ws_conversation_stream(websocket: WebSocket, conversation_id: str) -> None:
    # A key in the URL is refused outright; the key arrives in the first frame instead.
    if key_in_url(websocket):
        await websocket.close(code=WS_CLOSE_UNAUTHORIZED)
        return

    await websocket.accept()
    # Validate the API key and conversation ownership before sending anything or subscribing.
    api_key = await receive_api_key(websocket)
    close_code = WS_CLOSE_UNAUTHORIZED if api_key is None else _authorize(api_key, conversation_id)
    if close_code is not None:
        with contextlib.suppress(Exception):
            await websocket.close(code=close_code)
        return
    await websocket.send_json({"type": "auth_ok", "payload": {}})

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
