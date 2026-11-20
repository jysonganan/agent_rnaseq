"""VariantAgent — GATK HaplotypeCaller + variant filtering."""

from __future__ import annotations

from typing import Any, TypedDict

from src.agents.specialists._base import BaseSpecialistAgent, _make_stage_output
from src.db.enums import ArtifactType, StageName
from src.db.models.run import PipelineStage
from src.tools.variant.gatk import (
    GATKHaplotypeCallerInput,
    GATKVariantFilterInput,
    run_gatk_haplotypecaller,
    run_gatk_variant_filter,
)

SNP_FILTER_EXPRESSION = "QD < 2.0 || FS > 60.0"
INDEL_FILTER_EXPRESSION = "QD < 2.0 || FS > 200.0"


class VariantStageInput(TypedDict):
    run_id: str
    sample_id: str
    bam_path: str
    bam_index_path: str
    reference_fasta: str
    output_dir: str
    dbsnp_path: str | None


class VariantAgent(BaseSpecialistAgent):
    supports_external_compute = True

    def __init__(self, db, llm_client=None, dry_run: bool = False, mock_registry=None):
        super().__init__(
            StageName.variant_calling,
            db,
            llm_client=llm_client,
            dry_run=dry_run,
            mock_registry=mock_registry,
        )

    def run(self, stage_input: VariantStageInput) -> dict[str, Any]:  # type: ignore[override]
        return self._run_split(stage_input, self.compute)

    def tool_name(self, stage_input: VariantStageInput) -> str:  # type: ignore[override]
        return "gatk"

    def compute(self, stage_input: VariantStageInput) -> dict[str, Any]:  # type: ignore[override]
        hc_out = run_gatk_haplotypecaller(
            GATKHaplotypeCallerInput(
                bam_path=stage_input["bam_path"],
                bam_index_path=stage_input["bam_index_path"],
                reference_fasta=stage_input["reference_fasta"],
                output_vcf_path=stage_input["output_dir"] + "/raw.vcf.gz",
                dbsnp_path=stage_input.get("dbsnp_path"),
            )
        )
        filter_out = run_gatk_variant_filter(
            GATKVariantFilterInput(
                vcf_path=hc_out.vcf_path,
                reference_fasta=stage_input["reference_fasta"],
                output_vcf_path=stage_input["output_dir"] + "/filtered.vcf.gz",
                snp_filter_expression=SNP_FILTER_EXPRESSION,
                indel_filter_expression=INDEL_FILTER_EXPRESSION,
            )
        )
        return {"haplotypecaller": hc_out, "filter": filter_out}

    def persist(  # type: ignore[override]
        self, stage: PipelineStage, stage_input: VariantStageInput, outs: dict[str, Any]
    ) -> dict[str, Any]:
        hc_out, filter_out = outs["haplotypecaller"], outs["filter"]
        self._write_artifact(
            stage.id, stage_input["run_id"], ArtifactType.vcf, filter_out.filtered_vcf_path
        )
        self._complete_stage(stage, tool_version=hc_out.tool_version)
        return _make_stage_output(
            "variant_calling", "completed", filter_out.model_dump(), hc_out.tool_version
        )
