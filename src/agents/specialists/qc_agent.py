"""QCAgent — pre-alignment read QC (FastQC + MultiQC) for a single sample.

RSeQC needs a BAM, so it runs later in the ``alignment_qc`` stage (AlignmentQCAgent).
"""

from __future__ import annotations

import uuid
from typing import Any, TypedDict

from src.agents.specialists._base import BaseSpecialistAgent, _make_stage_output
from src.db.enums import ArtifactType, PassFail, StageName
from src.db.models.results import QCMetric
from src.db.models.run import PipelineStage
from src.tools.qc.fastqc import FastQCInput, run_fastqc
from src.tools.qc.multiqc import MultiQCInput, run_multiqc


class QCStageInput(TypedDict):
    run_id: str
    sample_id: str
    fastq_paths: list[str]
    output_dir: str


def _to_pass_fail(value: str) -> PassFail | None:
    return {"PASS": PassFail.pass_, "WARN": PassFail.warn, "FAIL": PassFail.fail}.get(value.upper())


class QCAgent(BaseSpecialistAgent):
    supports_external_compute = True

    def __init__(self, db, llm_client=None, dry_run: bool = False, mock_registry=None):
        super().__init__(
            StageName.qc, db, llm_client=llm_client, dry_run=dry_run, mock_registry=mock_registry
        )

    def run(self, stage_input: QCStageInput) -> dict[str, Any]:  # type: ignore[override]
        return self._run_split(stage_input, self.compute)

    def tool_name(self, stage_input: QCStageInput) -> str:  # type: ignore[override]
        return "fastqc"

    def compute(self, stage_input: QCStageInput) -> dict[str, Any]:  # type: ignore[override]
        outs: dict[str, Any] = {
            "fastqc": run_fastqc(
                FastQCInput(
                    fastq_paths=stage_input["fastq_paths"],
                    output_dir=stage_input["output_dir"],
                )
            )
        }
        outs["multiqc"] = run_multiqc(
            MultiQCInput(
                input_dirs=[stage_input["output_dir"]],
                output_dir=stage_input["output_dir"],
            )
        )
        return outs

    def persist(  # type: ignore[override]
        self, stage: PipelineStage, stage_input: QCStageInput, outs: dict[str, Any]
    ) -> dict[str, Any]:
        fastqc_out = outs["fastqc"]
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

        self.db.flush()
        self._complete_stage(stage, tool_version=fastqc_out.tool_version)
        return _make_stage_output(
            "qc", "completed", fastqc_out.model_dump(), fastqc_out.tool_version
        )
