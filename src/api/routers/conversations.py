"""Conversation and chat message endpoints."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session

from src.api.auth import require_api_key
from src.api.rate_limit import limiter
from src.db.enums import MessageRole
from src.db.models.auth import APIKey
from src.db.models.conversation import ChatMessage, Conversation
from src.db.session import get_db
from src.schemas.conversation import (
    ChatMessageRead,
    ConversationCreate,
    ConversationDetailRead,
    ConversationRead,
    ConversationsListRead,
    MessagesListRead,
    SendMessageRequest,
    SendMessageResponse,
)

router = APIRouter(prefix="/conversations", tags=["conversations"])


async def _enqueue_chat_message(
    conversation_id: str,
    message_id: str,
    api_key_id: str,
) -> None:
    """Enqueue process_chat_message task via ARQ. Patched in unit tests."""
    from arq.connections import RedisSettings, create_pool

    from src.config import get_settings

    pool = await create_pool(RedisSettings.from_dsn(get_settings().redis_url))
    await pool.enqueue_job(
        "process_chat_message",
        conversation_id=conversation_id,
        message_id=message_id,
        api_key_id=api_key_id,
    )
    await pool.aclose()


# ── Create conversation ───────────────────────────────────────────────────────


@router.post("", status_code=201, response_model=ConversationRead)
def create_conversation(
    body: ConversationCreate | None = None,
    db: Session = Depends(get_db),
    api_key: APIKey = Depends(require_api_key),
) -> ConversationRead:
    title = (body.title if body and body.title else None) or "New conversation"
    conv = Conversation(
        title=title,
        created_by=api_key.id,
        updated_at=datetime.now(UTC),
    )
    db.add(conv)
    db.commit()
    db.refresh(conv)
    return ConversationRead.model_validate(conv)


# ── List conversations ────────────────────────────────────────────────────────


@router.get("", response_model=ConversationsListRead)
def list_conversations(
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    api_key: APIKey = Depends(require_api_key),
) -> ConversationsListRead:
    base = (
        db.query(Conversation)
        .filter(
            Conversation.created_by == api_key.id,
            Conversation.deleted_at.is_(None),
        )
        .order_by(Conversation.updated_at.desc())
    )
    total = base.count()
    items = base.offset(offset).limit(limit).all()
    return ConversationsListRead(
        conversations=[ConversationRead.model_validate(c) for c in items],
        total=total,
        limit=limit,
        offset=offset,
    )


# ── Get conversation ──────────────────────────────────────────────────────────


@router.get("/{conversation_id}", response_model=ConversationDetailRead)
def get_conversation(
    conversation_id: uuid.UUID,
    db: Session = Depends(get_db),
    api_key: APIKey = Depends(require_api_key),
) -> ConversationDetailRead:
    conv = _get_owned_conversation(conversation_id, api_key, db)
    count = (
        db.query(ChatMessage)
        .filter(ChatMessage.conversation_id == conv.id)
        .count()
    )
    return ConversationDetailRead(
        **ConversationRead.model_validate(conv).model_dump(),
        message_count=count,
    )


# ── Get messages ──────────────────────────────────────────────────────────────


@router.get("/{conversation_id}/messages", response_model=MessagesListRead)
def get_messages(
    conversation_id: uuid.UUID,
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    api_key: APIKey = Depends(require_api_key),
) -> MessagesListRead:
    _get_owned_conversation(conversation_id, api_key, db)
    base = (
        db.query(ChatMessage)
        .filter(ChatMessage.conversation_id == conversation_id)
        .order_by(ChatMessage.created_at)
    )
    total = base.count()
    msgs = base.offset(offset).limit(limit).all()
    return MessagesListRead(
        messages=[ChatMessageRead.model_validate(m) for m in msgs],
        total=total,
        limit=limit,
        offset=offset,
    )


# ── Send message ──────────────────────────────────────────────────────────────


@router.post(
    "/{conversation_id}/messages",
    status_code=202,
    response_model=SendMessageResponse,
)
@limiter.limit("10/minute")
async def send_message(
    request: Request,
    conversation_id: uuid.UUID,
    body: SendMessageRequest,
    db: Session = Depends(get_db),
    api_key: APIKey = Depends(require_api_key),
) -> SendMessageResponse:
    conv = _get_owned_conversation(conversation_id, api_key, db)

    # Update title from first user message (if still default)
    is_first_message = (
        db.query(ChatMessage)
        .filter(
            ChatMessage.conversation_id == conv.id,
            ChatMessage.role == MessageRole.user,
        )
        .count()
        == 0
    )
    if is_first_message and conv.title == "New conversation":
        conv.title = body.content[:60]

    msg = ChatMessage(
        conversation_id=conv.id,
        role=MessageRole.user,
        content=body.content,
    )
    db.add(msg)
    conv.updated_at = datetime.now(UTC)
    db.commit()
    db.refresh(msg)

    await _enqueue_chat_message(
        conversation_id=str(conv.id),
        message_id=str(msg.id),
        api_key_id=str(api_key.id),
    )

    return SendMessageResponse(message_id=msg.id, run_id=None, status="processing")


# ── Delete conversation (soft-delete) ─────────────────────────────────────────


@router.delete("/{conversation_id}", status_code=204)
def delete_conversation(
    conversation_id: uuid.UUID,
    db: Session = Depends(get_db),
    api_key: APIKey = Depends(require_api_key),
) -> None:
    conv = _get_owned_conversation(conversation_id, api_key, db)
    conv.deleted_at = datetime.now(UTC)
    db.commit()


# ── Helper ────────────────────────────────────────────────────────────────────


def _get_owned_conversation(
    conversation_id: uuid.UUID, api_key: APIKey, db: Session
) -> Conversation:
    conv = (
        db.query(Conversation)
        .filter(
            Conversation.id == conversation_id,
            Conversation.created_by == api_key.id,
            Conversation.deleted_at.is_(None),
        )
        .first()
    )
    if conv is None:
        raise HTTPException(
            status_code=404,
            detail=f"Conversation {conversation_id!s} not found",
        )
    return conv
