"""AlignmentAgent — STAR alignment + samtools sort/index."""

from __future__ import annotations

from typing import Any, TypedDict

from src.agents.specialists._base import BaseSpecialistAgent, _make_stage_output
from src.db.enums import ArtifactType, StageName
from src.tools.alignment.samtools import SamtoolsInput, run_samtools_sort_index
from src.tools.alignment.star import STARAlignInput, run_star_align
from src.tools.base import ToolExecutionError


class AlignmentStageInput(TypedDict):
    run_id: str
    sample_id: str
    fastq_r1: str
    fastq_r2: str | None
    genome_dir: str
    output_prefix: str
    threads: int


class AlignmentAgent(BaseSpecialistAgent):
    def __init__(self, db, llm_client=None, dry_run: bool = False, mock_registry=None):
        super().__init__(
            StageName.alignment,
            db,
            llm_client=llm_client,
            dry_run=dry_run,
            mock_registry=mock_registry,
        )

    def run(self, stage_input: AlignmentStageInput) -> dict[str, Any]:  # type: ignore[override]
        stage = self._start_stage(
            stage_input["run_id"], StageName.alignment, "star", sample_id=stage_input["sample_id"]
        )
        try:
            star_out = run_star_align(
                STARAlignInput(
                    fastq_r1=stage_input["fastq_r1"],
                    fastq_r2=stage_input.get("fastq_r2"),
                    genome_dir=stage_input["genome_dir"],
                    output_prefix=stage_input["output_prefix"],
                    threads=stage_input.get("threads", 8),
                )
            )

            samtools_out = run_samtools_sort_index(
                SamtoolsInput(
                    bam_path=star_out.bam_path,
                    output_prefix=stage_input["output_prefix"] + "_sorted",
                )
            )

            self._write_artifact(
                stage.id, stage_input["run_id"], ArtifactType.bam, samtools_out.sorted_bam_path
            )
            self._write_artifact(
                stage.id, stage_input["run_id"], ArtifactType.bai, samtools_out.bai_path
            )

            tool_version = star_out.tool_version
            self._complete_stage(stage, tool_version=tool_version)
            return _make_stage_output("alignment", "completed", star_out.model_dump(), tool_version)

        except ToolExecutionError as exc:
            self._fail_stage(stage, str(exc))
            raise
