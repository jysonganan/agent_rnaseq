"""Tests for DEAgent."""

from __future__ import annotations

import contextlib
from unittest.mock import patch

import pytest

from src.agents.specialists.de_agent import DEAgent, DEStageInput
from src.db.enums import StageStatus
from src.db.models.results import DEGResult
from src.db.models.run import Artifact, PipelineStage
from src.tools.base import ToolExecutionError
from src.tools.de.deseq2 import DESeq2Output
from src.tools.de.parsers import DEContrastSummary
from tests.agents.specialists.conftest import RUN_ID

_DESEQ2_CSV = (
    "gene_id,baseMean,log2FoldChange,lfcSE,stat,pvalue,padj\n"
    "GENE1,500.0,2.3,0.4,5.75,1e-6,5e-5\n"
    "GENE2,200.0,-1.5,0.3,-5.0,5e-6,2e-4\n"
    "GENE3,100.0,0.1,0.5,0.2,0.8,NA\n"
)

_DESEQ2_OUT = DESeq2Output(
    results_paths={"treatment_vs_control": "/out/de/treatment_vs_control.csv"},
    normalized_counts_path="/out/de/normalized_counts.csv",
    size_factors_path="/out/de/size_factors.csv",
    dispersion_plot_path="/out/de/dispersion_plot.pdf",
    pca_plot_path="/out/de/pca_plot.pdf",
    contrast_summaries={
        "treatment_vs_control": DEContrastSummary(
            total_genes=3, upregulated=1, downregulated=1, not_significant=1
        )
    },
    tool_version="DESeq2 1.40.0",
)


def _base_input(**kwargs) -> DEStageInput:
    return DEStageInput(
        run_id=RUN_ID,
        counts_matrix_path="/data/counts.csv",
        sample_metadata_path="/data/metadata.csv",
        contrasts=[
            {"name": "treatment_vs_control", "numerator": "treatment", "denominator": "control"}
        ],
        output_dir="/out/de",
        alpha=0.05,
        lfc_threshold=0.0,
        r_script_path="/src/r/deseq2_analysis.R",
        **kwargs,
    )


@patch("src.agents.specialists.de_agent._read_deseq2_file", return_value=_DESEQ2_CSV)
@patch("src.agents.specialists.de_agent.run_deseq2", return_value=_DESEQ2_OUT)
class TestDEAgentSuccess:
    def test_stage_status_completed(self, mock_deseq2, mock_read, db) -> None:
        DEAgent(db).run(_base_input())
        stage = db.query(PipelineStage).one()
        assert stage.status == StageStatus.completed

    def test_tool_version_not_null(self, mock_deseq2, mock_read, db) -> None:
        DEAgent(db).run(_base_input())
        stage = db.query(PipelineStage).one()
        assert stage.tool_version == "DESeq2 1.40.0"

    def test_deg_rows_inserted(self, mock_deseq2, mock_read, db) -> None:
        DEAgent(db).run(_base_input())
        rows = db.query(DEGResult).all()
        assert len(rows) == 3

    def test_deg_contrast_label(self, mock_deseq2, mock_read, db) -> None:
        DEAgent(db).run(_base_input())
        rows = db.query(DEGResult).all()
        assert all(r.contrast == "treatment_vs_control" for r in rows)

    def test_deg_gene_ids_correct(self, mock_deseq2, mock_read, db) -> None:
        DEAgent(db).run(_base_input())
        gene_ids = {r.gene_id for r in db.query(DEGResult).all()}
        assert gene_ids == {"GENE1", "GENE2", "GENE3"}

    def test_deg_values_from_tool_not_llm(self, mock_deseq2, mock_read, db) -> None:
        DEAgent(db).run(_base_input())
        rows = {r.gene_id: r for r in db.query(DEGResult).all()}
        assert rows["GENE1"].log2_fold_change == pytest.approx(2.3)
        assert rows["GENE2"].padj == pytest.approx(2e-4)
        assert rows["GENE3"].padj is None

    def test_de_artifact_written(self, mock_deseq2, mock_read, db) -> None:
        DEAgent(db).run(_base_input())
        artifacts = db.query(Artifact).all()
        assert any("treatment_vs_control.csv" in a.path for a in artifacts)

    def test_stage_name_is_de(self, mock_deseq2, mock_read, db) -> None:
        DEAgent(db).run(_base_input())
        stage = db.query(PipelineStage).one()
        assert stage.stage_name.value == "differential_expression"


@patch("src.agents.specialists.de_agent._read_deseq2_file", return_value=_DESEQ2_CSV)
@patch("src.agents.specialists.de_agent.run_deseq2")
class TestDEAgentFailure:
    def test_tool_error_fails_stage(self, mock_deseq2, mock_read, db) -> None:
        mock_deseq2.side_effect = ToolExecutionError("deseq2", 1, "R error", [])
        with pytest.raises(ToolExecutionError):
            DEAgent(db).run(_base_input())
        stage = db.query(PipelineStage).one()
        assert stage.status == StageStatus.failed

    def test_no_deg_rows_on_failure(self, mock_deseq2, mock_read, db) -> None:
        mock_deseq2.side_effect = ToolExecutionError("deseq2", 1, "R error", [])
        with contextlib.suppress(ToolExecutionError):
            DEAgent(db).run(_base_input())
        assert db.query(DEGResult).count() == 0
