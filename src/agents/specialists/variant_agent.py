"""VariantAgent — GATK HaplotypeCaller + variant filtering."""

from __future__ import annotations

from typing import Any, TypedDict

from src.agents.specialists._base import BaseSpecialistAgent, _make_stage_output
from src.db.enums import ArtifactType, StageName
from src.tools.base import ToolExecutionError
from src.tools.variant.gatk import (
    GATKHaplotypeCallerInput,
    GATKVariantFilterInput,
    run_gatk_haplotypecaller,
    run_gatk_variant_filter,
)


class VariantStageInput(TypedDict):
    run_id: str
    sample_id: str
    bam_path: str
    bam_index_path: str
    reference_fasta: str
    output_dir: str
    dbsnp_path: str | None


class VariantAgent(BaseSpecialistAgent):
    def __init__(self, db, llm_client=None, dry_run: bool = False, mock_registry=None):
        super().__init__(StageName.variant_calling, db, llm_client=llm_client, dry_run=dry_run, mock_registry=mock_registry)

    def run(self, stage_input: VariantStageInput) -> dict[str, Any]:  # type: ignore[override]
        stage = self._start_stage(
            stage_input["run_id"], StageName.variant_calling, "gatk", sample_id=stage_input["sample_id"]
        )
        try:
            raw_vcf = stage_input["output_dir"] + "/raw.vcf.gz"
            hc_out = run_gatk_haplotypecaller(
                GATKHaplotypeCallerInput(
                    bam_path=stage_input["bam_path"],
                    bam_index_path=stage_input["bam_index_path"],
                    reference_fasta=stage_input["reference_fasta"],
                    output_vcf_path=raw_vcf,
                    dbsnp_path=stage_input.get("dbsnp_path"),
                )
            )

            filtered_vcf = stage_input["output_dir"] + "/filtered.vcf.gz"
            filter_out = run_gatk_variant_filter(
                GATKVariantFilterInput(
                    vcf_path=hc_out.vcf_path,
                    reference_fasta=stage_input["reference_fasta"],
                    output_vcf_path=filtered_vcf,
                    snp_filter_expression="QD < 2.0 || FS > 60.0",
                    indel_filter_expression="QD < 2.0 || FS > 200.0",
                )
            )

            self._write_artifact(stage.id, stage_input["run_id"], ArtifactType.vcf, filter_out.filtered_vcf_path)

            tool_version = hc_out.tool_version
            self._complete_stage(stage, tool_version=tool_version)
            return _make_stage_output("variant_calling", "completed", filter_out.model_dump(), tool_version)

        except ToolExecutionError as exc:
            self._fail_stage(stage, str(exc))
            raise
