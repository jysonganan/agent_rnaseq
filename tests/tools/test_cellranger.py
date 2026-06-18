"""Tests for run_cellranger_count, CellRanger parser, and input validation."""

from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from pydantic import ValidationError

from src.tools.base import ToolExecutionError, ToolTimeoutError
from src.tools.scrna.cellranger import (
    CellRangerCountInput,
    CellRangerCountOutput,
    run_cellranger_count,
)
from src.tools.scrna.parsers import parse_web_summary

FIXTURE_DIR = Path(__file__).parent / "fixtures"
WEB_SUMMARY_TEXT = (FIXTURE_DIR / "cellranger_web_summary.csv").read_text()

_STATS = {
    "estimated_cells": 2700,
    "median_genes_per_cell": 1847,
    "mean_reads_per_cell": 32739,
    "number_of_reads": 88929447,
    "median_umi_counts_per_cell": 5765,
    "total_genes_detected": 16563,
}


# ── parse_web_summary ──────────────────────────────────────────────────────────


class TestParseWebSummary:
    def test_estimated_cells(self) -> None:
        result = parse_web_summary(WEB_SUMMARY_TEXT)
        assert result["estimated_cells"] == 2700

    def test_median_genes_per_cell(self) -> None:
        result = parse_web_summary(WEB_SUMMARY_TEXT)
        assert result["median_genes_per_cell"] == 1847

    def test_mean_reads_per_cell(self) -> None:
        result = parse_web_summary(WEB_SUMMARY_TEXT)
        assert result["mean_reads_per_cell"] == 32739

    def test_number_of_reads(self) -> None:
        result = parse_web_summary(WEB_SUMMARY_TEXT)
        assert result["number_of_reads"] == 88929447

    def test_median_umi_counts_per_cell(self) -> None:
        result = parse_web_summary(WEB_SUMMARY_TEXT)
        assert result["median_umi_counts_per_cell"] == 5765

    def test_total_genes_detected(self) -> None:
        result = parse_web_summary(WEB_SUMMARY_TEXT)
        assert result["total_genes_detected"] == 16563

    def test_percentage_value_stripped(self) -> None:
        # Valid Barcodes = "98.7%" → float 98.7
        result = parse_web_summary(WEB_SUMMARY_TEXT)
        assert isinstance(result["valid_barcodes"], float)
        assert result["valid_barcodes"] == pytest.approx(98.7)

    def test_empty_text_returns_empty_dict(self) -> None:
        assert parse_web_summary("") == {}

    def test_header_only_returns_empty_dict(self) -> None:
        header = "Estimated Number of Cells,Median Genes per Cell\n"
        assert parse_web_summary(header) == {}


# ── CellRangerCountInput validation ───────────────────────────────────────────


class TestCellRangerCountInput:
    def _base(self, **kwargs) -> CellRangerCountInput:  # type: ignore[no-untyped-def]
        return CellRangerCountInput(
            fastq_dirs=["/data/fastqs"],
            sample_name="pbmc3k",
            transcriptome_path="/ref/GRCh38",
            output_dir="/out/cellranger",
            **kwargs,
        )

    def test_valid_defaults(self) -> None:
        inp = self._base()
        assert inp.localcores == 8
        assert inp.localmem == 64
        assert inp.expected_cells is None

    def test_fastq_dirs_min_length_enforced(self) -> None:
        with pytest.raises(ValidationError):
            CellRangerCountInput(
                fastq_dirs=[],
                sample_name="pbmc3k",
                transcriptome_path="/ref/GRCh38",
                output_dir="/out/cellranger",
            )

    def test_multiple_fastq_dirs_valid(self) -> None:
        inp = CellRangerCountInput(
            fastq_dirs=["/data/lane1", "/data/lane2"],
            sample_name="pbmc3k",
            transcriptome_path="/ref/GRCh38",
            output_dir="/out/cellranger",
        )
        assert len(inp.fastq_dirs) == 2

    def test_expected_cells_optional(self) -> None:
        inp = self._base(expected_cells=3000)
        assert inp.expected_cells == 3000

    def test_localcores_zero_raises(self) -> None:
        with pytest.raises(ValidationError):
            self._base(localcores=0)

    def test_localcores_above_max_raises(self) -> None:
        with pytest.raises(ValidationError):
            self._base(localcores=257)

    def test_localmem_zero_raises(self) -> None:
        with pytest.raises(ValidationError):
            self._base(localmem=0)

    def test_localmem_above_max_raises(self) -> None:
        with pytest.raises(ValidationError):
            self._base(localmem=513)


