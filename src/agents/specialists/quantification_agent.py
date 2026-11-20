"""QuantificationAgent — HTSeq, Salmon, or RSEM based on RunConfig."""

from __future__ import annotations

from typing import Any, TypedDict

from src.agents.specialists._base import BaseSpecialistAgent, _make_stage_output
from src.db.enums import ArtifactType, StageName
from src.db.models.run import PipelineStage
from src.tools.quantification.htseq import HTSeqInput, HTSeqOutput, run_htseq_count
from src.tools.quantification.rsem import RSEMInput, run_rsem
from src.tools.quantification.salmon import SalmonQuantInput, SalmonQuantOutput, run_salmon_quant


class QuantStageInput(TypedDict):
    run_id: str
    sample_id: str
    quantification_method: str  # "star_htseq" | "salmon" | "rsem"
    output_dir: str
    # htseq / rsem
    bam_path: str | None
    gtf_path: str | None
    # salmon
    fastq_r1: str | None
    fastq_r2: str | None
    index_path: str | None
    # rsem
    rsem_reference: str | None


def counts_path_of(out: Any) -> str:
    """Per-sample counts file of any quantification ToolOutput."""
    if isinstance(out, HTSeqOutput):
        return out.counts_path
    if isinstance(out, SalmonQuantOutput):
        return out.quant_sf_path
    return out.genes_results_path


class QuantificationAgent(BaseSpecialistAgent):
    supports_external_compute = True

    def __init__(self, db, llm_client=None, dry_run: bool = False, mock_registry=None):
        super().__init__(
            StageName.quantification,
            db,
            llm_client=llm_client,
            dry_run=dry_run,
            mock_registry=mock_registry,
        )

    def run(self, stage_input: QuantStageInput) -> dict[str, Any]:  # type: ignore[override]
        return self._run_split(stage_input, self.compute)

    def tool_name(self, stage_input: QuantStageInput) -> str:  # type: ignore[override]
        method = stage_input["quantification_method"]
        return {"star_htseq": "htseq", "salmon": "salmon", "rsem": "rsem"}.get(method, method)

    def compute(self, stage_input: QuantStageInput) -> dict[str, Any]:  # type: ignore[override]
        method = stage_input["quantification_method"]
        if method == "star_htseq":
            out: Any = run_htseq_count(
                HTSeqInput(
                    bam_path=stage_input["bam_path"] or "",
                    gtf_path=stage_input["gtf_path"] or "",
                    output_path=stage_input["output_dir"] + "/counts.tsv",
                )
            )
        elif method == "salmon":
            out = run_salmon_quant(
                SalmonQuantInput(
                    fastq_r1=stage_input["fastq_r1"] or "",
                    fastq_r2=stage_input.get("fastq_r2"),
                    index_path=stage_input["index_path"] or "",
                    output_dir=stage_input["output_dir"],
                )
            )
        else:  # rsem
            out = run_rsem(
                RSEMInput(
                    bam_path=stage_input["bam_path"] or "",
                    rsem_reference=stage_input["rsem_reference"] or "",
                    output_prefix=stage_input["output_dir"] + "/rsem",
                )
            )
        return {"quant": out}

    def persist(  # type: ignore[override]
        self, stage: PipelineStage, stage_input: QuantStageInput, outs: dict[str, Any]
    ) -> dict[str, Any]:
        out = outs["quant"]
        self._write_artifact(
            stage.id, stage_input["run_id"], ArtifactType.counts_matrix, counts_path_of(out)
        )
        self._complete_stage(stage, tool_version=out.tool_version)
        return _make_stage_output("quantification", "completed", out.model_dump(), out.tool_version)
