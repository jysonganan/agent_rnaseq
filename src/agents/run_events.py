"""Pipeline progress events published while stages execute.

Two Redis pub/sub channels (see docs/specs/api_contracts.md):

* ``logs:{run_id}`` — flat run-log frames for ``WS /ws/runs/{run_id}/logs``
  ``{ts, level, stage, agent, message}``
* ``conv:{conversation_id}`` — only for chat-originated runs; payload-wrapped
  ``stage_update`` / ``tool_call`` / ``error`` frames for
  ``WS /ws/conversations/{id}/stream``.

Every value published is either a fixed string or excerpted from a validated tool
output model (``output_excerpt``) — never LLM text. Publishing is best-effort: a Redis
outage must not fail a pipeline run.
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from typing import Any, Protocol

from src.agents.sanitize import sanitize_text

logger = logging.getLogger(__name__)

_MAX_SUMMARY_LEN = 1000


class RunEvents(Protocol):
    def stage_update(self, stage: str, status: str) -> None: ...
    def tool_call(self, tool_name: str, status: str, summary: str | None = None) -> None: ...
    def log(self, level: str, stage: str | None, agent: str | None, message: str) -> None: ...
    def run_error(self, message: str) -> None: ...
    def assistant_message(self, message_id: str, text: str) -> None: ...


class NullRunEvents:
    """No-op publisher (tests, dry runs without Redis)."""

    def stage_update(self, stage: str, status: str) -> None:
        pass

    def tool_call(self, tool_name: str, status: str, summary: str | None = None) -> None:
        pass

    def log(self, level: str, stage: str | None, agent: str | None, message: str) -> None:
        pass

    def run_error(self, message: str) -> None:
        pass

    def assistant_message(self, message_id: str, text: str) -> None:
        pass


def _numeric_only(value: Any, depth: int = 0) -> Any:
    """Keep numbers/bools (and dicts of them); drop strings such as file paths."""
    if isinstance(value, bool | int | float):
        return value
    if isinstance(value, dict) and depth < 3:
        kept = {str(k): _numeric_only(v, depth + 1) for k, v in value.items()}
        kept = {k: v for k, v in kept.items() if v is not None and v != {}}
        return kept or None
    return None


def output_excerpt(stage_output: dict[str, Any]) -> str | None:
    """JSON excerpt of a validated StageOutput for ``tool_call.summary`` (no prose, no paths)."""
    if "samples" in stage_output or "contrasts" in stage_output:
        key = "samples" if "samples" in stage_output else "contrasts"
        items = stage_output.get(key) or {}
        excerpt: Any = {"n_" + key: len(items)}
    else:
        excerpt = _numeric_only(stage_output.get("output") or {})
    if not excerpt:
        return None
    return json.dumps(excerpt, sort_keys=True)[:_MAX_SUMMARY_LEN]


class RedisRunEvents:
    def __init__(
        self,
        redis_client: Any,
        run_id: str,
        conversation_id: str | None = None,
        message_id: str | None = None,
    ) -> None:
        self._redis = redis_client
        self._run_id = run_id
        self._conv_channel = f"conv:{conversation_id}" if conversation_id else None
        self._message_id = message_id

    @classmethod
    def from_url(
        cls, url: str, run_id: str, conversation_id: str | None, message_id: str | None
    ) -> RedisRunEvents:
        import redis

        return cls(redis.Redis.from_url(url), run_id, conversation_id, message_id)

    def _publish(self, channel: str, frame: dict[str, Any]) -> None:
        try:
            self._redis.publish(channel, json.dumps(frame))
        except Exception:  # best-effort
            logger.warning("run_events: publish to %s failed", channel, exc_info=True)

    def _conv(self, frame_type: str, payload: dict[str, Any]) -> None:
        if self._conv_channel:
            self._publish(self._conv_channel, {"type": frame_type, "payload": payload})

    def stage_update(self, stage: str, status: str) -> None:
        self._conv("stage_update", {"run_id": self._run_id, "stage_name": stage, "status": status})

    def tool_call(self, tool_name: str, status: str, summary: str | None = None) -> None:
        if self._message_id:
            self._conv(
                "tool_call",
                {
                    "message_id": self._message_id,
                    "tool_name": tool_name,
                    "status": status,
                    "summary": summary,
                },
            )

    def log(self, level: str, stage: str | None, agent: str | None, message: str) -> None:
        self._publish(
            f"logs:{self._run_id}",
            {
                "ts": datetime.now(UTC).isoformat(),
                "level": level,
                "stage": stage,
                "agent": agent,
                "message": sanitize_text(message, 500),
            },
        )

    def run_error(self, message: str) -> None:
        self._conv("error", {"message": sanitize_text(message, 500)})

    def assistant_message(self, message_id: str, text: str) -> None:
        """A complete assistant turn (run summary): one token frame + done frame."""
        self._conv("token", {"message_id": message_id, "token": text})
        self._conv("done", {"message_id": message_id, "run_id": self._run_id})
