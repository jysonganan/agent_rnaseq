"""Tests for run_rmats and the rMATS parsers."""

from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import MagicMock, mock_open, patch

import pytest
from pydantic import ValidationError

from src.tools.base import ToolExecutionError, ToolTimeoutError
from src.tools.splicing.parsers import count_rmats_significant, parse_rmats_summary
from src.tools.splicing.rmats import RMATSInput, RMATSOutput, run_rmats

FIXTURE_DIR = Path(__file__).parent / "fixtures"

SUMMARY_TEXT = (FIXTURE_DIR / "rmats_summary.txt").read_text()
JC_TEXT = (FIXTURE_DIR / "rmats_SE.MATS.JC.txt").read_text()

_SUMMARY_COUNTS = {
    "SE": 120,
    "A5SS": 25,
    "A3SS": 18,
    "MXE": 40,
    "RI": 55,
}


# ── parse_rmats_summary ────────────────────────────────────────────────────────


class TestParseRmatsSummary:
    def test_se_count(self) -> None:
        result = parse_rmats_summary(SUMMARY_TEXT)
        assert result["SE"] == 120

    def test_a5ss_count(self) -> None:
        result = parse_rmats_summary(SUMMARY_TEXT)
        assert result["A5SS"] == 25

    def test_all_event_types_present(self) -> None:
        result = parse_rmats_summary(SUMMARY_TEXT)
        assert set(result.keys()) == {"SE", "A5SS", "A3SS", "MXE", "RI"}

    def test_skips_header_row(self) -> None:
        result = parse_rmats_summary(SUMMARY_TEXT)
        assert "EventType" not in result

    def test_empty_text_returns_empty_dict(self) -> None:
        result = parse_rmats_summary("")
        assert result == {}

    def test_comment_lines_skipped(self) -> None:
        text = "# comment\nSE\t500\t30\n"
        result = parse_rmats_summary(text)
        assert result == {"SE": 30}

    def test_ri_count(self) -> None:
        result = parse_rmats_summary(SUMMARY_TEXT)
        assert result["RI"] == 55


# ── count_rmats_significant ────────────────────────────────────────────────────


class TestCountRmatsSignificant:
    def test_two_significant_events(self) -> None:
        # FDR values in fixture: 0.01, 0.60, 0.02 → 2 pass the 0.05 threshold
        result = count_rmats_significant(JC_TEXT)
        assert result == 2

    def test_non_significant_excluded(self) -> None:
        # Row 2 has FDR=0.60; confirm it is not counted
        result = count_rmats_significant(JC_TEXT, fdr_threshold=0.05)
        assert result < 3

    def test_header_skipped(self) -> None:
        # Header starts with non-integer "ID"; ensure count stays correct
        result = count_rmats_significant(JC_TEXT)
        assert result == 2

    def test_empty_text_returns_zero(self) -> None:
        assert count_rmats_significant("") == 0

    def test_custom_fdr_threshold(self) -> None:
        # With threshold 0.005, FDR=0.01 and 0.02 both fail → 0
        assert count_rmats_significant(JC_TEXT, fdr_threshold=0.005) == 0

    def test_permissive_fdr_threshold(self) -> None:
        # With threshold 1.0, all 3 data rows pass
        assert count_rmats_significant(JC_TEXT, fdr_threshold=1.0) == 3


# ── RMATSInput validation ──────────────────────────────────────────────────────


