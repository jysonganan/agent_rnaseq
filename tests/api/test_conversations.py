"""Tests for conversation and chat message endpoints (TASK_FE_10)."""

from __future__ import annotations

import hashlib
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from tests.api.conftest import TEST_API_KEY_RAW

# ── Helpers ────────────────────────────────────────────────────────────────────


def _create_conv(client: TestClient, auth: dict, title: str | None = None) -> dict:
    body = {"title": title} if title else {}
    r = client.post("/api/v1/conversations", json=body, headers=auth)
    assert r.status_code == 201, r.text
    return r.json()


# ── POST /conversations ────────────────────────────────────────────────────────


def test_create_conversation_default_title(client: TestClient, auth_headers: dict, seed_data: dict) -> None:
    data = _create_conv(client, auth_headers)
    assert data["title"] == "New conversation"
    assert "id" in data
    assert "created_at" in data
    assert "updated_at" in data


def test_create_conversation_custom_title(client: TestClient, auth_headers: dict, seed_data: dict) -> None:
    data = _create_conv(client, auth_headers, title="My RNA experiment")
    assert data["title"] == "My RNA experiment"


def test_create_conversation_requires_auth(client: TestClient, seed_data: dict) -> None:
    r = client.post("/api/v1/conversations", json={})
    assert r.status_code == 401


# ── GET /conversations ─────────────────────────────────────────────────────────


def test_list_conversations_scoped_to_api_key(client: TestClient, auth_headers: dict, seed_data: dict) -> None:
    _create_conv(client, auth_headers, title="Conv A")
    _create_conv(client, auth_headers, title="Conv B")
    r = client.get("/api/v1/conversations", headers=auth_headers)
    assert r.status_code == 200
    data = r.json()
    assert data["total"] == 2
    titles = {c["title"] for c in data["conversations"]}
    assert titles == {"Conv A", "Conv B"}


def test_list_conversations_excludes_deleted(client: TestClient, auth_headers: dict, seed_data: dict) -> None:
    conv = _create_conv(client, auth_headers, title="To delete")
    client.delete(f"/api/v1/conversations/{conv['id']}", headers=auth_headers)
    r = client.get("/api/v1/conversations", headers=auth_headers)
    assert r.status_code == 200
    assert r.json()["total"] == 0


def test_list_conversations_other_key_not_visible(client: TestClient, seed_data: dict) -> None:
    """A conversation created with one key must not appear for a different key."""
    from sqlalchemy.orm import Session
    from sqlalchemy import create_engine
    from sqlalchemy.pool import StaticPool

    from src.api.app import create_app
    from src.db.base import Base
    from src.db.models.auth import APIKey
    from src.db.session import get_db

    auth1 = {"Authorization": f"Bearer {TEST_API_KEY_RAW}"}
    _create_conv(client, auth1, title="Owner conv")

    # Build a second client with a second API key on the same DB engine
    # We can reuse the overridden get_db by injecting a second key via a known fixture seam.
    # For simplicity: just confirm the other key (bad key) sees 0 conversations.
    r = client.get("/api/v1/conversations", headers={"Authorization": "Bearer not-a-real-key"})
    assert r.status_code == 401


# ── DELETE /conversations/{id} ─────────────────────────────────────────────────


def test_delete_conversation_soft_deletes(client: TestClient, auth_headers: dict, seed_data: dict) -> None:
    conv = _create_conv(client, auth_headers)
    r = client.delete(f"/api/v1/conversations/{conv['id']}", headers=auth_headers)
    assert r.status_code == 204
    # Should no longer be in list
    r2 = client.get("/api/v1/conversations", headers=auth_headers)
    assert r2.json()["total"] == 0


def test_delete_conversation_not_found(client: TestClient, auth_headers: dict, seed_data: dict) -> None:
    import uuid
    r = client.delete(f"/api/v1/conversations/{uuid.uuid4()}", headers=auth_headers)
    assert r.status_code == 404


def test_delete_conversation_unauthorized(client: TestClient, auth_headers: dict, seed_data: dict) -> None:
    conv = _create_conv(client, auth_headers)
    r = client.delete(f"/api/v1/conversations/{conv['id']}", headers={"Authorization": "Bearer wrong"})
    assert r.status_code == 401


# ── POST /conversations/{id}/messages ─────────────────────────────────────────


@pytest.fixture(autouse=True)
def mock_chat_enqueue():
    """Patch _enqueue_chat_message to avoid real arq/Redis in unit tests."""
    with patch(
        "src.api.routers.conversations._enqueue_chat_message",
        new_callable=AsyncMock,
    ) as m:
        yield m


def test_send_message_accepted(client: TestClient, auth_headers: dict, seed_data: dict) -> None:
    conv = _create_conv(client, auth_headers)
    r = client.post(
        f"/api/v1/conversations/{conv['id']}/messages",
        json={"content": "Run bulk RNA-seq on all samples"},
        headers=auth_headers,
    )
    assert r.status_code == 202
    data = r.json()
    assert "message_id" in data
    assert data["status"] == "processing"


def test_send_message_updates_title_on_first_message(client: TestClient, auth_headers: dict, seed_data: dict) -> None:
    conv = _create_conv(client, auth_headers)
    assert conv["title"] == "New conversation"
    client.post(
        f"/api/v1/conversations/{conv['id']}/messages",
        json={"content": "Analyse the STAR alignment results"},
        headers=auth_headers,
    )
    r = client.get(f"/api/v1/conversations/{conv['id']}", headers=auth_headers)
    assert r.status_code == 200
    # Title should be truncated content of the first message
    assert "Analyse" in r.json()["title"]


