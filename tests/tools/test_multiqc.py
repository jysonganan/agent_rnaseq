"""Tests for run_multiqc and the MultiQC general-stats parser."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, mock_open, patch

import pytest
from pydantic import ValidationError

from src.tools.base import ToolExecutionError
from src.tools.qc.multiqc import MultiQCInput, MultiQCOutput, run_multiqc
from src.tools.qc.parsers import parse_multiqc_general_stats

FIXTURE_DIR = Path(__file__).parent / "fixtures"


# ── Parser tests ───────────────────────────────────────────────────────────────


class TestParseMultiQCGeneralStats:
    def _fixture_data(self) -> dict:  # type: ignore[type-arg]
        return json.loads((FIXTURE_DIR / "multiqc_data.json").read_text())

    def test_parses_all_samples(self) -> None:
        result = parse_multiqc_general_stats(self._fixture_data())
        assert "ctrl_1" in result
        assert "trt_1" in result

    def test_metric_values_match_fixture(self) -> None:
        result = parse_multiqc_general_stats(self._fixture_data())
        assert result["ctrl_1"]["pct_duplicates"] == pytest.approx(12.3)
        assert result["ctrl_1"]["total_sequences"] == 45_000_000

    def test_trt_sample_metrics(self) -> None:
        result = parse_multiqc_general_stats(self._fixture_data())
        assert result["trt_1"]["pct_gc"] == pytest.approx(49.8)

    def test_none_metrics_stripped(self) -> None:
        data = {"s1": {"metric_a": 1.0, "metric_b": None}}
        result = parse_multiqc_general_stats(data)
        assert "metric_b" not in result["s1"]
        assert result["s1"]["metric_a"] == 1.0

    def test_non_dict_sample_skipped(self) -> None:
        data = {"good": {"m": 1}, "bad": "not_a_dict"}
        result = parse_multiqc_general_stats(data)
        assert "good" in result
        assert "bad" not in result

    def test_empty_input(self) -> None:
        assert parse_multiqc_general_stats({}) == {}


# ── MultiQCInput validation ────────────────────────────────────────────────────


class TestMultiQCInput:
    def test_valid(self) -> None:
        inp = MultiQCInput(input_dirs=["/qc_out"], output_dir="/multiqc_out")
        assert inp.report_name == "multiqc_report"

    def test_empty_input_dirs_raises(self) -> None:
        with pytest.raises(ValidationError):
            MultiQCInput(input_dirs=[], output_dir="/out")

    def test_custom_report_name(self) -> None:
        inp = MultiQCInput(
            input_dirs=["/d1", "/d2"],
            output_dir="/out",
            report_name="my_report",
        )
        assert inp.report_name == "my_report"


# ── run_multiqc (subprocess mocked) ────────────────────────────────────────────


class TestRunMultiQC:
    def _mock_proc(self, returncode: int = 0) -> MagicMock:
        proc = MagicMock(spec=subprocess.CompletedProcess)
        proc.returncode = returncode
        proc.stdout = b""
        proc.stderr = b""
        return proc

    @patch("src.tools.qc.multiqc.detect_version", return_value="multiqc, version 1.21")
    @patch("os.path.exists", return_value=True)
    @patch("os.makedirs")
    @patch("src.tools.base.subprocess.run")
    def test_success_parses_general_stats(
        self, mock_run, mock_makedirs, mock_exists, mock_version
    ) -> None:
        mock_run.return_value = self._mock_proc()
        fixture_content = (FIXTURE_DIR / "multiqc_data.json").read_text()
        with (
            patch("builtins.open", mock_open(read_data=fixture_content)),
            patch("json.load", return_value=json.loads(fixture_content)),
        ):
            inp = MultiQCInput(input_dirs=["/qc_out"], output_dir="/multiqc_out")
            out = run_multiqc(inp)
        assert isinstance(out, MultiQCOutput)
        assert out.tool_version == "multiqc, version 1.21"
        assert "ctrl_1" in out.parsed_metrics

    @patch("src.tools.qc.multiqc.detect_version", return_value=None)
    @patch("os.makedirs")
    @patch("src.tools.base.subprocess.run")
    def test_nonzero_exit_raises(self, mock_run, mock_makedirs, mock_version) -> None:
        mock_run.return_value = self._mock_proc(returncode=1)
        inp = MultiQCInput(input_dirs=["/qc_out"], output_dir="/out")
        with pytest.raises(ToolExecutionError) as exc_info:
            run_multiqc(inp)
        assert exc_info.value.tool_name == "multiqc"

    @patch("src.tools.qc.multiqc.detect_version", return_value=None)
    @patch("os.path.exists", return_value=False)
    @patch("os.makedirs")
    @patch("src.tools.base.subprocess.run")
    def test_missing_stats_file_returns_empty_metrics(
        self, mock_run, mock_makedirs, mock_exists, mock_version
    ) -> None:
        mock_run.return_value = self._mock_proc()
        inp = MultiQCInput(input_dirs=["/qc_out"], output_dir="/out")
        out = run_multiqc(inp)
        assert out.parsed_metrics == {}

    @patch("src.tools.qc.multiqc.detect_version", return_value=None)
    @patch("os.makedirs")
    @patch("src.tools.base.subprocess.run")
    def test_command_built_correctly(self, mock_run, mock_makedirs, mock_version) -> None:
        mock_run.return_value = self._mock_proc()
        with patch("os.path.exists", return_value=False):
            inp = MultiQCInput(
                input_dirs=["/d1", "/d2"],
                output_dir="/out",
                report_name="my_report",
            )
            run_multiqc(inp)
        called_cmd = mock_run.call_args[0][0]
        assert "multiqc" in called_cmd
        assert "/d1" in called_cmd
        assert "/d2" in called_cmd
        assert "--filename" in called_cmd
        assert "my_report" in called_cmd