# ── run_cellranger_count (subprocess mocked) ──────────────────────────────────


class TestRunCellRangerCount:
    def _mock_proc(self, returncode: int = 0) -> MagicMock:
        proc = MagicMock(spec=subprocess.CompletedProcess)
        proc.returncode = returncode
        proc.stdout = b""
        proc.stderr = b""
        return proc

    def _base_inp(self, **kwargs) -> CellRangerCountInput:  # type: ignore[no-untyped-def]
        return CellRangerCountInput(
            fastq_dirs=["/data/fastqs"],
            sample_name="pbmc3k",
            transcriptome_path="/ref/GRCh38",
            output_dir="/out/cellranger",
            **kwargs,
        )

    @patch("src.tools.scrna.cellranger.detect_version", return_value="cellranger 7.1.0")
    @patch("src.tools.scrna.cellranger._read_summary_stats", return_value=_STATS)
    @patch("os.makedirs")
    @patch("src.tools.base.subprocess.run")
    def test_success_returns_output(
        self, mock_run, mock_makedirs, mock_stats, mock_version
    ) -> None:
        mock_run.return_value = self._mock_proc()
        out = run_cellranger_count(self._base_inp())
        assert isinstance(out, CellRangerCountOutput)

    @patch("src.tools.scrna.cellranger.detect_version", return_value=None)
    @patch("src.tools.scrna.cellranger._read_summary_stats", return_value=_STATS)
    @patch("os.makedirs")
    @patch("src.tools.base.subprocess.run")
    def test_summary_stats_estimated_cells(
        self, mock_run, mock_makedirs, mock_stats, mock_version
    ) -> None:
        mock_run.return_value = self._mock_proc()
        out = run_cellranger_count(self._base_inp())
        assert out.summary_stats["estimated_cells"] == 2700

    @patch("src.tools.scrna.cellranger.detect_version", return_value=None)
    @patch("src.tools.scrna.cellranger._read_summary_stats", return_value=_STATS)
    @patch("os.makedirs")
    @patch("src.tools.base.subprocess.run")
    def test_summary_stats_median_genes(
        self, mock_run, mock_makedirs, mock_stats, mock_version
    ) -> None:
        mock_run.return_value = self._mock_proc()
        out = run_cellranger_count(self._base_inp())
        assert out.summary_stats["median_genes_per_cell"] == 1847

    @patch("src.tools.scrna.cellranger.detect_version", return_value="cellranger 7.1.0")
    @patch("src.tools.scrna.cellranger._read_summary_stats", return_value=_STATS)
    @patch("os.makedirs")
    @patch("src.tools.base.subprocess.run")
    def test_tool_version_in_output(
        self, mock_run, mock_makedirs, mock_stats, mock_version
    ) -> None:
        mock_run.return_value = self._mock_proc()
        out = run_cellranger_count(self._base_inp())
        assert out.tool_version == "cellranger 7.1.0"

    @patch("src.tools.scrna.cellranger.detect_version", return_value=None)
    @patch("src.tools.scrna.cellranger._read_summary_stats", return_value=_STATS)
    @patch("os.makedirs")
    @patch("src.tools.base.subprocess.run")
    def test_fastqs_in_command(
        self, mock_run, mock_makedirs, mock_stats, mock_version
    ) -> None:
        mock_run.return_value = self._mock_proc()
        run_cellranger_count(self._base_inp())
        called_cmd = mock_run.call_args[0][0]
        assert any("--fastqs=" in arg for arg in called_cmd)
        assert any("/data/fastqs" in arg for arg in called_cmd)

    @patch("src.tools.scrna.cellranger.detect_version", return_value=None)
    @patch("src.tools.scrna.cellranger._read_summary_stats", return_value=_STATS)
    @patch("os.makedirs")
    @patch("src.tools.base.subprocess.run")
    def test_multiple_fastq_dirs_comma_joined(
        self, mock_run, mock_makedirs, mock_stats, mock_version
    ) -> None:
        mock_run.return_value = self._mock_proc()
        inp = CellRangerCountInput(
            fastq_dirs=["/lane1", "/lane2"],
            sample_name="pbmc3k",
            transcriptome_path="/ref/GRCh38",
            output_dir="/out/cellranger",
        )
        run_cellranger_count(inp)
        called_cmd = mock_run.call_args[0][0]
        assert any("--fastqs=/lane1,/lane2" in arg for arg in called_cmd)

    @patch("src.tools.scrna.cellranger.detect_version", return_value=None)
    @patch("src.tools.scrna.cellranger._read_summary_stats", return_value=_STATS)
    @patch("os.makedirs")
    @patch("src.tools.base.subprocess.run")
    def test_expect_cells_in_command_when_set(
        self, mock_run, mock_makedirs, mock_stats, mock_version
    ) -> None:
        mock_run.return_value = self._mock_proc()
        run_cellranger_count(self._base_inp(expected_cells=3000))
        called_cmd = mock_run.call_args[0][0]
        assert any("--expect-cells=3000" in arg for arg in called_cmd)

    @patch("src.tools.scrna.cellranger.detect_version", return_value=None)
    @patch("src.tools.scrna.cellranger._read_summary_stats", return_value=_STATS)
    @patch("os.makedirs")
    @patch("src.tools.base.subprocess.run")
    def test_expect_cells_omitted_when_none(
        self, mock_run, mock_makedirs, mock_stats, mock_version
    ) -> None:
        mock_run.return_value = self._mock_proc()
        run_cellranger_count(self._base_inp())
        called_cmd = mock_run.call_args[0][0]
        assert not any("--expect-cells" in arg for arg in called_cmd)

    @patch("src.tools.scrna.cellranger.detect_version", return_value=None)
    @patch("src.tools.scrna.cellranger._read_summary_stats", return_value=_STATS)
    @patch("os.makedirs")
    @patch("src.tools.base.subprocess.run")
    def test_output_paths_use_sample_name(
        self, mock_run, mock_makedirs, mock_stats, mock_version
    ) -> None:
        mock_run.return_value = self._mock_proc()
        out = run_cellranger_count(self._base_inp())
        assert "pbmc3k" in out.filtered_matrix_dir
        assert "pbmc3k" in out.molecule_info_path
        assert "pbmc3k" in out.summary_html_path

    @patch("src.tools.scrna.cellranger.detect_version", return_value=None)
    @patch("os.makedirs")
    @patch("src.tools.base.subprocess.run")
    def test_nonzero_exit_raises_tool_execution_error(
        self, mock_run, mock_makedirs, mock_version
    ) -> None:
        mock_run.return_value = self._mock_proc(returncode=1)
        with pytest.raises(ToolExecutionError) as exc_info:
            run_cellranger_count(self._base_inp())
        assert exc_info.value.tool_name == "cellranger"

    @patch("src.tools.scrna.cellranger.detect_version", return_value=None)
    @patch("os.makedirs")
    @patch("src.tools.base.subprocess.run")
    def test_timeout_raises_tool_timeout_error(
        self, mock_run, mock_makedirs, mock_version
    ) -> None:
        mock_run.side_effect = subprocess.TimeoutExpired(cmd=["cellranger"], timeout=3600)
        with pytest.raises(ToolTimeoutError):
            run_cellranger_count(self._base_inp())