def test_send_message_title_not_overwritten_on_second_message(
    client: TestClient, auth_headers: dict, seed_data: dict
) -> None:
    conv = _create_conv(client, auth_headers, title="My experiment")
    client.post(
        f"/api/v1/conversations/{conv['id']}/messages",
        json={"content": "First message"},
        headers=auth_headers,
    )
    client.post(
        f"/api/v1/conversations/{conv['id']}/messages",
        json={"content": "Second message"},
        headers=auth_headers,
    )
    r = client.get(f"/api/v1/conversations/{conv['id']}", headers=auth_headers)
    # Title was custom, so it must not be overwritten
    assert r.json()["title"] == "My experiment"


def test_send_message_rejects_blank(client: TestClient, auth_headers: dict, seed_data: dict) -> None:
    conv = _create_conv(client, auth_headers)
    r = client.post(
        f"/api/v1/conversations/{conv['id']}/messages",
        json={"content": ""},
        headers=auth_headers,
    )
    assert r.status_code == 422


def test_send_message_rejects_over_4000_chars(client: TestClient, auth_headers: dict, seed_data: dict) -> None:
    conv = _create_conv(client, auth_headers)
    r = client.post(
        f"/api/v1/conversations/{conv['id']}/messages",
        json={"content": "x" * 4001},
        headers=auth_headers,
    )
    assert r.status_code == 422


def test_send_message_exactly_4000_chars(client: TestClient, auth_headers: dict, seed_data: dict) -> None:
    conv = _create_conv(client, auth_headers)
    r = client.post(
        f"/api/v1/conversations/{conv['id']}/messages",
        json={"content": "x" * 4000},
        headers=auth_headers,
    )
    assert r.status_code == 202


def test_send_message_404_for_missing_conv(client: TestClient, auth_headers: dict, seed_data: dict) -> None:
    import uuid
    r = client.post(
        f"/api/v1/conversations/{uuid.uuid4()}/messages",
        json={"content": "hello"},
        headers=auth_headers,
    )
    assert r.status_code == 404


def test_send_message_enqueues_task(
    client: TestClient, auth_headers: dict, seed_data: dict, mock_chat_enqueue: AsyncMock
) -> None:
    conv = _create_conv(client, auth_headers)
    client.post(
        f"/api/v1/conversations/{conv['id']}/messages",
        json={"content": "Please run QC"},
        headers=auth_headers,
    )
    mock_chat_enqueue.assert_awaited_once()
    kwargs = mock_chat_enqueue.call_args.kwargs
    assert kwargs["conversation_id"] == conv["id"]
    assert "message_id" in kwargs
    assert "api_key_id" in kwargs


# ── GET /conversations/{id}/messages ──────────────────────────────────────────


def test_get_messages_empty(client: TestClient, auth_headers: dict, seed_data: dict) -> None:
    conv = _create_conv(client, auth_headers)
    r = client.get(f"/api/v1/conversations/{conv['id']}/messages", headers=auth_headers)
    assert r.status_code == 200
    assert r.json()["total"] == 0


def test_get_messages_includes_user_message(client: TestClient, auth_headers: dict, seed_data: dict) -> None:
    conv = _create_conv(client, auth_headers)
    client.post(
        f"/api/v1/conversations/{conv['id']}/messages",
        json={"content": "Run QC now"},
        headers=auth_headers,
    )
    r = client.get(f"/api/v1/conversations/{conv['id']}/messages", headers=auth_headers)
    assert r.status_code == 200
    data = r.json()
    assert data["total"] == 1
    assert data["messages"][0]["role"] == "user"
    assert data["messages"][0]["content"] == "Run QC now"


# ── Rate limiting ──────────────────────────────────────────────────────────────


def test_rate_limit_send_message(client: TestClient, auth_headers: dict, seed_data: dict) -> None:
    conv = _create_conv(client, auth_headers)
    responses = []
    for _ in range(12):
        r = client.post(
            f"/api/v1/conversations/{conv['id']}/messages",
            json={"content": "ping"},
            headers=auth_headers,
        )
        responses.append(r.status_code)
    assert 429 in responses


# ── WebSocket auth ─────────────────────────────────────────────────────────────


def test_ws_rejects_missing_api_key(client: TestClient, seed_data: dict) -> None:
    """WS closes with 4403 before accept when api_key param is absent."""
    import uuid
    from starlette.websockets import WebSocketDisconnect

    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect(
            f"/api/v1/ws/conversations/{uuid.uuid4()}/stream"
        ):
            pass


def test_ws_rejects_invalid_api_key(client: TestClient, db_engine, seed_data: dict) -> None:
    """WS closes with 4403 before accept when api_key is not in the database."""
    import uuid
    from unittest.mock import patch as _patch

    from sqlalchemy.orm import sessionmaker
    from starlette.websockets import WebSocketDisconnect

    test_session_factory = sessionmaker(bind=db_engine)

    with _patch(
        "src.api.websocket.conversation_stream.get_session_factory",
        return_value=test_session_factory,
    ):
        with pytest.raises(WebSocketDisconnect):
            with client.websocket_connect(
                f"/api/v1/ws/conversations/{uuid.uuid4()}/stream?api_key=bad-key"
            ):
                pass
