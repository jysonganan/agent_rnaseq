"""ARQ background task: process_chat_message."""

from __future__ import annotations

import contextlib
import logging

from arq import ArqRedis

from src.agents.orchestrator import ChatDispatchInput, OrchestratorAgent
from src.config import get_settings
from src.db.session import get_session_factory

logger = logging.getLogger(__name__)


async def process_chat_message(
    ctx: dict,
    *,
    conversation_id: str,
    message_id: str,
    api_key_id: str,
) -> None:
    """Dequeue and process a user chat message through the orchestrator."""
    from openai import AsyncOpenAI, OpenAI

    from src.db.models.conversation import ChatMessage, Conversation

    settings = get_settings()
    redis_client = ctx.get("redis")

    db_factory = get_session_factory()
    db = db_factory()
    try:
        msg = db.query(ChatMessage).filter(ChatMessage.id == message_id).first()
        if msg is None:
            logger.warning("process_chat_message: message %s not found, skipping", message_id)
            return

        conv = db.query(Conversation).filter(Conversation.id == conversation_id).first()
        if conv is None or conv.deleted_at is not None:
            logger.warning("process_chat_message: conversation %s not found or deleted, skipping", conversation_id)
            return

        llm_client = OpenAI(api_key=settings.openai_api_key)
        agent = OrchestratorAgent(llm_client)

        dispatch_input = ChatDispatchInput(
            conversation_id=conversation_id,
            message_id=message_id,
            user_content=msg.content,
            api_key_id=api_key_id,
        )

        await agent.dispatch_from_chat(dispatch_input, db=db, redis_client=redis_client)
    except Exception:
        logger.exception("process_chat_message failed for message=%s", message_id)
        with contextlib.suppress(Exception):
            import json

            if redis_client is not None:
                error_frame = json.dumps(
                    {
                        "type": "error",
                        "payload": {
                            "message_id": message_id,
                            "detail": "Processing failed. Please try again.",
                        },
                    }
                )
                await redis_client.publish(f"conv:{conversation_id}", error_frame)
    finally:
        db.close()


class WorkerSettings:
    functions = [process_chat_message]
    redis_settings_dsn_env = "REDIS_URL"
