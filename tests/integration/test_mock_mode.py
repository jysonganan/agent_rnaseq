"""Integration test: dry_run=True mode — no tool calls, no DB writes."""

from __future__ import annotations

from unittest.mock import patch

from src.agents.base_agent import MockToolRegistry
from src.agents.specialists.alignment_agent import AlignmentAgent
from src.agents.specialists.de_agent import DEAgent
from src.agents.specialists.qc_agent import QCAgent
from src.agents.state import RunState
from src.db.models.run import PipelineStage
from tests.integration.conftest import FIXTURES_DIR, RUN_ID, SAMPLE_ID


def _make_run_state(stage_name: str, run_config: dict) -> RunState:
    return RunState(
        run_id=RUN_ID,
        run_config=run_config,
        stages=[stage_name],
        completed_stages=[],
        failed_stage=None,
        stage_outputs={},
        error_message=None,
        current_stage=stage_name,
    )


def _qc_config() -> dict:
    return {
        "run_id": RUN_ID,
        "sample_id": SAMPLE_ID,
        "fastq_paths": [str(FIXTURES_DIR / "synthetic_R1.fastq.gz")],
        "output_dir": "/out/qc",
        "bam_path": None,
        "bam_index_path": None,
        "bed_annotation_path": None,
    }


def _align_config() -> dict:
    return {
        "run_id": RUN_ID,
        "sample_id": SAMPLE_ID,
        "fastq_r1": str(FIXTURES_DIR / "synthetic_R1.fastq.gz"),
        "fastq_r2": None,
        "genome_dir": "/ref/genome",
        "output_prefix": "/out/align/sample",
        "threads": 4,
    }


def _de_config() -> dict:
    return {
        "run_id": RUN_ID,
        "counts_matrix_path": "/out/quant/counts.tsv",
        "sample_metadata_path": "/out/metadata.csv",
        "contrasts": [{"name": "trt_vs_ctrl", "numerator": "trt", "denominator": "ctrl"}],
        "output_dir": "/out/de",
        "alpha": 0.05,
        "lfc_threshold": 0.0,
        "r_script_path": "/scripts/deseq2.R",
    }


def test_dry_run_qc_does_not_call_fastqc(db):
    with patch("src.agents.specialists.qc_agent.run_fastqc") as mock_fastqc:
        registry = MockToolRegistry()
        registry.register("qc", {"stage": "qc", "mock": True})
        agent = QCAgent(db, dry_run=True, mock_registry=registry)
        state = _make_run_state("qc", _qc_config())
        agent.execute(state)
        mock_fastqc.assert_not_called()


def test_dry_run_qc_writes_no_db_rows(db):
    with patch("src.agents.specialists.qc_agent.run_fastqc"):
        registry = MockToolRegistry()
        registry.register("qc", {"stage": "qc", "mock": True})
        agent = QCAgent(db, dry_run=True, mock_registry=registry)
        state = _make_run_state("qc", _qc_config())
        agent.execute(state)

    assert db.query(PipelineStage).count() == 0


def test_dry_run_qc_returns_completed_status(db):
    registry = MockToolRegistry()
    registry.register("qc", {"stage": "qc", "mock": True})
    agent = QCAgent(db, dry_run=True, mock_registry=registry)
    state = _make_run_state("qc", _qc_config())
    result = agent.execute(state)
    assert result["status"] == "completed"


def test_dry_run_returns_mock_registry_output(db):
    registry = MockToolRegistry()
    registry.register("qc", {"stage": "qc", "mock": True, "custom_key": "custom_value"})
    agent = QCAgent(db, dry_run=True, mock_registry=registry)
    state = _make_run_state("qc", _qc_config())
    result = agent.execute(state)
    assert result["output"]["custom_key"] == "custom_value"


def test_dry_run_alignment_does_not_call_star(db):
    with patch("src.agents.specialists.alignment_agent.run_star_align") as mock_star:
        registry = MockToolRegistry()
        registry.register("alignment", {"stage": "alignment", "mock": True})
        agent = AlignmentAgent(db, dry_run=True, mock_registry=registry)
        state = _make_run_state("alignment", _align_config())
        agent.execute(state)
        mock_star.assert_not_called()


def test_dry_run_alignment_writes_no_db_rows(db):
    registry = MockToolRegistry()
    registry.register("alignment", {})
    agent = AlignmentAgent(db, dry_run=True, mock_registry=registry)
    state = _make_run_state("alignment", _align_config())
    agent.execute(state)
    assert db.query(PipelineStage).count() == 0


def test_non_dry_run_calls_tool(db):
    """Verify that dry_run=False actually calls the mocked tool."""
    from src.tools.alignment.samtools import SamtoolsOutput
    from src.tools.alignment.star import STARAlignOutput

    mock_star = STARAlignOutput(
        bam_path="/out/align/sample.bam",
        bam_index_path="/out/align/sample.bam.bai",
        log_final_path="/out/align/Log.final.out",
        splice_junctions_path="/out/align/SJ.out.tab",
        alignment_stats={},
        tool_version="STAR 2.7.10a",
    )
    mock_samtools = SamtoolsOutput(
        sorted_bam_path="/out/align/sorted.bam",
        bai_path="/out/align/sorted.bam.bai",
        flagstat={},
        tool_version="samtools 1.17",
    )

    with (
        patch(
            "src.agents.specialists.alignment_agent.run_star_align", return_value=mock_star
        ) as mock_s,
        patch(
            "src.agents.specialists.alignment_agent.run_samtools_sort_index",
            return_value=mock_samtools,
        ),
    ):
        agent = AlignmentAgent(db, dry_run=False)
        state = _make_run_state("alignment", _align_config())
        agent.execute(state)
        mock_s.assert_called_once()


def test_dry_run_de_does_not_call_deseq2(db):
    with patch("src.agents.specialists.de_agent.run_deseq2") as mock_de:
        registry = MockToolRegistry()
        registry.register("differential_expression", {"stage": "de", "mock": True})
        agent = DEAgent(db, dry_run=True, mock_registry=registry)
        state = _make_run_state("differential_expression", _de_config())
        agent.execute(state)
        mock_de.assert_not_called()
