"""Tests for scRNAAgent."""

from __future__ import annotations

import contextlib
from unittest.mock import patch

import pytest

from src.agents.specialists.scrna_agent import ScRNAStageInput, scRNAAgent
from src.db.enums import ArtifactType, StageStatus
from src.db.models.results import ScRNAClusterResult
from src.db.models.run import Artifact, PipelineStage
from src.tools.base import ToolExecutionError
from src.tools.scrna.cellranger import CellRangerCountOutput
from src.tools.scrna.scanpy_tool import ClusterSummary, ScanpyOutput
from tests.agents.specialists.conftest import RUN_ID, SAMPLE_ID

_CR_OUT = CellRangerCountOutput(
    output_dir="/out/scrna/pbmc3k",
    filtered_matrix_dir="/out/scrna/pbmc3k/outs/filtered_feature_bc_matrix",
    molecule_info_path="/out/scrna/pbmc3k/outs/molecule_info.h5",
    summary_html_path="/out/scrna/pbmc3k/outs/web_summary.html",
    summary_stats={"estimated_cells": 2700, "median_genes_per_cell": 847},
    tool_version="cellranger 7.1.0",
)

_SCANPY_OUT = ScanpyOutput(
    h5ad_path="/out/scrna/scanpy/cells.h5ad",
    umap_plot_path="/out/scrna/scanpy/umap.pdf",
    marker_genes_path="/out/scrna/scanpy/marker_genes.csv",
    cluster_summary=ClusterSummary(
        n_clusters=4,
        cells_per_cluster={"0": 700, "1": 800, "2": 600, "3": 600},
    ),
    tool_version="scanpy 1.9.3",
)


def _base_input(**kwargs) -> ScRNAStageInput:
    return ScRNAStageInput(
        run_id=RUN_ID,
        sample_id=SAMPLE_ID,
        fastq_dirs=["/data/pbmc3k"],
        sample_name="pbmc3k",
        transcriptome_path="/ref/refdata-gex-GRCh38",
        output_dir="/out/scrna",
        script_path="/src/scripts/scanpy_pipeline.py",
        **kwargs,
    )


@patch("src.agents.specialists.scrna_agent.run_scanpy_pipeline", return_value=_SCANPY_OUT)
@patch("src.agents.specialists.scrna_agent.run_cellranger_count", return_value=_CR_OUT)
class TestScRNAAgentSuccess:
    def test_stage_status_completed(self, mock_cr, mock_scanpy, db) -> None:
        scRNAAgent(db).run(_base_input())
        stage = db.query(PipelineStage).one()
        assert stage.status == StageStatus.completed

    def test_tool_version_from_cellranger(self, mock_cr, mock_scanpy, db) -> None:
        scRNAAgent(db).run(_base_input())
        stage = db.query(PipelineStage).one()
        assert stage.tool_version == "cellranger 7.1.0"

    def test_cluster_result_rows_inserted(self, mock_cr, mock_scanpy, db) -> None:
        scRNAAgent(db).run(_base_input())
        rows = db.query(ScRNAClusterResult).all()
        assert len(rows) == 4  # one per cluster

    def test_n_clusters_in_each_row(self, mock_cr, mock_scanpy, db) -> None:
        scRNAAgent(db).run(_base_input())
        rows = db.query(ScRNAClusterResult).all()
        assert all(r.n_clusters == 4 for r in rows)

    def test_cluster_ids_correct(self, mock_cr, mock_scanpy, db) -> None:
        scRNAAgent(db).run(_base_input())
        cluster_ids = {r.cluster_id for r in db.query(ScRNAClusterResult).all()}
        assert cluster_ids == {0, 1, 2, 3}

    def test_n_cells_correct(self, mock_cr, mock_scanpy, db) -> None:
        scRNAAgent(db).run(_base_input())
        rows = {r.cluster_id: r for r in db.query(ScRNAClusterResult).all()}
        assert rows[0].n_cells == 700
        assert rows[1].n_cells == 800

    def test_h5ad_artifact_written(self, mock_cr, mock_scanpy, db) -> None:
        scRNAAgent(db).run(_base_input())
        artifacts = db.query(Artifact).all()
        types = {a.artifact_type for a in artifacts}
        assert ArtifactType.scrna_h5ad in types

    def test_umap_artifact_written(self, mock_cr, mock_scanpy, db) -> None:
        scRNAAgent(db).run(_base_input())
        artifacts = db.query(Artifact).all()
        types = {a.artifact_type for a in artifacts}
        assert ArtifactType.scrna_umap in types

    def test_marker_genes_artifact_written(self, mock_cr, mock_scanpy, db) -> None:
        scRNAAgent(db).run(_base_input())
        artifacts = db.query(Artifact).all()
        types = {a.artifact_type for a in artifacts}
        assert ArtifactType.marker_genes in types


@patch("src.agents.specialists.scrna_agent.run_scanpy_pipeline", return_value=_SCANPY_OUT)
@patch("src.agents.specialists.scrna_agent.run_cellranger_count")
class TestScRNAAgentFailure:
    def test_cellranger_error_fails_stage(self, mock_cr, mock_scanpy, db) -> None:
        mock_cr.side_effect = ToolExecutionError("cellranger", 1, "err", [])
        with pytest.raises(ToolExecutionError):
            scRNAAgent(db).run(_base_input())
        stage = db.query(PipelineStage).one()
        assert stage.status == StageStatus.failed

    def test_no_cluster_rows_on_failure(self, mock_cr, mock_scanpy, db) -> None:
        mock_cr.side_effect = ToolExecutionError("cellranger", 1, "err", [])
        with contextlib.suppress(ToolExecutionError):
            scRNAAgent(db).run(_base_input())
        assert db.query(ScRNAClusterResult).count() == 0
