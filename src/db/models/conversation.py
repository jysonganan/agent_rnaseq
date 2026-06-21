"""Conversation and ChatMessage ORM models."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import DateTime, ForeignKey, String, Text, Uuid
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.db.base import Base, CreatedAtMixin, UUIDPrimaryKeyMixin
from src.db.enums import MessageRole, ToolStatus


def _utcnow() -> datetime:
    return datetime.now(UTC)


class Conversation(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    __tablename__ = "conversations"

    title: Mapped[str] = mapped_column(
        String(256), nullable=False, default="New conversation"
    )
    created_by: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("api_keys.id"), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow
    )
    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    messages: Mapped[list["ChatMessage"]] = relationship(
        "ChatMessage",
        back_populates="conversation",
        order_by="ChatMessage.created_at",
    )
    api_key: Mapped["APIKey"] = relationship("APIKey")  # type: ignore[name-defined]  # noqa: F821


class ChatMessage(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    __tablename__ = "chat_messages"

    conversation_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("conversations.id"), nullable=False
    )
    role: Mapped[MessageRole] = mapped_column(
        SAEnum(MessageRole, native_enum=False), nullable=False
    )
    content: Mapped[str] = mapped_column(Text, nullable=False)
    # Soft reference to AnalysisRun — no FK to avoid circular dependency with
    # AnalysisRun.triggering_message_id (SQLite does not support ALTER TABLE ADD CONSTRAINT).
    run_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    tool_name: Mapped[str | None] = mapped_column(String(64), nullable=True)
    tool_status: Mapped[ToolStatus | None] = mapped_column(
        SAEnum(ToolStatus, native_enum=False), nullable=True
    )

    conversation: Mapped[Conversation] = relationship(
        "Conversation", back_populates="messages"
    )
