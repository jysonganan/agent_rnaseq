"""Scanpy single-cell preprocessing pipeline tool wrapper."""

from __future__ import annotations

import json
import os

from pydantic import BaseModel, Field

from src.tools.base import detect_version, run_subprocess, tool_call


class ClusterSummary(BaseModel):
    n_clusters: int
    cells_per_cluster: dict[str, int]


class ScanpyInput(BaseModel):
    matrix_dir: str
    output_dir: str
    min_genes: int = Field(default=200, ge=1)
    min_cells: int = Field(default=3, ge=1)
    max_pct_mt: float = Field(default=20.0, ge=5.0, le=50.0)
    n_top_genes: int = Field(default=2000, ge=1)
    n_neighbors: int = Field(default=15, ge=2)
    script_path: str


class ScanpyOutput(BaseModel):
    h5ad_path: str
    umap_plot_path: str
    marker_genes_path: str
    cluster_summary: ClusterSummary
    tool_version: str | None = None


def _read_cluster_summary(output_dir: str) -> ClusterSummary:
    """Read cluster_summary.json written by the Scanpy script (patchable in tests)."""
    json_path = os.path.join(output_dir, "cluster_summary.json")
    try:
        with open(json_path) as fh:
            data = json.load(fh)
        return ClusterSummary(**data)
    except (OSError, KeyError, ValueError, TypeError):
        return ClusterSummary(n_clusters=0, cells_per_cluster={})


@tool_call
def run_scanpy_pipeline(inp: ScanpyInput) -> ScanpyOutput:
    """Run the Scanpy single-cell preprocessing pipeline as a Python subprocess.

    The script is invoked with explicit ``--flag value`` arguments; no
    user-supplied text is interpolated into Python code, satisfying the
    safety policy.  The script writes ``cells.h5ad``, ``umap.pdf``,
    ``marker_genes.csv``, and ``cluster_summary.json`` to ``output_dir``.
    """
    os.makedirs(inp.output_dir, exist_ok=True)

    version = detect_version(["python", "--version"], "scanpy")

    cmd = [
        "python",
        inp.script_path,
        "--matrix-dir", inp.matrix_dir,
        "--output-dir", inp.output_dir,
        "--min-genes", str(inp.min_genes),
        "--min-cells", str(inp.min_cells),
        "--max-pct-mt", str(inp.max_pct_mt),
        "--n-top-genes", str(inp.n_top_genes),
        "--n-neighbors", str(inp.n_neighbors),
    ]
    run_subprocess(cmd, tool_name="scanpy")

    cluster_summary = _read_cluster_summary(inp.output_dir)

    return ScanpyOutput(
        h5ad_path=os.path.join(inp.output_dir, "cells.h5ad"),
        umap_plot_path=os.path.join(inp.output_dir, "umap.pdf"),
        marker_genes_path=os.path.join(inp.output_dir, "marker_genes.csv"),
        cluster_summary=cluster_summary,
        tool_version=version,
    )
