"""Tests for SplicingAgent."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from src.agents.specialists.splicing_agent import SplicingAgent, SplicingStageInput
from src.db.enums import StageStatus
from src.db.models.results import SplicingResult
from src.db.models.run import PipelineStage
from src.tools.base import ToolExecutionError
from src.tools.splicing.rmats import RMATSOutput
from tests.agents.specialists.conftest import RUN_ID

_RMATS_OUT = RMATSOutput(
    output_dir="/out/splicing",
    event_types=["SE", "A5SS", "A3SS", "MXE", "RI"],
    significant_events_count={"SE": 2, "A5SS": 1, "A3SS": 0, "MXE": 0, "RI": 0},
    summary_path="/out/splicing/summary.txt",
    tool_version="rMATS 4.1.2",
)


def _base_input(**kwargs) -> SplicingStageInput:
    return SplicingStageInput(
        run_id=RUN_ID,
        bam_list_b1=["/out/align/ctrl_1.bam", "/out/align/ctrl_2.bam"],
        bam_list_b2=["/out/align/trt_1.bam", "/out/align/trt_2.bam"],
        gtf_path="/ref/genes.gtf",
        output_dir="/out/splicing",
        read_length=150,
        contrast="treatment_vs_control",
        **kwargs,
    )


@patch("src.agents.specialists.splicing_agent.run_rmats", return_value=_RMATS_OUT)
class TestSplicingAgentSuccess:
    def test_stage_status_completed(self, mock_rmats, db) -> None:
        SplicingAgent(db).run(_base_input())
        stage = db.query(PipelineStage).one()
        assert stage.status == StageStatus.completed

    def test_tool_version_not_null(self, mock_rmats, db) -> None:
        SplicingAgent(db).run(_base_input())
        stage = db.query(PipelineStage).one()
        assert stage.tool_version == "rMATS 4.1.2"

    def test_splicing_rows_inserted(self, mock_rmats, db) -> None:
        SplicingAgent(db).run(_base_input())
        rows = db.query(SplicingResult).all()
        assert len(rows) == 3  # 2 SE + 1 A5SS

    def test_splicing_contrast_label(self, mock_rmats, db) -> None:
        SplicingAgent(db).run(_base_input())
        rows = db.query(SplicingResult).all()
        assert all(r.contrast == "treatment_vs_control" for r in rows)

    def test_splicing_event_types_populated(self, mock_rmats, db) -> None:
        SplicingAgent(db).run(_base_input())
        event_types = {r.event_type.value for r in db.query(SplicingResult).all()}
        assert "SE" in event_types
        assert "A5SS" in event_types

    def test_zero_count_events_not_inserted(self, mock_rmats, db) -> None:
        SplicingAgent(db).run(_base_input())
        event_types = {r.event_type.value for r in db.query(SplicingResult).all()}
        assert "A3SS" not in event_types
        assert "MXE" not in event_types

    def test_artifact_written(self, mock_rmats, db) -> None:
        from src.db.models.run import Artifact
        SplicingAgent(db).run(_base_input())
        artifacts = db.query(Artifact).all()
        assert any("summary.txt" in a.path for a in artifacts)


@patch("src.agents.specialists.splicing_agent.run_rmats")
class TestSplicingAgentFailure:
    def test_tool_error_fails_stage(self, mock_rmats, db) -> None:
        mock_rmats.side_effect = ToolExecutionError("rmats", 1, "err", [])
        with pytest.raises(ToolExecutionError):
            SplicingAgent(db).run(_base_input())
        stage = db.query(PipelineStage).one()
        assert stage.status == StageStatus.failed

    def test_no_rows_on_failure(self, mock_rmats, db) -> None:
        mock_rmats.side_effect = ToolExecutionError("rmats", 1, "err", [])
        try:
            SplicingAgent(db).run(_base_input())
        except ToolExecutionError:
            pass
        assert db.query(SplicingResult).count() == 0
