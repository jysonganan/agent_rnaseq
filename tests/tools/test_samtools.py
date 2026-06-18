"""Tests for run_samtools_sort_index and the flagstat parser."""

from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from pydantic import ValidationError

from src.tools.alignment.parsers import parse_samtools_flagstat
from src.tools.alignment.samtools import SamtoolsInput, SamtoolsOutput, run_samtools_sort_index
from src.tools.base import ToolExecutionError, ToolTimeoutError

FIXTURE_DIR = Path(__file__).parent / "fixtures"


# ── Parser tests ───────────────────────────────────────────────────────────────


class TestParseSamtoolsFlagstat:
    def _fixture_text(self) -> str:
        return (FIXTURE_DIR / "samtools_flagstat.txt").read_text()

    def test_total_reads(self) -> None:
        result = parse_samtools_flagstat(self._fixture_text())
        assert result["total"] == 50_000_000

    def test_mapped_count(self) -> None:
        result = parse_samtools_flagstat(self._fixture_text())
        assert result["mapped"] == 49_000_000

    def test_mapped_pct(self) -> None:
        result = parse_samtools_flagstat(self._fixture_text())
        assert result["mapped_pct"] == pytest.approx(98.00)

    def test_properly_paired(self) -> None:
        result = parse_samtools_flagstat(self._fixture_text())
        assert result["properly_paired"] == 48_000_000

    def test_properly_paired_pct(self) -> None:
        result = parse_samtools_flagstat(self._fixture_text())
        assert result["properly_paired_pct"] == pytest.approx(96.00)

    def test_duplicates(self) -> None:
        result = parse_samtools_flagstat(self._fixture_text())
        assert result["duplicates"] == 6_000_000

    def test_secondary_zero(self) -> None:
        result = parse_samtools_flagstat(self._fixture_text())
        assert result["secondary"] == 0

    def test_singletons_zero(self) -> None:
        result = parse_samtools_flagstat(self._fixture_text())
        assert result["singletons"] == 0

    def test_read1_read2_counts(self) -> None:
        result = parse_samtools_flagstat(self._fixture_text())
        assert result["read1"] == 25_000_000
        assert result["read2"] == 25_000_000

    def test_empty_text_returns_empty(self) -> None:
        assert parse_samtools_flagstat("") == {}

    def test_partial_text(self) -> None:
        text = "10000 + 0 in total (QC-passed reads + QC-failed reads)\n"
        result = parse_samtools_flagstat(text)
        assert result["total"] == 10_000
        assert "mapped" not in result


# ── SamtoolsInput validation ───────────────────────────────────────────────────


class TestSamtoolsInput:
    def test_valid_defaults(self) -> None:
        inp = SamtoolsInput(bam_path="/data/ctrl.bam", output_prefix="/out/ctrl")
        assert inp.threads == 4

    def test_threads_zero_raises(self) -> None:
        with pytest.raises(ValidationError):
            SamtoolsInput(bam_path="/data/ctrl.bam", output_prefix="/out/ctrl", threads=0)

    def test_threads_above_max_raises(self) -> None:
        with pytest.raises(ValidationError):
            SamtoolsInput(bam_path="/data/ctrl.bam", output_prefix="/out/ctrl", threads=257)

    def test_custom_threads(self) -> None:
        inp = SamtoolsInput(bam_path="/data/ctrl.bam", output_prefix="/out/ctrl", threads=8)
        assert inp.threads == 8


# ── run_samtools_sort_index (subprocess mocked) ────────────────────────────────


FLAGSTAT_TEXT = (FIXTURE_DIR / "samtools_flagstat.txt").read_text()


