"""Tests for GSEAAgent."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from src.agents.specialists.gsea_agent import GSEAAgent, GSEAStageInput
from src.db.enums import StageStatus
from src.db.models.results import GSEAResult
from src.db.models.run import Artifact, PipelineStage
from src.tools.base import ToolExecutionError
from src.tools.gsea.reactome import ReactomeGSEAOutput
from tests.agents.specialists.conftest import RUN_ID

_GSEA_CSV = (
    "pathway_id,pathway_name,NES,pvalue,padj\n"
    "R-HSA-1234,Immune signalling,2.1,0.002,0.01\n"
    "R-HSA-5678,Cell cycle,1.8,0.005,0.03\n"
    "R-HSA-9012,Apoptosis,-1.5,0.1,0.4\n"
)

_GSEA_OUT = ReactomeGSEAOutput(
    results_path="/out/gsea/treatment_vs_control/gsea_results.csv",
    enrichment_plots_dir="/out/gsea/treatment_vs_control/plots",
    significant_pathway_count=2,
    tool_version="fgsea 1.24.0",
)


def _base_input(**kwargs) -> GSEAStageInput:
    return GSEAStageInput(
        run_id=RUN_ID,
        de_results_paths={"treatment_vs_control": "/out/de/treatment_vs_control.csv"},
        output_dir="/out/gsea",
        organism="human",
        r_script_path="/src/r/reactome_gsea.R",
        **kwargs,
    )


@patch("src.agents.specialists.gsea_agent._read_gsea_file", return_value=_GSEA_CSV)
@patch("src.agents.specialists.gsea_agent.run_reactome_gsea", return_value=_GSEA_OUT)
class TestGSEAAgentSuccess:
    def test_stage_status_completed(self, mock_gsea, mock_read, db) -> None:
        GSEAAgent(db).run(_base_input())
        stage = db.query(PipelineStage).one()
        assert stage.status == StageStatus.completed

    def test_tool_version_not_null(self, mock_gsea, mock_read, db) -> None:
        GSEAAgent(db).run(_base_input())
        stage = db.query(PipelineStage).one()
        assert stage.tool_version == "fgsea 1.24.0"

    def test_gsea_rows_inserted(self, mock_gsea, mock_read, db) -> None:
        GSEAAgent(db).run(_base_input())
        rows = db.query(GSEAResult).all()
        assert len(rows) == 3

    def test_gsea_contrast_label(self, mock_gsea, mock_read, db) -> None:
        GSEAAgent(db).run(_base_input())
        rows = db.query(GSEAResult).all()
        assert all(r.contrast == "treatment_vs_control" for r in rows)

    def test_gsea_pathway_ids(self, mock_gsea, mock_read, db) -> None:
        GSEAAgent(db).run(_base_input())
        pathway_ids = {r.pathway_id for r in db.query(GSEAResult).all()}
        assert pathway_ids == {"R-HSA-1234", "R-HSA-5678", "R-HSA-9012"}

    def test_gsea_values_from_tool_not_llm(self, mock_gsea, mock_read, db) -> None:
        GSEAAgent(db).run(_base_input())
        rows = {r.pathway_id: r for r in db.query(GSEAResult).all()}
        assert rows["R-HSA-1234"].nes == pytest.approx(2.1)
        assert rows["R-HSA-1234"].padj == pytest.approx(0.01)

    def test_gsea_artifact_written(self, mock_gsea, mock_read, db) -> None:
        GSEAAgent(db).run(_base_input())
        artifacts = db.query(Artifact).all()
        assert any("gsea_results.csv" in a.path for a in artifacts)

    def test_multiple_contrasts_all_rows_inserted(self, mock_gsea, mock_read, db) -> None:
        inp = _base_input()
        inp["de_results_paths"] = {
            "trt_vs_ctrl": "/out/de/trt_vs_ctrl.csv",
            "dose_vs_ctrl": "/out/de/dose_vs_ctrl.csv",
        }
        GSEAAgent(db).run(inp)
        rows = db.query(GSEAResult).all()
        assert len(rows) == 6  # 3 pathways × 2 contrasts


@patch("src.agents.specialists.gsea_agent._read_gsea_file", return_value=_GSEA_CSV)
@patch("src.agents.specialists.gsea_agent.run_reactome_gsea")
class TestGSEAAgentFailure:
    def test_tool_error_fails_stage(self, mock_gsea, mock_read, db) -> None:
        mock_gsea.side_effect = ToolExecutionError("reactome_gsea", 1, "R error", [])
        with pytest.raises(ToolExecutionError):
            GSEAAgent(db).run(_base_input())
        stage = db.query(PipelineStage).one()
        assert stage.status == StageStatus.failed

    def test_no_gsea_rows_on_failure(self, mock_gsea, mock_read, db) -> None:
        mock_gsea.side_effect = ToolExecutionError("reactome_gsea", 1, "R error", [])
        try:
            GSEAAgent(db).run(_base_input())
        except ToolExecutionError:
            pass
        assert db.query(GSEAResult).count() == 0
