"""Tests for run_rseqc and the RSeQC output parsers."""

from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from pydantic import ValidationError

from src.tools.base import ToolExecutionError
from src.tools.qc.parsers import parse_rseqc_infer_experiment, parse_rseqc_read_distribution
from src.tools.qc.rseqc import RSeQCInput, RSeQCOutput, run_rseqc

FIXTURE_DIR = Path(__file__).parent / "fixtures"


# ── read_distribution parser ───────────────────────────────────────────────────


class TestParseRSeQCReadDistribution:
    def _fixture_text(self) -> str:
        return (FIXTURE_DIR / "rseqc_read_distribution.txt").read_text()

    def test_parses_cds_exons(self) -> None:
        result = parse_rseqc_read_distribution(self._fixture_text())
        assert result["CDS_Exons"] == 38_000_000

    def test_parses_introns(self) -> None:
        result = parse_rseqc_read_distribution(self._fixture_text())
        assert result["Introns"] == 250_000

    def test_parses_total_reads(self) -> None:
        result = parse_rseqc_read_distribution(self._fixture_text())
        assert result["Total_Reads"] == 45_000_000

    def test_parses_total_assigned_tags(self) -> None:
        result = parse_rseqc_read_distribution(self._fixture_text())
        assert result["Total_Assigned_Tags"] == 42_750_000

    def test_parses_utr_regions(self) -> None:
        result = parse_rseqc_read_distribution(self._fixture_text())
        assert "5'UTR_Exons" in result
        assert result["3'UTR_Exons"] == 2_000_000

    def test_parses_tss_tes_regions(self) -> None:
        result = parse_rseqc_read_distribution(self._fixture_text())
        assert result["TSS_up_1kb"] == 150_000
        assert result["TES_down_10kb"] == 300_000

    def test_empty_text_returns_empty(self) -> None:
        assert parse_rseqc_read_distribution("") == {}

    def test_skips_header_line(self) -> None:
        text = "Group               Total_bases         Tag_count           Tags/Kb\n"
        result = parse_rseqc_read_distribution(text)
        assert "Group" not in result


# ── infer_experiment parser ────────────────────────────────────────────────────


class TestParseRSeQCInferExperiment:
    def _fixture_text(self) -> str:
        return (FIXTURE_DIR / "rseqc_infer_experiment.txt").read_text()

    def test_library_type_paired(self) -> None:
        result = parse_rseqc_infer_experiment(self._fixture_text())
        assert result["library_type"] == "PairEnd"

    def test_undetermined_fraction(self) -> None:
        result = parse_rseqc_infer_experiment(self._fixture_text())
        assert result["undetermined"] == pytest.approx(0.0032)

    def test_sense_fraction(self) -> None:
        result = parse_rseqc_infer_experiment(self._fixture_text())
        assert result["sense"] == pytest.approx(0.0065)

    def test_antisense_fraction(self) -> None:
        result = parse_rseqc_infer_experiment(self._fixture_text())
        assert result["antisense"] == pytest.approx(0.9903)

    def test_single_end_detection(self) -> None:
        text = "This is SingleEnd Data\nFraction of reads failed to determine: 0.01\n"
        result = parse_rseqc_infer_experiment(text)
        assert result["library_type"] == "SingleEnd"

    def test_unknown_library_type(self) -> None:
        result = parse_rseqc_infer_experiment("No type information here\n")
        assert result["library_type"] == "Unknown"

    def test_empty_text_returns_defaults(self) -> None:
        result = parse_rseqc_infer_experiment("")
        assert result["library_type"] == "Unknown"
        assert result["undetermined"] == 0.0


# ── RSeQCInput validation ──────────────────────────────────────────────────────


class TestRSeQCInput:
    def test_valid_defaults(self) -> None:
        inp = RSeQCInput(
            bam_path="/data/ctrl.bam",
            bam_index_path="/data/ctrl.bam.bai",
            bed_annotation_path="/ref/genes.bed",
            output_prefix="/out/ctrl",
        )
        assert "read_distribution" in inp.modules

    def test_invalid_module_raises(self) -> None:
        with pytest.raises(ValidationError):
            RSeQCInput(
                bam_path="/data/ctrl.bam",
                bam_index_path="/data/ctrl.bai",
                bed_annotation_path="/ref/genes.bed",
                output_prefix="/out/ctrl",
                modules=["nonexistent_module"],
            )

    def test_single_module(self) -> None:
        inp = RSeQCInput(
            bam_path="/data/ctrl.bam",
            bam_index_path="/data/ctrl.bai",
            bed_annotation_path="/ref/genes.bed",
            output_prefix="/out/ctrl",
            modules=["read_distribution"],
        )
        assert inp.modules == ["read_distribution"]


