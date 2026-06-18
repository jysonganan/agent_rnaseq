"""Tests for ReportAgent."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from src.agents.specialists.report_agent import ReportAgent, ReportStageInput
from src.db.enums import ArtifactType, StageStatus
from src.db.models.run import Artifact, PipelineStage
from src.tools.base import ToolExecutionError
from src.tools.report.compile import ReportOutput
from tests.agents.specialists.conftest import RUN_ID

_REPORT_OUT = ReportOutput(
    html_report_path="/out/report/report.html",
    markdown_report_path="/out/report/report.md",
    tool_version="report_compiler 1.0.0",
)


def _base_input(**kwargs) -> ReportStageInput:
    return ReportStageInput(
        run_id=RUN_ID,
        run_name="my_analysis",
        qc_summary={"total_reads": 1_000_000},
        de_summary={"upregulated": 42},
        gsea_summary={"significant_pathways": 5},
        artifact_paths={"bam": "/out/align/sample.bam"},
        output_dir="/out/report",
        template_path="/src/templates/report.html.j2",
        **kwargs,
    )


@patch("src.agents.specialists.report_agent.compile_report", return_value=_REPORT_OUT)
class TestReportAgentSuccess:
    def test_stage_status_completed(self, mock_compile, db) -> None:
        ReportAgent(db).run(_base_input())
        stage = db.query(PipelineStage).one()
        assert stage.status == StageStatus.completed

    def test_tool_version_not_null(self, mock_compile, db) -> None:
        ReportAgent(db).run(_base_input())
        stage = db.query(PipelineStage).one()
        assert stage.tool_version == "report_compiler 1.0.0"

    def test_html_artifact_written(self, mock_compile, db) -> None:
        ReportAgent(db).run(_base_input())
        artifacts = db.query(Artifact).all()
        types = {a.artifact_type for a in artifacts}
        assert ArtifactType.html_report in types

    def test_html_path_in_artifact(self, mock_compile, db) -> None:
        ReportAgent(db).run(_base_input())
        artifacts = db.query(Artifact).all()
        assert any("report.html" in a.path for a in artifacts)

    def test_run_name_passed_to_tool(self, mock_compile, db) -> None:
        ReportAgent(db).run(_base_input())
        called_inp = mock_compile.call_args[0][0]
        assert called_inp.run_name == "my_analysis"

    def test_return_stage_name(self, mock_compile, db) -> None:
        result = ReportAgent(db).run(_base_input())
        assert result["stage_name"] == "report"
        assert result["status"] == "completed"


@patch("src.agents.specialists.report_agent.compile_report")
class TestReportAgentFailure:
    def test_tool_error_fails_stage(self, mock_compile, db) -> None:
        mock_compile.side_effect = ToolExecutionError("report_compiler", 1, "err", [])
        with pytest.raises(ToolExecutionError):
            ReportAgent(db).run(_base_input())
        stage = db.query(PipelineStage).one()
        assert stage.status == StageStatus.failed
