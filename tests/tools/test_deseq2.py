"""Tests for run_deseq2, DESeq2 parsers, and input validation."""

from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from pydantic import ValidationError

from src.tools.base import ToolExecutionError, ToolTimeoutError
from src.tools.de.deseq2 import (
    DEContrast,
    DESeq2Input,
    DESeq2Output,
    run_deseq2,
)
from src.tools.de.parsers import (
    DEContrastSummary,
    DEGResult,
    compute_contrast_summary,
    parse_deseq2_results,
)

FIXTURE_DIR = Path(__file__).parent / "fixtures"
DE_RESULTS_TEXT = (FIXTURE_DIR / "deseq2_results.csv").read_text()

# Fixture: 8 genes total — 2 up, 2 down, 4 not-sig (alpha=0.05)
_SUMMARY = DEContrastSummary(total_genes=8, upregulated=2, downregulated=2, not_significant=4)


# ── parse_deseq2_results ───────────────────────────────────────────────────────


class TestParseDeseq2Results:
    def test_gene_count(self) -> None:
        results = parse_deseq2_results(DE_RESULTS_TEXT)
        assert len(results) == 8

    def test_returns_deg_result_instances(self) -> None:
        results = parse_deseq2_results(DE_RESULTS_TEXT)
        assert all(isinstance(r, DEGResult) for r in results)

    def test_first_gene_id(self) -> None:
        results = parse_deseq2_results(DE_RESULTS_TEXT)
        assert results[0].gene_id == "GENE1"

    def test_numeric_fields_parsed(self) -> None:
        results = parse_deseq2_results(DE_RESULTS_TEXT)
        assert results[0].log2_fold_change == pytest.approx(2.3)
        assert results[0].padj == pytest.approx(0.000001)

    def test_na_fields_become_none(self) -> None:
        # GENE8 has NA for all numeric fields
        results = parse_deseq2_results(DE_RESULTS_TEXT)
        gene8 = next(r for r in results if r.gene_id == "GENE8")
        assert gene8.log2_fold_change is None
        assert gene8.padj is None
        assert gene8.pvalue is None

    def test_empty_text_returns_empty_list(self) -> None:
        assert parse_deseq2_results("") == []

    def test_header_only_returns_empty_list(self) -> None:
        header = "gene_id,baseMean,log2FoldChange,lfcSE,stat,pvalue,padj\n"
        assert parse_deseq2_results(header) == []


# ── compute_contrast_summary ───────────────────────────────────────────────────


class TestComputeContrastSummary:
    def _results(self) -> list[DEGResult]:
        return parse_deseq2_results(DE_RESULTS_TEXT)

    def test_total_genes(self) -> None:
        summary = compute_contrast_summary(self._results(), alpha=0.05)
        assert summary.total_genes == 8

    def test_upregulated_count(self) -> None:
        summary = compute_contrast_summary(self._results(), alpha=0.05)
        assert summary.upregulated == 2

    def test_downregulated_count(self) -> None:
        summary = compute_contrast_summary(self._results(), alpha=0.05)
        assert summary.downregulated == 2

    def test_not_significant_count(self) -> None:
        summary = compute_contrast_summary(self._results(), alpha=0.05)
        assert summary.not_significant == 4

    def test_counts_sum_to_total(self) -> None:
        summary = compute_contrast_summary(self._results(), alpha=0.05)
        assert (
            summary.upregulated + summary.downregulated + summary.not_significant
            == summary.total_genes
        )

    def test_strict_alpha_leaves_fewer_significant(self) -> None:
        # alpha=0.0001: GENE1 (padj=1e-6 up), GENE2 (padj=5e-6 down), GENE4 (padj=1.8e-6 up) pass
        # GENE5 (padj=0.0012) does NOT pass (0.0012 > 0.0001)
        summary = compute_contrast_summary(self._results(), alpha=0.0001)
        assert summary.upregulated == 2
        assert summary.downregulated == 1

    def test_na_padj_counted_as_not_significant(self) -> None:
        results = [
            DEGResult(
                gene_id="G",
                base_mean=10.0,
                log2_fold_change=5.0,
                lfc_se=None,
                stat=None,
                pvalue=None,
                padj=None,
            )
        ]
        summary = compute_contrast_summary(results, alpha=0.05)
        assert summary.not_significant == 1
        assert summary.upregulated == 0

    def test_empty_results_all_zeros(self) -> None:
        summary = compute_contrast_summary([])
        assert summary.total_genes == 0
        assert summary.upregulated == 0


# ── DESeq2Input validation ─────────────────────────────────────────────────────