# ── run_rseqc (subprocess mocked) ─────────────────────────────────────────────


RD_FIXTURE = (FIXTURE_DIR / "rseqc_read_distribution.txt").read_text()
IE_FIXTURE = (FIXTURE_DIR / "rseqc_infer_experiment.txt").read_text()


class TestRunRSeQC:
    def _mock_proc(self, stdout: str = "", returncode: int = 0) -> MagicMock:
        proc = MagicMock(spec=subprocess.CompletedProcess)
        proc.returncode = returncode
        proc.stdout = stdout.encode()
        proc.stderr = b""
        return proc

    def _base_inp(self, modules: list[str] | None = None) -> RSeQCInput:
        return RSeQCInput(
            bam_path="/data/ctrl.bam",
            bam_index_path="/data/ctrl.bam.bai",
            bed_annotation_path="/ref/genes.bed",
            output_prefix="/out/ctrl",
            modules=modules or ["read_distribution"],
        )

    @patch("src.tools.qc.rseqc.detect_version", return_value="read_distribution.py 5.0.1")
    @patch("os.makedirs")
    @patch("builtins.open", MagicMock())
    @patch("src.tools.base.subprocess.run")
    def test_read_distribution_parsed(self, mock_run, mock_makedirs, mock_version) -> None:
        mock_run.return_value = self._mock_proc(stdout=RD_FIXTURE)
        out = run_rseqc(self._base_inp(["read_distribution"]))
        assert isinstance(out, RSeQCOutput)
        assert out.read_distribution["CDS_Exons"] == 38_000_000
        assert "read_distribution" in out.module_outputs

    @patch("src.tools.qc.rseqc.detect_version", return_value=None)
    @patch("os.makedirs")
    @patch("builtins.open", MagicMock())
    @patch("src.tools.base.subprocess.run")
    def test_infer_experiment_parsed(self, mock_run, mock_makedirs, mock_version) -> None:
        mock_run.return_value = self._mock_proc(stdout=IE_FIXTURE)
        out = run_rseqc(self._base_inp(["infer_experiment"]))
        assert out.infer_experiment_result["library_type"] == "PairEnd"
        assert out.infer_experiment_result["antisense"] == pytest.approx(0.9903)

    @patch("src.tools.qc.rseqc.detect_version", return_value=None)
    @patch("os.makedirs")
    @patch("src.tools.base.subprocess.run")
    def test_nonzero_exit_raises(self, mock_run, mock_makedirs, mock_version) -> None:
        mock_run.return_value = self._mock_proc(returncode=1)
        with pytest.raises(ToolExecutionError) as exc_info:
            run_rseqc(self._base_inp())
        assert exc_info.value.tool_name == "rseqc"

    @patch("src.tools.qc.rseqc.detect_version", return_value=None)
    @patch("os.makedirs")
    @patch("builtins.open", MagicMock())
    @patch("src.tools.base.subprocess.run")
    def test_junction_saturation_module(self, mock_run, mock_makedirs, mock_version) -> None:
        mock_run.return_value = self._mock_proc()
        out = run_rseqc(self._base_inp(["junction_saturation"]))
        assert "junction_saturation" in out.module_outputs
        # Junction saturation records output_prefix, not a txt file
        assert out.module_outputs["junction_saturation"] == "/out/ctrl"

    @patch("src.tools.qc.rseqc.detect_version", return_value=None)
    @patch("os.makedirs")
    @patch("builtins.open", MagicMock())
    @patch("src.tools.base.subprocess.run")
    def test_multiple_modules_run(self, mock_run, mock_makedirs, mock_version) -> None:
        # Alternate stdout depending on call count
        call_results = [
            self._mock_proc(stdout=RD_FIXTURE),
            self._mock_proc(stdout=IE_FIXTURE),
        ]
        mock_run.side_effect = call_results
        out = run_rseqc(self._base_inp(["read_distribution", "infer_experiment"]))
        assert mock_run.call_count == 2
        assert out.read_distribution["Total_Reads"] == 45_000_000
        assert out.infer_experiment_result["library_type"] == "PairEnd"

    @patch("src.tools.qc.rseqc.detect_version", return_value=None)
    @patch("os.makedirs")
    @patch("src.tools.base.subprocess.run")
    def test_timeout_raises(self, mock_run, mock_makedirs, mock_version) -> None:
        mock_run.side_effect = subprocess.TimeoutExpired(cmd=["read_distribution.py"], timeout=30)
        from src.tools.base import ToolTimeoutError

        with pytest.raises(ToolTimeoutError):
            run_rseqc(self._base_inp())