class TestRunSamtoolsSortIndex:
    def _mock_proc(self, returncode: int = 0, stdout: bytes = b"") -> MagicMock:
        proc = MagicMock(spec=subprocess.CompletedProcess)
        proc.returncode = returncode
        proc.stdout = stdout
        proc.stderr = b""
        return proc

    def _base_inp(self) -> SamtoolsInput:
        return SamtoolsInput(bam_path="/data/ctrl.bam", output_prefix="/out/ctrl")

    @patch("src.tools.alignment.samtools.detect_version", return_value="samtools 1.19")
    @patch("os.makedirs")
    @patch("src.tools.base.subprocess.run")
    def test_success_three_subprocess_calls(self, mock_run, mock_makedirs, mock_version) -> None:
        mock_run.side_effect = [
            self._mock_proc(),  # sort
            self._mock_proc(),  # index
            self._mock_proc(stdout=FLAGSTAT_TEXT.encode()),  # flagstat
        ]
        out = run_samtools_sort_index(self._base_inp())
        assert isinstance(out, SamtoolsOutput)
        assert mock_run.call_count == 3

    @patch("src.tools.alignment.samtools.detect_version", return_value="samtools 1.19")
    @patch("os.makedirs")
    @patch("src.tools.base.subprocess.run")
    def test_sorted_bam_path(self, mock_run, mock_makedirs, mock_version) -> None:
        mock_run.side_effect = [
            self._mock_proc(),
            self._mock_proc(),
            self._mock_proc(stdout=FLAGSTAT_TEXT.encode()),
        ]
        out = run_samtools_sort_index(self._base_inp())
        assert out.sorted_bam_path == "/out/ctrl.sorted.bam"

    @patch("src.tools.alignment.samtools.detect_version", return_value=None)
    @patch("os.makedirs")
    @patch("src.tools.base.subprocess.run")
    def test_bai_path(self, mock_run, mock_makedirs, mock_version) -> None:
        mock_run.side_effect = [
            self._mock_proc(),
            self._mock_proc(),
            self._mock_proc(stdout=FLAGSTAT_TEXT.encode()),
        ]
        out = run_samtools_sort_index(self._base_inp())
        assert out.bai_path == "/out/ctrl.sorted.bam.bai"

    @patch("src.tools.alignment.samtools.detect_version", return_value="samtools 1.19")
    @patch("os.makedirs")
    @patch("src.tools.base.subprocess.run")
    def test_flagstat_parsed(self, mock_run, mock_makedirs, mock_version) -> None:
        mock_run.side_effect = [
            self._mock_proc(),
            self._mock_proc(),
            self._mock_proc(stdout=FLAGSTAT_TEXT.encode()),
        ]
        out = run_samtools_sort_index(self._base_inp())
        assert out.flagstat["total"] == 50_000_000
        assert out.flagstat["mapped"] == 49_000_000
        assert out.flagstat["mapped_pct"] == pytest.approx(98.00)

    @patch("src.tools.alignment.samtools.detect_version", return_value="samtools 1.19")
    @patch("os.makedirs")
    @patch("src.tools.base.subprocess.run")
    def test_tool_version_in_output(self, mock_run, mock_makedirs, mock_version) -> None:
        mock_run.side_effect = [
            self._mock_proc(),
            self._mock_proc(),
            self._mock_proc(stdout=FLAGSTAT_TEXT.encode()),
        ]
        out = run_samtools_sort_index(self._base_inp())
        assert out.tool_version == "samtools 1.19"

    @patch("src.tools.alignment.samtools.detect_version", return_value=None)
    @patch("os.makedirs")
    @patch("src.tools.base.subprocess.run")
    def test_sort_failure_raises_tool_execution_error(
        self, mock_run, mock_makedirs, mock_version
    ) -> None:
        mock_run.return_value = self._mock_proc(returncode=1)
        with pytest.raises(ToolExecutionError) as exc_info:
            run_samtools_sort_index(self._base_inp())
        assert exc_info.value.tool_name == "samtools"

    @patch("src.tools.alignment.samtools.detect_version", return_value=None)
    @patch("os.makedirs")
    @patch("src.tools.base.subprocess.run")
    def test_timeout_raises_tool_timeout_error(self, mock_run, mock_makedirs, mock_version) -> None:
        mock_run.side_effect = subprocess.TimeoutExpired(cmd=["samtools"], timeout=3600)
        with pytest.raises(ToolTimeoutError):
            run_samtools_sort_index(self._base_inp())

    @patch("src.tools.alignment.samtools.detect_version", return_value=None)
    @patch("os.makedirs")
    @patch("src.tools.base.subprocess.run")
    def test_sort_command_includes_threads_and_output(
        self, mock_run, mock_makedirs, mock_version
    ) -> None:
        mock_run.side_effect = [
            self._mock_proc(),
            self._mock_proc(),
            self._mock_proc(stdout=FLAGSTAT_TEXT.encode()),
        ]
        inp = SamtoolsInput(bam_path="/data/ctrl.bam", output_prefix="/out/ctrl", threads=8)
        run_samtools_sort_index(inp)
        sort_cmd = mock_run.call_args_list[0][0][0]
        assert "samtools" in sort_cmd
        assert "sort" in sort_cmd
        assert "-@" in sort_cmd
        assert "8" in sort_cmd
        assert "/out/ctrl.sorted.bam" in sort_cmd