class TestDESeq2Input:
    def _base(self, **kwargs) -> DESeq2Input:  # type: ignore[no-untyped-def]
        return DESeq2Input(
            counts_matrix_path="/data/counts.csv",
            sample_metadata_path="/data/meta.csv",
            contrasts=[
                DEContrast(name="treated_vs_ctrl", numerator="treated", denominator="control")
            ],
            output_dir="/out/de",
            r_script_path="/r/deseq2_analysis.R",
            **kwargs,
        )

    def test_valid_defaults(self) -> None:
        inp = self._base()
        assert inp.alpha == pytest.approx(0.05)
        assert inp.min_count == 10
        assert inp.lfc_threshold == pytest.approx(0.0)

    def test_alpha_lower_bound(self) -> None:
        inp = self._base(alpha=0.001)
        assert inp.alpha == pytest.approx(0.001)

    def test_alpha_upper_bound(self) -> None:
        inp = self._base(alpha=0.1)
        assert inp.alpha == pytest.approx(0.1)

    def test_alpha_below_minimum_raises(self) -> None:
        with pytest.raises(ValidationError):
            self._base(alpha=0.0009)

    def test_alpha_above_maximum_raises(self) -> None:
        with pytest.raises(ValidationError):
            self._base(alpha=0.11)

    def test_lfc_threshold_above_max_raises(self) -> None:
        with pytest.raises(ValidationError):
            self._base(lfc_threshold=5.1)

    def test_lfc_threshold_negative_raises(self) -> None:
        with pytest.raises(ValidationError):
            self._base(lfc_threshold=-0.1)

    def test_contrasts_empty_raises(self) -> None:
        with pytest.raises(ValidationError):
            DESeq2Input(
                counts_matrix_path="/data/counts.csv",
                sample_metadata_path="/data/meta.csv",
                contrasts=[],
                output_dir="/out/de",
                r_script_path="/r/deseq2_analysis.R",
            )

    def test_multiple_contrasts_valid(self) -> None:
        inp = DESeq2Input(
            counts_matrix_path="/data/counts.csv",
            sample_metadata_path="/data/meta.csv",
            contrasts=[
                DEContrast(name="c1", numerator="A", denominator="B"),
                DEContrast(name="c2", numerator="A", denominator="C"),
            ],
            output_dir="/out/de",
            r_script_path="/r/deseq2_analysis.R",
        )
        assert len(inp.contrasts) == 2

    def test_min_count_range(self) -> None:
        with pytest.raises(ValidationError):
            self._base(min_count=0)
        with pytest.raises(ValidationError):
            self._base(min_count=1001)


# ── run_deseq2 (subprocess mocked) ────────────────────────────────────────────


