"""QuantificationAgent — HTSeq, Salmon, or RSEM based on RunConfig."""

from __future__ import annotations

from typing import Any, TypedDict

from src.agents.specialists._base import BaseSpecialistAgent, _make_stage_output
from src.db.enums import ArtifactType, StageName
from src.tools.base import ToolExecutionError
from src.tools.quantification.htseq import HTSeqInput, run_htseq_count
from src.tools.quantification.rsem import RSEMInput, run_rsem
from src.tools.quantification.salmon import SalmonQuantInput, run_salmon_quant


class QuantStageInput(TypedDict):
    run_id: str
    sample_id: str
    quantification_method: str   # "star_htseq" | "salmon" | "rsem"
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


class QuantificationAgent(BaseSpecialistAgent):
    def __init__(self, db, llm_client=None, dry_run: bool = False, mock_registry=None):
        super().__init__(StageName.quantification, db, llm_client=llm_client, dry_run=dry_run, mock_registry=mock_registry)

    def run(self, stage_input: QuantStageInput) -> dict[str, Any]:  # type: ignore[override]
        method = stage_input["quantification_method"]
        tool_name = {"star_htseq": "htseq", "salmon": "salmon", "rsem": "rsem"}.get(method, method)
        stage = self._start_stage(
            stage_input["run_id"], StageName.quantification, tool_name, sample_id=stage_input["sample_id"]
        )
        try:
            if method == "star_htseq":
                out = run_htseq_count(
                    HTSeqInput(
                        bam_path=stage_input["bam_path"] or "",
                        gtf_path=stage_input["gtf_path"] or "",
                        output_path=stage_input["output_dir"] + "/counts.tsv",
                    )
                )
                counts_path = out.counts_path
                tool_version = out.tool_version
                output_dict = out.model_dump()

            elif method == "salmon":
                out = run_salmon_quant(
                    SalmonQuantInput(
                        fastq_r1=stage_input["fastq_r1"] or "",
                        fastq_r2=stage_input.get("fastq_r2"),
                        index_path=stage_input["index_path"] or "",
                        output_dir=stage_input["output_dir"],
                    )
                )
                counts_path = out.quant_sf_path
                tool_version = out.tool_version
                output_dict = out.model_dump()

            else:  # rsem
                out = run_rsem(
                    RSEMInput(
                        bam_path=stage_input["bam_path"] or "",
                        rsem_reference=stage_input["rsem_reference"] or "",
                        output_prefix=stage_input["output_dir"] + "/rsem",
                    )
                )
                counts_path = out.genes_results_path
                tool_version = out.tool_version
                output_dict = out.model_dump()

            self._write_artifact(stage.id, stage_input["run_id"], ArtifactType.counts_matrix, counts_path)
            self._complete_stage(stage, tool_version=tool_version)
            return _make_stage_output("quantification", "completed", output_dict, tool_version)

        except ToolExecutionError as exc:
            self._fail_stage(stage, str(exc))
            raise
