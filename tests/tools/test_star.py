"""Tests for run_star_align and the STAR log parser."""

from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from pydantic import ValidationError

from src.tools.alignment.parsers import parse_star_log_final
from src.tools.alignment.star import STARAlignInput, STARAlignOutput, run_star_align
from src.tools.base import ToolExecutionError, ToolTimeoutError

FIXTURE_DIR = Path(__file__).parent / "fixtures"

_EMPTY_STATS: dict = {
    "total_reads": 0,
    "uniquely_mapped_pct": 0.0,
    "multi_mapped_pct": 0.0,
    "unmapped_pct": 0.0,
}


# ── Parser tests ───────────────────────────────────────────────────────────────


class TestParseStarLogFinal:
    def _fixture_text(self) -> str:
        return (FIXTURE_DIR / "star_log_final.out").read_text()

    def test_total_reads(self) -> None:
        result = parse_star_log_final(self._fixture_text())
        assert result["total_reads"] == 45_000_000

    def test_uniquely_mapped_pct(self) -> None:
        result = parse_star_log_final(self._fixture_text())
        assert result["uniquely_mapped_pct"] == pytest.approx(93.33)

    def test_multi_mapped_pct(self) -> None:
        result = parse_star_log_final(self._fixture_text())
        assert result["multi_mapped_pct"] == pytest.approx(3.00)

    def test_unmapped_pct_is_sum(self) -> None:
        # fixture has 0.05 + 3.00 + 0.52 = 3.57
        result = parse_star_log_final(self._fixture_text())
        assert result["unmapped_pct"] == pytest.approx(3.57)

    def test_empty_text_returns_defaults(self) -> None:
        result = parse_star_log_final("")
        assert result["total_reads"] == 0
        assert result["uniquely_mapped_pct"] == 0.0
        assert result["unmapped_pct"] == 0.0

    def test_skips_lines_without_pipe(self) -> None:
        text = "No pipe here\nNumber of input reads |	1000\n"
        result = parse_star_log_final(text)
        assert result["total_reads"] == 1000

    def test_partial_log_preserves_defaults(self) -> None:
        text = "Uniquely mapped reads % |	85.50%\n"
        result = parse_star_log_final(text)
        assert result["uniquely_mapped_pct"] == pytest.approx(85.50)
        assert result["total_reads"] == 0

    def test_invalid_integer_skipped(self) -> None:
        text = "Number of input reads |	N/A\n"
        result = parse_star_log_final(text)
        assert result["total_reads"] == 0


# ── STARAlignInput validation ──────────────────────────────────────────────────


class TestSTARAlignInput:
    def _base(self, **kwargs) -> STARAlignInput:  # type: ignore[no-untyped-def]
        return STARAlignInput(
            fastq_r1="/data/ctrl_R1.fastq.gz",
            genome_dir="/ref/star_index",
            output_prefix="/out/ctrl_",
            **kwargs,
        )

    def test_valid_defaults(self) -> None:
        inp = self._base()
        assert inp.threads == 8
        assert inp.alignment_mode == "genome"
        assert inp.quantification_mode == "GeneCounts"
        assert inp.extra_args == []

    def test_valid_paired_end(self) -> None:
        inp = self._base(fastq_r2="/data/ctrl_R2.fastq.gz")
        assert inp.fastq_r2 == "/data/ctrl_R2.fastq.gz"

    def test_fastq_r2_optional(self) -> None:
        inp = self._base(fastq_r2=None)
        assert inp.fastq_r2 is None

    def test_threads_zero_raises(self) -> None:
        with pytest.raises(ValidationError):
            self._base(threads=0)

    def test_threads_above_max_raises(self) -> None:
        with pytest.raises(ValidationError):
            self._base(threads=257)

    def test_alignment_mode_both(self) -> None:
        inp = self._base(alignment_mode="both")
        assert inp.alignment_mode == "both"

    def test_invalid_alignment_mode_raises(self) -> None:
        with pytest.raises(ValidationError):
            self._base(alignment_mode="invalid")  # type: ignore[arg-type]

    def test_extra_args_stored(self) -> None:
        inp = self._base(extra_args=["--outFilterMismatchNmax", "2"])
        assert inp.extra_args == ["--outFilterMismatchNmax", "2"]


