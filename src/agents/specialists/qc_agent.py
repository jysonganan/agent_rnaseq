"""QCAgent — runs FastQC, RSeQC, and MultiQC for a single sample."""

from __future__ import annotations

import uuid
from typing import Any, TypedDict

from src.agents.specialists._base import BaseSpecialistAgent, _make_stage_output
from src.db.enums import ArtifactType, PassFail, StageName
from src.db.models.results import QCMetric
from src.tools.base import ToolExecutionError
from src.tools.qc.fastqc import FastQCInput, run_fastqc
from src.tools.qc.multiqc import MultiQCInput, run_multiqc
from src.tools.qc.rseqc import RSeQCInput, run_rseqc


class QCStageInput(TypedDict):
    run_id: str
    sample_id: str
    fastq_paths: list[str]
    output_dir: str
    bam_path: str | None
    bam_index_path: str | None
    bed_annotation_path: str | None


def _to_pass_fail(value: str) -> PassFail | None:
    return {"PASS": PassFail.pass_, "WARN": PassFail.warn, "FAIL": PassFail.fail}.get(
        value.upper()
    )


class QCAgent(BaseSpecialistAgent):
    def __init__(self, db, llm_client=None, dry_run: bool = False, mock_registry=None):
        super().__init__(StageName.qc, db, llm_client=llm_client, dry_run=dry_run, mock_registry=mock_registry)

    def run(self, stage_input: QCStageInput) -> dict[str, Any]:  # type: ignore[override]
        stage = self._start_stage(
            stage_input["run_id"], StageName.qc, "fastqc", sample_id=stage_input["sample_id"]
        )
        try:
            fastqc_out = run_fastqc(
                FastQCInput(
                    fastq_paths=stage_input["fastq_paths"],
                    output_dir=stage_input["output_dir"],
                )
            )

            sample_uuid = uuid.UUID(stage_input["sample_id"])
            for module, result in fastqc_out.summary.items():
                self.db.add(
                    QCMetric(
                        stage_id=stage.id,
                        sample_id=sample_uuid,
                        metric_name=module,
                        metric_value_str=result,
                        pass_fail=_to_pass_fail(result),
                    )
                )

            for path in fastqc_out.report_html_paths:
                self._write_artifact(stage.id, stage_input["run_id"], ArtifactType.fastqc_report, path)

            if stage_input.get("bam_path"):
                run_rseqc(
                    RSeQCInput(
                        bam_path=stage_input["bam_path"],
                        bam_index_path=stage_input["bam_index_path"] or "",
                        bed_annotation_path=stage_input["bed_annotation_path"] or "",
                        output_prefix=stage_input["output_dir"] + "/rseqc",
                    )
                )

            run_multiqc(
                MultiQCInput(
                    input_dirs=[stage_input["output_dir"]],
                    output_dir=stage_input["output_dir"],
                )
            )

            self.db.flush()
            self._complete_stage(stage, tool_version=fastqc_out.tool_version)
            return _make_stage_output("qc", "completed", fastqc_out.model_dump(), fastqc_out.tool_version)

        except ToolExecutionError as exc:
            self._fail_stage(stage, str(exc))
            raise
