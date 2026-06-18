"""Tests for run_htseq_count and the HTSeq counts parser."""

from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import MagicMock, mock_open, patch

import pytest
from pydantic import ValidationError

from src.tools.base import ToolExecutionError, ToolTimeoutError
from src.tools.quantification.htseq import HTSeqInput, HTSeqOutput, run_htseq_count
from src.tools.quantification.parsers import parse_htseq_counts

FIXTURE_DIR = Path(__file__).parent / "fixtures"

HTSEQ_TEXT = (FIXTURE_DIR / "htseq_counts.tsv").read_text()

# fixture totals:
# counted_reads = 150 + 20 + 300 + 75 + 89 = 634
# no_feature = 5000, ambiguous = 200, too_low_aQual = 0, not_aligned = 100, not_unique = 500
# total = 634 + 5000 + 200 + 0 + 100 + 500 = 6434


# ── Parser tests ───────────────────────────────────────────────────────────────


class TestParseHTSeqCounts:
    def test_counted_reads(self) -> None:
        result = parse_htseq_counts(HTSEQ_TEXT)
        assert result["counted_reads"] == 634

    def test_no_feature_reads(self) -> None:
        result = parse_htseq_counts(HTSEQ_TEXT)
        assert result["no_feature_reads"] == 5000

    def test_ambiguous_reads(self) -> None:
        result = parse_htseq_counts(HTSEQ_TEXT)
        assert result["ambiguous_reads"] == 200

    def test_total_reads(self) -> None:
        result = parse_htseq_counts(HTSEQ_TEXT)
        assert result["total_reads"] == 6434

    def test_too_low_aqual_zero(self) -> None:
        result = parse_htseq_counts(HTSEQ_TEXT)
        assert result["too_low_aqual_reads"] == 0

    def test_not_aligned_reads(self) -> None:
        result = parse_htseq_counts(HTSEQ_TEXT)
        assert result["not_aligned_reads"] == 100

    def test_empty_text_returns_zeros(self) -> None:
        result = parse_htseq_counts("")
        assert result["counted_reads"] == 0
        assert result["total_reads"] == 0

    def test_skips_malformed_lines(self) -> None:
        text = "not_a_tab_separated_line\nENSG001\t50\n"
        result = parse_htseq_counts(text)
        assert result["counted_reads"] == 50

    def test_skips_non_integer_counts(self) -> None:
        text = "ENSG001\tNA\n"
        result = parse_htseq_counts(text)
        assert result["counted_reads"] == 0

    def test_unknown_special_prefix_ignored(self) -> None:
        text = "__unknown_category\t999\nENSG001\t10\n"
        result = parse_htseq_counts(text)
        assert result["counted_reads"] == 10


# ── HTSeqInput validation ──────────────────────────────────────────────────────


class TestHTSeqInput:
    def _base(self, **kwargs) -> HTSeqInput:  # type: ignore[no-untyped-def]
        return HTSeqInput(
            bam_path="/data/ctrl.bam",
            gtf_path="/ref/genes.gtf",
            output_path="/out/counts.tsv",
            **kwargs,
        )

    def test_valid_defaults(self) -> None:
        inp = self._base()
        assert inp.stranded == "reverse"
        assert inp.mode == "union"
        assert inp.additional_args == []

    def test_stranded_yes(self) -> None:
        inp = self._base(stranded="yes")
        assert inp.stranded == "yes"

    def test_stranded_no(self) -> None:
        inp = self._base(stranded="no")
        assert inp.stranded == "no"

    def test_invalid_stranded_raises(self) -> None:
        with pytest.raises(ValidationError):
            self._base(stranded="forward")  # type: ignore[arg-type]

    def test_invalid_mode_raises(self) -> None:
        with pytest.raises(ValidationError):
            self._base(mode="strict")  # type: ignore[arg-type]

    def test_additional_args_stored(self) -> None:
        inp = self._base(additional_args=["--minaqual", "10"])
        assert inp.additional_args == ["--minaqual", "10"]


# ── run_htseq_count (subprocess mocked) ───────────────────────────────────────