class TestRunDeseq2:
    def _mock_proc(self, returncode: int = 0) -> MagicMock:
        proc = MagicMock(spec=subprocess.CompletedProcess)
        proc.returncode = returncode
        proc.stdout = b""
        proc.stderr = b""
        return proc

    def _base_inp(self, **kwargs) -> DESeq2Input:  # type: ignore[no-untyped-def]
        return DESeq2Input(
            counts_matrix_path="/data/counts.csv",
            sample_metadata_path="/data/meta.csv",
            contrasts=[
                DEContrast(name="treated_vs_ctrl", numerator="treated", denominator="control")
            ],
            output_dir="/out/de",
            r_script_path="/r/deseq2_analysis.R",
            **kwargs,
        )

    @patch("src.tools.de.deseq2.detect_version", return_value="R version 4.3.0")
    @patch("src.tools.de.deseq2._read_contrast_summary", return_value=_SUMMARY)
    @patch("os.makedirs")
    @patch("src.tools.base.subprocess.run")
    def test_success_returns_deseq2_output(
        self, mock_run, mock_makedirs, mock_summary, mock_version
    ) -> None:
        mock_run.return_value = self._mock_proc()
        out = run_deseq2(self._base_inp())
        assert isinstance(out, DESeq2Output)

    @patch("src.tools.de.deseq2.detect_version", return_value=None)
    @patch("src.tools.de.deseq2._read_contrast_summary", return_value=_SUMMARY)
    @patch("os.makedirs")
    @patch("src.tools.base.subprocess.run")
    def test_contrast_summary_in_output(
        self, mock_run, mock_makedirs, mock_summary, mock_version
    ) -> None:
        mock_run.return_value = self._mock_proc()
        out = run_deseq2(self._base_inp())
        assert "treated_vs_ctrl" in out.contrast_summaries
        cs = out.contrast_summaries["treated_vs_ctrl"]
        assert cs.upregulated == 2
        assert cs.downregulated == 2
        assert cs.total_genes == 8

    @patch("src.tools.de.deseq2.detect_version", return_value="R version 4.3.0")
    @patch("src.tools.de.deseq2._read_contrast_summary", return_value=_SUMMARY)
    @patch("os.makedirs")
    @patch("src.tools.base.subprocess.run")
    def test_tool_version_in_output(
        self, mock_run, mock_makedirs, mock_summary, mock_version
    ) -> None:
        mock_run.return_value = self._mock_proc()
        out = run_deseq2(self._base_inp())
        assert out.tool_version == "R version 4.3.0"

    @patch("src.tools.de.deseq2.detect_version", return_value=None)
    @patch("src.tools.de.deseq2._read_contrast_summary", return_value=_SUMMARY)
    @patch("os.makedirs")
    @patch("src.tools.base.subprocess.run")
    def test_r_script_path_as_positional_arg(
        self, mock_run, mock_makedirs, mock_summary, mock_version
    ) -> None:
        mock_run.return_value = self._mock_proc()
        run_deseq2(self._base_inp())
        called_cmd = mock_run.call_args[0][0]
        assert called_cmd[0] == "Rscript"
        assert called_cmd[1] == "--vanilla"
        assert called_cmd[2] == "/r/deseq2_analysis.R"

    @patch("src.tools.de.deseq2.detect_version", return_value=None)
    @patch("src.tools.de.deseq2._read_contrast_summary", return_value=_SUMMARY)
    @patch("os.makedirs")
    @patch("src.tools.base.subprocess.run")
    def test_no_eval_in_command_args(
        self, mock_run, mock_makedirs, mock_summary, mock_version
    ) -> None:
        mock_run.return_value = self._mock_proc()
        run_deseq2(self._base_inp())
        called_cmd = mock_run.call_args[0][0]
        assert not any("eval(" in arg for arg in called_cmd)

    @patch("src.tools.de.deseq2.detect_version", return_value=None)
    @patch("src.tools.de.deseq2._read_contrast_summary", return_value=_SUMMARY)
    @patch("os.makedirs")
    @patch("src.tools.base.subprocess.run")
    def test_contrast_args_in_command(
        self, mock_run, mock_makedirs, mock_summary, mock_version
    ) -> None:
        mock_run.return_value = self._mock_proc()
        run_deseq2(self._base_inp())
        called_cmd = mock_run.call_args[0][0]
        assert "treated_vs_ctrl" in called_cmd
        assert "treated" in called_cmd
        assert "control" in called_cmd

    @patch("src.tools.de.deseq2.detect_version", return_value=None)
    @patch("src.tools.de.deseq2._read_contrast_summary", return_value=_SUMMARY)
    @patch("os.makedirs")
    @patch("src.tools.base.subprocess.run")
    def test_results_path_in_output(
        self, mock_run, mock_makedirs, mock_summary, mock_version
    ) -> None:
        mock_run.return_value = self._mock_proc()
        out = run_deseq2(self._base_inp())
        assert "treated_vs_ctrl" in out.results_paths
        assert out.results_paths["treated_vs_ctrl"].endswith("treated_vs_ctrl_results.csv")

    @patch("src.tools.de.deseq2.detect_version", return_value=None)
    @patch("src.tools.de.deseq2._read_contrast_summary", return_value=_SUMMARY)
    @patch("os.makedirs")
    @patch("src.tools.base.subprocess.run")
    def test_two_contrasts_calls_subprocess_twice(
        self, mock_run, mock_makedirs, mock_summary, mock_version
    ) -> None:
        mock_run.return_value = self._mock_proc()
        inp = DESeq2Input(
            counts_matrix_path="/data/counts.csv",
            sample_metadata_path="/data/meta.csv",
            contrasts=[
                DEContrast(name="c1", numerator="A", denominator="B"),
                DEContrast(name="c2", numerator="A", denominator="C"),
            ],
            output_dir="/out/de",
            r_script_path="/r/deseq2_analysis.R",
        )
        run_deseq2(inp)
        assert mock_run.call_count == 2

    @patch("src.tools.de.deseq2.detect_version", return_value=None)
    @patch("os.makedirs")
    @patch("src.tools.base.subprocess.run")
    def test_nonzero_exit_raises_tool_execution_error(
        self, mock_run, mock_makedirs, mock_version
    ) -> None:
        mock_run.return_value = self._mock_proc(returncode=1)
        with pytest.raises(ToolExecutionError) as exc_info:
            run_deseq2(self._base_inp())
        assert exc_info.value.tool_name == "DESeq2"

    @patch("src.tools.de.deseq2.detect_version", return_value=None)
    @patch("os.makedirs")
    @patch("src.tools.base.subprocess.run")
    def test_timeout_raises_tool_timeout_error(self, mock_run, mock_makedirs, mock_version) -> None:
        mock_run.side_effect = subprocess.TimeoutExpired(cmd=["Rscript"], timeout=3600)
        with pytest.raises(ToolTimeoutError):
            run_deseq2(self._base_inp())
