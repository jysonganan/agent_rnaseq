"""Tests for AlignmentAgent."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from src.agents.specialists.alignment_agent import AlignmentAgent, AlignmentStageInput
from src.db.enums import ArtifactType, StageStatus
from src.db.models.run import Artifact, PipelineStage
from src.tools.alignment.samtools import SamtoolsOutput
from src.tools.alignment.star import STARAlignOutput
from src.tools.base import ToolExecutionError
from tests.agents.specialists.conftest import RUN_ID, SAMPLE_ID


def _mock_star_out(tool_version: str = "STAR 2.7.11a") -> STARAlignOutput:
    return STARAlignOutput(
        bam_path="/out/align/Aligned.sortedByCoord.out.bam",
        bam_index_path="/out/align/Aligned.sortedByCoord.out.bam.bai",
        log_final_path="/out/align/Log.final.out",
        splice_junctions_path="/out/align/SJ.out.tab",
        gene_counts_path="/out/align/ReadsPerGene.out.tab",
        transcriptome_bam_path=None,
        alignment_stats={},
        tool_version=tool_version,
    )


def _mock_samtools_out() -> SamtoolsOutput:
    return SamtoolsOutput(
        sorted_bam_path="/out/align/sample_sorted.bam",
        bai_path="/out/align/sample_sorted.bam.bai",
        flagstat={},
        tool_version=None,
    )


def _base_input(**kwargs) -> AlignmentStageInput:
    return AlignmentStageInput(
        run_id=RUN_ID,
        sample_id=SAMPLE_ID,
        fastq_r1="/data/sample_R1.fastq.gz",
        fastq_r2="/data/sample_R2.fastq.gz",
        genome_dir="/ref/star_index",
        output_prefix="/out/align/sample",
        threads=8,
        **kwargs,
    )


@patch("src.agents.specialists.alignment_agent.run_samtools_sort_index")
@patch("src.agents.specialists.alignment_agent.run_star_align")
class TestAlignmentAgentSuccess:
    def test_stage_status_completed(self, mock_star, mock_samtools, db) -> None:
        mock_star.return_value = _mock_star_out()
        mock_samtools.return_value = _mock_samtools_out()
        AlignmentAgent(db).run(_base_input())
        stage = db.query(PipelineStage).one()
        assert stage.status == StageStatus.completed

    def test_tool_version_not_null(self, mock_star, mock_samtools, db) -> None:
        mock_star.return_value = _mock_star_out("STAR 2.7.11a")
        mock_samtools.return_value = _mock_samtools_out()
        AlignmentAgent(db).run(_base_input())
        stage = db.query(PipelineStage).one()
        assert stage.tool_version == "STAR 2.7.11a"

    def test_bam_artifact_written(self, mock_star, mock_samtools, db) -> None:
        mock_star.return_value = _mock_star_out()
        mock_samtools.return_value = _mock_samtools_out()
        AlignmentAgent(db).run(_base_input())
        artifacts = db.query(Artifact).all()
        types = {a.artifact_type for a in artifacts}
        assert ArtifactType.bam in types

    def test_bai_artifact_written(self, mock_star, mock_samtools, db) -> None:
        mock_star.return_value = _mock_star_out()
        mock_samtools.return_value = _mock_samtools_out()
        AlignmentAgent(db).run(_base_input())
        artifacts = db.query(Artifact).all()
        types = {a.artifact_type for a in artifacts}
        assert ArtifactType.bai in types

    def test_return_stage_name(self, mock_star, mock_samtools, db) -> None:
        mock_star.return_value = _mock_star_out()
        mock_samtools.return_value = _mock_samtools_out()
        result = AlignmentAgent(db).run(_base_input())
        assert result["stage_name"] == "alignment"
        assert result["status"] == "completed"

    def test_star_called_with_genome_dir(self, mock_star, mock_samtools, db) -> None:
        mock_star.return_value = _mock_star_out()
        mock_samtools.return_value = _mock_samtools_out()
        AlignmentAgent(db).run(_base_input())
        called_inp = mock_star.call_args[0][0]
        assert called_inp.genome_dir == "/ref/star_index"


@patch("src.agents.specialists.alignment_agent.run_samtools_sort_index")
@patch("src.agents.specialists.alignment_agent.run_star_align")
class TestAlignmentAgentFailure:
    def test_star_error_fails_stage(self, mock_star, mock_samtools, db) -> None:
        mock_star.side_effect = ToolExecutionError("star", 1, "index not found", [])
        with pytest.raises(ToolExecutionError):
            AlignmentAgent(db).run(_base_input())
        stage = db.query(PipelineStage).one()
        assert stage.status == StageStatus.failed

    def test_samtools_error_fails_stage(self, mock_star, mock_samtools, db) -> None:
        mock_star.return_value = _mock_star_out()
        mock_samtools.side_effect = ToolExecutionError("samtools", 1, "err", [])
        with pytest.raises(ToolExecutionError):
            AlignmentAgent(db).run(_base_input())
        stage = db.query(PipelineStage).one()
        assert stage.status == StageStatus.failed
