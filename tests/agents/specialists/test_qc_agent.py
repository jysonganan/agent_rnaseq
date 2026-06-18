"""Tests for QCAgent."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from src.agents.specialists.qc_agent import QCAgent, QCStageInput
from src.db.enums import StageStatus
from src.db.models.results import QCMetric
from src.db.models.run import PipelineStage
from src.tools.base import ToolExecutionError
from src.tools.qc.fastqc import FastQCOutput
from src.tools.qc.multiqc import MultiQCOutput
from tests.agents.specialists.conftest import RUN_ID, SAMPLE_ID


def _mock_fastqc_out(tool_version: str = "FastQC v0.12.1") -> FastQCOutput:
    return FastQCOutput(
        report_html_paths=["/out/qc/sample_fastqc.html"],
        report_zip_paths=["/out/qc/sample_fastqc.zip"],
        summary={"Basic Statistics": "PASS", "Per base sequence quality": "WARN"},
        tool_version=tool_version,
    )


def _mock_multiqc_out() -> MultiQCOutput:
    return MultiQCOutput(
        report_html_path="/out/qc/multiqc_report.html",
        data_dir="/out/qc/multiqc_data",
        parsed_metrics={},
        tool_version=None,
    )


def _base_input(**kwargs) -> QCStageInput:
    return QCStageInput(
        run_id=RUN_ID,
        sample_id=SAMPLE_ID,
        fastq_paths=["/data/sample_R1.fastq.gz"],
        output_dir="/out/qc",
        bam_path=None,
        bam_index_path=None,
        bed_annotation_path=None,
        **kwargs,
    )


@patch("src.agents.specialists.qc_agent.run_multiqc")
@patch("src.agents.specialists.qc_agent.run_fastqc")
class TestQCAgentSuccess:
    def test_stage_status_completed(self, mock_fastqc, mock_multiqc, db) -> None:
        mock_fastqc.return_value = _mock_fastqc_out()
        mock_multiqc.return_value = _mock_multiqc_out()
        QCAgent(db).run(_base_input())
        stage = db.query(PipelineStage).one()
        assert stage.status == StageStatus.completed

    def test_tool_version_not_null(self, mock_fastqc, mock_multiqc, db) -> None:
        mock_fastqc.return_value = _mock_fastqc_out("FastQC v0.12.1")
        mock_multiqc.return_value = _mock_multiqc_out()
        QCAgent(db).run(_base_input())
        stage = db.query(PipelineStage).one()
        assert stage.tool_version == "FastQC v0.12.1"

    def test_qc_metric_rows_created(self, mock_fastqc, mock_multiqc, db) -> None:
        mock_fastqc.return_value = _mock_fastqc_out()
        mock_multiqc.return_value = _mock_multiqc_out()
        QCAgent(db).run(_base_input())
        metrics = db.query(QCMetric).all()
        assert len(metrics) == 2  # two modules in summary

    def test_qc_metric_module_names(self, mock_fastqc, mock_multiqc, db) -> None:
        mock_fastqc.return_value = _mock_fastqc_out()
        mock_multiqc.return_value = _mock_multiqc_out()
        QCAgent(db).run(_base_input())
        names = {m.metric_name for m in db.query(QCMetric).all()}
        assert "Basic Statistics" in names
        assert "Per base sequence quality" in names

    def test_qc_metric_pass_fail_values(self, mock_fastqc, mock_multiqc, db) -> None:
        mock_fastqc.return_value = _mock_fastqc_out()
        mock_multiqc.return_value = _mock_multiqc_out()
        QCAgent(db).run(_base_input())
        by_name = {m.metric_name: m for m in db.query(QCMetric).all()}
        assert by_name["Basic Statistics"].pass_fail.value == "pass"
        assert by_name["Per base sequence quality"].pass_fail.value == "warn"

    def test_artifact_written(self, mock_fastqc, mock_multiqc, db) -> None:
        mock_fastqc.return_value = _mock_fastqc_out()
        mock_multiqc.return_value = _mock_multiqc_out()
        from src.db.models.run import Artifact
        QCAgent(db).run(_base_input())
        artifacts = db.query(Artifact).all()
        assert len(artifacts) >= 1
        assert any("sample_fastqc.html" in a.path for a in artifacts)

    def test_stage_name_is_qc(self, mock_fastqc, mock_multiqc, db) -> None:
        mock_fastqc.return_value = _mock_fastqc_out()
        mock_multiqc.return_value = _mock_multiqc_out()
        QCAgent(db).run(_base_input())
        stage = db.query(PipelineStage).one()
        assert stage.stage_name.value == "qc"

    def test_return_value_stage_name(self, mock_fastqc, mock_multiqc, db) -> None:
        mock_fastqc.return_value = _mock_fastqc_out()
        mock_multiqc.return_value = _mock_multiqc_out()
        result = QCAgent(db).run(_base_input())
        assert result["stage_name"] == "qc"
        assert result["status"] == "completed"


@patch("src.agents.specialists.qc_agent.run_multiqc")
@patch("src.agents.specialists.qc_agent.run_fastqc")
class TestQCAgentFailure:
    def test_tool_error_sets_stage_failed(self, mock_fastqc, mock_multiqc, db) -> None:
        mock_fastqc.side_effect = ToolExecutionError("fastqc", 1, "no such file", [])
        with pytest.raises(ToolExecutionError):
            QCAgent(db).run(_base_input())
        stage = db.query(PipelineStage).one()
        assert stage.status == StageStatus.failed

    def test_tool_error_propagates(self, mock_fastqc, mock_multiqc, db) -> None:
        mock_fastqc.side_effect = ToolExecutionError("fastqc", 1, "err", [])
        with pytest.raises(ToolExecutionError):
            QCAgent(db).run(_base_input())

    def test_no_metrics_on_failure(self, mock_fastqc, mock_multiqc, db) -> None:
        mock_fastqc.side_effect = ToolExecutionError("fastqc", 1, "err", [])
        try:
            QCAgent(db).run(_base_input())
        except ToolExecutionError:
            pass
        assert db.query(QCMetric).count() == 0
