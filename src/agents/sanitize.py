"""Strip file paths, AWS credential patterns and tracebacks from user-visible text.

Used for chat content (safety_policy Rule 11.6) and for run/stage error messages
(Rule 9: "Error messages ... are sanitized: no file system paths or credentials").
"""

from __future__ import annotations

import re

_PATH_RE = re.compile(r"(/[a-zA-Z0-9_/.\-]+){2,}")
_AWS_KEY_RE = re.compile(r"AKIA[0-9A-Z]{16}")
_TRACEBACK_RE = re.compile(r"Traceback \(most recent call last\):.*", re.DOTALL)


def sanitize_text(text: str, max_len: int | None = None) -> str:
    text = _PATH_RE.sub("[PATH]", text)
    text = _AWS_KEY_RE.sub("[REDACTED]", text)
    text = _TRACEBACK_RE.sub("[TRACEBACK REMOVED]", text)
    text = text.strip()
    return text[:max_len] if max_len is not None else text
