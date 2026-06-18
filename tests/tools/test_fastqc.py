"""Tests for run_fastqc and the FastQC summary parser."""

from __future__ import annotations

import io
import subprocess
import zipfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from pydantic import ValidationError

from src.tools.base import ToolExecutionError
from src.tools.qc.fastqc import (
    FastQCInput,
    FastQCOutput,
    _read_zip_summary,
    _sample_stem,
    run_fastqc,
)
from src.tools.qc.parsers import parse_fastqc_summary

FIXTURE_DIR = Path(__file__).parent / "fixtures"


# ── Parser tests ───────────────────────────────────────────────────────────────


class TestParseFastQCSummary:
    def _fixture_text(self) -> str:
        return (FIXTURE_DIR / "fastqc_summary.txt").read_text()

    def test_parses_all_modules(self) -> None:
        result = parse_fastqc_summary(self._fixture_text())
        assert len(result) == 10

    def test_pass_module(self) -> None:
        result = parse_fastqc_summary(self._fixture_text())
        assert result["Basic Statistics"] == "PASS"

    def test_warn_module(self) -> None:
        result = parse_fastqc_summary(self._fixture_text())
        assert result["Per base sequence content"] == "WARN"

    def test_fail_module(self) -> None:
        result = parse_fastqc_summary(self._fixture_text())
        assert result["Per sequence GC content"] == "FAIL"

    def test_empty_string_returns_empty_dict(self) -> None:
        assert parse_fastqc_summary("") == {}

    def test_skips_blank_lines(self) -> None:
        text = "\nPASS\tBasic Statistics\tfile.fq.gz\n\n"
        result = parse_fastqc_summary(text)
        assert result == {"Basic Statistics": "PASS"}

    def test_skips_malformed_lines(self) -> None:
        text = "not_enough_fields\n"
        result = parse_fastqc_summary(text)
        assert result == {}


# ── _sample_stem ───────────────────────────────────────────────────────────────


class TestSampleStem:
    def test_fastq_gz(self) -> None:
        assert _sample_stem("/data/ctrl_1_R1.fastq.gz") == "ctrl_1_R1"

    def test_fq_gz(self) -> None:
        assert _sample_stem("/data/sample.fq.gz") == "sample"

    def test_fastq(self) -> None:
        assert _sample_stem("/data/ctrl.fastq") == "ctrl"

    def test_no_recognized_suffix(self) -> None:
        assert _sample_stem("/data/sample.bam") == "sample.bam"


# ── FastQCInput validation ─────────────────────────────────────────────────────


class TestFastQCInput:
    def test_valid_single_end(self) -> None:
        inp = FastQCInput(fastq_paths=["/data/r1.fastq.gz"], output_dir="/out")
        assert inp.threads == 4

    def test_valid_paired_end(self) -> None:
        inp = FastQCInput(
            fastq_paths=["/data/r1.fastq.gz", "/data/r2.fastq.gz"],
            output_dir="/out",
        )
        assert len(inp.fastq_paths) == 2

    def test_empty_fastq_paths_raises(self) -> None:
        with pytest.raises(ValidationError):
            FastQCInput(fastq_paths=[], output_dir="/out")

    def test_three_paths_raises(self) -> None:
        with pytest.raises(ValidationError):
            FastQCInput(
                fastq_paths=["/a.fq.gz", "/b.fq.gz", "/c.fq.gz"],
                output_dir="/out",
            )

    def test_thread_bounds(self) -> None:
        with pytest.raises(ValidationError):
            FastQCInput(fastq_paths=["/r1.fq.gz"], output_dir="/out", threads=0)


# ── run_fastqc integration (subprocess mocked) ────────────────────────────────


