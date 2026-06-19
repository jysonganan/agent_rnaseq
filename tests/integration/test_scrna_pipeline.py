"""Integration test: scRNA-seq pipeline (CellRanger + Scanpy clustering)."""

from __future__ import annotations

from unittest.mock import patch

from src.agents.specialists.scrna_agent import scRNAAgent
from src.db.enums import StageStatus
from src.db.models.results import ScRNAClusterResult
from src.db.models.run import Artifact, PipelineStage
from src.tools.scrna.cellranger import CellRangerCountOutput
from src.tools.scrna.scanpy_tool import ClusterSummary, ScanpyOutput

from tests.integration.conftest import RUN_ID, SAMPLE_ID


def _mock_cellranger() -> CellRangerCountOutput:
    return CellRangerCountOutput(
        output_dir="/out/scrna/cellranger",
        filtered_matrix_dir="/out/scrna/cellranger/filtered_feature_bc_matrix",
        molecule_info_path="/out/scrna/cellranger/molecule_info.h5",
        summary_html_path="/out/scrna/cellranger/web_summary.html",
        summary_stats={
            "estimated_number_of_cells": 5000,
            "mean_reads_per_cell": 50000,
            "median_genes_per_cell": 2500,
        },
        tool_version="CellRanger 7.1.0",
    )


def _mock_scanpy() -> ScanpyOutput:
    return ScanpyOutput(
        h5ad_path="/out/scrna/scanpy/output.h5ad",
        umap_plot_path="/out/scrna/scanpy/umap.png",
        marker_genes_path="/out/scrna/scanpy/marker_genes.csv",
        cluster_summary=ClusterSummary(
            n_clusters=3,
            cells_per_cluster={"0": 2000, "1": 1500, "2": 1500},
        ),
        tool_version="Scanpy 1.9.6",
    )


def _scrna_input() -> dict:
    return {
        "run_id": RUN_ID,
        "sample_id": SAMPLE_ID,
        "fastq_dirs": ["/data/scrna/fastq"],
        "sample_name": "scrna_sample_001",
        "transcriptome_path": "/ref/GRCh38_transcriptome",
        "output_dir": "/out/scrna",
        "script_path": "/scripts/scanpy_pipeline.py",
    }


def test_scrna_stage_completes(db):
    with (
        patch("src.agents.specialists.scrna_agent.run_cellranger_count", return_value=_mock_cellranger()),
        patch("src.agents.specialists.scrna_agent.run_scanpy_pipeline", return_value=_mock_scanpy()),
    ):
        scRNAAgent(db).run(_scrna_input())

    stage = db.query(PipelineStage).one()
    assert stage.status == StageStatus.completed


def test_scrna_cluster_results_written(db):
    with (
        patch("src.agents.specialists.scrna_agent.run_cellranger_count", return_value=_mock_cellranger()),
        patch("src.agents.specialists.scrna_agent.run_scanpy_pipeline", return_value=_mock_scanpy()),
    ):
        scRNAAgent(db).run(_scrna_input())

    rows = db.query(ScRNAClusterResult).all()
    assert len(rows) == 3


def test_scrna_cluster_count(db):
    with (
        patch("src.agents.specialists.scrna_agent.run_cellranger_count", return_value=_mock_cellranger()),
        patch("src.agents.specialists.scrna_agent.run_scanpy_pipeline", return_value=_mock_scanpy()),
    ):
        scRNAAgent(db).run(_scrna_input())

    rows = db.query(ScRNAClusterResult).all()
    assert all(r.n_clusters == 3 for r in rows)
    cluster_ids = {r.cluster_id for r in rows}
    assert cluster_ids == {0, 1, 2}


def test_scrna_total_cells_correct(db):
    with (
        patch("src.agents.specialists.scrna_agent.run_cellranger_count", return_value=_mock_cellranger()),
        patch("src.agents.specialists.scrna_agent.run_scanpy_pipeline", return_value=_mock_scanpy()),
    ):
        scRNAAgent(db).run(_scrna_input())

    rows = db.query(ScRNAClusterResult).all()
    total_cells = sum(r.n_cells for r in rows)
    assert total_cells == 5000


def test_scrna_artifacts_written(db):
    with (
        patch("src.agents.specialists.scrna_agent.run_cellranger_count", return_value=_mock_cellranger()),
        patch("src.agents.specialists.scrna_agent.run_scanpy_pipeline", return_value=_mock_scanpy()),
    ):
        scRNAAgent(db).run(_scrna_input())

    artifact_paths = {a.path for a in db.query(Artifact).all()}
    assert "/out/scrna/scanpy/output.h5ad" in artifact_paths
    assert "/out/scrna/scanpy/umap.png" in artifact_paths
    assert "/out/scrna/scanpy/marker_genes.csv" in artifact_paths
