"""Tests for VariantAgent."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from src.agents.specialists.variant_agent import VariantAgent, VariantStageInput
from src.db.enums import ArtifactType, StageStatus
from src.db.models.run import Artifact, PipelineStage
from src.tools.base import ToolExecutionError
from src.tools.variant.gatk import GATKHaplotypeCallerOutput, GATKVariantFilterOutput
from tests.agents.specialists.conftest import RUN_ID, SAMPLE_ID

_HC_OUT = GATKHaplotypeCallerOutput(
    vcf_path="/out/variant/raw.vcf.gz",
    vcf_index_path="/out/variant/raw.vcf.gz.tbi",
    variant_count=1500,
    tool_version="GATK 4.4.0.0",
)

_FILTER_OUT = GATKVariantFilterOutput(
    filtered_vcf_path="/out/variant/filtered.vcf.gz",
    filtered_vcf_index_path="/out/variant/filtered.vcf.gz.tbi",
    pass_variant_count=1200,
    filtered_variant_count=300,
    tool_version=None,
)


def _base_input(**kwargs) -> VariantStageInput:
    return VariantStageInput(
        run_id=RUN_ID,
        sample_id=SAMPLE_ID,
        bam_path="/out/align/sample_sorted.bam",
        bam_index_path="/out/align/sample_sorted.bam.bai",
        reference_fasta="/ref/GRCh38.fa",
        output_dir="/out/variant",
        dbsnp_path=None,
        **kwargs,
    )


@patch("src.agents.specialists.variant_agent.run_gatk_variant_filter", return_value=_FILTER_OUT)
@patch("src.agents.specialists.variant_agent.run_gatk_haplotypecaller", return_value=_HC_OUT)
class TestVariantAgentSuccess:
    def test_stage_status_completed(self, mock_hc, mock_filter, db) -> None:
        VariantAgent(db).run(_base_input())
        stage = db.query(PipelineStage).one()
        assert stage.status == StageStatus.completed

    def test_tool_version_from_haplotypecaller(self, mock_hc, mock_filter, db) -> None:
        VariantAgent(db).run(_base_input())
        stage = db.query(PipelineStage).one()
        assert stage.tool_version == "GATK 4.4.0.0"

    def test_vcf_artifact_written(self, mock_hc, mock_filter, db) -> None:
        VariantAgent(db).run(_base_input())
        artifacts = db.query(Artifact).all()
        types = {a.artifact_type for a in artifacts}
        assert ArtifactType.vcf in types

    def test_filtered_vcf_path_in_artifact(self, mock_hc, mock_filter, db) -> None:
        VariantAgent(db).run(_base_input())
        artifacts = db.query(Artifact).all()
        assert any("filtered.vcf.gz" in a.path for a in artifacts)

    def test_return_stage_name(self, mock_hc, mock_filter, db) -> None:
        result = VariantAgent(db).run(_base_input())
        assert result["stage_name"] == "variant_calling"


@patch("src.agents.specialists.variant_agent.run_gatk_variant_filter", return_value=_FILTER_OUT)
@patch("src.agents.specialists.variant_agent.run_gatk_haplotypecaller")
class TestVariantAgentFailure:
    def test_hc_error_fails_stage(self, mock_hc, mock_filter, db) -> None:
        mock_hc.side_effect = ToolExecutionError("gatk", 1, "err", [])
        with pytest.raises(ToolExecutionError):
            VariantAgent(db).run(_base_input())
        stage = db.query(PipelineStage).one()
        assert stage.status == StageStatus.failed
