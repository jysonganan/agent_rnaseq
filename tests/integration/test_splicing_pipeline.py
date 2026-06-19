"""Integration test: Alignment → Splicing analysis."""

from __future__ import annotations

from unittest.mock import patch

from src.agents.specialists.alignment_agent import AlignmentAgent
from src.agents.specialists.splicing_agent import SplicingAgent
from src.db.enums import StageStatus
from src.db.models.results import SplicingResult
from src.db.models.run import PipelineStage
from src.tools.alignment.samtools import SamtoolsOutput
from src.tools.alignment.star import STARAlignOutput
from src.tools.splicing.rmats import RMATSOutput
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


def _mock_rmats() -> RMATSOutput:
    return RMATSOutput(
        output_dir="/out/splicing",
        event_types=["SE", "A5SS", "A3SS", "MXE", "RI"],
        significant_events_count={"SE": 3, "A5SS": 1, "A3SS": 0, "MXE": 2, "RI": 0},
        summary_path="/out/splicing/summary.txt",
        tool_version="rMATS-turbo v4.1.2",
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


def _splicing_input() -> dict:
    return {
        "run_id": RUN_ID,
        "bam_list_b1": ["/out/align/treated_sorted.bam"],
        "bam_list_b2": ["/out/align/control_sorted.bam"],
        "gtf_path": "/ref/hg38.gtf",
        "output_dir": "/out/splicing",
        "read_length": 100,
        "contrast": "treated_vs_control",
    }


def test_splicing_stage_completes(db):
    with (
        patch("src.agents.specialists.alignment_agent.run_star_align", return_value=_mock_star()),
        patch(
            "src.agents.specialists.alignment_agent.run_samtools_sort_index",
            return_value=_mock_samtools(),
        ),
        patch("src.agents.specialists.splicing_agent.run_rmats", return_value=_mock_rmats()),
    ):
        AlignmentAgent(db).run(_align_input())
        SplicingAgent(db).run(_splicing_input())

    stages = db.query(PipelineStage).all()
    assert len(stages) == 2
    assert all(s.status == StageStatus.completed for s in stages)


def test_splicing_results_written_to_db(db):
    with (
        patch("src.agents.specialists.alignment_agent.run_star_align", return_value=_mock_star()),
        patch(
            "src.agents.specialists.alignment_agent.run_samtools_sort_index",
            return_value=_mock_samtools(),
        ),
        patch("src.agents.specialists.splicing_agent.run_rmats", return_value=_mock_rmats()),
    ):
        AlignmentAgent(db).run(_align_input())
        SplicingAgent(db).run(_splicing_input())

    results = db.query(SplicingResult).all()
    # SE: 3, A5SS: 1, MXE: 2 → 6 rows total
    assert len(results) == 6


def test_splicing_event_types_stored(db):
    with (
        patch("src.agents.specialists.alignment_agent.run_star_align", return_value=_mock_star()),
        patch(
            "src.agents.specialists.alignment_agent.run_samtools_sort_index",
            return_value=_mock_samtools(),
        ),
        patch("src.agents.specialists.splicing_agent.run_rmats", return_value=_mock_rmats()),
    ):
        AlignmentAgent(db).run(_align_input())
        SplicingAgent(db).run(_splicing_input())

    event_types = {str(r.event_type) for r in db.query(SplicingResult).all()}
    assert "SE" in event_types
    assert "A5SS" in event_types
    assert "MXE" in event_types


def test_splicing_contrast_stored(db):
    with (
        patch("src.agents.specialists.alignment_agent.run_star_align", return_value=_mock_star()),
        patch(
            "src.agents.specialists.alignment_agent.run_samtools_sort_index",
            return_value=_mock_samtools(),
        ),
        patch("src.agents.specialists.splicing_agent.run_rmats", return_value=_mock_rmats()),
    ):
        AlignmentAgent(db).run(_align_input())
        SplicingAgent(db).run(_splicing_input())

    assert all(r.contrast == "treated_vs_control" for r in db.query(SplicingResult).all())
