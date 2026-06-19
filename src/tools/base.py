"""Shared tool infrastructure: exceptions, subprocess helper, timing decorator."""

from __future__ import annotations

import enum
import logging
import subprocess
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from functools import wraps


class ExecutionBackend(enum.StrEnum):
    local = "local"
    nextflow = "nextflow"
    aws_batch = "aws_batch"

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT = 3600  # 1 hour


# ── Exception types ────────────────────────────────────────────────────────────


@dataclass
class ToolExecutionError(Exception):
    tool_name: str
    exit_code: int
    stderr: str
    command: list[str] = field(default_factory=list)

    def __str__(self) -> str:
        cmd_preview = " ".join(self.command[:5]) + ("…" if len(self.command) > 5 else "")
        return f"[{self.tool_name}] exit={self.exit_code} cmd={cmd_preview!r}: {self.stderr[:500]}"


@dataclass
class ToolValidationError(Exception):
    tool_name: str
    field: str
    message: str

    def __str__(self) -> str:
        return f"[{self.tool_name}] validation error on '{self.field}': {self.message}"


@dataclass
class ToolTimeoutError(Exception):
    tool_name: str
    timeout_seconds: int

    def __str__(self) -> str:
        return f"[{self.tool_name}] timed out after {self.timeout_seconds}s"


# ── Decorator ──────────────────────────────────────────────────────────────────


def tool_call(fn: Callable) -> Callable:
    """Decorator that logs start/finish and elapsed time for every tool call."""

    @wraps(fn)
    def wrapper(*args, **kwargs):  # type: ignore[no-untyped-def]
        start = time.monotonic()
        logger.debug("tool_call: starting %s", fn.__name__)
        try:
            result = fn(*args, **kwargs)
        except (ToolExecutionError, ToolValidationError, ToolTimeoutError):
            elapsed = time.monotonic() - start
            logger.debug("tool_call: %s raised after %.3fs", fn.__name__, elapsed)
            raise
        except Exception:
            elapsed = time.monotonic() - start
            logger.error("tool_call: %s failed after %.3fs", fn.__name__, elapsed)
            raise
        elapsed = time.monotonic() - start
        logger.debug("tool_call: %s completed in %.3fs", fn.__name__, elapsed)
        return result

    return wrapper


# ── Subprocess helper ──────────────────────────────────────────────────────────


def run_subprocess(
    cmd: list[str],
    *,
    tool_name: str,
    timeout: int = DEFAULT_TIMEOUT,
    cwd: str | None = None,
) -> subprocess.CompletedProcess:  # type: ignore[type-arg]
    """Run *cmd* and return the completed process.

    Raises:
        ToolTimeoutError: if the process exceeds *timeout* seconds.
        ToolExecutionError: if the process exits with a non-zero code.
    """
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            timeout=timeout,
            cwd=cwd,
        )
    except subprocess.TimeoutExpired as err:
        raise ToolTimeoutError(tool_name=tool_name, timeout_seconds=timeout) from err

    if proc.returncode != 0:
        raise ToolExecutionError(
            tool_name=tool_name,
            exit_code=proc.returncode,
            stderr=proc.stderr.decode("utf-8", errors="replace"),
            command=cmd,
        )
    return proc


def detect_version(version_cmd: list[str], tool_name: str) -> str | None:
    """Return the version string from *version_cmd*, or None if unavailable."""
    try:
        proc = subprocess.run(version_cmd, capture_output=True, timeout=10)
        raw = (proc.stdout + proc.stderr).decode("utf-8", errors="replace").strip()
        return raw.splitlines()[0] if raw else None
    except Exception:
        logger.debug("Could not detect version for %s", tool_name)
        return None
