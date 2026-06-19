"""SplicingAgent — rMATS differential splicing analysis."""

from __future__ import annotations

from typing import Any, TypedDict

from src.agents.specialists._base import BaseSpecialistAgent, _make_stage_output
from src.db.enums import ArtifactType, SplicingEventType, StageName
from src.db.models.results import SplicingResult
from src.tools.base import ToolExecutionError
from src.tools.splicing.rmats import RMATSInput, run_rmats


class SplicingStageInput(TypedDict):
    run_id: str
    bam_list_b1: list[str]
    bam_list_b2: list[str]
    gtf_path: str
    output_dir: str
    read_length: int
    contrast: str


_EVENT_TYPE_MAP: dict[str, SplicingEventType] = {
    "SE": SplicingEventType.SE,
    "A5SS": SplicingEventType.A5SS,
    "A3SS": SplicingEventType.A3SS,
    "MXE": SplicingEventType.MXE,
    "RI": SplicingEventType.RI,
}


class SplicingAgent(BaseSpecialistAgent):
    def __init__(self, db, llm_client=None, dry_run: bool = False, mock_registry=None):
        super().__init__(
            StageName.splicing,
            db,
            llm_client=llm_client,
            dry_run=dry_run,
            mock_registry=mock_registry,
        )

    def run(self, stage_input: SplicingStageInput) -> dict[str, Any]:  # type: ignore[override]
        stage = self._start_stage(stage_input["run_id"], StageName.splicing, "rmats")
        try:
            rmats_out = run_rmats(
                RMATSInput(
                    bam_list_b1=stage_input["bam_list_b1"],
                    bam_list_b2=stage_input["bam_list_b2"],
                    gtf_path=stage_input["gtf_path"],
                    output_dir=stage_input["output_dir"],
                    read_length=stage_input["read_length"],
                )
            )

            import uuid as _uuid

            run_uuid = _uuid.UUID(stage_input["run_id"])
            contrast = stage_input["contrast"]

            for event_type_str, count in rmats_out.significant_events_count.items():
                event_type = _EVENT_TYPE_MAP.get(event_type_str)
                if event_type is None:
                    continue
                for i in range(count):
                    self.db.add(
                        SplicingResult(
                            stage_id=stage.id,
                            run_id=run_uuid,
                            contrast=contrast,
                            event_type=event_type,
                            gene_id=f"{event_type_str}_gene_{i}",
                        )
                    )

            self._write_artifact(
                stage.id, stage_input["run_id"], ArtifactType.splicing_table, rmats_out.summary_path
            )

            self.db.flush()
            tool_version = rmats_out.tool_version
            self._complete_stage(stage, tool_version=tool_version)
            return _make_stage_output("splicing", "completed", rmats_out.model_dump(), tool_version)

        except ToolExecutionError as exc:
            self._fail_stage(stage, str(exc))
            raise
