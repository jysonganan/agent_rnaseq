"""AlignmentQCAgent — post-alignment QC with RSeQC on the sorted BAM (``alignment_qc`` stage).

Runs after ``alignment``: read distribution over gene features and library strandedness
(``infer_experiment``). FastQC/MultiQC stay in the pre-alignment ``qc`` stage.
"""

from __future__ import annotations

import posixpath
import uuid
from typing import Any, TypedDict

from src.agents.specialists._base import BaseSpecialistAgent, _make_stage_output
from src.db.enums import ArtifactType, StageName
from src.db.models.results import QCMetric
from src.db.models.run import PipelineStage
from src.tools.qc.gtf_to_bed import ensure_gene_model_bed
from src.tools.qc.rseqc import RSeQCInput, RSeQCOutput, run_rseqc

# Fast, informative modules. junction_saturation resamples the BAM many times and needs R.
ALIGNMENT_QC_MODULES = ["read_distribution", "infer_experiment"]


class AlignmentQCStageInput(TypedDict):
    run_id: str
    sample_id: str
    bam_path: str
    bam_index_path: str
    bed_annotation_path: str | None  # genome's BED12, if registered
    gtf_path: str  # used to derive a BED12 when the genome has none
    gene_model_path: str  # run-scoped location of the derived BED12
    output_dir: str


def rseqc_output_prefix(output_dir: str, sample_id: str) -> str:
    """``<output_dir>/<sid>.rseqc`` → files ``<sid>.rseqc_<module>.txt`` (same as Nextflow)."""
    return posixpath.join(output_dir, f"{sample_id}.rseqc")


def rseqc_metrics(out: RSeQCOutput) -> list[tuple[str, float | None, str | None]]:
    """(metric_name, numeric value, string value) rows from a validated RSeQC output."""
    rows: list[tuple[str, float | None, str | None]] = []
    for region, count in out.read_distribution.items():
        rows.append((f"rseqc_rd_{region}"[:64].lower(), float(count), None))
    ie = out.infer_experiment_result
    if ie:
        for key in ("undetermined", "sense", "antisense"):
            if key in ie:
                rows.append((f"rseqc_ie_{key}", float(ie[key]), None))
        if "library_type" in ie:
            rows.append(("rseqc_library_type", None, str(ie["library_type"])))
        if "strandedness" in ie:
            rows.append(("rseqc_strandedness", None, str(ie["strandedness"])))
    return rows


class AlignmentQCAgent(BaseSpecialistAgent):
    supports_external_compute = True

    def __init__(self, db, llm_client=None, dry_run: bool = False, mock_registry=None):
        super().__init__(
            StageName.alignment_qc,
            db,
            llm_client=llm_client,
            dry_run=dry_run,
            mock_registry=mock_registry,
        )

    def run(self, stage_input: AlignmentQCStageInput) -> dict[str, Any]:  # type: ignore[override]
        return self._run_split(stage_input, self.compute)

    def tool_name(self, stage_input: AlignmentQCStageInput) -> str:  # type: ignore[override]
        return "rseqc"

    def compute(self, stage_input: AlignmentQCStageInput) -> dict[str, Any]:  # type: ignore[override]
        bed = ensure_gene_model_bed(
            stage_input.get("bed_annotation_path"),
            stage_input["gtf_path"],
            stage_input["gene_model_path"],
        )
        out = run_rseqc(
            RSeQCInput(
                bam_path=stage_input["bam_path"],
                bam_index_path=stage_input["bam_index_path"],
                bed_annotation_path=bed,
                output_prefix=rseqc_output_prefix(
                    stage_input["output_dir"], stage_input["sample_id"]
                ),
                modules=ALIGNMENT_QC_MODULES,
            )
        )
        return {"rseqc": out}

    def persist(  # type: ignore[override]
        self, stage: PipelineStage, stage_input: AlignmentQCStageInput, outs: dict[str, Any]
    ) -> dict[str, Any]:
        out: RSeQCOutput = outs["rseqc"]
        sample_uuid = uuid.UUID(stage_input["sample_id"])
        for name, value, value_str in rseqc_metrics(out):
            self.db.add(
                QCMetric(
                    stage_id=stage.id,
                    sample_id=sample_uuid,
                    metric_name=name,
                    metric_value=value,
                    metric_value_str=value_str,
                )
            )
        for path in out.module_outputs.values():
            self._write_artifact(stage.id, stage_input["run_id"], ArtifactType.rseqc_report, path)

        self.db.flush()
        self._complete_stage(stage, tool_version=out.tool_version)
        return _make_stage_output("alignment_qc", "completed", out.model_dump(), out.tool_version)
