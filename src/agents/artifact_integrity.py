"""Re-verify upstream artifacts before a stage consumes them (safety_policy Rule 10).

Every file path appearing in a stage's inputs that matches an ``Artifact`` row of the same
run with a recorded ``checksum_md5`` is re-hashed; a missing file or a different checksum
stops the stage before any tool runs.
"""

from __future__ import annotations

import os
import uuid
from collections.abc import Iterable
from typing import Any

from sqlalchemy.orm import Session


class ArtifactIntegrityError(Exception):
    """An upstream artifact is missing or changed since it was produced."""


def _paths_in(value: Any) -> Iterable[str]:
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for v in value.values():
            yield from _paths_in(v)
    elif isinstance(value, list | tuple):
        for v in value:
            yield from _paths_in(v)


def verify_input_artifacts(db: Session, run_id: str, inputs: list[dict[str, Any]]) -> int:
    """Return how many artifacts were verified; raise on mismatch."""
    from src.agents.specialists._base import _file_size_and_md5
    from src.db.models.run import Artifact

    paths = {p for inp in inputs for p in _paths_in(inp) if p.startswith("/")}
    if not paths:
        return 0
    rows = (
        db.query(Artifact)
        .filter(
            Artifact.run_id == uuid.UUID(run_id),
            Artifact.path.in_(paths),
            Artifact.checksum_md5.is_not(None),
        )
        .all()
    )
    checked: dict[str, str] = {}
    for row in rows:
        if row.path in checked:
            continue
        name = os.path.basename(row.path)
        if not os.path.isfile(row.path):
            raise ArtifactIntegrityError(f"Upstream artifact {name} is missing")
        _, md5 = _file_size_and_md5(row.path)
        if md5 != row.checksum_md5:
            raise ArtifactIntegrityError(
                f"Upstream artifact {name} changed since it was produced (checksum mismatch)"
            )
        checked[row.path] = md5
    return len(checked)
