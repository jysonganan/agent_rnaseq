"""Tests for run_reactome_gsea, GSEA parsers, and input validation."""

from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from pydantic import ValidationError

from src.tools.base import ToolExecutionError, ToolTimeoutError
from src.tools.gsea.parsers import (
    GSEAResult,
    count_significant_pathways,
    parse_gsea_results,
)
from src.tools.gsea.reactome import (
    ReactomeGSEAInput,
    ReactomeGSEAOutput,
    run_reactome_gsea,
)

FIXTURE_DIR = Path(__file__).parent / "fixtures"
GSEA_TEXT = (FIXTURE_DIR / "gsea_results.csv").read_text()

# Fixture: 5 pathways, 3 significant at padj < 0.05
_SIG_COUNT = 3


# ── parse_gsea_results ─────────────────────────────────────────────────────────


class TestParseGseaResults:
    def test_pathway_count(self) -> None:
        results = parse_gsea_results(GSEA_TEXT)
        assert len(results) == 5

    def test_returns_gsea_result_instances(self) -> None:
        results = parse_gsea_results(GSEA_TEXT)
        assert all(isinstance(r, GSEAResult) for r in results)

    def test_first_pathway_id(self) -> None:
        results = parse_gsea_results(GSEA_TEXT)
        assert results[0].pathway_id == "R-HSA-1234"

    def test_nes_parsed(self) -> None:
        results = parse_gsea_results(GSEA_TEXT)
        assert results[0].nes == pytest.approx(2.3)

    def test_padj_parsed(self) -> None:
        results = parse_gsea_results(GSEA_TEXT)
        assert results[0].padj == pytest.approx(0.002)

    def test_empty_text_returns_empty_list(self) -> None:
        assert parse_gsea_results("") == []

    def test_header_only_returns_empty_list(self) -> None:
        header = "pathway_id,pathway_name,NES,pvalue,padj\n"
        assert parse_gsea_results(header) == []

    def test_pathway_name_field(self) -> None:
        results = parse_gsea_results(GSEA_TEXT)
        assert results[0].pathway_name == "Signaling by EGFR"


# ── count_significant_pathways ─────────────────────────────────────────────────


class TestCountSignificantPathways:
    def _results(self) -> list[GSEAResult]:
        return parse_gsea_results(GSEA_TEXT)

    def test_three_significant_at_default_threshold(self) -> None:
        assert count_significant_pathways(self._results()) == 3

    def test_zero_significant_at_strict_threshold(self) -> None:
        assert count_significant_pathways(self._results(), padj_threshold=0.001) == 0

    def test_all_significant_at_permissive_threshold(self) -> None:
        assert count_significant_pathways(self._results(), padj_threshold=1.0) == 5

    def test_exact_boundary_not_included(self) -> None:
        # R-HSA-9012 padj=0.015; threshold=0.015 means padj < threshold → not included
        results = [GSEAResult(pathway_id="P", pathway_name="X", nes=1.0, pvalue=0.01, padj=0.015)]
        assert count_significant_pathways(results, padj_threshold=0.015) == 0

    def test_empty_list_returns_zero(self) -> None:
        assert count_significant_pathways([]) == 0


# ── ReactomeGSEAInput validation ──────────────────────────────────────────────