def _make_fastqc_zip_bytes(summary_text: str, stem: str = "ctrl_1_R1") -> bytes:
    """Build a minimal in-memory FastQC ZIP for testing."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr(f"{stem}_fastqc/summary.txt", summary_text)
    return buf.getvalue()


SUMMARY_TEXT = (FIXTURE_DIR / "fastqc_summary.txt").read_text()


class TestRunFastQC:
    def _mock_proc(self, returncode: int = 0, stderr: str = "") -> MagicMock:
        proc = MagicMock(spec=subprocess.CompletedProcess)
        proc.returncode = returncode
        proc.stdout = b""
        proc.stderr = stderr.encode()
        return proc

    @patch("src.tools.qc.fastqc.detect_version", return_value="FastQC v0.12.1")
    @patch("src.tools.qc.fastqc._read_zip_summary", return_value=parse_fastqc_summary(SUMMARY_TEXT))
    @patch("os.path.exists", return_value=True)
    @patch("os.makedirs")
    @patch("src.tools.base.subprocess.run")
    def test_success_returns_output(
        self,
        mock_run,
        mock_makedirs,
        mock_exists,
        mock_zip,
        mock_version,
    ) -> None:
        mock_run.return_value = self._mock_proc()
        inp = FastQCInput(fastq_paths=["/data/ctrl_1_R1.fastq.gz"], output_dir="/out")
        out = run_fastqc(inp)
        assert isinstance(out, FastQCOutput)
        assert out.tool_version == "FastQC v0.12.1"
        assert out.summary["Basic Statistics"] == "PASS"
        assert len(out.report_html_paths) == 1
        assert len(out.report_zip_paths) == 1

    @patch("src.tools.qc.fastqc.detect_version", return_value=None)
    @patch("os.makedirs")
    @patch("src.tools.base.subprocess.run")
    def test_nonzero_exit_raises_tool_execution_error(
        self, mock_run, mock_makedirs, mock_version
    ) -> None:
        mock_run.return_value = self._mock_proc(returncode=1, stderr="FastQC failed")
        inp = FastQCInput(fastq_paths=["/data/r1.fastq.gz"], output_dir="/out")
        with pytest.raises(ToolExecutionError) as exc_info:
            run_fastqc(inp)
        assert exc_info.value.exit_code == 1
        assert exc_info.value.tool_name == "fastqc"
        assert "FastQC failed" in exc_info.value.stderr

    @patch("src.tools.qc.fastqc.detect_version", return_value=None)
    @patch("os.makedirs")
    @patch("src.tools.base.subprocess.run")
    def test_timeout_raises_tool_timeout_error(self, mock_run, mock_makedirs, mock_version) -> None:
        mock_run.side_effect = subprocess.TimeoutExpired(cmd=["fastqc"], timeout=10)
        inp = FastQCInput(fastq_paths=["/data/r1.fastq.gz"], output_dir="/out")
        from src.tools.base import ToolTimeoutError

        with pytest.raises(ToolTimeoutError):
            run_fastqc(inp)

    @patch("src.tools.qc.fastqc.detect_version", return_value=None)
    @patch("src.tools.qc.fastqc._read_zip_summary", return_value={})
    @patch("os.path.exists", return_value=False)
    @patch("os.makedirs")
    @patch("src.tools.base.subprocess.run")
    def test_no_zip_returns_empty_summary(
        self, mock_run, mock_makedirs, mock_exists, mock_zip, mock_version
    ) -> None:
        mock_run.return_value = self._mock_proc()
        inp = FastQCInput(fastq_paths=["/data/r1.fastq.gz"], output_dir="/out")
        out = run_fastqc(inp)
        assert out.summary == {}

    def test_read_zip_summary_uses_fixture(self, tmp_path: Path) -> None:
        """_read_zip_summary reads summary.txt from a real ZIP."""
        zip_path = tmp_path / "ctrl_1_R1_fastqc.zip"
        zip_bytes = _make_fastqc_zip_bytes(SUMMARY_TEXT)
        zip_path.write_bytes(zip_bytes)
        result = _read_zip_summary(str(zip_path))
        assert result["Basic Statistics"] == "PASS"
        assert result["Per sequence GC content"] == "FAIL"


# ── @tool_call decorator ───────────────────────────────────────────────────────


class TestToolCallDecorator:
    def test_records_elapsed_time(self) -> None:
        import time

        from src.tools.base import tool_call

        @tool_call
        def slow_tool() -> str:
            time.sleep(0.01)
            return "done"

        result = slow_tool()
        assert result == "done"

    def test_propagates_tool_execution_error(self) -> None:
        from src.tools.base import tool_call

        @tool_call
        def bad_tool() -> None:
            raise ToolExecutionError(tool_name="test", exit_code=1, stderr="oops")

        with pytest.raises(ToolExecutionError):
            bad_tool()
