"""Tests for run_scanpy_pipeline and input validation."""

from __future__ import annotations

import subprocess
from unittest.mock import MagicMock, patch

import pytest
from pydantic import ValidationError

from src.tools.base import ToolExecutionError, ToolTimeoutError
from src.tools.scrna.scanpy_tool import (
    ClusterSummary,
    ScanpyInput,
    ScanpyOutput,
    run_scanpy_pipeline,
)

_CLUSTER_SUMMARY = ClusterSummary(
    n_clusters=8,
    cells_per_cluster={"0": 350, "1": 290, "2": 400, "3": 210,
                       "4": 180, "5": 320, "6": 150, "7": 100},
)


# ── ClusterSummary model ───────────────────────────────────────────────────────


class TestClusterSummary:
    def test_n_clusters_field(self) -> None:
        cs = ClusterSummary(n_clusters=5, cells_per_cluster={"0": 100, "1": 200})
        assert cs.n_clusters == 5

    def test_cells_per_cluster_field(self) -> None:
        cs = ClusterSummary(n_clusters=2, cells_per_cluster={"0": 100, "1": 200})
        assert cs.cells_per_cluster["0"] == 100


# ── ScanpyInput validation ────────────────────────────────────────────────────


class TestScanpyInput:
    def _base(self, **kwargs) -> ScanpyInput:  # type: ignore[no-untyped-def]
        return ScanpyInput(
            matrix_dir="/data/filtered_feature_bc_matrix",
            output_dir="/out/scanpy",
            script_path="/src/scripts/scanpy_pipeline.py",
            **kwargs,
        )

    def test_valid_defaults(self) -> None:
        inp = self._base()
        assert inp.min_genes == 200
        assert inp.min_cells == 3
        assert inp.max_pct_mt == pytest.approx(20.0)
        assert inp.n_top_genes == 2000
        assert inp.n_neighbors == 15

    def test_max_pct_mt_lower_bound(self) -> None:
        inp = self._base(max_pct_mt=5.0)
        assert inp.max_pct_mt == pytest.approx(5.0)

    def test_max_pct_mt_upper_bound(self) -> None:
        inp = self._base(max_pct_mt=50.0)
        assert inp.max_pct_mt == pytest.approx(50.0)

    def test_max_pct_mt_below_minimum_raises(self) -> None:
        with pytest.raises(ValidationError):
            self._base(max_pct_mt=4.9)

    def test_max_pct_mt_above_maximum_raises(self) -> None:
        with pytest.raises(ValidationError):
            self._base(max_pct_mt=50.1)

    def test_min_genes_zero_raises(self) -> None:
        with pytest.raises(ValidationError):
            self._base(min_genes=0)

    def test_min_cells_zero_raises(self) -> None:
        with pytest.raises(ValidationError):
            self._base(min_cells=0)

    def test_n_neighbors_below_min_raises(self) -> None:
        with pytest.raises(ValidationError):
            self._base(n_neighbors=1)

    def test_n_top_genes_zero_raises(self) -> None:
        with pytest.raises(ValidationError):
            self._base(n_top_genes=0)


# ── run_scanpy_pipeline (subprocess mocked) ────────────────────────────────────


