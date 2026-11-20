"""Base class shared by all specialist sub-agents."""

from __future__ import annotations

import abc
import hashlib
import json
import os
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.orm import Session

from src.agents.base_agent import BaseStageAgent, MockToolRegistry
from src.agents.state import RunState
from src.db.enums import ArtifactType, Executor, StageName, StageStatus
from src.db.models.run import Artifact, PipelineStage
from src.tools.base import ToolExecutionError


class StageOutput(dict):
    """Typed dict-like container returned by each specialist's ``run()`` method."""


def _make_stage_output(
    stage_name: str,
    status: str,
    output: dict,
    tool_version: str | None,
    summary: str | None = None,
) -> dict[str, Any]:
    return {
        "stage_name": stage_name,
        "status": status,
        "output": output,
        "tool_version": tool_version,
        "summary": summary,
    }


class BaseSpecialistAgent(BaseStageAgent, abc.ABC):
    """Specialist sub-agent base class.

    Adds DB session management and common helpers on top of :class:`BaseStageAgent`.
    Subclasses implement ``run(stage_input)`` with the stage-specific logic.
    """

    def __init__(
        self,
        stage_name: str,
        db: Session,
        llm_client: Any = None,
        dry_run: bool = False,
        mock_registry: MockToolRegistry | None = None,
    ) -> None:
        super().__init__(stage_name, dry_run=dry_run, mock_registry=mock_registry)
        self.db = db
        self.llm_client = llm_client
        self._audit_input: dict[str, Any] | None = None
        self._audit_executor: Executor = Executor.local

    def run_stage(
        self, stage_input: Any, compute: Any = None, executor: str = "local"
    ) -> dict[str, Any]:
        """Run one stage invocation, recording ``stage_input`` as the audit input.

        Used by the LangGraph executor; ``run()`` may still be called directly.
        ``compute`` replaces the specialist's own tool calls (e.g. a Nextflow backend);
        only specialists that implement ``compute``/``persist`` accept it.
        """
        self._audit_input = json.loads(json.dumps(dict(stage_input), default=str))
        self._audit_executor = Executor(executor)
        try:
            if compute is None:
                return self.run(stage_input)
            if not self.supports_external_compute:
                raise TypeError(f"{type(self).__name__} cannot use an external compute backend")
            return self._run_split(stage_input, compute)
        finally:
            self._audit_input = None
            self._audit_executor = Executor.local

    # ── compute / persist split (heavy, per-sample stages) ───────────────────────

    supports_external_compute: bool = False

    def tool_name(self, stage_input: Any) -> str:  # pragma: no cover - overridden
        raise NotImplementedError

    def compute(self, stage_input: Any) -> dict[str, Any]:  # pragma: no cover - overridden
        """Run the tools; return validated ToolOutput models keyed by role."""
        raise NotImplementedError

    def persist(
        self, stage: PipelineStage, stage_input: Any, outs: dict[str, Any]
    ) -> dict[str, Any]:  # pragma: no cover - overridden
        """Write result/artifact rows from validated outputs; return the StageOutput."""
        raise NotImplementedError

    def _run_split(self, stage_input: Any, compute: Any) -> dict[str, Any]:
        stage = self._start_stage(
            stage_input["run_id"],
            StageName(self.stage_name),
            self.tool_name(stage_input),
            sample_id=stage_input.get("sample_id"),
        )
        try:
            outs = compute(stage_input)
            return self.persist(stage, stage_input, outs)
        except ToolExecutionError as exc:
            self._fail_stage(stage, str(exc))
            raise

    # ── LangGraph bridge ────────────────────────────────────────────────────────

    def _run(self, state: RunState) -> dict[str, Any]:
        """Delegate to ``run()`` extracting stage_input from LangGraph state."""
        run_config = state.get("run_config", {})
        return self.run(run_config)  # type: ignore[arg-type]

    # ── Primary public interface ─────────────────────────────────────────────────

    @abc.abstractmethod
    def run(self, stage_input: Any) -> dict[str, Any]:
        """Execute this stage.  Subclasses implement tool calls here."""

    # ── DB helpers ───────────────────────────────────────────────────────────────

    def _start_stage(
        self,
        run_id: str,
        stage_name: StageName,
        tool_name: str,
        sample_id: str | None = None,
    ) -> PipelineStage:
        """Insert a PipelineStage row with status=running and return it."""
        stage = PipelineStage(
            run_id=uuid.UUID(run_id),
            sample_id=uuid.UUID(sample_id) if sample_id else None,
            stage_name=stage_name,
            status=StageStatus.running,
            tool_name=tool_name,
            input_params=self._audit_input,
            executor=self._audit_executor,
            started_at=datetime.now(UTC),
        )
        self.db.add(stage)
        self.db.flush()
        return stage

    def _complete_stage(
        self,
        stage: PipelineStage,
        tool_version: str | None = None,
        output_summary: dict | None = None,
    ) -> None:
        stage.status = StageStatus.completed
        stage.tool_version = tool_version
        stage.output_summary = output_summary
        stage.completed_at = datetime.now(UTC)  # type: ignore[assignment]
        self.db.flush()

    def _fail_stage(self, stage: PipelineStage, error_msg: str) -> None:
        stage.status = StageStatus.failed
        stage.completed_at = datetime.now(UTC)  # type: ignore[assignment]
        self.db.flush()

    def _write_artifact(
        self,
        stage_id: uuid.UUID,
        run_id: str,
        artifact_type: ArtifactType,
        path: str,
    ) -> None:
        size, md5 = _file_size_and_md5(path)
        artifact = Artifact(
            stage_id=stage_id,
            run_id=uuid.UUID(run_id),
            artifact_type=artifact_type,
            path=path,
            file_size_bytes=size,
            checksum_md5=md5,
        )
        self.db.add(artifact)
        self.db.flush()


def _file_size_and_md5(path: str) -> tuple[int | None, str | None]:
    """Size and MD5 of a local artifact (safety_policy Rule 10); ``None`` if not local."""
    if not os.path.isfile(path):
        return None, None
    digest = hashlib.md5(usedforsecurity=False)
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            digest.update(chunk)
    return os.path.getsize(path), digest.hexdigest()