class TestRunHTSeqCount:
    def _mock_proc(self, returncode: int = 0, stdout: bytes = b"") -> MagicMock:
        proc = MagicMock(spec=subprocess.CompletedProcess)
        proc.returncode = returncode
        proc.stdout = stdout
        proc.stderr = b""
        return proc

    def _base_inp(self, **kwargs) -> HTSeqInput:  # type: ignore[no-untyped-def]
        return HTSeqInput(
            bam_path="/data/ctrl.bam",
            gtf_path="/ref/genes.gtf",
            output_path="/out/counts.tsv",
            **kwargs,
        )

    @patch("src.tools.quantification.htseq.detect_version", return_value="HTSeq 2.0.5")
    @patch("os.makedirs")
    @patch("builtins.open", mock_open())
    @patch("src.tools.base.subprocess.run")
    def test_success_returns_htseq_output(self, mock_run, mock_makedirs, mock_version) -> None:
        mock_run.return_value = self._mock_proc(stdout=HTSEQ_TEXT.encode())
        out = run_htseq_count(self._base_inp())
        assert isinstance(out, HTSeqOutput)
        assert out.counted_reads == 634
        assert out.no_feature_reads == 5000
        assert out.total_reads == 6434

    @patch("src.tools.quantification.htseq.detect_version", return_value="HTSeq 2.0.5")
    @patch("os.makedirs")
    @patch("builtins.open", mock_open())
    @patch("src.tools.base.subprocess.run")
    def test_counts_path_in_output(self, mock_run, mock_makedirs, mock_version) -> None:
        mock_run.return_value = self._mock_proc(stdout=HTSEQ_TEXT.encode())
        out = run_htseq_count(self._base_inp())
        assert out.counts_path == "/out/counts.tsv"

    @patch("src.tools.quantification.htseq.detect_version", return_value="HTSeq 2.0.5")
    @patch("os.makedirs")
    @patch("builtins.open", mock_open())
    @patch("src.tools.base.subprocess.run")
    def test_tool_version_in_output(self, mock_run, mock_makedirs, mock_version) -> None:
        mock_run.return_value = self._mock_proc(stdout=HTSEQ_TEXT.encode())
        out = run_htseq_count(self._base_inp())
        assert out.tool_version == "HTSeq 2.0.5"

    @patch("src.tools.quantification.htseq.detect_version", return_value=None)
    @patch("os.makedirs")
    @patch("src.tools.base.subprocess.run")
    def test_nonzero_exit_raises_tool_execution_error(
        self, mock_run, mock_makedirs, mock_version
    ) -> None:
        mock_run.return_value = self._mock_proc(returncode=1)
        with pytest.raises(ToolExecutionError) as exc_info:
            run_htseq_count(self._base_inp())
        assert exc_info.value.tool_name == "htseq-count"

    @patch("src.tools.quantification.htseq.detect_version", return_value=None)
    @patch("os.makedirs")
    @patch("src.tools.base.subprocess.run")
    def test_timeout_raises_tool_timeout_error(self, mock_run, mock_makedirs, mock_version) -> None:
        mock_run.side_effect = subprocess.TimeoutExpired(cmd=["htseq-count"], timeout=3600)
        with pytest.raises(ToolTimeoutError):
            run_htseq_count(self._base_inp())

    @patch("src.tools.quantification.htseq.detect_version", return_value=None)
    @patch("os.makedirs")
    @patch("builtins.open", mock_open())
    @patch("src.tools.base.subprocess.run")
    def test_additional_args_in_command(self, mock_run, mock_makedirs, mock_version) -> None:
        mock_run.return_value = self._mock_proc(stdout=HTSEQ_TEXT.encode())
        inp = self._base_inp(additional_args=["--minaqual", "10"])
        run_htseq_count(inp)
        called_cmd = mock_run.call_args[0][0]
        assert "--minaqual" in called_cmd
        assert "10" in called_cmd

    @patch("src.tools.quantification.htseq.detect_version", return_value=None)
    @patch("os.makedirs")
    @patch("builtins.open", mock_open())
    @patch("src.tools.base.subprocess.run")
    def test_stranded_and_mode_in_command(self, mock_run, mock_makedirs, mock_version) -> None:
        mock_run.return_value = self._mock_proc(stdout=HTSEQ_TEXT.encode())
        inp = self._base_inp(stranded="yes", mode="intersection-strict")
        run_htseq_count(inp)
        called_cmd = mock_run.call_args[0][0]
        assert "--stranded" in called_cmd
        assert "yes" in called_cmd
        assert "--mode" in called_cmd
        assert "intersection-strict" in called_cmd