class TestRunScanpyPipeline:
    def _mock_proc(self, returncode: int = 0) -> MagicMock:
        proc = MagicMock(spec=subprocess.CompletedProcess)
        proc.returncode = returncode
        proc.stdout = b""
        proc.stderr = b""
        return proc

    def _base_inp(self, **kwargs) -> ScanpyInput:  # type: ignore[no-untyped-def]
        return ScanpyInput(
            matrix_dir="/data/filtered_feature_bc_matrix",
            output_dir="/out/scanpy",
            script_path="/src/scripts/scanpy_pipeline.py",
            **kwargs,
        )

    @patch("src.tools.scrna.scanpy_tool.detect_version", return_value="Python 3.11.0")
    @patch("src.tools.scrna.scanpy_tool._read_cluster_summary", return_value=_CLUSTER_SUMMARY)
    @patch("os.makedirs")
    @patch("src.tools.base.subprocess.run")
    def test_success_returns_scanpy_output(
        self, mock_run, mock_makedirs, mock_summary, mock_version
    ) -> None:
        mock_run.return_value = self._mock_proc()
        out = run_scanpy_pipeline(self._base_inp())
        assert isinstance(out, ScanpyOutput)

    @patch("src.tools.scrna.scanpy_tool.detect_version", return_value=None)
    @patch("src.tools.scrna.scanpy_tool._read_cluster_summary", return_value=_CLUSTER_SUMMARY)
    @patch("os.makedirs")
    @patch("src.tools.base.subprocess.run")
    def test_cluster_summary_n_clusters(
        self, mock_run, mock_makedirs, mock_summary, mock_version
    ) -> None:
        mock_run.return_value = self._mock_proc()
        out = run_scanpy_pipeline(self._base_inp())
        assert out.cluster_summary.n_clusters == 8

    @patch("src.tools.scrna.scanpy_tool.detect_version", return_value=None)
    @patch("src.tools.scrna.scanpy_tool._read_cluster_summary", return_value=_CLUSTER_SUMMARY)
    @patch("os.makedirs")
    @patch("src.tools.base.subprocess.run")
    def test_cluster_summary_cells_per_cluster(
        self, mock_run, mock_makedirs, mock_summary, mock_version
    ) -> None:
        mock_run.return_value = self._mock_proc()
        out = run_scanpy_pipeline(self._base_inp())
        assert out.cluster_summary.cells_per_cluster["0"] == 350

    @patch("src.tools.scrna.scanpy_tool.detect_version", return_value="Python 3.11.0")
    @patch("src.tools.scrna.scanpy_tool._read_cluster_summary", return_value=_CLUSTER_SUMMARY)
    @patch("os.makedirs")
    @patch("src.tools.base.subprocess.run")
    def test_tool_version_in_output(
        self, mock_run, mock_makedirs, mock_summary, mock_version
    ) -> None:
        mock_run.return_value = self._mock_proc()
        out = run_scanpy_pipeline(self._base_inp())
        assert out.tool_version == "Python 3.11.0"

    @patch("src.tools.scrna.scanpy_tool.detect_version", return_value=None)
    @patch("src.tools.scrna.scanpy_tool._read_cluster_summary", return_value=_CLUSTER_SUMMARY)
    @patch("os.makedirs")
    @patch("src.tools.base.subprocess.run")
    def test_script_path_as_positional_arg(
        self, mock_run, mock_makedirs, mock_summary, mock_version
    ) -> None:
        mock_run.return_value = self._mock_proc()
        run_scanpy_pipeline(self._base_inp())
        called_cmd = mock_run.call_args[0][0]
        assert called_cmd[0] == "python"
        assert called_cmd[1] == "/src/scripts/scanpy_pipeline.py"

    @patch("src.tools.scrna.scanpy_tool.detect_version", return_value=None)
    @patch("src.tools.scrna.scanpy_tool._read_cluster_summary", return_value=_CLUSTER_SUMMARY)
    @patch("os.makedirs")
    @patch("src.tools.base.subprocess.run")
    def test_matrix_dir_flag_in_command(
        self, mock_run, mock_makedirs, mock_summary, mock_version
    ) -> None:
        mock_run.return_value = self._mock_proc()
        run_scanpy_pipeline(self._base_inp())
        called_cmd = mock_run.call_args[0][0]
        assert "--matrix-dir" in called_cmd
        assert "/data/filtered_feature_bc_matrix" in called_cmd

    @patch("src.tools.scrna.scanpy_tool.detect_version", return_value=None)
    @patch("src.tools.scrna.scanpy_tool._read_cluster_summary", return_value=_CLUSTER_SUMMARY)
    @patch("os.makedirs")
    @patch("src.tools.base.subprocess.run")
    def test_max_pct_mt_flag_in_command(
        self, mock_run, mock_makedirs, mock_summary, mock_version
    ) -> None:
        mock_run.return_value = self._mock_proc()
        run_scanpy_pipeline(self._base_inp(max_pct_mt=15.0))
        called_cmd = mock_run.call_args[0][0]
        assert "--max-pct-mt" in called_cmd
        assert "15.0" in called_cmd

    @patch("src.tools.scrna.scanpy_tool.detect_version", return_value=None)
    @patch("src.tools.scrna.scanpy_tool._read_cluster_summary", return_value=_CLUSTER_SUMMARY)
    @patch("os.makedirs")
    @patch("src.tools.base.subprocess.run")
    def test_output_paths_correct(
        self, mock_run, mock_makedirs, mock_summary, mock_version
    ) -> None:
        mock_run.return_value = self._mock_proc()
        out = run_scanpy_pipeline(self._base_inp())
        assert out.h5ad_path.endswith("cells.h5ad")
        assert out.umap_plot_path.endswith("umap.pdf")
        assert out.marker_genes_path.endswith("marker_genes.csv")

    @patch("src.tools.scrna.scanpy_tool.detect_version", return_value=None)
    @patch("os.makedirs")
    @patch("src.tools.base.subprocess.run")
    def test_nonzero_exit_raises_tool_execution_error(
        self, mock_run, mock_makedirs, mock_version
    ) -> None:
        mock_run.return_value = self._mock_proc(returncode=1)
        with pytest.raises(ToolExecutionError) as exc_info:
            run_scanpy_pipeline(self._base_inp())
        assert exc_info.value.tool_name == "scanpy"

    @patch("src.tools.scrna.scanpy_tool.detect_version", return_value=None)
    @patch("os.makedirs")
    @patch("src.tools.base.subprocess.run")
    def test_timeout_raises_tool_timeout_error(
        self, mock_run, mock_makedirs, mock_version
    ) -> None:
        mock_run.side_effect = subprocess.TimeoutExpired(cmd=["python"], timeout=3600)
        with pytest.raises(ToolTimeoutError):
            run_scanpy_pipeline(self._base_inp())


# ── scanpy_pipeline.py CLI ────────────────────────────────────────────────────


class TestScanpyPipelineCLI:
    def test_help_exits_zero(self) -> None:
        """python src/scripts/scanpy_pipeline.py --help must succeed."""
        from src.scripts.scanpy_pipeline import parse_args

        with pytest.raises(SystemExit) as exc_info:
            parse_args(["--help"])
        assert exc_info.value.code == 0

    def test_missing_required_args_exits_nonzero(self) -> None:
        from src.scripts.scanpy_pipeline import parse_args

        with pytest.raises(SystemExit) as exc_info:
            parse_args([])
        assert exc_info.value.code != 0

    def test_defaults_parsed_correctly(self) -> None:
        from src.scripts.scanpy_pipeline import parse_args

        args = parse_args(["--matrix-dir", "/m", "--output-dir", "/o"])
        assert args.min_genes == 200
        assert args.min_cells == 3
        assert args.max_pct_mt == pytest.approx(20.0)
        assert args.n_top_genes == 2000
        assert args.n_neighbors == 15

    def test_custom_params_parsed(self) -> None:
        from src.scripts.scanpy_pipeline import parse_args

        args = parse_args([
            "--matrix-dir", "/m",
            "--output-dir", "/o",
            "--min-genes", "300",
            "--max-pct-mt", "25.0",
            "--n-neighbors", "20",
        ])
        assert args.min_genes == 300
        assert args.max_pct_mt == pytest.approx(25.0)
        assert args.n_neighbors == 20
