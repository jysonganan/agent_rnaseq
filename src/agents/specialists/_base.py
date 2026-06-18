"""Base class shared by all specialist sub-agents."""

from __future__ import annotations

import abc
import uuid
from typing import Any

from sqlalchemy.orm import Session

from src.agents.base_agent import BaseStageAgent, MockToolRegistry
from src.agents.state import RunState
from src.db.enums import ArtifactType, StageName, StageStatus
from src.db.models.run import Artifact, PipelineStage


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
        self.db.flush()

    def _fail_stage(self, stage: PipelineStage, error_msg: str) -> None:
        stage.status = StageStatus.failed
        self.db.flush()

    def _write_artifact(
        self,
        stage_id: uuid.UUID,
        run_id: str,
        artifact_type: ArtifactType,
        path: str,
    ) -> None:
        artifact = Artifact(
            stage_id=stage_id,
            run_id=uuid.UUID(run_id),
            artifact_type=artifact_type,
            path=path,
        )
        self.db.add(artifact)
        self.db.flush()