class TestRMATSInput:
    def _base(self, **kwargs) -> RMATSInput:  # type: ignore[no-untyped-def]
        return RMATSInput(
            bam_list_b1=["/data/ctrl1.bam"],
            bam_list_b2=["/data/treat1.bam"],
            gtf_path="/ref/GRCh38.gtf",
            output_dir="/out/rmats",
            read_length=150,
            **kwargs,
        )

    def test_valid_defaults(self) -> None:
        inp = self._base()
        assert inp.paired_stats is True
        assert inp.novelSS is False
        assert inp.extra_args == []

    def test_b1_min_length_enforced(self) -> None:
        with pytest.raises(ValidationError):
            RMATSInput(
                bam_list_b1=[],
                bam_list_b2=["/data/treat1.bam"],
                gtf_path="/ref/GRCh38.gtf",
                output_dir="/out/rmats",
                read_length=150,
            )

    def test_b2_min_length_enforced(self) -> None:
        with pytest.raises(ValidationError):
            RMATSInput(
                bam_list_b1=["/data/ctrl1.bam"],
                bam_list_b2=[],
                gtf_path="/ref/GRCh38.gtf",
                output_dir="/out/rmats",
                read_length=150,
            )

    def test_read_length_ge_1(self) -> None:
        with pytest.raises(ValidationError):
            RMATSInput(
                bam_list_b1=["/data/ctrl1.bam"],
                bam_list_b2=["/data/treat1.bam"],
                gtf_path="/ref/GRCh38.gtf",
                output_dir="/out/rmats",
                read_length=0,
            )

    def test_novel_ss_enabled(self) -> None:
        inp = self._base(novelSS=True)
        assert inp.novelSS is True

    def test_multiple_bams(self) -> None:
        inp = RMATSInput(
            bam_list_b1=["/data/ctrl1.bam", "/data/ctrl2.bam"],
            bam_list_b2=["/data/treat1.bam", "/data/treat2.bam"],
            gtf_path="/ref/GRCh38.gtf",
            output_dir="/out/rmats",
            read_length=150,
        )
        assert len(inp.bam_list_b1) == 2
        assert len(inp.bam_list_b2) == 2


# ── run_rmats (subprocess mocked) ─────────────────────────────────────────────


