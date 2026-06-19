"""Integration test: Alignment → Variant Calling (GATK)."""

from __future__ import annotations

from unittest.mock import patch

from src.agents.specialists.alignment_agent import AlignmentAgent
from src.agents.specialists.variant_agent import VariantAgent
from src.db.enums import ArtifactType, StageStatus
from src.db.models.run import Artifact, PipelineStage
from src.tools.alignment.samtools import SamtoolsOutput
from src.tools.alignment.star import STARAlignOutput
from src.tools.variant.gatk import GATKHaplotypeCallerOutput, GATKVariantFilterOutput

from tests.integration.conftest import FIXTURES_DIR, RUN_ID, SAMPLE_ID


def _mock_star() -> STARAlignOutput:
    return STARAlignOutput(
        bam_path="/out/align/sample.bam",
        bam_index_path="/out/align/sample.bam.bai",
        log_final_path="/out/align/Log.final.out",
        splice_junctions_path="/out/align/SJ.out.tab",
        gene_counts_path=None,
        alignment_stats={},
        tool_version="STAR 2.7.10a",
    )


def _mock_samtools() -> SamtoolsOutput:
    return SamtoolsOutput(
        sorted_bam_path="/out/align/sample_sorted.bam",
        bai_path="/out/align/sample_sorted.bam.bai",
        flagstat={},
        tool_version="samtools 1.17",
    )


def _mock_gatk_hc() -> GATKHaplotypeCallerOutput:
    return GATKHaplotypeCallerOutput(
        vcf_path="/out/variant/raw.vcf.gz",
        vcf_index_path="/out/variant/raw.vcf.gz.tbi",
        variant_count=150,
        tool_version="GATK 4.4.0.0",
    )


def _mock_gatk_filter() -> GATKVariantFilterOutput:
    return GATKVariantFilterOutput(
        filtered_vcf_path="/out/variant/filtered.vcf.gz",
        filtered_vcf_index_path="/out/variant/filtered.vcf.gz.tbi",
        pass_variant_count=120,
        filtered_variant_count=30,
        tool_version="GATK 4.4.0.0",
    )


def _align_input() -> dict:
    return {
        "run_id": RUN_ID,
        "sample_id": SAMPLE_ID,
        "fastq_r1": str(FIXTURES_DIR / "synthetic_R1.fastq.gz"),
        "fastq_r2": str(FIXTURES_DIR / "synthetic_R2.fastq.gz"),
        "genome_dir": "/ref/genome",
        "output_prefix": "/out/align/sample",
        "threads": 4,
    }


def _variant_input() -> dict:
    return {
        "run_id": RUN_ID,
        "sample_id": SAMPLE_ID,
        "bam_path": "/out/align/sample_sorted.bam",
        "bam_index_path": "/out/align/sample_sorted.bam.bai",
        "reference_fasta": "/ref/hg38.fa",
        "output_dir": "/out/variant",
        "dbsnp_path": None,
    }


def test_variant_stage_completes(db):
    with (
        patch("src.agents.specialists.alignment_agent.run_star_align", return_value=_mock_star()),
        patch("src.agents.specialists.alignment_agent.run_samtools_sort_index", return_value=_mock_samtools()),
        patch("src.agents.specialists.variant_agent.run_gatk_haplotypecaller", return_value=_mock_gatk_hc()),
        patch("src.agents.specialists.variant_agent.run_gatk_variant_filter", return_value=_mock_gatk_filter()),
    ):
        AlignmentAgent(db).run(_align_input())
        VariantAgent(db).run(_variant_input())

    stages = db.query(PipelineStage).all()
    assert len(stages) == 2
    assert all(s.status == StageStatus.completed for s in stages)


def test_vcf_artifact_written(db):
    with (
        patch("src.agents.specialists.alignment_agent.run_star_align", return_value=_mock_star()),
        patch("src.agents.specialists.alignment_agent.run_samtools_sort_index", return_value=_mock_samtools()),
        patch("src.agents.specialists.variant_agent.run_gatk_haplotypecaller", return_value=_mock_gatk_hc()),
        patch("src.agents.specialists.variant_agent.run_gatk_variant_filter", return_value=_mock_gatk_filter()),
    ):
        AlignmentAgent(db).run(_align_input())
        VariantAgent(db).run(_variant_input())

    vcf_artifacts = [
        a for a in db.query(Artifact).all()
        if a.artifact_type == ArtifactType.vcf
    ]
    assert len(vcf_artifacts) == 1
    assert vcf_artifacts[0].path == "/out/variant/filtered.vcf.gz"


def test_variant_tool_version_recorded(db):
    with (
        patch("src.agents.specialists.alignment_agent.run_star_align", return_value=_mock_star()),
        patch("src.agents.specialists.alignment_agent.run_samtools_sort_index", return_value=_mock_samtools()),
        patch("src.agents.specialists.variant_agent.run_gatk_haplotypecaller", return_value=_mock_gatk_hc()),
        patch("src.agents.specialists.variant_agent.run_gatk_variant_filter", return_value=_mock_gatk_filter()),
    ):
        AlignmentAgent(db).run(_align_input())
        VariantAgent(db).run(_variant_input())

    variant_stage = next(
        s for s in db.query(PipelineStage).all()
        if str(s.stage_name) == "variant_calling"
    )
    assert variant_stage.tool_version == "GATK 4.4.0.0"