class TestReactomeGSEAInput:
    def _base(self, **kwargs) -> ReactomeGSEAInput:  # type: ignore[no-untyped-def]
        return ReactomeGSEAInput(
            de_results_path="/out/de/treated_vs_ctrl_results.csv",
            contrast_name="treated_vs_ctrl",
            output_dir="/out/gsea",
            r_script_path="/r/reactome_gsea.R",
            **kwargs,
        )

    def test_valid_defaults(self) -> None:
        inp = self._base()
        assert inp.organism == "human"
        assert inp.rank_metric == "stat"
        assert inp.nperm == 1000

    def test_organism_mouse(self) -> None:
        inp = self._base(organism="mouse")
        assert inp.organism == "mouse"

    def test_invalid_organism_raises(self) -> None:
        with pytest.raises(ValidationError):
            self._base(organism="zebrafish")  # type: ignore[arg-type]

    def test_rank_metric_log2fc_signed(self) -> None:
        inp = self._base(rank_metric="log2fc_signed")
        assert inp.rank_metric == "log2fc_signed"

    def test_invalid_rank_metric_raises(self) -> None:
        with pytest.raises(ValidationError):
            self._base(rank_metric="foldchange")  # type: ignore[arg-type]

    def test_nperm_lower_bound(self) -> None:
        inp = self._base(nperm=100)
        assert inp.nperm == 100

    def test_nperm_upper_bound(self) -> None:
        inp = self._base(nperm=10000)
        assert inp.nperm == 10000

    def test_nperm_below_minimum_raises(self) -> None:
        with pytest.raises(ValidationError):
            self._base(nperm=99)

    def test_nperm_above_maximum_raises(self) -> None:
        with pytest.raises(ValidationError):
            self._base(nperm=10001)


# ── run_reactome_gsea (subprocess mocked) ─────────────────────────────────────