# ── run_star_align (subprocess mocked) ────────────────────────────────────────


class TestRunStarAlign:
    def _mock_proc(self, returncode: int = 0) -> MagicMock:
        proc = MagicMock(spec=subprocess.CompletedProcess)
        proc.returncode = returncode
        proc.stdout = b""
        proc.stderr = b""
        return proc

    def _base_inp(self, **kwargs) -> STARAlignInput:  # type: ignore[no-untyped-def]
        return STARAlignInput(
            fastq_r1="/data/ctrl_R1.fastq.gz",
            genome_dir="/ref/star",
            output_prefix="/out/ctrl_",
            **kwargs,
        )

    @patch("src.tools.alignment.star.detect_version", return_value="STAR_2.7.11a")
    @patch("src.tools.alignment.star._read_log_final", return_value=_EMPTY_STATS)
    @patch("os.makedirs")
    @patch("src.tools.base.subprocess.run")
    def test_genome_mode_single_subprocess_call(
        self, mock_run, mock_makedirs, mock_log, mock_version
    ) -> None:
        mock_run.return_value = self._mock_proc()
        out = run_star_align(self._base_inp(alignment_mode="genome"))
        assert isinstance(out, STARAlignOutput)
        assert mock_run.call_count == 1

    @patch("src.tools.alignment.star.detect_version", return_value=None)
    @patch("src.tools.alignment.star._read_log_final", return_value=_EMPTY_STATS)
    @patch("os.makedirs")
    @patch("src.tools.base.subprocess.run")
    def test_transcriptome_mode_single_subprocess_call(
        self, mock_run, mock_makedirs, mock_log, mock_version
    ) -> None:
        mock_run.return_value = self._mock_proc()
        out = run_star_align(self._base_inp(alignment_mode="transcriptome"))
        assert mock_run.call_count == 1
        assert out.transcriptome_bam_path is not None
        assert "toTranscriptome" in out.transcriptome_bam_path

    @patch("src.tools.alignment.star.detect_version", return_value="STAR_2.7.11a")
    @patch("src.tools.alignment.star._read_log_final", return_value=_EMPTY_STATS)
    @patch("os.makedirs")
    @patch("src.tools.base.subprocess.run")
    def test_both_mode_triggers_two_subprocess_calls(
        self, mock_run, mock_makedirs, mock_log, mock_version
    ) -> None:
        mock_run.return_value = self._mock_proc()
        out = run_star_align(self._base_inp(alignment_mode="both"))
        assert mock_run.call_count == 2
        assert out.gene_counts_path is not None
        assert out.transcriptome_bam_path is not None

    @patch("src.tools.alignment.star.detect_version", return_value="STAR_2.7.11a")
    @patch("src.tools.alignment.star._read_log_final", return_value=_EMPTY_STATS)
    @patch("os.makedirs")
    @patch("src.tools.base.subprocess.run")
    def test_tool_version_in_output(self, mock_run, mock_makedirs, mock_log, mock_version) -> None:
        mock_run.return_value = self._mock_proc()
        out = run_star_align(self._base_inp())
        assert out.tool_version == "STAR_2.7.11a"

    @patch("src.tools.alignment.star.detect_version", return_value=None)
    @patch("os.makedirs")
    @patch("src.tools.base.subprocess.run")
    def test_nonzero_exit_raises_tool_execution_error(
        self, mock_run, mock_makedirs, mock_version
    ) -> None:
        mock_run.return_value = self._mock_proc(returncode=1)
        with pytest.raises(ToolExecutionError) as exc_info:
            run_star_align(self._base_inp())
        assert exc_info.value.tool_name == "STAR"
        assert exc_info.value.exit_code == 1

    @patch("src.tools.alignment.star.detect_version", return_value=None)
    @patch("os.makedirs")
    @patch("src.tools.base.subprocess.run")
    def test_timeout_raises_tool_timeout_error(self, mock_run, mock_makedirs, mock_version) -> None:
        mock_run.side_effect = subprocess.TimeoutExpired(cmd=["STAR"], timeout=3600)
        with pytest.raises(ToolTimeoutError):
            run_star_align(self._base_inp())

    @patch("src.tools.alignment.star.detect_version", return_value=None)
    @patch("src.tools.alignment.star._read_log_final", return_value=_EMPTY_STATS)
    @patch("os.makedirs")
    @patch("src.tools.base.subprocess.run")
    def test_extra_args_passed_to_subprocess(
        self, mock_run, mock_makedirs, mock_log, mock_version
    ) -> None:
        mock_run.return_value = self._mock_proc()
        inp = self._base_inp(extra_args=["--outFilterMismatchNmax", "2"])
        run_star_align(inp)
        called_cmd = mock_run.call_args[0][0]
        assert "--outFilterMismatchNmax" in called_cmd
        assert "2" in called_cmd

    @patch("src.tools.alignment.star.detect_version", return_value=None)
    @patch("src.tools.alignment.star._read_log_final", return_value=_EMPTY_STATS)
    @patch("os.makedirs")
    @patch("src.tools.base.subprocess.run")
    def test_gene_counts_path_set_for_genome_mode(
        self, mock_run, mock_makedirs, mock_log, mock_version
    ) -> None:
        mock_run.return_value = self._mock_proc()
        out = run_star_align(self._base_inp(alignment_mode="genome"))
        assert out.gene_counts_path is not None
        assert "ReadsPerGene" in out.gene_counts_path

    @patch("src.tools.alignment.star.detect_version", return_value=None)
    @patch("src.tools.alignment.star._read_log_final", return_value=_EMPTY_STATS)
    @patch("os.makedirs")
    @patch("src.tools.base.subprocess.run")
    def test_transcriptome_bam_none_for_genome_mode(
        self, mock_run, mock_makedirs, mock_log, mock_version
    ) -> None:
        mock_run.return_value = self._mock_proc()
        out = run_star_align(self._base_inp(alignment_mode="genome"))
        assert out.transcriptome_bam_path is None

    @patch("src.tools.alignment.star.detect_version", return_value=None)
    @patch("src.tools.alignment.star._read_log_final", return_value=_EMPTY_STATS)
    @patch("os.makedirs")
    @patch("src.tools.base.subprocess.run")
    def test_paired_end_r2_included_in_command(
        self, mock_run, mock_makedirs, mock_log, mock_version
    ) -> None:
        mock_run.return_value = self._mock_proc()
        inp = self._base_inp(fastq_r2="/data/ctrl_R2.fastq.gz")
        run_star_align(inp)
        called_cmd = mock_run.call_args[0][0]
        assert "/data/ctrl_R2.fastq.gz" in called_cmd

    @patch("src.tools.alignment.star.detect_version", return_value=None)
    @patch("src.tools.alignment.star._read_log_final", return_value=_EMPTY_STATS)
    @patch("os.makedirs")
    @patch("src.tools.base.subprocess.run")
    def test_gz_input_adds_readfiles_command(
        self, mock_run, mock_makedirs, mock_log, mock_version
    ) -> None:
        mock_run.return_value = self._mock_proc()
        run_star_align(self._base_inp())  # fastq_r1 ends with .gz
        called_cmd = mock_run.call_args[0][0]
        assert "--readFilesCommand" in called_cmd
        assert "zcat" in called_cmd

    @patch("src.tools.alignment.star.detect_version", return_value=None)
    @patch("src.tools.alignment.star._read_log_final", return_value=_EMPTY_STATS)
    @patch("os.makedirs")
    @patch("src.tools.base.subprocess.run")
    def test_alignment_stats_from_log_parser(
        self, mock_run, mock_makedirs, mock_log, mock_version
    ) -> None:
        mock_run.return_value = self._mock_proc()
        mock_log.return_value = {"total_reads": 45_000_000, "uniquely_mapped_pct": 93.33}
        out = run_star_align(self._base_inp())
        assert out.alignment_stats["total_reads"] == 45_000_000
        assert out.alignment_stats["uniquely_mapped_pct"] == pytest.approx(93.33)
