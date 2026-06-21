"""Pydantic schemas for Conversation and ChatMessage."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from src.db.enums import MessageRole, ToolStatus


class ConversationCreate(BaseModel):
    title: str | None = Field(None, max_length=256)


class ConversationRead(BaseModel):
    id: uuid.UUID
    title: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ConversationDetailRead(ConversationRead):
    message_count: int


class ConversationsListRead(BaseModel):
    conversations: list[ConversationRead]
    total: int
    limit: int
    offset: int


class ChatMessageRead(BaseModel):
    id: uuid.UUID
    conversation_id: uuid.UUID
    role: MessageRole
    content: str
    run_id: uuid.UUID | None
    tool_name: str | None
    tool_status: ToolStatus | None
    created_at: datetime

    model_config = {"from_attributes": True}


class MessagesListRead(BaseModel):
    messages: list[ChatMessageRead]
    total: int
    limit: int
    offset: int


class SendMessageRequest(BaseModel):
    content: str = Field(..., min_length=1, max_length=4000)


class SendMessageResponse(BaseModel):
    message_id: uuid.UUID
    run_id: uuid.UUID | None
    status: str = "processing"