class TestRunReactomeGsea:
    def _mock_proc(self, returncode: int = 0) -> MagicMock:
        proc = MagicMock(spec=subprocess.CompletedProcess)
        proc.returncode = returncode
        proc.stdout = b""
        proc.stderr = b""
        return proc

    def _base_inp(self, **kwargs) -> ReactomeGSEAInput:  # type: ignore[no-untyped-def]
        return ReactomeGSEAInput(
            de_results_path="/out/de/treated_vs_ctrl_results.csv",
            contrast_name="treated_vs_ctrl",
            output_dir="/out/gsea",
            r_script_path="/r/reactome_gsea.R",
            **kwargs,
        )

    @patch("src.tools.gsea.reactome.detect_version", return_value="R version 4.3.0")
    @patch("src.tools.gsea.reactome._count_significant_gsea", return_value=_SIG_COUNT)
    @patch("os.makedirs")
    @patch("src.tools.base.subprocess.run")
    def test_success_returns_reactome_output(
        self, mock_run, mock_makedirs, mock_count, mock_version
    ) -> None:
        mock_run.return_value = self._mock_proc()
        out = run_reactome_gsea(self._base_inp())
        assert isinstance(out, ReactomeGSEAOutput)

    @patch("src.tools.gsea.reactome.detect_version", return_value=None)
    @patch("src.tools.gsea.reactome._count_significant_gsea", return_value=_SIG_COUNT)
    @patch("os.makedirs")
    @patch("src.tools.base.subprocess.run")
    def test_significant_pathway_count(
        self, mock_run, mock_makedirs, mock_count, mock_version
    ) -> None:
        mock_run.return_value = self._mock_proc()
        out = run_reactome_gsea(self._base_inp())
        assert out.significant_pathway_count == 3

    @patch("src.tools.gsea.reactome.detect_version", return_value="R version 4.3.0")
    @patch("src.tools.gsea.reactome._count_significant_gsea", return_value=_SIG_COUNT)
    @patch("os.makedirs")
    @patch("src.tools.base.subprocess.run")
    def test_tool_version_in_output(
        self, mock_run, mock_makedirs, mock_count, mock_version
    ) -> None:
        mock_run.return_value = self._mock_proc()
        out = run_reactome_gsea(self._base_inp())
        assert out.tool_version == "R version 4.3.0"

    @patch("src.tools.gsea.reactome.detect_version", return_value=None)
    @patch("src.tools.gsea.reactome._count_significant_gsea", return_value=_SIG_COUNT)
    @patch("os.makedirs")
    @patch("src.tools.base.subprocess.run")
    def test_r_script_path_as_positional_arg(
        self, mock_run, mock_makedirs, mock_count, mock_version
    ) -> None:
        mock_run.return_value = self._mock_proc()
        run_reactome_gsea(self._base_inp())
        called_cmd = mock_run.call_args[0][0]
        assert called_cmd[0] == "Rscript"
        assert called_cmd[1] == "--vanilla"
        assert called_cmd[2] == "/r/reactome_gsea.R"

    @patch("src.tools.gsea.reactome.detect_version", return_value=None)
    @patch("src.tools.gsea.reactome._count_significant_gsea", return_value=_SIG_COUNT)
    @patch("os.makedirs")
    @patch("src.tools.base.subprocess.run")
    def test_no_eval_in_command_args(
        self, mock_run, mock_makedirs, mock_count, mock_version
    ) -> None:
        mock_run.return_value = self._mock_proc()
        run_reactome_gsea(self._base_inp())
        called_cmd = mock_run.call_args[0][0]
        assert not any("eval(" in arg for arg in called_cmd)

    @patch("src.tools.gsea.reactome.detect_version", return_value=None)
    @patch("src.tools.gsea.reactome._count_significant_gsea", return_value=_SIG_COUNT)
    @patch("os.makedirs")
    @patch("src.tools.base.subprocess.run")
    def test_organism_passed_as_arg(
        self, mock_run, mock_makedirs, mock_count, mock_version
    ) -> None:
        mock_run.return_value = self._mock_proc()
        run_reactome_gsea(self._base_inp(organism="mouse"))
        called_cmd = mock_run.call_args[0][0]
        assert "mouse" in called_cmd

    @patch("src.tools.gsea.reactome.detect_version", return_value=None)
    @patch("src.tools.gsea.reactome._count_significant_gsea", return_value=_SIG_COUNT)
    @patch("os.makedirs")
    @patch("src.tools.base.subprocess.run")
    def test_nperm_passed_as_arg(self, mock_run, mock_makedirs, mock_count, mock_version) -> None:
        mock_run.return_value = self._mock_proc()
        run_reactome_gsea(self._base_inp(nperm=500))
        called_cmd = mock_run.call_args[0][0]
        assert "500" in called_cmd

    @patch("src.tools.gsea.reactome.detect_version", return_value=None)
    @patch("src.tools.gsea.reactome._count_significant_gsea", return_value=_SIG_COUNT)
    @patch("os.makedirs")
    @patch("src.tools.base.subprocess.run")
    def test_results_path_in_output(
        self, mock_run, mock_makedirs, mock_count, mock_version
    ) -> None:
        mock_run.return_value = self._mock_proc()
        out = run_reactome_gsea(self._base_inp())
        assert out.results_path.endswith("gsea_results.csv")

    @patch("src.tools.gsea.reactome.detect_version", return_value=None)
    @patch("src.tools.gsea.reactome._count_significant_gsea", return_value=_SIG_COUNT)
    @patch("os.makedirs")
    @patch("src.tools.base.subprocess.run")
    def test_enrichment_plots_dir_in_output(
        self, mock_run, mock_makedirs, mock_count, mock_version
    ) -> None:
        mock_run.return_value = self._mock_proc()
        out = run_reactome_gsea(self._base_inp())
        assert out.enrichment_plots_dir.endswith("plots")

    @patch("src.tools.gsea.reactome.detect_version", return_value=None)
    @patch("os.makedirs")
    @patch("src.tools.base.subprocess.run")
    def test_nonzero_exit_raises_tool_execution_error(
        self, mock_run, mock_makedirs, mock_version
    ) -> None:
        mock_run.return_value = self._mock_proc(returncode=1)
        with pytest.raises(ToolExecutionError) as exc_info:
            run_reactome_gsea(self._base_inp())
        assert exc_info.value.tool_name == "reactome_gsea"

    @patch("src.tools.gsea.reactome.detect_version", return_value=None)
    @patch("os.makedirs")
    @patch("src.tools.base.subprocess.run")
    def test_timeout_raises_tool_timeout_error(self, mock_run, mock_makedirs, mock_version) -> None:
        mock_run.side_effect = subprocess.TimeoutExpired(cmd=["Rscript"], timeout=3600)
        with pytest.raises(ToolTimeoutError):
            run_reactome_gsea(self._base_inp())