class TestRunRmats:
    def _mock_proc(self, returncode: int = 0) -> MagicMock:
        proc = MagicMock(spec=subprocess.CompletedProcess)
        proc.returncode = returncode
        proc.stdout = b""
        proc.stderr = b""
        return proc

    def _base_inp(self, **kwargs) -> RMATSInput:  # type: ignore[no-untyped-def]
        return RMATSInput(
            bam_list_b1=["/data/ctrl1.bam", "/data/ctrl2.bam"],
            bam_list_b2=["/data/treat1.bam", "/data/treat2.bam"],
            gtf_path="/ref/GRCh38.gtf",
            output_dir="/out/rmats",
            read_length=150,
            **kwargs,
        )

    @patch("src.tools.splicing.rmats.detect_version", return_value=None)
    @patch("src.tools.splicing.rmats._read_event_counts", return_value=_SUMMARY_COUNTS)
    @patch("os.makedirs")
    @patch("builtins.open", new_callable=mock_open)
    @patch("src.tools.base.subprocess.run")
    def test_success_returns_output(
        self, mock_run, mock_open_, mock_makedirs, mock_counts, mock_version
    ) -> None:
        mock_run.return_value = self._mock_proc()
        out = run_rmats(self._base_inp())
        assert isinstance(out, RMATSOutput)

    @patch("src.tools.splicing.rmats.detect_version", return_value=None)
    @patch("src.tools.splicing.rmats._read_event_counts", return_value=_SUMMARY_COUNTS)
    @patch("os.makedirs")
    @patch("builtins.open", new_callable=mock_open)
    @patch("src.tools.base.subprocess.run")
    def test_significant_se_count(
        self, mock_run, mock_open_, mock_makedirs, mock_counts, mock_version
    ) -> None:
        mock_run.return_value = self._mock_proc()
        out = run_rmats(self._base_inp())
        assert out.significant_events_count["SE"] == 120

    @patch("src.tools.splicing.rmats.detect_version", return_value=None)
    @patch("src.tools.splicing.rmats._read_event_counts", return_value=_SUMMARY_COUNTS)
    @patch("os.makedirs")
    @patch("builtins.open", new_callable=mock_open)
    @patch("src.tools.base.subprocess.run")
    def test_event_types_list(
        self, mock_run, mock_open_, mock_makedirs, mock_counts, mock_version
    ) -> None:
        mock_run.return_value = self._mock_proc()
        out = run_rmats(self._base_inp())
        assert set(out.event_types) == {"SE", "A5SS", "A3SS", "MXE", "RI"}

    @patch("src.tools.splicing.rmats.detect_version", return_value=None)
    @patch("src.tools.splicing.rmats._read_event_counts", return_value=_SUMMARY_COUNTS)
    @patch("os.makedirs")
    @patch("builtins.open", new_callable=mock_open)
    @patch("src.tools.base.subprocess.run")
    def test_output_dir_preserved(
        self, mock_run, mock_open_, mock_makedirs, mock_counts, mock_version
    ) -> None:
        mock_run.return_value = self._mock_proc()
        out = run_rmats(self._base_inp())
        assert out.output_dir == "/out/rmats"

    @patch("src.tools.splicing.rmats.detect_version", return_value=None)
    @patch("src.tools.splicing.rmats._read_event_counts", return_value=_SUMMARY_COUNTS)
    @patch("os.makedirs")
    @patch("builtins.open", new_callable=mock_open)
    @patch("src.tools.base.subprocess.run")
    def test_novel_ss_flag_in_command(
        self, mock_run, mock_open_, mock_makedirs, mock_counts, mock_version
    ) -> None:
        mock_run.return_value = self._mock_proc()
        run_rmats(self._base_inp(novelSS=True))
        called_cmd = mock_run.call_args[0][0]
        assert "--novelSS" in called_cmd

    @patch("src.tools.splicing.rmats.detect_version", return_value=None)
    @patch("src.tools.splicing.rmats._read_event_counts", return_value=_SUMMARY_COUNTS)
    @patch("os.makedirs")
    @patch("builtins.open", new_callable=mock_open)
    @patch("src.tools.base.subprocess.run")
    def test_novel_ss_omitted_when_false(
        self, mock_run, mock_open_, mock_makedirs, mock_counts, mock_version
    ) -> None:
        mock_run.return_value = self._mock_proc()
        run_rmats(self._base_inp(novelSS=False))
        called_cmd = mock_run.call_args[0][0]
        assert "--novelSS" not in called_cmd

    @patch("src.tools.splicing.rmats.detect_version", return_value=None)
    @patch("src.tools.splicing.rmats._read_event_counts", return_value=_SUMMARY_COUNTS)
    @patch("os.makedirs")
    @patch("builtins.open", new_callable=mock_open)
    @patch("src.tools.base.subprocess.run")
    def test_paired_stats_in_command(
        self, mock_run, mock_open_, mock_makedirs, mock_counts, mock_version
    ) -> None:
        mock_run.return_value = self._mock_proc()
        run_rmats(self._base_inp(paired_stats=True))
        called_cmd = mock_run.call_args[0][0]
        assert "-t" in called_cmd
        assert "paired" in called_cmd

    @patch("src.tools.splicing.rmats.detect_version", return_value=None)
    @patch("src.tools.splicing.rmats._read_event_counts", return_value=_SUMMARY_COUNTS)
    @patch("os.makedirs")
    @patch("builtins.open", new_callable=mock_open)
    @patch("src.tools.base.subprocess.run")
    def test_single_mode_in_command(
        self, mock_run, mock_open_, mock_makedirs, mock_counts, mock_version
    ) -> None:
        mock_run.return_value = self._mock_proc()
        run_rmats(self._base_inp(paired_stats=False))
        called_cmd = mock_run.call_args[0][0]
        assert "single" in called_cmd

    @patch("src.tools.splicing.rmats.detect_version", return_value=None)
    @patch("os.makedirs")
    @patch("builtins.open", new_callable=mock_open)
    @patch("src.tools.base.subprocess.run")
    def test_nonzero_exit_raises_tool_execution_error(
        self, mock_run, mock_open_, mock_makedirs, mock_version
    ) -> None:
        mock_run.return_value = self._mock_proc(returncode=1)
        with pytest.raises(ToolExecutionError) as exc_info:
            run_rmats(self._base_inp())
        assert exc_info.value.tool_name == "rMATS"

    @patch("src.tools.splicing.rmats.detect_version", return_value=None)
    @patch("os.makedirs")
    @patch("builtins.open", new_callable=mock_open)
    @patch("src.tools.base.subprocess.run")
    def test_timeout_raises_tool_timeout_error(
        self, mock_run, mock_open_, mock_makedirs, mock_version
    ) -> None:
        mock_run.side_effect = subprocess.TimeoutExpired(cmd=["rmats.py"], timeout=7200)
        with pytest.raises(ToolTimeoutError):
            run_rmats(self._base_inp())
