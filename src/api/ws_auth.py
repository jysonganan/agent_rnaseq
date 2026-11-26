"""First-message authentication for WebSockets (api_contracts.md "WebSocket authentication").

Browsers can't set an ``Authorization`` header on a WebSocket, and a key in the URL leaks into
proxy and access logs. So the client connects with no credentials and sends
``{"type": "auth", "api_key": "<key>"}`` as its first frame. Nothing is sent to the client and
no Redis channel is subscribed until the key and resource ownership have been checked.
"""

from __future__ import annotations

import asyncio
import json

from fastapi import WebSocket

WS_CLOSE_UNAUTHORIZED = 4403  # no/malformed auth frame, bad key, or key put in the URL
WS_CLOSE_NOT_FOUND = 4404  # malformed id, unknown resource, or owned by another principal

WS_AUTH_TIMEOUT_S = 10.0
_MAX_AUTH_FRAME_CHARS = 1024


def key_in_url(websocket: WebSocket) -> bool:
    """True if the client put an API key in the URL (refused: it is already in someone's logs)."""
    return "api_key" in websocket.query_params


async def receive_api_key(websocket: WebSocket) -> str | None:
    """Read the auth frame from an accepted socket; return the raw key, or ``None`` if invalid.

    ``None`` covers a timeout, a disconnect, a binary or oversized frame, non-JSON, a wrong
    ``type`` and a missing or non-string ``api_key``.
    """
    try:
        raw = await asyncio.wait_for(websocket.receive_text(), timeout=WS_AUTH_TIMEOUT_S)
    except Exception:  # timeout, disconnect, or a binary frame
        return None
    if len(raw) > _MAX_AUTH_FRAME_CHARS:
        return None
    try:
        frame = json.loads(raw)
    except ValueError:
        return None
    if not isinstance(frame, dict) or frame.get("type") != "auth":
        return None
    key = frame.get("api_key")
    return key if isinstance(key, str) and key else None
